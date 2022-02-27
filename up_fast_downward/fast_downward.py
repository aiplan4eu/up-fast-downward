import pkg_resources

from typing import List
from unified_planning.shortcuts import ProblemKind
from unified_planning.solvers import PDDLSolver


class FastDownwardPDDLSolver(PDDLSolver):

    def __init__(self):
        super().__init__()

    def destroy(self):
        pass

    @staticmethod
    def name() -> str:
        return 'Fast Downward'

    def _get_cmd(self, domain_filename: str,
                 problem_filename: str, plan_filename: str) -> List[str]:
        downward = pkg_resources.resource_filename(__name__,
                                                   'downward/fast-downward.py')
        cmd = [downward, '--plan-file', plan_filename, '--alias', 'lama-first',
               domain_filename, problem_filename]
        return cmd

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
