import pytest
import networkx as nx
import random

from unified_planning.engines import (OptimalityGuarantee,
        PlanGenerationResultStatus)
from unified_planning.shortcuts import *
unified_planning.shortcuts.get_environment().credits_stream = None # silence credits


def test_valid_result_status():

    # from notebook
    def generate_problem(num_locations, num_parcels):
        # generate a random connected graph with the locations
        graph = nx.connected_watts_strogatz_graph(num_locations, 4, 0.2)

        # randomly choose the origin and destination of every parcel
        jobs = []
        for parcel in range(num_parcels):
            origin = random.randrange(num_locations)
            destination = random.choice([x for x in range(num_locations)
                                         if x != origin])
            jobs.append((origin, destination))


        # randlomly choose a truck location
        truck_location = random.randrange(num_locations)
        return graph, jobs, truck_location

    def get_planning_task(graph, jobs, truck_location):
        num_parcels = len(jobs)
        num_locations = len(graph)
        # declare user types
        Location = UserType('Location')
        Parcel = UserType('Parcel')

        # declare predicates
        truck_at = up.model.Fluent('truck_at', BoolType(), l=Location)
        parcel_at = up.model.Fluent('parcel_at', BoolType(), p=Parcel, l=Location)
        parcel_loaded = up.model.Fluent('parcel_loaded', BoolType(), p=Parcel)
        delivered = up.model.Fluent('delivered', BoolType(), p=Parcel)
        destination = up.model.Fluent('destination', BoolType(), p=Parcel, l=Location)
        connected = up.model.Fluent('connected', BoolType(), l_from=Location, l_to=Location)

        # add (typed) objects to problem
        problem = up.model.Problem('parcels')
        locations = [up.model.Object('loc%s' % i, Location)
                     for i in range(num_locations)]
        parcels = [up.model.Object('parcel%s' % i, Parcel)
                   for i in range(num_parcels)]
        problem.add_objects(locations)
        problem.add_objects(parcels)

        # specify the initial state
        problem.add_fluent(truck_at, default_initial_value=False)
        problem.add_fluent(parcel_at, default_initial_value=False)
        problem.add_fluent(parcel_loaded, default_initial_value=False)
        problem.add_fluent(delivered, default_initial_value=False)
        problem.add_fluent(destination, default_initial_value=False)
        problem.add_fluent(connected, default_initial_value=False)
        for parcel_id, (origin, dest) in enumerate(jobs):
            p = parcels[parcel_id]
            problem.set_initial_value(parcel_at(p, locations[origin]), True)
            problem.set_initial_value(destination(p, locations[dest]), True)
        for (l1, l2) in graph.edges():
            problem.set_initial_value(connected(locations[l1], locations[l2]), True)
            problem.set_initial_value(connected(locations[l2], locations[l1]), True)
        problem.set_initial_value(truck_at(locations[truck_location]), True)

        # add actions
        move = up.model.InstantaneousAction('move', l_from=Location, l_to=Location)
        l_from = move.parameter('l_from')
        l_to = move.parameter('l_to')
        move.add_precondition(connected(l_from, l_to))
        move.add_precondition(truck_at(l_from))
        move.add_effect(truck_at(l_from), False)
        move.add_effect(truck_at(l_to), True)
        problem.add_action(move)

        load = up.model.InstantaneousAction('load', p=Parcel, l=Location)
        p = load.parameter('p')
        loc = load.parameter('l')
        load.add_precondition(truck_at(loc))
        load.add_precondition(parcel_at(p, loc))
        load.add_effect(parcel_at(p, loc), False)
        load.add_effect(parcel_loaded(p), True)
        problem.add_action(load)

        unload = up.model.InstantaneousAction('unload', p=Parcel, l=Location)
        p = unload.parameter('p')
        loc = unload.parameter('l')
        unload.add_precondition(truck_at(loc))
        unload.add_precondition(parcel_loaded(p))
        unload.add_precondition(destination(p, loc))
        unload.add_effect(delivered(p), True)
        unload.add_effect(parcel_loaded(p), False)
        problem.add_action(unload)

        # specify the goal: all parcels should have been delivered
        for parcel_id, _ in enumerate(jobs):
            p = parcels[parcel_id]
            problem.add_goal(delivered(p))

        # we only want to minimize the number of actions
        problem.add_quality_metric(MinimizeSequentialPlanLength())
        return problem

    graph, jobs, truck_location = generate_problem(10, 8)
    small_problem = get_planning_task(graph, jobs, truck_location)

    expensive_edges = random.sample(list(graph.edges), 6)
    Location = small_problem.user_type("Location")
    move_cost = up.model.Fluent("move_cost", IntType(), from_loc=Location, to_loc=Location)
    small_problem.add_fluent(move_cost, default_initial_value=Int(1))
    for l1, l2 in expensive_edges:
        loc1 = small_problem.object("loc%s" % l1)
        loc2 = small_problem.object("loc%s" % l2)
        small_problem.set_initial_value(move_cost(loc1, loc2), Int(3))
        small_problem.set_initial_value(move_cost(loc2, loc1), Int(3))

    move = small_problem.action("move")
    m = MinimizeActionCosts({move : move_cost(move.l_from, move.l_to)}, default=Int(1))
    small_problem.clear_quality_metrics()
    small_problem.add_quality_metric(m)

    params = {
        'fast_downward_anytime_alias': 'seq-sat-fdss-2',
        'fast_downward_search_time_limit': "20s"
    }

    with AnytimePlanner(name="fast-downward", params=params) as planner:
        for result in planner.get_solutions(small_problem): # you can try it on "problem" here
            if result.status == up.engines.PlanGenerationResultStatus.INTERMEDIATE:
                print("Found an intermediate plan of length:", len(result.plan.actions))
                print("Continue searching...")
            elif result.status == up.engines.PlanGenerationResultStatus.SOLVED_SATISFICING:
                print("The final plan has length:", len(result.plan.actions))
                print(result.plan)
            else:
                print(result) # Gives additional context
                print("No plan found.")
                assert False
