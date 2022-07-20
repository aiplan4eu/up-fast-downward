import pkg_resources
import sys
import unified_planning as up

from typing import List, Optional, Union
from unified_planning.model import ProblemKind
from unified_planning.engines import OptimalityGuarantee, PlanGenerationResultStatus
from unified_planning.engines import PDDLPlanner, Credits


credits = Credits('Fast Downward',
                  'Uni Basel team and contributors (cf. https://github.com/aibasel/downward/blob/main/README.md)',
                  'gabriele.roeger@unibas.ch',
                  'https://www.fast-downward.org',
                  'GPLv3',
                  'Fast Downward is a domain-independent classical planning system.',
                  'Fast Downward is a domain-independent classical planning system.')


class FastDownwardPDDLPlanner(PDDLPlanner):

    def __init__(self):
        super().__init__()

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
        cmd = [sys.executable, downward, '--plan-file', plan_filename, '--alias', 'lama-first',
               domain_filename, problem_filename]
        return cmd

    def _result_status(
        self,
        problem: "up.model.Problem",
        plan: Optional["up.plans.Plan"],
        retval: int = None, # Default value for legacy support
        #log_messages: Optional[List[LogMessage]] = None,
        log_messages = None,
        ) -> "up.engines.results.PlanGenerationResultStatus":

        # https://www.fast-downward.org/ExitCodes
        if retval is None: # legacy support
            if plan is None:
                return PlanGenerationResultStatus.UNSOLVABLE_INCOMPLETELY
            else:
                return PlanGenerationResultStatus.SOLVED_SATISFICING
        if retval in (0, 1, 2, 3):
            if plan is None:
                # Should not be possible after portfolios have been fixed
                return PlanGenerationResultStatus.UNSOLVABLE_INCOMPLETELY
            else:
                return PlanGenerationResultStatus.SOLVED_SATISFICING
        if retval in (10, 11):
            return PlanGenerationResultStatus.UNSOLVABLE_PROVEN
        if retval == 12:
            return PlanGenerationResultStatus.UNSOLVABLE_INCOMPLETELY
        else:
            return up.engines.results.PlanGenerationResultStatus.INTERNAL_ERROR

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
        supported_kind.set_quality_metrics("ACTIONS_COST")
        supported_kind.set_quality_metrics("PLAN_LENGTH")
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
        cmd = [sys.executable, downward, '--plan-file', plan_filename, domain_filename, problem_filename, '--search',
                'astar(lmcut())']
        return cmd

    def _result_status(
        self,
        problem: "up.model.Problem",
        plan: Optional["up.plans.Plan"],
        retval: int = None, # Default value for legacy support
        #log_messages: Optional[List[LogMessage]] = None,
        log_messages = None,
        ) -> "up.engines.results.PlanGenerationResultStatus":
        # https://www.fast-downward.org/ExitCodes
        if retval is None: # legacy support
            if plan is None:
                return PlanGenerationResultStatus.UNSOLVABLE_PROVEN
            else:
                return PlanGenerationResultStatus.SOLVED_OPTIMALLY
        if retval in (0, 1, 2, 3):
            return PlanGenerationResultStatus.SOLVED_OPTIMALLY
        if retval in (10, 11):
            return PlanGenerationResultStatus.UNSOLVABLE_PROVEN
        if retval == 12:
            return PlanGenerationResultStatus.UNSOLVABLE_INCOMPLETELY
        else:
            return PlanGenerationResultStatus.INTERNAL_ERROR

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
        supported_kind.set_quality_metrics("ACTIONS_COST")
        supported_kind.set_quality_metrics("PLAN_LENGTH")
        return supported_kind

    @staticmethod
    def supports(problem_kind: 'ProblemKind') -> bool:
        return problem_kind <= FastDownwardOptimalPDDLPlanner.supported_kind()

    @staticmethod
    def satisfies(optimality_guarantee: OptimalityGuarantee) -> bool:
        return True
