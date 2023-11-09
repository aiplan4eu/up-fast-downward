from collections import defaultdict
from io import StringIO
from itertools import count
import os.path
import sys
import unified_planning as up
from functools import partial

from typing import Callable, Mapping, Optional, Union, Set, Tuple
from unified_planning.model import FNode, Problem, ProblemKind, MinimizeActionCosts
from unified_planning.model.walkers import Simplifier
from unified_planning.model.action import InstantaneousAction
from unified_planning.model.operators import OperatorKind
from unified_planning.engines.compilers.utils import lift_action_instance
from unified_planning.engines.compilers.grounder import (
    Grounder,
    ground_minimize_action_costs_metric,
)
from unified_planning.engines.engine import Engine
from unified_planning.engines import Credits
from unified_planning.engines.mixins.compiler import CompilationKind
from unified_planning.engines.mixins.compiler import CompilerMixin
from unified_planning.engines.results import CompilerResult
from unified_planning.exceptions import UPUnsupportedProblemTypeError
from up_fast_downward import utils


credits = Credits(
    "Fast Downward",
    "Uni Basel team and contributors "
    "(cf. https://github.com/aibasel/downward/blob/main/README.md)",
    "gabriele.roeger@unibas.ch (for UP integration)",
    "https://www.fast-downward.org",
    "GPLv3",
    "Fast Downward is a domain-independent classical planning system.",
    "Fast Downward is a domain-independent classical planning system.",
)

axioms_msg = """ Grounding this problem introduces axioms.

Does the problem use existantial quantification and negation that corresponds
to universal quantification (in negation normal form)?
"""


class FastDownwardReachabilityGrounder(Engine, CompilerMixin):
    def __init__(self):
        Engine.__init__(self)
        CompilerMixin.__init__(self, CompilationKind.GROUNDING)

    @property
    def name(self) -> str:
        return "Fast Downward Reachability Grounder"

    @staticmethod
    def get_credits(**kwargs) -> Optional["Credits"]:
        return credits

    @staticmethod
    def supported_kind() -> ProblemKind:
        supported_kind = ProblemKind(version=2)
        supported_kind.set_problem_class("ACTION_BASED")
        supported_kind.set_typing("FLAT_TYPING")
        supported_kind.set_typing("HIERARCHICAL_TYPING")
        supported_kind.set_conditions_kind("NEGATIVE_CONDITIONS")
        supported_kind.set_conditions_kind("DISJUNCTIVE_CONDITIONS")
        supported_kind.set_conditions_kind("EQUALITIES")
        supported_kind.set_effects_kind("CONDITIONAL_EFFECTS")
        supported_kind.set_effects_kind("FORALL_EFFECTS")
        supported_kind.set_effects_kind("STATIC_FLUENTS_IN_BOOLEAN_ASSIGNMENTS")
        supported_kind.set_effects_kind("FLUENTS_IN_BOOLEAN_ASSIGNMENTS")
        supported_kind.set_quality_metrics("ACTIONS_COST")
        supported_kind.set_actions_cost_kind("STATIC_FLUENTS_IN_ACTIONS_COST")
        supported_kind.set_actions_cost_kind("INT_NUMBERS_IN_ACTIONS_COST")
        supported_kind.set_quality_metrics("PLAN_LENGTH")
        supported_kind.set_conditions_kind("UNIVERSAL_CONDITIONS")
        supported_kind.set_conditions_kind("EXISTENTIAL_CONDITIONS")
        return supported_kind

    @staticmethod
    def supports(problem_kind: "up.model.ProblemKind") -> bool:
        return problem_kind <= FastDownwardReachabilityGrounder.supported_kind()

    @staticmethod
    def supports_compilation(compilation_kind: CompilationKind) -> bool:
        return compilation_kind == CompilationKind.GROUNDING

    @staticmethod
    def resulting_problem_kind(
        problem_kind: ProblemKind, compilation_kind: Optional[CompilationKind] = None
    ) -> ProblemKind:
        return problem_kind.clone()

    def _compile(
        self, problem: "up.model.AbstractProblem", compilation_kind: "CompilationKind"
    ) -> CompilerResult:
        """
        Takes an instance of a :class:`~up.model.Problem` and the `GROUNDING`
        :class:`~up.engines.CompilationKind` and returns a `CompilerResult`
        where the problem does not have actions with parameters; so every
        action is grounded.
        :param problem: The instance of the `Problem` that must be grounded.
        :param compilation_kind: The `CompilationKind` that must be applied on
            the given problem; only `GROUNDING` is supported by this compiler
        :return: The resulting `CompilerResult` data structure.
        """
        assert isinstance(problem, Problem)

        writer = up.io.PDDLWriter(problem)
        pddl_problem = writer.get_problem().split("\n")
        pddl_domain = writer.get_domain().split("\n")

        # perform Fast Downward translation until (and including)
        # the reachability analysis
        orig_path = list(sys.path)
        orig_stdout = sys.stdout
        sys.stdout = StringIO()
        path = os.path.join(
            os.path.dirname(__file__), "downward/builds/release/bin/translate"
        )
        sys.path.insert(1, path)
        import pddl_parser as fast_downward_pddl_parser
        import normalize as fast_downward_normalize
        from pddl_to_prolog import translate as prolog_program
        from build_model import compute_model
        import pddl

        lisp_parser = fast_downward_pddl_parser.lisp_parser
        fd_domain = lisp_parser.parse_nested_list(pddl_domain)
        fd_problem = lisp_parser.parse_nested_list(pddl_problem)
        parse = fast_downward_pddl_parser.parsing_functions.parse_task
        task = parse(fd_domain, fd_problem)
        fast_downward_normalize.normalize(task)
        prog = prolog_program(task)
        model = compute_model(prog)
        sys.stdout = orig_stdout
        sys.path = orig_path

        # The model contains an overapproximation of the reachable components
        # of the task, in particular also of the reachable ground actions.
        # We retreive the parameters from these actions and hand them over to
        # the Grounder from the UP, which performs the instantiation on the
        # side of the UP.
        grounding_action_map = defaultdict(list)
        exp_manager = problem.environment.expression_manager
        for atom in model:
            if isinstance(atom.predicate, pddl.Action):
                action = atom.predicate
                schematic_up_action = writer.get_item_named(action.name)
                params = (
                    writer.get_item_named(p)
                    for p in atom.args[: action.num_external_parameters]
                )
                up_params = tuple(exp_manager.ObjectExp(p) for p in params)
                grounding_action_map[schematic_up_action].append(up_params)

        up_grounder = Grounder(grounding_actions_map=grounding_action_map)
        up_res = up_grounder.compile(problem, compilation_kind)
        new_problem = up_res.problem
        new_problem.name = f"{self.name}_{problem.name}"

        return CompilerResult(new_problem, up_res.map_back_action_instance, self.name)


