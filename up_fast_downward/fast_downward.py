import pkg_resources
import sys
import unified_planning as up
import unified_planning.engines.mixins as mixins
from typing import Callable, Iterator, IO, List, Optional, Tuple, Union
from unified_planning.model import ProblemKind
from unified_planning.engines import OptimalityGuarantee
from unified_planning.engines import PlanGenerationResultStatus as ResultStatus
from unified_planning.engines import PDDLPlanner, OperationMode, Credits
from unified_planning.engines.results import LogLevel, LogMessage, PlanGenerationResult


credits = {
    "name": "Fast Downward",
    "author": "Uni Basel team and contributors (cf. https://github.com/aibasel/downward/blob/main/README.md)",
    "contact": "gabriele.roeger@unibas.ch (for UP integration)",
    "website": "https://www.fast-downward.org",
    "license": "GPLv3",
    "short_description": "Fast Downward is a domain-independent classical planning system.",
    "long_description": "Fast Downward is a domain-independent classical planning system.",
}


class FastDownwardPDDLPlannerBase(PDDLPlanner):
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
        super().__init__(rewrite_bool_assignments=True)
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
        self._mode_running = OperationMode.ONESHOT_PLANNER

    def _get_cmd(
        self, domain_filename: str, problem_filename: str, plan_filename: str
    ) -> List[str]:
        downward = pkg_resources.resource_filename(
            __name__, "downward/fast-downward.py"
        )
        assert sys.executable, "Path to interpreter could not be found"
        cmd = [sys.executable, downward, "--plan-file", plan_filename]
        if self._fd_search_time_limit is not None:
            cmd += ["--search-time-limit", self._fd_search_time_limit]
        cmd += ["--log-level", self._log_level]
        if self._mode_running is OperationMode.ONESHOT_PLANNER:
            if self._fd_alias:
                cmd += ["--alias", self._fd_alias]
            cmd += [domain_filename, problem_filename]
            if self._fd_translate_options:
                cmd += ["--translate-options"] + self._fd_translate_options
            if self._fd_search_config:
                cmd += ["--search-options", "--search"] + self._fd_search_config.split()
        elif self._mode_running is OperationMode.ANYTIME_PLANNER:
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
        else:
            return ResultStatus.INTERNAL_ERROR


class FastDownwardPDDLPlanner(FastDownwardPDDLPlannerBase, mixins.AnytimePlannerMixin):
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
        if fast_downward_search_config is None and fast_downward_alias is None:
            fast_downward_alias = "lama-first"
        if (
            fast_downward_anytime_search_config is None
            and fast_downward_anytime_alias is None
        ):
            fast_downward_anytime_alias = "seq-sat-lama-2011"
        super().__init__(
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

    def _solve(
        self,
        problem: "up.model.AbstractProblem",
        heuristic: Optional[
            Callable[["up.model.state.ROState"], Optional[float]]
        ] = None,
        timeout: Optional[float] = None,
        output_stream: Optional[Union[Tuple[IO[str], IO[str]], IO[str]]] = None,
        anytime: bool = False,
    ):
        if anytime:
            self._mode_running = OperationMode.ANYTIME_PLANNER
        else:
            self._mode_running = OperationMode.ONESHOT_PLANNER
        return super()._solve(problem, heuristic, timeout, output_stream)

    def _get_solutions(
        self,
        problem: "up.model.AbstractProblem",
        timeout: Optional[float] = None,
        output_stream: Optional[IO[str]] = None,
    ) -> Iterator["up.engines.results.PlanGenerationResult"]:
        import threading
        import queue

        q: queue.Queue = queue.Queue()

        class Writer(up.AnyBaseClass):
            def __init__(self, os, q, engine):
                self._os = os
                self._q = q
                self._engine = engine
                self._plan = []
                self._storing = False
                self._sequential_plan = None

            def write(self, txt: str):
                if self._os is not None:
                    self._os.write(txt)
                for l in txt.splitlines():
                    if l.endswith("Solution found!"):
                        self._storing = True
                    elif self._storing:
                        if l.endswith("step(s)."):
                            self._storing = False
                            plan_str = "\n".join(self._plan)
                            plan = self._engine._plan_from_str(
                                problem, plan_str, self._engine._writer.get_item_named
                            )
                            res = PlanGenerationResult(
                                ResultStatus.INTERMEDIATE,
                                plan=plan,
                                engine_name=self._engine.name,
                            )
                            self._q.put(res)
                            self._sequential_plan = plan
                            self._plan = []
                        elif not l.startswith("[t="):
                            self._plan.append("(%s)" % l.split("(")[0].strip())
                    if l.startswith("search exit code"):
                        # search terminated
                        if self._sequential_plan is not None:
                            res = PlanGenerationResult(
                                ResultStatus.SOLVED_SATISFICING,
                                plan=self._sequential_plan,
                                engine_name=self._engine.name,
                            )
                            self._q.put(res)

        def run():
            writer: IO[str] = Writer(output_stream, q, self)
            res = self._solve(problem, output_stream=writer, anytime=True)
            q.put(res)

        try:
            t = threading.Thread(target=run, daemon=True)
            t.start()
            status = ResultStatus.INTERMEDIATE
            while status == ResultStatus.INTERMEDIATE:
                res = q.get()
                status = res.status
                yield res
        finally:
            if self._process is not None:
                try:
                    self._process.kill()
                except OSError:
                    pass  # This can happen if the process is already terminated
            t.join()

    @staticmethod
    def satisfies(optimality_guarantee: "OptimalityGuarantee") -> bool:
        if optimality_guarantee == OptimalityGuarantee.SATISFICING:
            return True
        return False

    @staticmethod
    def supported_kind() -> "ProblemKind":
        supported_kind = ProblemKind()
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
        supported_kind.set_quality_metrics("ACTIONS_COST")
        supported_kind.set_actions_cost_kind("STATIC_FLUENTS_IN_ACTIONS_COST")
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


class FastDownwardOptimalPDDLPlanner(FastDownwardPDDLPlannerBase):
    def __init__(self, log_level: str = "info"):
        super().__init__(
            fast_downward_search_config="astar(lmcut())", log_level=log_level
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
        supported_kind = ProblemKind()
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
        supported_kind.set_quality_metrics("PLAN_LENGTH")
        return supported_kind

    @staticmethod
    def supports(problem_kind: "ProblemKind") -> bool:
        return problem_kind <= FastDownwardOptimalPDDLPlanner.supported_kind()

    @staticmethod
    def satisfies(optimality_guarantee: OptimalityGuarantee) -> bool:
        return True
