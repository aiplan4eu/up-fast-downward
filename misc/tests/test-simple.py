import pytest

from unified_planning.engines import (OptimalityGuarantee,
        PlanGenerationResultStatus)
from unified_planning.shortcuts import *
unified_planning.shortcuts.get_environment().credits_stream = None # silence credits


@pytest.mark.parametrize("oneshot_planner_name", ["fast-downward",
                                                  "fast-downward-opt"])
def test_valid_result_status(oneshot_planner_name):
    # create problem
    x = Fluent('x')
    y = Fluent('y')
    a = InstantaneousAction('a')
    a.add_precondition(y)
    a.add_effect(x, True)
    a.add_effect(y, False)
    problem = Problem('basic')
    problem.add_fluent(x)
    problem.add_fluent(y)
    problem.add_action(a)
    problem.set_initial_value(x, False)
    problem.set_initial_value(y, True)
    problem.add_goal(x)
    
    with OneshotPlanner(name=oneshot_planner_name) as planner:
        result = planner.solve(problem)
    assert result.plan is not None
    assert result.status is PlanGenerationResultStatus.SOLVED_SATISFICING

