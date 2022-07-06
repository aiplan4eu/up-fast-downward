import pkg_resources
import sys
from typing import List, Optional

import unified_planning as up
from unified_planning.model import ProblemKind
from unified_planning.engines import OptimalityGuarantee
from unified_planning.engines import PlanGenerationResultStatus
from unified_planning.engines import PDDLPlanner, Credits
from unified_planning.exceptions import UPUsageError


credits = Credits(
        'Fast Downward',
        ('Uni Basel team and contributors (cf. '
         'https://github.com/aibasel/downward/blob/main/README.md)'),
        'gabriele.roeger@unibas.ch',
        'https://www.fast-downward.org',
        'GPLv3',
        'Fast Downward is a domain-independent classical planning system.',
        'Fast Downward is a domain-independent classical planning system.')


class FastDownwardPDDLPlanner(PDDLPlanner):

    def __init__(self, alias=None, search=None, evaluators=[]):
        super().__init__()
        self._alias = alias
        self._search = search
        self._evaluators = evaluators
        if self._search and self._alias:
            raise UPUsageError("If you specify an alias, you cannot"
                               "also specify the search in Fast Downward.")
        if self._search is None and self._alias is None:
            self._alias = "lama-first"

    @property
    def name(self) -> str:
        return 'Fast Downward'

    @staticmethod
    def get_credits(**kwargs) -> Optional['Credits']:
        return credits

    def _get_cmd(self, domain_filename: str,
                 problem_filename: str, plan_filename: str) -> List[str]:
        downward = pkg_resources.resource_filename(__name__,
                                                   'downward/fast-downward.py')
        assert sys.executable, "Path to interpreter could not be found"
        if self._alias:
            cmd = [sys.executable, downward, '--plan-file', plan_filename,
                   '--alias', self._alias, domain_filename, problem_filename]
        else:
            assert self._search is not None
            evaluators = []
            for evaluator in self._evaluators:
                evaluators.append("--evaluator")
                evaluators.append(evaluator)
            cmd = [sys.executable, downward, '--plan-file', plan_filename,
                   domain_filename, problem_filename]
            cmd += evaluators
            cmd += ['--search', self._search]
        return cmd

    def _result_status(self, problem: 'up.model.Problem',
                       plan: Optional['up.plan.Plan']) -> int:
        if plan is None:
            return PlanGenerationResultStatus.UNSOLVABLE_INCOMPLETELY
        else:
            return PlanGenerationResultStatus.SOLVED_SATISFICING

    @staticmethod
    def satisfies(optimality_guarantee: 'OptimalityGuarantee') -> bool:
        if optimality_guarantee == OptimalityGuarantee.SATISFICING:
            return True
        return False

    @staticmethod
    def supported_kind() -> 'ProblemKind':
        supported_kind = ProblemKind()
        supported_kind.set_problem_class('ACTION_BASED')
        supported_kind.set_typing('FLAT_TYPING')
        supported_kind.set_conditions_kind('NEGATIVE_CONDITIONS')
        supported_kind.set_conditions_kind('DISJUNCTIVE_CONDITIONS')
        supported_kind.set_conditions_kind('EXISTENTIAL_CONDITIONS')
        supported_kind.set_conditions_kind('UNIVERSAL_CONDITIONS')
        supported_kind.set_conditions_kind('EQUALITY')
        supported_kind.set_effects_kind('CONDITIONAL_EFFECTS')
        return supported_kind

    @staticmethod
    def supports(problem_kind: 'ProblemKind') -> bool:
        return problem_kind <= FastDownwardPDDLPlanner.supported_kind()


class FastDownwardOptimalPDDLPlanner(PDDLPlanner):

    def __init__(self):
        super().__init__()

    @property
    def name(self) -> str:
        return 'Fast Downward (with optimality guarantee)'

    @staticmethod
    def get_credits(**kwargs) -> Optional['Credits']:
        return credits

    def _get_cmd(self, domain_filename: str,
                 problem_filename: str, plan_filename: str) -> List[str]:
        downward = pkg_resources.resource_filename(__name__,
                                                   'downward/fast-downward.py')
        assert sys.executable, "Path to interpreter could not be found"
        cmd = [sys.executable, downward, '--plan-file', plan_filename,
               domain_filename, problem_filename, '--search',
               'astar(lmcut())']
        return cmd

    def _result_status(self, problem: 'up.model.Problem',
                       plan: Optional['up.plan.Plan']) -> int:
        if plan is None:
            return PlanGenerationResultStatus.UNSOLVABLE_PROVEN
        else:
            return PlanGenerationResultStatus.SOLVED_OPTIMALLY

    @staticmethod
    def supported_kind() -> 'ProblemKind':
        # TODO this actually depends on the parameters, which we don't know in
        # a static method.
        # TODO metrics MinimizeActionCosts and MinimizeSequentialPlanLength
        supported_kind = ProblemKind()
        supported_kind.set_problem_class('ACTION_BASED')
        supported_kind.set_typing('FLAT_TYPING')
        supported_kind.set_conditions_kind('NEGATIVE_CONDITIONS')
        supported_kind.set_conditions_kind('DISJUNCTIVE_CONDITIONS')
        supported_kind.set_conditions_kind('EXISTENTIAL_CONDITIONS')
        supported_kind.set_conditions_kind('UNIVERSAL_CONDITIONS')
        supported_kind.set_conditions_kind('EQUALITY')
        supported_kind.set_effects_kind('CONDITIONAL_EFFECTS')
        return supported_kind

    @staticmethod
    def supports(problem_kind: 'ProblemKind') -> bool:
        return problem_kind <= FastDownwardOptimalPDDLPlanner.supported_kind()

    @staticmethod
    def satisfies(optimality_guarantee: OptimalityGuarantee) -> bool:
        return True
