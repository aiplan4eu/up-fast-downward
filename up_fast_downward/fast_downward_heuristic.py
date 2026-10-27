"""
Fast Downward heuristics as engines of the unified_planning Heuristic
operation mode. See doc/heuristics.md for the design.

Each engine translates the problem once with the Fast Downward translator and
starts a Fast Downward process running the eval_server search plugin
(up_fast_downward/eval_server/eval_server.cc). For every call to ``value``, the
UP state is mapped to the values of the translated (SAS) variables and sent to
that process, which replies with the heuristic value.
"""

import importlib.resources
import os
import subprocess
import sys
import tempfile
from collections import deque
from contextlib import redirect_stdout, suppress
from io import StringIO
from typing import List, NamedTuple, Optional, Tuple

import unified_planning as up
from unified_planning.engines import Credits
from unified_planning.engines.engine import Engine
from unified_planning.engines.mixins.heuristic import (
    HeuristicGuarantee,
    HeuristicMixin,
)
from unified_planning.exceptions import UPException, UPUnsupportedProblemTypeError
from unified_planning.model import FNode, ProblemKind

from fast_downward.translate.main import pddl_to_sas
from fast_downward.translate.normalize import normalize
from fast_downward.translate.options import set_options
from fast_downward.translate.pddl_parser import lisp_parser, parsing_functions
from fast_downward.translate.sas_tasks import SASTask

from up_fast_downward.fast_downward import FastDownwardPDDLPlanner, credits

ADMISSIBLE = HeuristicGuarantee.ADMISSIBLE
CONSISTENT = HeuristicGuarantee.CONSISTENT
GOAL_AWARE = HeuristicGuarantee.GOAL_AWARE
SAFE = HeuristicGuarantee.SAFE
ALL_GUARANTEES = ADMISSIBLE | CONSISTENT | GOAL_AWARE | SAFE

# pddl_to_sas returns this single dummy variable when it solves the task itself.
TRIVIAL_TASK_VALUE_NAMES = [["Atom dummy(val1)", "Atom dummy(val2)"]]

# Lines from eval_server that start with this prefix are replies; all other
# lines are Fast Downward's log, kept for error messages.
REPLY_PREFIX = "@"
READY_REPLY = "ready"
DEAD_END_REPLY = "inf"


class SASVariable(NamedTuple):
    """How the value of one translated variable is read from a UP state."""

    # The value when none of the atoms holds: the "NegatedAtom" or
    # "<none of those>" value. Derived variables always use this value, since
    # Fast Downward recomputes them from the axioms.
    default_value: int
    # The fluent expression of each "Atom" value, with that value.
    atoms: List[Tuple[FNode, int]]


def _downward_binary() -> str:
    exe = "downward.exe" if sys.platform == "win32" else "downward"
    path = f"downward/builds/release/bin/{exe}"
    return str(importlib.resources.files("up_fast_downward").joinpath(path))


