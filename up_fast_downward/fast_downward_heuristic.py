import importlib.resources
import os
import subprocess
import sys
import tempfile
from collections import deque
from contextlib import redirect_stdout
from io import StringIO
from typing import List, Optional, Tuple

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

from up_fast_downward.fast_downward import FastDownwardPDDLPlanner, credits

ADM = HeuristicGuarantee.ADMISSIBLE
CONS = HeuristicGuarantee.CONSISTENT
GA = HeuristicGuarantee.GOAL_AWARE
SAFE = HeuristicGuarantee.SAFE
NONE = HeuristicGuarantee(0)

# What pddl_to_sas returns when it decides the task without building it.
TRIVIAL_TASK_VALUE_NAMES = [["Atom dummy(val1)", "Atom dummy(val2)"]]


def _downward_binary() -> str:
    exe = "downward.exe" if sys.platform == "win32" else "downward"
    return str(
        importlib.resources.files("up_fast_downward").joinpath(
            f"downward/builds/release/bin/{exe}"
        )
    )


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

    # Overridden by the named engines.
    _evaluator: Optional[str] = None
    _engine_name = "fast-downward-heuristic"
    _supports_axioms = True
    _supports_conditional_effects = True

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
        # Set when the translator decides the task, so no process is needed.
        self._trivial = False
        self._fixed_value: Optional[int] = None
        self._start(problem, self._evaluator or fast_downward_heuristic)

    @property
    def name(self) -> str:
        return self._engine_name

    @staticmethod
    def get_credits(**kwargs) -> Optional["Credits"]:
        return Credits(**credits)

    @classmethod
    def supported_kind(cls) -> "ProblemKind":
        supported_kind = FastDownwardPDDLPlanner.supported_kind()
        if not cls._supports_conditional_effects:
            supported_kind.unset_effects_kind("CONDITIONAL_EFFECTS")
        return supported_kind

    @classmethod
    def supports(cls, problem_kind: "ProblemKind") -> bool:
        return problem_kind <= cls.supported_kind()

    def _start(self, problem: "up.model.Problem", evaluator: str):
        writer = up.io.PDDLWriter(problem)
        with redirect_stdout(StringIO()):
            set_options(["domain.pddl", "problem.pddl"])
            task = parsing_functions.parse_task(
                lisp_parser.parse_nested_list(writer.get_domain().split("\n")),
                lisp_parser.parse_nested_list(writer.get_problem().split("\n")),
            )
            normalize(task)
            sas_task = pddl_to_sas(task)

        if sas_task.axioms and not self._supports_axioms:
            raise UPUnsupportedProblemTypeError(
                f"{self.name} does not support the axioms that Fast Downward "
                "introduces for this problem (e.g. for universal conditions or "
                "non-conjunctive goals)."
            )
        has_conditional_effects = any(
            cond for op in sas_task.operators for _, _, _, cond in op.pre_post
        )
        if has_conditional_effects and not self._supports_conditional_effects:
            raise UPUnsupportedProblemTypeError(
                f"{self.name} does not support conditional effects."
            )

        if (
            sas_task.variables.value_names == TRIVIAL_TASK_VALUE_NAMES
            and not sas_task.operators
        ):
            self._trivial = True
            self._fixed_value = 0 if sas_task.goal.pairs == [(0, 0)] else None
            return

        self._variables = self._map_variables(problem, writer, sas_task)

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
            self._read_reply()  # "ready", once the task file has been read
        finally:
            os.remove(task_file)

    def _map_variables(
        self, problem: "up.model.Problem", writer: "up.io.PDDLWriter", sas_task
    ) -> List[Tuple[int, List[Tuple[FNode, int]]]]:
        """
        For each SAS variable, returns the value to use when none of its atoms
        holds, and its atoms as UP fluent expressions with their values.
        """
        em = problem.environment.expression_manager
        variables = []
        for var, names in enumerate(sas_task.variables.value_names):
            # Derived variables are recomputed by Fast Downward.
            default = sas_task.init.values[var]
            atoms = []
            if sas_task.variables.axiom_layers[var] == -1:
                for value, name in enumerate(names):
                    if name.startswith("Atom "):
                        predicate, args = name[len("Atom ") : -1].split("(", 1)
                        objects = [writer.get_item_named(a) for a in args.split(", ") if a]
                        fluent = writer.get_item_named(predicate)
                        atoms.append((em.FluentExp(fluent, objects), value))
                    else:  # "NegatedAtom ..." or "<none of those>"
                        default = value
            variables.append((default, atoms))
        return variables

    def _read_reply(self) -> str:
        assert self._process is not None and self._process.stdout is not None
        for line in self._process.stdout:
            if line.startswith("@"):
                return line[1:].strip()
            self._log.append(line)
        exit_code = self._process.wait()
        self._process = None
        raise UPException(
            f"Fast Downward exited with code {exit_code}:\n" + "".join(self._log)
        )

    def _value(self, state: "up.model.State") -> Optional[float]:
        if self._trivial:
            return self._fixed_value
        if self._process is None:
            raise UPException(f"{self.name} has been destroyed.")
        # ponytail: one get_value per translated atom, O(#atoms) per call; read
        # UPState's values directly if this dominates a search.
        values = []
        for default, atoms in self._variables:
            value = default
            for fnode, atom_value in atoms:
                if state.get_value(fnode).bool_constant_value():
                    value = atom_value
                    break
            values.append(str(value))
        try:
            self._process.stdin.write(" ".join(values) + "\n")
            self._process.stdin.flush()
        except OSError:
            pass  # the process died; _read_reply reports why
        reply = self._read_reply()
        return None if reply == "inf" else int(reply)

    def destroy(self):
        if self._process is not None:
            self._process.stdin.close()
            try:
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            self._process.stdout.close()
            self._process = None


