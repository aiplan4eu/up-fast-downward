from collections import defaultdict
import os.path
import sys
import unified_planning as up
from functools import partial

from typing import Callable, Optional, Union
from unified_planning.model import FNode, Problem, ProblemKind, MinimizeActionCosts
from unified_planning.model.walkers import Simplifier
from unified_planning.model.action import InstantaneousAction
from unified_planning.engines.compilers.utils import lift_action_instance
from unified_planning.engines.compilers.grounder import Grounder, ground_minimize_action_costs_metric
from unified_planning.engines.engine import Engine
from unified_planning.engines import Credits
from unified_planning.engines.mixins.compiler import CompilationKind
from unified_planning.engines.mixins.compiler import CompilerMixin
from unified_planning.engines.results import CompilerResult
from unified_planning.exceptions import UPUnsupportedProblemTypeError


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
        supported_kind = ProblemKind()
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
        supported_kind.set_quality_metrics("PLAN_LENGTH")
        supported_kind.set_conditions_kind("UNIVERSAL_CONDITIONS")
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
        return ProblemKind(problem_kind.features)

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

        orig_path = list(sys.path)
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
        grounding_action_map = defaultdict(list)
        exp_manager = problem.environment.expression_manager
        for atom in model:
            if isinstance(atom.predicate, pddl.Action):
                action = atom.predicate
                schematic_up_action = writer.get_item_named(action.name)
                params = (
                    writer.get_item_named(p)
                    for p in atom.args[: len(action.parameters)]
                )
                up_params = tuple(exp_manager.ObjectExp(p) for p in params)
                grounding_action_map[schematic_up_action].append(up_params)
        sys.path = orig_path

        up_grounder = Grounder(grounding_actions_map=grounding_action_map)
        up_res = up_grounder.compile(problem, compilation_kind)
        new_problem = up_res.problem
        new_problem.name = f"{self.name}_{problem.name}"

        return CompilerResult(
            new_problem, up_res.map_back_action_instance, self.name
        )

    def destroy(self):
        pass


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
        supported_kind = ProblemKind()
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
        orig_features = problem_kind.features
        features = set.difference(orig_features, {"DISJUNCTIVE_CONDITIONS"})
        return ProblemKind(features)

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
    ) -> InstantaneousAction:
        def fnode(fact):
            return self._get_fnode(fact, problem, get_item_named)
        exp_manager = problem.environment.expression_manager

        name_and_args = fd_action.name[1:-1].split()
        name = get_item_named(name_and_args[0]).name
        name_and_args[0] = name
        action = InstantaneousAction("_".join(name_and_args))
        for fact in fd_action.precondition:
            action.add_precondition(fnode(fact))
        for cond, fact in fd_action.add_effects:
            c = exp_manager.And(fnode(f) for f in cond)
            action.add_effect(fnode(fact), True, c)
        for cond, fact in fd_action.del_effects:
            c = exp_manager.And(fnode(f) for f in cond)
            action.add_effect(fnode(fact), False, c)
        return action

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

        orig_path = list(sys.path)
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

        if axioms:
            raise UPUnsupportedProblemTypeError(axioms_msg)

        new_problem = problem.clone()
        new_problem.name = f"{self.name}_{problem.name}"
        new_problem.clear_actions()
        new_problem.clear_goals()

        trace_back_map = dict()

        exp_manager = problem.environment.expression_manager

        for a in actions:
            inst_action = self._transform_action(a, new_problem, writer.get_item_named)
            name_and_args = a.name[1:-1].split()
            schematic_up_action = writer.get_item_named(name_and_args[0])
            params = (writer.get_item_named(p) for p in name_and_args[1:])
            up_params = tuple(exp_manager.ObjectExp(p) for p in params)
            trace_back_map[inst_action] = (schematic_up_action, up_params)
            new_problem.add_action(inst_action)

        for g in goals:
            fnode = self._get_fnode(g, new_problem, writer.get_item_named)
            new_problem.add_goal(fnode)
        sys.path = orig_path

        new_problem.clear_quality_metrics()
        for qm in problem.quality_metrics:
            if isinstance(qm, MinimizeActionCosts):
                simplifier = Simplifier(new_problem)
                ground_minimize_action_costs_metric(qm, trace_back_map, simplifier)
            else:
                new_problem.add_quality_metric(qm)

        return CompilerResult(
            new_problem,
            partial(lift_action_instance, map=trace_back_map),
            self.name,
        )

    def destroy(self):
        pass
