import importlib.resources
import sys
import unified_planning as up
from typing import Callable, Iterator, IO, List, Optional, Tuple, Union
from unified_planning.model import ProblemKind, InstantaneousAction
from unified_planning.engines import OptimalityGuarantee
from unified_planning.engines import PlanGenerationResultStatus as ResultStatus
from unified_planning.engines import PDDLAnytimePlanner, PDDLPlanner
from unified_planning.engines import OperationMode, Credits
from unified_planning.shortcuts import BoolType, MinimizeActionCosts
from unified_planning.engines.results import LogLevel, LogMessage, PlanGenerationResult
from up_fast_downward import utils

credits = {
    "name": "Fast Downward",
    "author": "Uni Basel team and contributors (cf. https://github.com/aibasel/downward/blob/main/README.md)",
    "contact": "gabriele.roeger@unibas.ch (for UP integration)",
    "website": "https://www.fast-downward.org",
    "license": "GPLv3",
    "short_description": "Fast Downward is a domain-independent classical planning system.",
    "long_description": "Fast Downward is a domain-independent classical planning system.",
}


class FastDownwardMixin:
    def __init__(
        self,
        fast_downward_alias: Optional[str] = None,
        fast_downward_search_config: Optional[str] = None,
        fast_downward_anytime_alias: Optional[str] = None,
        fast_downward_anytime_search_config: Optional[str] = None,
        fast_downward_translate_options: Optional[List[str]] = None,
        fast_downward_search_time_limit: Optional[str] = None,
        log_level: str = "info",
    ):
        self._fd_alias = fast_downward_alias
        self._fd_search_config = fast_downward_search_config
        self._fd_anytime_alias = fast_downward_anytime_alias
        self._fd_anytime_search_config = fast_downward_anytime_search_config
        self._fd_translate_options = fast_downward_translate_options
        self._fd_search_time_limit = fast_downward_search_time_limit
        self._log_level = log_level
        assert not (self._fd_alias and self._fd_search_config)
        assert not (self._fd_anytime_alias and self._fd_anytime_search_config)
        self._guarantee_no_plan_found = ResultStatus.UNSOLVABLE_INCOMPLETELY
        self._guarantee_metrics_task = ResultStatus.SOLVED_SATISFICING

    def _base_cmd(self, plan_filename: str):
        loc = "downward/fast-downward.py"
        downward_res = importlib.resources.files("up_fast_downward").joinpath(loc)
        with importlib.resources.as_file(downward_res) as downward:
            # This will clean up any temporary files created for accessing
            # downward once we leave the with statement. Since the resource is
            # not packed into a zip file or anything, this should be save
            # enough. Otherwise, we need to explore an atexit handler:
            # cf https://importlib-resources.readthedocs.io/en/latest/migration.html
            assert sys.executable, "Path to interpreter could not be found"
            cmd = [sys.executable, downward, "--plan-file", plan_filename]
            if self._fd_search_time_limit is not None:
                cmd += ["--search-time-limit", self._fd_search_time_limit]
            cmd += ["--log-level", self._log_level]
            return cmd

    def _get_cmd(
        self, domain_filename: str, problem_filename: str, plan_filename: str
    ) -> List[str]:
        cmd = self._base_cmd(plan_filename)
        if self._fd_alias:
            cmd += ["--alias", self._fd_alias]
        cmd += [domain_filename, problem_filename]
        if self._fd_translate_options:
            cmd += ["--translate-options"] + self._fd_translate_options
        if self._fd_search_config:
            cmd += ["--search-options", "--search"] + self._fd_search_config.split()
        return cmd

    def _get_anytime_cmd(
        self, domain_filename: str, problem_filename: str, plan_filename: str
    ) -> List[str]:
        cmd = self._base_cmd(plan_filename)
        if self._fd_anytime_alias:
            cmd += ["--alias", self._fd_anytime_alias]
        cmd += [domain_filename, problem_filename]
        if self._fd_translate_options:
            cmd += ["--translate-options"] + self._fd_translate_options
        if self._fd_anytime_search_config:
            cmd += [
                "--search-options",
                "--search",
            ] + self._fd_anytime_search_config.split()
        return cmd

    def _result_status(
        self,
        problem: "up.model.Problem",
        plan: Optional["up.plans.Plan"],
        retval: int = None,  # Default value for legacy support
        log_messages: Optional[List[LogMessage]] = None,
    ) -> "up.engines.results.PlanGenerationResultStatus":
        def solved(metrics):
            if metrics:
                return self._guarantee_metrics_task
            else:
                return ResultStatus.SOLVED_SATISFICING

        # https://www.fast-downward.org/ExitCodes
        metrics = problem.quality_metrics
        if retval is None:  # legacy support
            if plan is None:
                return self._guarantee_no_plan_found
            else:
                return solved(metrics)
        if retval in (0, 1, 2, 3):
            if plan is None:
                return self._guarantee_no_plan_found
            else:
                return solved(metrics)
        if retval in (10, 11):
            return ResultStatus.UNSOLVABLE_PROVEN
        if retval == 12:
            return ResultStatus.UNSOLVABLE_INCOMPLETELY
        if retval == 34:
            return ResultStatus.UNSUPPORTED_PROBLEM
        if retval in (21, 23):
            return ResultStatus.TIMEOUT
        if retval in (20, 22):
            return ResultStatus.MEMOUT
        else:
            return ResultStatus.INTERNAL_ERROR


