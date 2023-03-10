import pkg_resources
import sys
import unified_planning as up

from typing import List, Optional, Union
from unified_planning.model import ProblemKind
from unified_planning.engines import OptimalityGuarantee
from unified_planning.engines import PDDLPlanner, Credits
from unified_planning.engines import PlanGenerationResultStatus as ResultStatus


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
        self.fd_alias = 'lama-first'
        self.fd_search_config = None
        self.guarantee_no_plan_found = ResultStatus.UNSOLVABLE_INCOMPLETELY
        self.guarantee_metrics_task = ResultStatus.SOLVED_SATISFICING

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
        assert not (self.fd_alias and self.fd_search_config)
        cmd = [sys.executable, downward, '--plan-file', plan_filename]
        if self.fd_alias:
            cmd += ['--alias', 'lama-first']
        cmd += [domain_filename, problem_filename]
        if self.fd_search_config:
            cmd += ['--search'] + self.fd_search_config.split()
        return cmd

    def _result_status(
        self,
        problem: "up.model.Problem",
        plan: Optional["up.plans.Plan"],
        retval: int = None, # Default value for legacy support
        #log_messages: Optional[List[LogMessage]] = None,
        log_messages = None,
        ) -> "up.engines.results.PlanGenerationResultStatus":

        def solved(metrics):
            if metrics:
                return self.guarantee_metrics_task
            else:
                return ResultStatus.SOLVED_SATISFICING
        
        # https://www.fast-downward.org/ExitCodes
        metrics = problem.quality_metrics
        if retval is None: # legacy support
            if plan is None:
                return self.guarantee_no_plan_found
            else:
                return solved(metrics)
        if retval in (0, 1, 2, 3):
            if plan is None:
                return self.guarantee_no_plan_found
            else:
                return solved(metrics)
        if retval in (10, 11):
            return ResultStatus.UNSOLVABLE_PROVEN
        if retval == 12:
            return ResultStatus.UNSOLVABLE_INCOMPLETELY
        else:
            return ResultStatus.INTERNAL_ERROR

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
        supported_kind.set_typing('HIERARCHICAL_TYPING')
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



class FastDownwardOptimalPDDLPlanner(FastDownwardPDDLPlanner):

    def __init__(self):
        super().__init__()
        self.fd_alias = None
        self.fd_search_config = "astar(lmcut())"
        self.guarantee_no_plan_found = ResultStatus.UNSOLVABLE_PROVEN
        self.guarantee_metrics_task = ResultStatus.SOLVED_OPTIMALLY

    @property
    def name(self) -> str:
        return 'Fast Downward (with optimality guarantee)'

    @staticmethod
    def supported_kind() -> 'ProblemKind':
        supported_kind = ProblemKind()
        supported_kind.set_problem_class('ACTION_BASED')
        supported_kind.set_typing('FLAT_TYPING')
        supported_kind.set_typing('HIERARCHICAL_TYPING')
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