class FastDownwardHeuristic(Engine, HeuristicMixin):
    """
    Evaluates states with any Fast Downward evaluator, given as a Fast Downward
    option string such as ``"ff()"`` or ``"max([hmax(), lmcut()])"``.

    The evaluator runs in a Fast Downward process that lives as long as this
    engine; use it in a ``with`` block or call ``destroy``. Values are
    computed on the task produced by the Fast Downward translator, so they are
    only meaningful for states reachable from the initial state of the problem.
    Path-dependent evaluators (the landmark heuristics) are rejected.

    No guarantees are claimed, since they depend on the evaluator; options such
    as ``cost_type=one`` also change the unit of the values. An instance is not
    thread-safe.
    """

    def __init__(
        self,
        problem: "up.model.AbstractProblem",
        error_on_failed_checks: bool = True,
        fast_downward_heuristic: str = "ff()",
    ):
        Engine.__init__(self)
        HeuristicMixin.__init__(self, problem, error_on_failed_checks)
        assert isinstance(problem, up.model.Problem)
        self._process: Optional[subprocess.Popen] = None
        self._log: deque = deque(maxlen=20)
        # Why the process was stopped, raised again by later calls to value.
        self._error: Optional[str] = None
        self._variables: List[SASVariable] = []
        # Set when the translator decides the task, so no process is needed.
        self._trivial = False
        self._trivial_value: Optional[int] = None

        writer = up.io.PDDLWriter(problem, rewrite_bool_assignments=True)
        sas_task = self._translate(writer)
        self._check_supported(sas_task)
        if self._is_trivial(sas_task):
            self._trivial = True
            self._trivial_value = 0 if sas_task.goal.pairs == [(0, 0)] else None
            return
        self._variables = self._map_variables(problem, writer, sas_task)
        self._start_process(sas_task, fast_downward_heuristic)

    @property
    def name(self) -> str:
        return "fast-downward-heuristic"

    @staticmethod
    def get_credits(**kwargs) -> Optional["Credits"]:
        return Credits(**credits)

    # Class attributes rather than parameters, since guarantees() and
    # supported_kind() are static.
    supports_axioms = True
    supports_conditional_effects = True

    @classmethod
    def supported_kind(cls) -> "ProblemKind":
        supported_kind = FastDownwardPDDLPlanner.supported_kind()
        if not cls.supports_conditional_effects:
            # As for fast-downward-opt, since the other kinds can be written as conditional effects.
            for kind in (
                "CONDITIONAL_EFFECTS",
                "FORALL_EFFECTS",
                "FLUENTS_IN_BOOLEAN_ASSIGNMENTS",
                "STATIC_FLUENTS_IN_BOOLEAN_ASSIGNMENTS",
            ):
                supported_kind.unset_effects_kind(kind)
        return supported_kind

    @classmethod
    def supports(cls, problem_kind: "ProblemKind") -> bool:
        return problem_kind <= cls.supported_kind()

    def _translate(self, writer: "up.io.PDDLWriter") -> SASTask:
        # The translator prints its progress, so silence it.
        with redirect_stdout(StringIO()):
            set_options(["domain.pddl", "problem.pddl"])
            task = parsing_functions.parse_task(
                lisp_parser.parse_nested_list(writer.get_domain().split("\n")),
                lisp_parser.parse_nested_list(writer.get_problem().split("\n")),
            )
            normalize(task)
            return pddl_to_sas(task)

    def _check_supported(self, sas_task: SASTask):
        """
        Raises if the translated task has axioms or conditional effects that
        this heuristic does not support. The problem kind cannot tell, since
        e.g. a disjunctive goal only sometimes yields axioms.
        """
        if sas_task.axioms and not self.supports_axioms:
            raise UPUnsupportedProblemTypeError(
                f"{self.name} does not support the axioms that Fast Downward "
                "introduces for this problem (e.g. for universal conditions or "
                "non-conjunctive goals)."
            )
        has_conditional_effects = any(
            effect_condition
            for op in sas_task.operators
            for _, _, _, effect_condition in op.pre_post
        )
        if has_conditional_effects and not self.supports_conditional_effects:
            raise UPUnsupportedProblemTypeError(
                f"{self.name} does not support conditional effects."
            )

    @staticmethod
    def _is_trivial(sas_task: SASTask) -> bool:
        return (
            sas_task.variables.value_names == TRIVIAL_TASK_VALUE_NAMES
            and not sas_task.operators
        )

    @staticmethod
    def _map_variables(
        problem: "up.model.Problem", writer: "up.io.PDDLWriter", sas_task: SASTask
    ) -> List[SASVariable]:
        """
        Reads the meaning of each translated variable from its value names,
        e.g. "Atom at(truck1, depot2)", "NegatedAtom at(truck1, depot2)" or
        "<none of those>", and maps the PDDL names back to the UP fluents and
        objects. Facts that the translator dropped have no variable.
        """
        em = problem.environment.expression_manager
        variables = []
        for var, value_names in enumerate(sas_task.variables.value_names):
            default_value = sas_task.init.values[var]
            atoms = []
            is_derived = sas_task.variables.axiom_layers[var] != -1
            if not is_derived:
                for value, value_name in enumerate(value_names):
                    if value_name.startswith("Atom "):
                        predicate, args = value_name[len("Atom ") : -1].split("(", 1)
                        fluent = writer.get_item_named(predicate)
                        objects = [writer.get_item_named(a) for a in args.split(", ") if a]
                        atoms.append((em.FluentExp(fluent, objects), value))
                    else:
                        default_value = value
            variables.append(SASVariable(default_value, atoms))
        return variables

    def _start_process(self, sas_task: SASTask, evaluator: str):
        """Starts eval_server and waits until it has built the evaluator."""
        # The task goes through a file because stdin carries the states.
        fd, task_file = tempfile.mkstemp(suffix=".sas")
        try:
            with os.fdopen(fd, "w") as f:
                sas_task.output(f)
            cmd = [
                _downward_binary(),
                "--task-file",
                task_file,
                "--search",
                f"eval_server(eval={evaluator})",
            ]
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                reply = self._read_reply()
                if reply != READY_REPLY:
                    raise UPException(f"Unexpected reply from eval_server: {reply}")
            except BaseException:
                self._stop()
                raise
        finally:
            # eval_server has read the task once it is ready, or it has exited.
            os.remove(task_file)

    def _read_reply(self) -> str:
        """Returns the next reply, or raises with the log if the process exited."""
        assert self._process is not None and self._process.stdout is not None
        for line in self._process.stdout:
            if line.startswith(REPLY_PREFIX):
                return line[len(REPLY_PREFIX) :].strip()
            self._log.append(line)
        exit_code = self._process.wait()
        self._error = f"Fast Downward exited with code {exit_code}:\n" + "".join(
            self._log
        )
        raise UPException(self._error)

    def _stop(self):
        """Kills the process if it still runs and closes its pipes."""
        if self._process is None:
            return
        self._process.kill()
        self._process.wait()
        # Closing stdin flushes it, which fails if the process is gone.
        with suppress(OSError):
            self._process.stdin.close()
        self._process.stdout.close()
        self._process = None

    def _sas_values(self, state: "up.model.State") -> List[int]:
        # ponytail: one get_value per translated atom, O(#atoms) per call; read
        # UPState's values directly if this dominates a search.
        values = []
        for variable in self._variables:
            value = variable.default_value
            for fnode, atom_value in variable.atoms:
                if state.get_value(fnode).bool_constant_value():
                    value = atom_value
                    break
            values.append(value)
        return values

    def _value(self, state: "up.model.State") -> Optional[float]:
        if self._trivial:
            return self._trivial_value
        if self._process is None:
            raise UPException(self._error or f"{self.name} has been destroyed.")
        request = " ".join(map(str, self._sas_values(state)))
        try:
            try:
                self._process.stdin.write(request + "\n")
                self._process.stdin.flush()
            except OSError:
                pass  # the process has exited; _read_reply raises with its log
            reply = self._read_reply()
        except BaseException as e:
            # An unread reply would be returned for the next state, so stop for good.
            self._stop()
            self._error = self._error or f"{self.name} was interrupted: {e!r}"
            raise
        return None if reply == DEAD_END_REPLY else int(reply)

    def destroy(self):
        if self._process is None:
            return
        # eval_server exits when its stdin closes.
        with suppress(OSError):
            self._process.stdin.close()
        with suppress(subprocess.TimeoutExpired):
            self._process.wait(timeout=1)
        self._stop()


