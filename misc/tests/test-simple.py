import pytest

from unified_planning.engines import (OptimalityGuarantee,
        PlanGenerationResultStatus)
from unified_planning.shortcuts import *
unified_planning.shortcuts.get_environment().credits_stream = None # silence credits


def basic_problem(metric=False):
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
    if metric:
        problem.add_quality_metric(
            up.model.metrics.MinimizeActionCosts({a: 10})
        )

    return problem


def lifted_problem():
    problem = Problem("lifted")

    # Define UserTypes
    Location = UserType("Location")
    
    # Define Fluent
    at = Fluent("at", loc = Location)
    problem.add_fluent(at, default_initial_value=False)
    
    connected = Fluent("connected", loc1 = Location, loc2 = Location)
    problem.add_fluent(connected, default_initial_value=False)

    # Define move action
    move = InstantaneousAction("move", l_from=Location, l_to=Location)
    l_from, l_to = move.parameter("l_from"), move.parameter("l_to")
    move.add_precondition(at(l_from))
    move.add_precondition(connected(l_from, l_to))
    move.add_effect(at(l_from), False)
    move.add_effect(at(l_to), True)
    problem.add_action(move)

    # Define objects
    l1 = Object("l1", Location)
    l2 = Object("l2", Location)
    l3 = Object("l3", Location)

    problem.add_objects((l1, l2, l3))
    problem.set_initial_value(at(l1), True)
    problem.set_initial_value(connected(l1, l2), True)
    problem.set_initial_value(connected(l2, l1), True)
    problem.add_goal(at(l2))

    return problem


@pytest.mark.parametrize("oneshot_planner_name", ["fast-downward",
                                                  "fast-downward-opt"])
def test_valid_result_status_no_metric(oneshot_planner_name):
    problem = basic_problem() 
    with OneshotPlanner(name=oneshot_planner_name) as planner:
        result = planner.solve(problem)
    assert result.plan is not None
    assert result.status is PlanGenerationResultStatus.SOLVED_SATISFICING


@pytest.mark.parametrize("oneshot_planner_name", ["fast-downward",
                                                  "fast-downward-opt"])
def test_valid_result_status_metric(oneshot_planner_name):
    problem = basic_problem(metric=True) 
    with OneshotPlanner(name=oneshot_planner_name) as planner:
        result = planner.solve(problem)
    assert result.plan is not None
    if planner.satisfies(OptimalityGuarantee.SOLVED_OPTIMALLY):
        assert result.status is PlanGenerationResultStatus.SOLVED_OPTIMALLY
    else:
        assert result.status is PlanGenerationResultStatus.SOLVED_SATISFICING


@pytest.mark.parametrize(
    "grounder_name", ["fast-downward-reachability-grounder",
                      "fast-downward-grounder"]
)
def test_grounder(grounder_name):
    problem = lifted_problem()
    with Compiler(name=grounder_name, compilation_kind=CompilationKind.GROUNDING) as g:
        res = g.compile(problem, CompilationKind.GROUNDING)
    grounded = res.problem
    print(grounded)

    assert grounded.actions, "grounder removed all actions"
    assert all(len(a.parameters) == 0 for a in grounded.actions)
    # reachability pruning: only l1 -> l2 and l2 -> l1 are reachable
    assert len(grounded.actions) == 2

    # solve the grounded problem, map the plan back, validate on the original
    with OneshotPlanner(name="fast-downward") as planner:
        plan = planner.solve(grounded).plan
    assert plan is not None
    original_plan = plan.replace_action_instances(res.map_back_action_instance)
    with PlanValidator(problem_kind=problem.kind, plan_kind=original_plan.kind) as v:
        assert v.validate(problem, original_plan) 
