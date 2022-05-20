import pkg_resources
import sys
import unified_planning as up

from typing import List, Optional, Union
from unified_planning.model import ProblemKind
from unified_planning.solvers import OptimalityGuarantee, PlanGenerationResultStatus
from unified_planning.solvers import PDDLSolver


class FastDownwardPDDLSolver(PDDLSolver):

    def __init__(self):
        super().__init__()

    def destroy(self):
        pass

    @property
    def name(self) -> str:
        return 'Fast Downward'

    def _get_cmd(self, domain_filename: str,
                 problem_filename: str, plan_filename: str) -> List[str]:
        downward = pkg_resources.resource_filename(__name__,
                                                   'downward/fast-downward.py')
        assert sys.executable, "Path to interpreter could not be found"
        cmd = [sys.executable, downward, '--plan-file', plan_filename, '--alias', 'lama-first',
               domain_filename, problem_filename]
        return cmd

    def _result_status(self, problem: 'up.model.Problem', plan: Optional['up.plan.Plan']) -> int:
        if plan is None:
            return PlanGenerationResultStatus.UNSOLVABLE_INCOMPLETELY
        else:
            return PlanGenerationResultStatus.SOLVED_SATISFICING

    @staticmethod
    def satisfies(optimality_guarantee: Union[int, str]) -> bool:
        if optimality_guarantee == OptimalityGuarantee.SATISFICING:
            return True
        return False

    @staticmethod
    def supports(problem_kind: 'ProblemKind') -> bool:
        supported_kind = ProblemKind()
        supported_kind.set_typing('FLAT_TYPING')
        supported_kind.set_conditions_kind('NEGATIVE_CONDITIONS')
        supported_kind.set_conditions_kind('DISJUNCTIVE_CONDITIONS')
        supported_kind.set_conditions_kind('EXISTENTIAL_CONDITIONS')
        supported_kind.set_conditions_kind('UNIVERSAL_CONDITIONS')
        supported_kind.set_conditions_kind('EQUALITY')
        supported_kind.set_effects_kind('CONDITIONAL_EFFECTS')
        return problem_kind <= supported_kind



class FastDownwardOptimalPDDLSolver(PDDLSolver):

    def __init__(self):
        super().__init__()

    def destroy(self):
        pass

    @property
    def name(self) -> str:
        return 'Fast Downward (with optimality guarantee)'

    def _get_cmd(self, domain_filename: str,
                 problem_filename: str, plan_filename: str) -> List[str]:
        downward = pkg_resources.resource_filename(__name__,
                                                   'downward/fast-downward.py')
        assert sys.executable, "Path to interpreter could not be found"
        cmd = [sys.executable, downward, '--plan-file', plan_filename, domain_filename, problem_filename, '--search',
                'astar(lmcut())']
        return cmd

    def _result_status(self, problem: 'up.model.Problem', plan: Optional['up.plan.Plan']) -> int:
        if plan is None:
            return PlanGenerationResultStatus.UNSOLVABLE_PROVEN
        else:
            return PlanGenerationResultStatus.SOLVED_OPTIMALLY

    @staticmethod
    def supports(problem_kind: 'ProblemKind') -> bool:
        # TODO metrics MinimizeActionCosts and MinimizeSequentialPlanLength
        supported_kind = ProblemKind()
        supported_kind.set_typing('FLAT_TYPING')
        supported_kind.set_conditions_kind('NEGATIVE_CONDITIONS')
        supported_kind.set_conditions_kind('DISJUNCTIVE_CONDITIONS')
        supported_kind.set_conditions_kind('EXISTENTIAL_CONDITIONS')
        supported_kind.set_conditions_kind('UNIVERSAL_CONDITIONS')
        supported_kind.set_conditions_kind('EQUALITY')
        return problem_kind <= supported_kind

    @staticmethod
    def satisfies(optimality_guarantee: Union[int, str]) -> bool:
        if optimality_guarantee in OptimalityGuarantee:
            return True
        return False