M_AND_S = (
    "merge_and_shrink(shrink_strategy=shrink_bisimulation(greedy=false),"
    "merge_strategy=merge_sccs(order_of_sccs=topological,"
    "merge_selector=score_based_filtering(scoring_functions=["
    "goal_relevance(),dfp(),total_order()])),"
    "label_reduction=exact(before_shrinking=true,before_merging=false),"
    "max_states=50k,threshold_before_merge=1)"
)

# Guarantees and language support as documented in Fast Downward 26.6, except
# GOAL_AWARE, which FD does not document: admissible values are >= 0, and the
# others return 0 on goal states by construction. hmax and hm are admissible
# only without axioms (hm also without conditional effects), so we reject them.
# operatorcounting and the potential heuristics need an LP solver, which the
# wheels do not include; they are only available through fast-downward-heuristic.
# (class name, engine name, evaluator, guarantees, axioms, conditional effects)
NAMED_HEURISTICS = [
    ("FastDownwardBlindHeuristic", "blind", "blind()", ADM | CONS | GA | SAFE, True, True),
    ("FastDownwardGoalCountHeuristic", "goalcount", "goalcount()", GA | SAFE, True, True),
    ("FastDownwardHMaxHeuristic", "hmax", "hmax()", ADM | CONS | GA | SAFE, False, True),
    ("FastDownwardAddHeuristic", "add", "add()", GA | SAFE, True, True),
    ("FastDownwardFFHeuristic", "ff", "ff()", GA | SAFE, True, True),
    ("FastDownwardCGHeuristic", "cg", "cg()", GA, True, True),
    ("FastDownwardCEAHeuristic", "cea", "cea()", GA, True, True),
    ("FastDownwardLMCutHeuristic", "lmcut", "lmcut()", ADM | GA | SAFE, False, False),
    ("FastDownwardHMHeuristic", "hm", "hm(m=2)", ADM | CONS | GA | SAFE, False, False),
    ("FastDownwardIPDBHeuristic", "ipdb", "ipdb()", ADM | CONS | GA | SAFE, False, False),
    ("FastDownwardCPDBsHeuristic", "cpdbs", "cpdbs()", ADM | CONS | GA | SAFE, False, False),
    ("FastDownwardZOPDBsHeuristic", "zopdbs", "zopdbs()", ADM | CONS | GA | SAFE, False, False),
    ("FastDownwardCEGARHeuristic", "cegar", "cegar()", ADM | CONS | GA | SAFE, False, False),
    ("FastDownwardMergeAndShrinkHeuristic", "merge_and_shrink", M_AND_S, ADM | CONS | GA | SAFE, False, True),
]


def _named_heuristic(engine, evaluator, guarantees, axioms, conditional_effects):
    def __init__(self, problem, error_on_failed_checks=True):
        FastDownwardHeuristic.__init__(self, problem, error_on_failed_checks)

    return {
        "__init__": __init__,
        "__doc__": f"Fast Downward's {evaluator} heuristic.",
        "_evaluator": evaluator,
        "_engine_name": f"fast-downward-{engine}",
        "_supports_axioms": axioms,
        "_supports_conditional_effects": conditional_effects,
        "guarantees": staticmethod(lambda g: g in guarantees),
    }


for _class_name, *_row in NAMED_HEURISTICS:
    globals()[_class_name] = type(
        _class_name, (FastDownwardHeuristic,), _named_heuristic(*_row)
    )
