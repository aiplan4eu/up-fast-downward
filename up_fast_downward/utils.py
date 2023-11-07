from itertools import count
from unified_planning.shortcuts import BoolType, MinimizeActionCosts
from unified_planning.model import InstantaneousAction
from typing import Mapping, Optional, Tuple


def introduce_artificial_goal_action(
    problem: "up.model.AbstractProblem", other_actions_destroy_goal=False
) -> Tuple[
    "up.model.AbstractProblem",
    Optional["up.model.InstantaneousAction"],
    Optional[Mapping["up.model.InstantaneousAction", "up.model.InstantaneousAction"]],
]:
    """
    Clones the task and adds an artificial goal atom and an additional action
    that achieves it when the original goal is satisfied.  Parameter
    other_actions_destroy_goal indicates whether all original actions should
    destroy the artificial goal atom. This is not necessary if we run our
    planner on the transformed problem (because search terminates once it finds
    a plan). If we use this in grounding, we do not know what others do with
    the task. Thus we need this option to ensure that for every plan of the
    transformed task, omitting all occurrences of the artificial goal action
    gives a plan for the original task.
    """

    def get_new_name(problem, prefix):
        for num in count():
            candidate = f"{prefix}{num}"
            if not problem.has_name(candidate):
                return candidate

    modified_problem = problem.clone()
    # add a new goal atom (initially false) plus an action that has the
    # original goal as precondition and sets the new goal atom
    goal_fluent_name = get_new_name(modified_problem, "goal")
    goal_fluent = modified_problem.add_fluent(
        goal_fluent_name, BoolType(), default_initial_value=False
    )

    if other_actions_destroy_goal:
        for action in modified_problem.actions:
            action.add_effect(goal_fluent, False)
    modified_to_orig_action = dict(
        elem for elem in zip(modified_problem.actions, problem.actions)
    )

    goal_action_name = get_new_name(modified_problem, "reach_goal")
    goal_action = InstantaneousAction(goal_action_name)
    for goal in modified_problem.goals:
        goal_action.add_precondition(goal)
    goal_action.add_effect(goal_fluent, True)
    modified_problem.add_action(goal_action)
    modified_problem.clear_goals()
    modified_problem.add_goal(goal_fluent)
    if modified_problem.quality_metrics and isinstance(
        modified_problem.quality_metrics[0], MinimizeActionCosts
    ):
        m = modified_problem.quality_metrics[0]
        action_costs = m.costs
        action_costs[goal_action] = 1
        metric = MinimizeActionCosts(action_costs, m.default, m.environment)
        modified_problem.clear_quality_metrics()
        modified_problem.add_quality_metric(metric)

    return modified_problem, goal_action, modified_to_orig_action
