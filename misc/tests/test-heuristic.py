import sys
import time

import pytest

pytest.importorskip("unified_planning.engines.mixins.heuristic")

from unified_planning.engines import HeuristicGuarantee
from unified_planning.exceptions import UPException, UPUnsupportedProblemTypeError
from unified_planning.shortcuts import *
from unified_planning.test.examples import get_example_problems

fdh = pytest.importorskip("up_fast_downward.fast_downward_heuristic")

unified_planning.shortcuts.get_environment().credits_stream = None # silence credits

def dead_end_problem():
    """Applying destroy leads to a state from which done is unreachable."""
    broken = Fluent('broken')
    done = Fluent('done')
    destroy = InstantaneousAction('destroy')
    destroy.add_precondition(Not(broken))
    destroy.add_effect(broken, True)
    finish = InstantaneousAction('finish')
    finish.add_precondition(Not(broken))
    finish.add_effect(done, True)
    problem = Problem('dead_end')
    problem.add_fluent(broken, default_initial_value=False)
    problem.add_fluent(done, default_initial_value=False)
    problem.add_actions([destroy, finish])
    problem.add_goal(done)
    return problem, destroy


def problems():
    """Small problems that all named engines support."""
    examples = get_example_problems()
    return [
        examples['robot_loader'].problem,
        examples['hierarchical_blocks_world'].problem,
        examples['basic_with_costs'].problem,
        dead_end_problem()[0],
    ]


def action_cost(problem, action):
    for qm in problem.quality_metrics:
        if isinstance(qm, up.model.metrics.MinimizeActionCosts):
            return qm.get_action_cost(action).constant_value()
    return 1


def optimal_trace(problem):
    """Returns the states along an optimal plan and the costs of its actions."""
    with OneshotPlanner(name='fast-downward-opt') as planner:
        plan = planner.solve(problem).plan
    with SequentialSimulator(problem) as sim:
        states = [sim.get_initial_state()]
        for ai in plan.actions:
            states.append(sim.apply(states[-1], ai))
    costs = [action_cost(problem, ai.action) for ai in plan.actions]
    return states, costs


@pytest.mark.parametrize('engine', fdh.NAMED_HEURISTICS, ids=lambda e: e.__name__)
@pytest.mark.parametrize('problem', problems(), ids=lambda p: p.name)
def test_guarantees_along_optimal_plan(engine, problem):
    """Checks every guarantee the engine claims on the states of an optimal plan."""
    if not engine.supports(problem.kind):
        pytest.skip('unsupported problem kind')
    states, costs = optimal_trace(problem)
    with engine(problem) as h:
        values = [h.value(s) for s in states]
    remaining = [sum(costs[i:]) for i in range(len(states))]
    if engine.guarantees(HeuristicGuarantee.GOAL_AWARE):
        assert values[-1] == 0
    if engine.guarantees(HeuristicGuarantee.SAFE):
        assert None not in values
    if engine.guarantees(HeuristicGuarantee.ADMISSIBLE):
        assert all(v <= r for v, r in zip(values, remaining)), values
    if engine.guarantees(HeuristicGuarantee.CONSISTENT):
        assert all(
            values[i] <= costs[i] + values[i + 1] for i in range(len(costs))
        ), values


@pytest.mark.parametrize('engine', [fdh.FastDownwardHMaxHeuristic, fdh.FastDownwardFFHeuristic])
def test_dead_end(engine):
    problem, destroy = dead_end_problem()
    with SequentialSimulator(problem) as sim, engine(problem) as h:
        state = sim.apply(sim.get_initial_state(), destroy)
        assert h.value(state) is None


def test_generic_engine():
    problem = get_example_problems()['robot_loader'].problem
    with SequentialSimulator(problem) as sim, \
            fdh.FastDownwardHeuristic(problem, fast_downward_heuristic='max([hmax(), lmcut()])') as h:
        assert h.value(sim.get_initial_state()) == 3
    assert fdh.FastDownwardHeuristic.guarantees(HeuristicGuarantee.SAFE) is False


def test_conditional_effects_not_supported():
    problem = get_example_problems()['basic_conditional'].problem
    assert not fdh.FastDownwardLMCutHeuristic.supports(problem.kind)
    assert fdh.FastDownwardFFHeuristic.supports(problem.kind)


def test_axioms_not_supported():
    # The translator introduces axioms for this non-conjunctive goal.
    x, y = Fluent('x'), Fluent('y')
    a = InstantaneousAction('a')
    a.add_effect(x, True)
    problem = Problem('disjunctive_goal')
    problem.add_fluent(x, default_initial_value=False)
    problem.add_fluent(y, default_initial_value=False)
    problem.add_action(a)
    problem.add_goal(And(Or(x, Not(y)), Or(y, x)))
    assert fdh.FastDownwardLMCutHeuristic.supports(problem.kind)
    with pytest.raises(UPUnsupportedProblemTypeError):
        fdh.FastDownwardLMCutHeuristic(problem)
    with SequentialSimulator(problem) as sim, fdh.FastDownwardFFHeuristic(problem) as h:
        assert h.value(sim.get_initial_state()) == 1


def test_path_dependent_rejected():
    problem = get_example_problems()['robot_loader'].problem
    with pytest.raises(UPException, match='path-dependent'):
        fdh.FastDownwardHeuristic(
            problem, fast_downward_heuristic='landmark_sum(lm_factory=lm_rhw())')


def test_trivially_unsolvable():
    # y is never achieved, so the translator proves the task unsolvable.
    x, y = Fluent('x'), Fluent('y')
    a = InstantaneousAction('a')
    a.add_precondition(y)
    a.add_effect(x, True)
    problem = Problem('unsolvable')
    problem.add_fluent(x, default_initial_value=False)
    problem.add_fluent(y, default_initial_value=False)
    problem.add_action(a)
    problem.add_goal(x)
    with SequentialSimulator(problem) as sim, fdh.FastDownwardFFHeuristic(problem) as h:
        assert h._process is None
        assert h.value(sim.get_initial_state()) is None


def benchmark(domain, problem_file, n=200):
    """Times value() on random-walk states; run as: python test-heuristic.py DOMAIN PROBLEM"""
    import random
    problem = up.io.PDDLReader().parse_problem(domain, problem_file)
    with SequentialSimulator(problem) as sim, fdh.FastDownwardFFHeuristic(problem) as h:
        states = [sim.get_initial_state()]
        while len(states) < n:
            actions = list(sim.get_applicable_actions(states[-1]))
            states.append(sim.apply(states[-1], *random.choice(actions)) if actions else states[0])
        start = time.perf_counter()
        for s in states:
            h.value(s)
        elapsed = time.perf_counter() - start
    print(f'{len(h._variables)} variables, '
          f'{sum(len(v.atoms) for v in h._variables)} atoms, '
          f'{1000 * elapsed / n:.2f} ms per value()')


if __name__ == '__main__':
    benchmark(*sys.argv[1:3])