class FastDownwardPDDLPlanner(FastDownwardMixin, PDDLAnytimePlanner):
    def __init__(
        self,
        fast_downward_alias: Optional[str] = None,
        fast_downward_search_config: Optional[str] = None,
        fast_downward_anytime_alias: Optional[str] = None,
        fast_downward_anytime_search_config: Optional[str] = None,
        fast_downward_translate_options: Optional[List[str]] = None,
        fast_downward_search_time_limit: Optional[str] = None,
        log_level: str = "info",
    ):
        PDDLAnytimePlanner.__init__(self)
        if fast_downward_search_config is None and fast_downward_alias is None:
            fast_downward_alias = "lama-first"
        if (
            fast_downward_anytime_search_config is None
            and fast_downward_anytime_alias is None
        ):
            fast_downward_anytime_alias = "seq-sat-lama-2011"

        FastDownwardMixin.__init__(
            self,
            fast_downward_alias=fast_downward_alias,
            fast_downward_search_config=fast_downward_search_config,
            fast_downward_anytime_alias=fast_downward_anytime_alias,
            fast_downward_anytime_search_config=fast_downward_anytime_search_config,
            fast_downward_translate_options=fast_downward_translate_options,
            fast_downward_search_time_limit=fast_downward_search_time_limit,
            log_level=log_level,
        )

    @property
    def name(self) -> str:
        return "Fast Downward"

    @staticmethod
    def get_credits(**kwargs) -> Optional["Credits"]:
        c = Credits(**credits)
        details = [
            c.long_description,
            "The default configuration uses the FF heuristic by Jörg Hoffmann and",
            "the landmark heuristic by Silvia Richter and Matthias Westphal.",
        ]
        c.long_description = " ".join(details)
        return c

    def _starting_plan_str(self) -> str:
        return "Solution found!"

    def _ending_plan_str(self) -> str:
        return "step(s)."

    def _parse_plan_line(self, plan_line: str) -> str:
        if plan_line.startswith("[t="):
            return ""
        return "(%s)" % plan_line.split("(")[0].strip()

    @staticmethod
    def satisfies(optimality_guarantee: "OptimalityGuarantee") -> bool:
        if optimality_guarantee == OptimalityGuarantee.SATISFICING:
            return True
        return False

    @staticmethod
    def supported_kind() -> "ProblemKind":
        supported_kind = ProblemKind(version=2)
        supported_kind.set_problem_class("ACTION_BASED")
        supported_kind.set_typing("FLAT_TYPING")
        supported_kind.set_typing("HIERARCHICAL_TYPING")
        supported_kind.set_conditions_kind("NEGATIVE_CONDITIONS")
        supported_kind.set_conditions_kind("DISJUNCTIVE_CONDITIONS")
        supported_kind.set_conditions_kind("EXISTENTIAL_CONDITIONS")
        supported_kind.set_conditions_kind("UNIVERSAL_CONDITIONS")
        supported_kind.set_conditions_kind("EQUALITIES")
        supported_kind.set_effects_kind("CONDITIONAL_EFFECTS")
        supported_kind.set_effects_kind("STATIC_FLUENTS_IN_BOOLEAN_ASSIGNMENTS")
        supported_kind.set_effects_kind("FLUENTS_IN_BOOLEAN_ASSIGNMENTS")
        supported_kind.set_effects_kind("FORALL_EFFECTS")
        supported_kind.set_quality_metrics("ACTIONS_COST")
        supported_kind.set_actions_cost_kind("STATIC_FLUENTS_IN_ACTIONS_COST")
        supported_kind.set_actions_cost_kind("INT_NUMBERS_IN_ACTIONS_COST")
        supported_kind.set_quality_metrics("PLAN_LENGTH")
        return supported_kind

    @staticmethod
    def supports(problem_kind: "ProblemKind") -> bool:
        return problem_kind <= FastDownwardPDDLPlanner.supported_kind()

    @staticmethod
    def ensures(anytime_guarantee: up.engines.AnytimeGuarantee) -> bool:
        if anytime_guarantee == up.engines.AnytimeGuarantee.INCREASING_QUALITY:
            return True
        return False