class FastDownwardGrounder(Engine, CompilerMixin):
    def __init__(self):
        Engine.__init__(self)
        CompilerMixin.__init__(self, CompilationKind.GROUNDING)

    @property
    def name(self) -> str:
        return "Fast Downward Grounder"

    @staticmethod
    def get_credits(**kwargs) -> Optional["Credits"]:
        return credits

    @staticmethod
    def supported_kind() -> ProblemKind:
        supported_kind = ProblemKind(version=2)
        supported_kind.set_problem_class("ACTION_BASED")
        supported_kind.set_typing("FLAT_TYPING")
        supported_kind.set_typing("HIERARCHICAL_TYPING")
        supported_kind.set_conditions_kind("NEGATIVE_CONDITIONS")
        supported_kind.set_conditions_kind("DISJUNCTIVE_CONDITIONS")
        supported_kind.set_conditions_kind("EQUALITIES")
        supported_kind.set_effects_kind("CONDITIONAL_EFFECTS")
        supported_kind.set_effects_kind("STATIC_FLUENTS_IN_BOOLEAN_ASSIGNMENTS")
        supported_kind.set_effects_kind("FLUENTS_IN_BOOLEAN_ASSIGNMENTS")
        supported_kind.set_quality_metrics("ACTIONS_COST")
        supported_kind.set_actions_cost_kind("STATIC_FLUENTS_IN_ACTIONS_COST")
        supported_kind.set_actions_cost_kind("INT_NUMBERS_IN_ACTIONS_COST")
        supported_kind.set_quality_metrics("PLAN_LENGTH")

        # We don't support allquantified conditions because they can lead
        # to the introduction of axioms during the Fast Downward
        # normalization process. In case axioms will be supported by
        # the unified planning framework, we can extend the grounder
        # accordingly.
        # supported_kind.set_conditions_kind("UNIVERSAL_CONDITIONS")

        # In principle, the same is true with existential conditions
        # if they get combined with negation. Since we only encounter
        # problems in this scenario, we still signal to support both
        # features and raise an Exception if it is not actually true
        # for the task at hand.
        supported_kind.set_conditions_kind("EXISTENTIAL_CONDITIONS")
        return supported_kind

    @staticmethod
    def supports(problem_kind: "up.model.ProblemKind") -> bool:
        return problem_kind <= FastDownwardGrounder.supported_kind()

    @staticmethod
    def supports_compilation(compilation_kind: CompilationKind) -> bool:
        return compilation_kind == CompilationKind.GROUNDING

    @staticmethod
    def resulting_problem_kind(
        problem_kind: ProblemKind, compilation_kind: Optional[CompilationKind] = None
    ) -> ProblemKind:
        resulting_problem_kind = problem_kind.clone()
        resulting_problem_kind.unset_conditions_kind("DISJUNCTIVE_CONDITIONS")
        resulting_problem_kind.unset_conditions_kind("EXISTENTIAL_CONDITIONS")
        return resulting_problem_kind

    def _get_fnode(
        self,
        fact,
        problem: "up.model.AbstractProblem",
        get_item_named: Callable[
            [str],
            Union[
                "up.model.Type",
                "up.model.Action",
                "up.model.Fluent",
                "up.model.Object",
                "up.model.Parameter",
                "up.model.Variable",
            ],
        ],
    ) -> FNode:
        """Translates a Fast Downward fact back into a FNode."""
        exp_manager = problem.environment.expression_manager
        fluent = get_item_named(fact.predicate)
        args = [problem.object(o) for o in fact.args]
        fnode = exp_manager.FluentExp(fluent, args)
        if fact.negated:
            return exp_manager.Not(fnode)
        else:
            return fnode

    def _transform_action(
        self,
        fd_action: "translate.pddl.Action",
        problem: "up.model.AbstractProblem",
        get_item_named: Callable[
            [str],
            Union[
                "up.model.Type",
                "up.model.Action",
                "up.model.Fluent",
                "up.model.Object",
                "up.model.Parameter",
                "up.model.Variable",
            ],
        ],
        used_action_names: Set[str],
    ) -> InstantaneousAction:
        """Takes a Fast Downward ground actions and builds it with the
        vobabulary of the UP."""

        def fnode(fact):
            return self._get_fnode(fact, problem, get_item_named)

        exp_manager = problem.environment.expression_manager

        name_and_args = fd_action.name[1:-1].split()
        name = get_item_named(name_and_args[0]).name
        name_and_args[0] = name
        full_name = "_".join(name_and_args)
        if full_name in used_action_names:
            for num in count():
                candidate = f"{full_name}_{num}"
                if candidate not in used_action_names:
                    full_name = candidate
                    break
        used_action_names.add(full_name)
        action = InstantaneousAction(full_name)
        for fact in fd_action.precondition:
            action.add_precondition(fnode(fact))
        for cond, fact in fd_action.add_effects:
            c = exp_manager.And(fnode(f) for f in cond)
            action.add_effect(fnode(fact), True, c)
        for cond, fact in fd_action.del_effects:
            c = exp_manager.And(fnode(f) for f in cond)
            action.add_effect(fnode(fact), False, c)
        return action

    def _add_goal_action_if_complicated_goal(
        self, problem: "up.model.AbstractProblem"
    ) -> Tuple[
        "up.model.AbstractProblem",
        Optional["up.model.InstantaneousAction"],
        Optional[
            Mapping["up.model.InstantaneousAction", "up.model.InstantaneousAction"]
        ],
    ]:
        """
        Tests whether the given problem has a complicated goal (not just
        a conjunction of positive and negative fluents). If yes, it returns
        a transformed problem with an artificial goal action and a single goal
        fluent, where the existing actions are modified to delete the goal fluent.
        The second return value is the new goal action. The third return value
        maps the actions of the modified problem to the actions of the original
        problem. If the goal was not complicated, it returns the original
        problem, None, and None.
        """
        COMPLICATED_KINDS = (
            OperatorKind.EXISTS,
            OperatorKind.FORALL,
            OperatorKind.IFF,
            OperatorKind.IMPLIES,
            OperatorKind.OR,
        )

        def is_complicated_goal(fnode):
            if fnode.node_type in COMPLICATED_KINDS or (
                fnode.node_type == OperatorKind.NOT
                and fnode.args[0].node_type != OperatorKind.FLUENT_EXP
            ):
                return True
            return any(is_complicated_goal(arg) for arg in fnode.args)

        if not any(is_complicated_goal(g) for g in problem.goals):
            # no complicated goal
            return problem, None, None
        else:
            # To avoid the introduction of axioms with complicated goals, we
            # introduce a separate goal action (later to be removed by
            # map_back)
            return utils.introduce_artificial_goal_action(problem, True)

    def _instantiate_with_fast_downward(self, pddl_problem, pddl_domain):
        orig_path = list(sys.path)
        orig_stdout = sys.stdout
        sys.stdout = StringIO()
        path = os.path.join(
            os.path.dirname(__file__), "downward/builds/release/bin/translate"
        )
        sys.path.insert(1, path)
        import pddl_parser as fast_downward_pddl_parser
        import instantiate as fd_instantiate
        import normalize as fast_downward_normalize

        lisp_parser = fast_downward_pddl_parser.lisp_parser
        fd_domain = lisp_parser.parse_nested_list(pddl_domain)
        fd_problem = lisp_parser.parse_nested_list(pddl_problem)
        parse = fast_downward_pddl_parser.parsing_functions.parse_task
        task = parse(fd_domain, fd_problem)
        fast_downward_normalize.normalize(task)

        _, _, actions, goals, axioms, _ = fd_instantiate.explore(task)
        sys.stdout = orig_stdout
        sys.path = orig_path
        return actions, goals, axioms

    def _compile(
        self, problem: "up.model.AbstractProblem", compilation_kind: "CompilationKind"
    ) -> CompilerResult:
        assert isinstance(problem, Problem)
        # If necessary, perform goal transformation to avoid the introduction
        # of axioms.
        (
            problem,
            artificial_goal_action,
            modified_to_orig_action,
        ) = self._add_goal_action_if_complicated_goal(problem)

        # Ground the problem with Fast Downward
        writer = up.io.PDDLWriter(problem)
        pddl_problem = writer.get_problem().split("\n")
        pddl_domain = writer.get_domain().split("\n")

        actions, goals, axioms = self._instantiate_with_fast_downward(
            pddl_problem, pddl_domain
        )

        if axioms:
            raise UPUnsupportedProblemTypeError(axioms_msg)

        # Rebuild the ground problem from Fast Downward in the UP
        new_problem = problem.clone()
        new_problem.name = f"{self.name}_{problem.name}"
        new_problem.clear_actions()
        new_problem.clear_goals()

        trace_back_map = dict()
        used_action_names = set()
        exp_manager = problem.environment.expression_manager

        # Construct Fast Downward ground actions in the UP and remember the
        # mapping from the ground actions to the original actions.
        for a in actions:
            inst_action = self._transform_action(
                a, new_problem, writer.get_item_named, used_action_names
            )
            name_and_args = a.name[1:-1].split()
            schematic_up_act = writer.get_item_named(name_and_args[0])
            if schematic_up_act == artificial_goal_action:
                trace_back_map[inst_action] = None
            else:
                if modified_to_orig_action is not None:
                    schematic_up_act = modified_to_orig_action[schematic_up_act]
                params = (writer.get_item_named(p) for p in name_and_args[1:])
                up_params = tuple(exp_manager.ObjectExp(p) for p in params)
                trace_back_map[inst_action] = (schematic_up_act, up_params)
            new_problem.add_action(inst_action)

        # Construct Fast Downward goals in the UP
        for g in goals:
            fnode = self._get_fnode(g, new_problem, writer.get_item_named)
            new_problem.add_goal(fnode)

        new_problem.clear_quality_metrics()
        for qm in problem.quality_metrics:
            if isinstance(qm, MinimizeActionCosts):
                simplifier = Simplifier(new_problem.environment, new_problem)
                ground_minimize_action_costs_metric(qm, trace_back_map, simplifier)
            else:
                new_problem.add_quality_metric(qm)

        # We need to use a more complicated function for mapping back the
        # actions because "partial(lift_action_instance, map=trace_back_map)"
        # cannot map an action to None (we need this for the artificial goal
        # action).
        mbai = lambda x: (
            None
            if trace_back_map[x.action] is None
            else partial(lift_action_instance, map=trace_back_map)(x)
        )

        return CompilerResult(
            new_problem,
            mbai,
            self.name,
        )