class _NamedHeuristic(FastDownwardHeuristic):
    """
    Base class of the engines that fix the evaluator, so that they can state
    its guarantees. The guarantees and the language support are those
    documented by Fast Downward 26.6, see doc/heuristics.md.
    """

    evaluator: str
    engine_name: str
    heuristic_guarantees = HeuristicGuarantee(0)

    def __init__(
        self, problem: "up.model.AbstractProblem", error_on_failed_checks: bool = True
    ):
        super().__init__(problem, error_on_failed_checks, self.evaluator)

    @property
    def name(self) -> str:
        return self.engine_name

    @classmethod
    def guarantees(cls, heuristic_guarantee: HeuristicGuarantee) -> bool:
        return heuristic_guarantee in cls.heuristic_guarantees


# GOAL_AWARE is not documented by Fast Downward. Admissible heuristics are
# goal-aware because Fast Downward heuristic values are never negative; the
# inadmissible ones below return 0 on goal states by construction.


class FastDownwardBlindHeuristic(_NamedHeuristic):
    """0 on goal states, the cheapest action cost elsewhere."""

    evaluator = "blind()"
    engine_name = "fast-downward-blind"
    heuristic_guarantees = ALL_GUARANTEES


class FastDownwardGoalCountHeuristic(_NamedHeuristic):
    """The number of unsatisfied goal facts."""

    evaluator = "goalcount()"
    engine_name = "fast-downward-goalcount"
    heuristic_guarantees = GOAL_AWARE | SAFE


class FastDownwardHMaxHeuristic(_NamedHeuristic):
    """The max heuristic (Bonet and Geffner 2001)."""

    evaluator = "hmax()"
    engine_name = "fast-downward-hmax"
    heuristic_guarantees = ALL_GUARANTEES
    # Fast Downward accepts axioms, but hmax is then not admissible.
    supports_axioms = False


class FastDownwardAddHeuristic(_NamedHeuristic):
    """The additive heuristic (Bonet and Geffner 2001)."""

    evaluator = "add()"
    engine_name = "fast-downward-add"
    heuristic_guarantees = GOAL_AWARE | SAFE