class FastDownwardOptimalPDDLPlanner(FastDownwardMixin, PDDLPlanner):
    def __init__(self, log_level: str = "info"):
        PDDLPlanner.__init__(self)
        FastDownwardMixin.__init__(
            self, fast_downward_search_config="astar(lmcut())", log_level=log_level
        )
        self._guarantee_no_plan_found = ResultStatus.UNSOLVABLE_PROVEN
        self._guarantee_metrics_task = ResultStatus.SOLVED_OPTIMALLY

    @property
    def name(self) -> str:
        return "Fast Downward (with optimality guarantee)"

    @staticmethod
    def get_credits(**kwargs) -> Optional["Credits"]:
        c = Credits(**credits)
        details = [
            c.long_description,
            "The optimal engine uses the LM-Cut heuristic by",
            "Malte Helmert and Carmel Domshlak.",
        ]
        c.long_description = " ".join(details)
        return c

    @staticmethod
    def supported_kind() -> "ProblemKind":
        supported_kind = ProblemKind(version=2)
        supported_kind.set_problem_class("ACTION_BASED")
        supported_kind.set_typing("FLAT_TYPING")
        supported_kind.set_typing("HIERARCHICAL_TYPING")
        supported_kind.set_conditions_kind("NEGATIVE_CONDITIONS")
        supported_kind.set_conditions_kind("DISJUNCTIVE_CONDITIONS")
        supported_kind.set_conditions_kind("EXISTENTIAL_CONDITIONS")
        supported_kind.set_conditions_kind("UNIVERSAL_CONDITIONS")
        supported_kind.set_conditions_kind("EQUALITIES")
        supported_kind.set_quality_metrics("ACTIONS_COST")
        supported_kind.set_actions_cost_kind("STATIC_FLUENTS_IN_ACTIONS_COST")
        supported_kind.set_actions_cost_kind("INT_NUMBERS_IN_ACTIONS_COST")
        supported_kind.set_quality_metrics("PLAN_LENGTH")
        return supported_kind

    @staticmethod
    def supports(problem_kind: "ProblemKind") -> bool:
        return problem_kind <= FastDownwardOptimalPDDLPlanner.supported_kind()

    @staticmethod
    def satisfies(optimality_guarantee: OptimalityGuarantee) -> bool:
        return True

    # To avoid the introduction of axioms with complicated goals, we introduce
    # a separate goal action (later to be removed from the plan)
    def _solve(
        self,
        problem: "up.model.AbstractProblem",
        heuristic: Optional[Callable[["up.model.state.State"], Optional[float]]] = None,
        timeout: Optional[float] = None,
        output_stream: Optional[Union[Tuple[IO[str], IO[str]], IO[str]]] = None,
    ) -> "up.engines.results.PlanGenerationResult":
        assert isinstance(problem, up.model.Problem)

        # add a new goal atom (initially false) plus an action that has the
        # original goal as precondition and sets the new goal atom
        modified_problem, _, _ = utils.introduce_artificial_goal_action(problem)
        return super()._solve(modified_problem, heuristic, timeout, output_stream)

    # overwrite plan extraction to remove the newly introduced goal action from
    # the end of the plan
    def _plan_from_file(
        self,
        problem: "up.model.Problem",
        plan_filename: str,
        get_item_named: Callable[
            [str],
            Union[
                "up.model.Type",
                "up.model.Action",
                "up.model.Fluent",
                "up.model.Object",
                "up.model.Parameter",
                "up.model.Variable",
                "up.model.multi_agent.Agent",
            ],
        ],
    ) -> "up.plans.Plan":
        """
        Takes a problem, a filename and a map of renaming and returns the plan parsed from the file.
        :param problem: The up.model.problem.Problem instance for which the plan is generated.
        :param plan_filename: The path of the file in which the plan is written.
        :param get_item_named: A function that takes a name and returns the original up.model element instance
            linked to that renaming.
        :return: The up.plans.Plan corresponding to the parsed plan from the file
        """
        with open(plan_filename) as plan:
            plan_string = plan.read()
            # Remove all comments from the plan string.
            plan_string = [
                line
                for line in plan_string.split("\n")
                if not line.strip().startswith(";")
            ]
            # Remove the last line (= goal action) from the plan string.
            plan_string = plan_string[:-2]
            plan_string = "\n".join(plan_string)
            return self._plan_from_str(problem, plan_string, get_item_named)