class FastDownwardFFHeuristic(_NamedHeuristic):
    """The FF heuristic (Hoffmann and Nebel 2001)."""

    evaluator = "ff()"
    engine_name = "fast-downward-ff"
    heuristic_guarantees = GOAL_AWARE | SAFE


class FastDownwardCGHeuristic(_NamedHeuristic):
    """The causal graph heuristic (Helmert 2004)."""

    evaluator = "cg()"
    engine_name = "fast-downward-cg"
    heuristic_guarantees = GOAL_AWARE


class FastDownwardCEAHeuristic(_NamedHeuristic):
    """The context-enhanced additive heuristic (Helmert and Geffner 2008)."""

    evaluator = "cea()"
    engine_name = "fast-downward-cea"
    heuristic_guarantees = GOAL_AWARE


class FastDownwardLMCutHeuristic(_NamedHeuristic):
    """The landmark-cut heuristic (Helmert and Domshlak 2009)."""

    evaluator = "lmcut()"
    engine_name = "fast-downward-lmcut"
    heuristic_guarantees = ADMISSIBLE | GOAL_AWARE | SAFE
    supports_axioms = False
    supports_conditional_effects = False


class FastDownwardHMHeuristic(_NamedHeuristic):
    """The h^m heuristic with m=2 (Haslum and Geffner 2000)."""

    evaluator = "hm(m=2)"
    engine_name = "fast-downward-hm"
    heuristic_guarantees = ALL_GUARANTEES
    # Fast Downward silently ignores both, which breaks the guarantees.
    supports_axioms = False
    supports_conditional_effects = False


class FastDownwardIPDBHeuristic(_NamedHeuristic):
    """Pattern databases selected by hill climbing (Haslum et al. 2007)."""

    evaluator = "ipdb()"
    engine_name = "fast-downward-ipdb"
    heuristic_guarantees = ALL_GUARANTEES
    supports_axioms = False
    supports_conditional_effects = False


class FastDownwardCPDBsHeuristic(_NamedHeuristic):
    """The canonical heuristic over systematic pattern databases."""

    evaluator = "cpdbs()"
    engine_name = "fast-downward-cpdbs"
    heuristic_guarantees = ALL_GUARANTEES
    supports_axioms = False
    supports_conditional_effects = False


class FastDownwardZOPDBsHeuristic(_NamedHeuristic):
    """Pattern databases with zero-one cost partitioning."""

    evaluator = "zopdbs()"
    engine_name = "fast-downward-zopdbs"
    heuristic_guarantees = ALL_GUARANTEES
    supports_axioms = False
    supports_conditional_effects = False


class FastDownwardCEGARHeuristic(_NamedHeuristic):
    """Additive Cartesian abstractions found by CEGAR (Seipp and Helmert 2018)."""

    evaluator = "cegar()"
    engine_name = "fast-downward-cegar"
    heuristic_guarantees = ALL_GUARANTEES
    supports_axioms = False
    supports_conditional_effects = False


class FastDownwardMergeAndShrinkHeuristic(_NamedHeuristic):
    """
    Merge-and-shrink (Helmert et al. 2014) in the configuration that Fast
    Downward recommends: bisimulation shrinking, SCC-DFP merging and at most
    50k abstract states.
    """

    evaluator = (
        "merge_and_shrink("
        "shrink_strategy=shrink_bisimulation(greedy=false),"
        "merge_strategy=merge_sccs(order_of_sccs=topological,"
        "merge_selector=score_based_filtering(scoring_functions=["
        "goal_relevance(),dfp(),total_order()])),"
        "label_reduction=exact(before_shrinking=true,before_merging=false),"
        "max_states=50k,threshold_before_merge=1)"
    )
    engine_name = "fast-downward-merge_and_shrink"
    heuristic_guarantees = ALL_GUARANTEES
    supports_axioms = False


# The LP-based heuristics (operatorcounting, potentials) have no named engine:
# the released wheels are built without an LP solver.
NAMED_HEURISTICS = [
    FastDownwardBlindHeuristic,
    FastDownwardGoalCountHeuristic,
    FastDownwardHMaxHeuristic,
    FastDownwardAddHeuristic,
    FastDownwardFFHeuristic,
    FastDownwardCGHeuristic,
    FastDownwardCEAHeuristic,
    FastDownwardLMCutHeuristic,
    FastDownwardHMHeuristic,
    FastDownwardIPDBHeuristic,
    FastDownwardCPDBsHeuristic,
    FastDownwardZOPDBsHeuristic,
    FastDownwardCEGARHeuristic,
    FastDownwardMergeAndShrinkHeuristic,
]
