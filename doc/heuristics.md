# Fast Downward heuristics in the Heuristic operation mode

This document describes how up_fast_downward exposes the heuristics of Fast
Downward as engines of the unified_planning (UP) Heuristic operation mode, and
why it is built this way. The code is in

- `up_fast_downward/fast_downward_heuristic.py`: the UP engines,
- `up_fast_downward/eval_server/eval_server.cc`: a Fast Downward search plugin
  that evaluates states,
- `up_fast_downward/_custom_build.py`: adds the plugin to the Fast Downward
  build,
- `misc/tests/test-heuristic.py`: the tests.

## The Heuristic operation mode

An engine of the Heuristic operation mode implements `HeuristicMixin`. It
receives the problem in its constructor and then answers `value(state)` for
any number of states. The value estimates the remaining cost to a goal state,
measured with the problem's quality metric (or in plan length if there is
none), and `None` means that the heuristic detected a dead end. An engine
states what it guarantees about its values through the static method
`guarantees(HeuristicGuarantee)`, with the members `ADMISSIBLE`, `CONSISTENT`,
`GOAL_AWARE` and `SAFE`.

Fast Downward is a C++ program that reads a translated task and runs a search.
It has no library interface, and its heuristics are only reachable from inside
that program. The design therefore has to answer three questions: how a UP
state reaches a Fast Downward heuristic, how the result comes back, and which
guarantees each heuristic can honestly claim.

## Overview

```
constructor
  UP problem
    -> PDDLWriter -> Fast Downward translator (in-process, Python)
    -> SAS task + one SASVariable per translated variable
    -> SAS task written to a temporary file
    -> downward --task-file <file> --search "eval_server(eval=<evaluator>)"
    <- "@ready" once the evaluator is built

value(state)
  UP state
    -> SAS values (Python, one value per translated variable)
    -> one line on the stdin of the downward process
    <- "@<h>" or "@inf" on its stdout
    -> int, or None for "inf"

destroy()
  close stdin; downward exits
```

Each engine owns one long-lived `downward` process. The translation and the
construction of the heuristic (which is expensive for pattern databases,
CEGAR and merge-and-shrink) happen once, in the constructor.

## Why a separate process

Three ways to call Fast Downward's heuristics were considered.

1. **A persistent subprocess** (chosen). The process is started once and
   evaluates states sent over a pipe.
2. **Python bindings** (pybind11 or nanobind) linked against Fast Downward's
   search code. The wheels of up_fast_downward are currently tagged
   `py3-none-<platform>`, because the package does not link against Python.
   Bindings would require one wheel per Python version, plus a CI matrix to
   build them.
3. **One Fast Downward run per state.** This repeats the translation and the
   heuristic construction for every state, which is far too slow.

The subprocess keeps the packaging unchanged, reuses the existing build, and
keeps a crash or memory exhaustion in Fast Downward away from the Python
interpreter. The cost is a pipe round trip per call, which is small next to
the cost of mapping the state (see [Performance](#performance)).

## Changes to the Fast Downward build

`_custom_build.py` clones the pinned Fast Downward release and, before
compiling it, makes two changes in `add_eval_server`.

**The eval_server plugin.** `eval_server.cc` is copied to
`src/search/search_algorithms/` and registered with one
`create_fast_downward_library` block appended to `src/search/CMakeLists.txt`.
It is a search plugin, not a separate executable, because Fast Downward's
libraries are CMake `INTERFACE` targets whose sources are compiled directly
into the `downward` executable. A second executable would compile all of Fast
Downward a second time. As a plugin it adds one source file to the build, and
the existing `downward` binary, which is already part of the package data,
gains the `eval_server(eval=...)` search option.

**Reading the task from a file.** `downward` reads the translated task from
stdin, and its parser requires end of input right after the task
(`confirm_end_of_input` in `tasks/root_task.cc`). The states for eval_server
must arrive on stdin too, so the task cannot. `planner.cc` is patched so that
`downward --task-file <file> ...` reads the task from the file and leaves
stdin open. The patch replaces one line, and the build fails with an assertion
if a new Fast Downward release changes that line.

Proposing the plugin and the option to Fast Downward upstream would remove
both changes from `_custom_build.py`.

## Translation and state mapping

### Translating the problem

The constructor writes the problem with `PDDLWriter` and runs the Fast
Downward translator in-process, as `fast_downward_grounder.py` already does.
The translator prints its progress, so its stdout is redirected. It uses its
default options, which include dropping facts that are unreachable from the
initial state and variables that are irrelevant for the goal. Disabling those
options would make more states representable exactly, but it would make the
task larger and the heuristics weaker or slower, and it gains nothing for
states that are reachable from the initial state.

### From UP states to SAS states

The translator groups mutually exclusive facts into finite-domain variables.
Each value of a variable has a name:

- `Atom at(truck1, depot2)`: the fact holds,
- `NegatedAtom at(truck1, depot2)`: the fact does not hold (for variables with
  a single fact),
- `<none of those>`: none of the variable's facts holds.

`_map_variables` parses these names and maps the PDDL names back to UP fluents
and objects with `PDDLWriter.get_item_named`. The result is one `SASVariable`
per translated variable, holding the fluent expression of each `Atom` value
and a default value for the case where none of them holds.

For each call to `value`, `_sas_values` evaluates the atoms of each variable
with `state.get_value` and takes the value of the first atom that holds, or the
default value. This uses only `State.get_value`, as the Heuristic operation
mode requires, so the state can come from any sequential simulator.

Derived variables, which the translator introduces for axioms, have no atoms.
Their value is ignored and eval_server recomputes it from the axioms.

### Which states are meaningful

The translated task does not contain the facts that the translator dropped,
so their values in the UP state are ignored. For states that are reachable
from the initial state of the problem this loses nothing. For other states,
e.g. a state that violates a mutex or makes an unreachable fact true, the
value is computed on a projection of the state and carries no guarantee.
States are not validated, which is consistent with `HeuristicMixin`, whose
`value` does not validate its input either.

### Trivial tasks

When the translator proves the task unsolvable, or proves that the goal holds
in every reachable state, it returns a task with a single `dummy` variable and
no operators. The engine detects this case, starts no process, and returns
`None` or `0` for every state.

## The eval_server plugin

### Protocol

The protocol is line-based on the process's stdin and stdout:

| direction | message | meaning |
|---|---|---|
| out | `@ready` | the evaluator has been constructed |
| in | `3 0 1 2 ...` | a state, as the values of all variables |
| out | `@12` | the heuristic value of that state |
| out | `@inf` | the heuristic detected a dead end |

The process exits when its stdin is closed. Fast Downward writes its log to
stdout as well, and stderr is redirected to stdout, so the reply lines carry
the `@` prefix and every other line is log output. The engine keeps the last
20 log lines and includes them in the `UPException` it raises if the process
exits unexpectedly. Errors therefore reach the user with Fast Downward's own
message, e.g. when a heuristic needs an LP solver that the build does not
include.

Before it prints `@ready`, eval_server checks that the evaluator is not
path-dependent (see [Excluded heuristics](#excluded-heuristics)).

### Evaluating a state that was not reached by search

Fast Downward's heuristics expect states that were created by its own search.
eval_server has to deal with two differences.

**Registered states.** Heuristics cache their values per state in
`PerStateInformation`, which only accepts states registered in a
`StateRegistry` and aborts on other states. The registry has no way to
register arbitrary values. eval_server creates a fresh registry for every
query, takes the ID of its initial state, and attaches the queried values as
unpacked data with `StateRegistry::lookup_state(id, values)`. Heuristics read
the unpacked values, so they evaluate the queried state. A fresh registry also
means that no cached value from an earlier query can be returned.

**Derived variables.** The search computes derived variables when it creates a
state. eval_server calls the task's `AxiomEvaluator` on the received values
instead.

**g values.** The cost of the path to a queried state is unknown. eval_server
evaluates every state with g = 0, so evaluators that read g (e.g. `g()` in the
generic engine) treat the queried state as the initial state.

## Engines

### The generic engine and the named engines

`HeuristicMixin.guarantees` is a static method, so an engine's guarantees
cannot depend on its constructor parameters. This leads to two kinds of
engines.

- `fast-downward-heuristic` (`FastDownwardHeuristic`) accepts any Fast Downward
  evaluator in its `fast_downward_heuristic` parameter, e.g.
  `"max([hmax(), lmcut()])"`. It claims no guarantees, because they depend on
  the evaluator and its options.
- The named engines, e.g. `fast-downward-lmcut`, fix the evaluator and state
  its guarantees. Each is a small subclass of `_NamedHeuristic` that sets the
  class attributes `evaluator`, `engine_name`, `heuristic_guarantees`,
  `supports_axioms` and `supports_conditional_effects`.

The named engines use the default options of each heuristic, in particular
`cost_type=normal`, so that their values are measured in the problem's action
costs and their guarantees hold with respect to the UP metric. The generic
engine passes its string to Fast Downward unchanged; with an option such as
`cost_type=one`, its values are measured in plan length instead.

### Guarantees

The guarantees are taken from the properties that Fast Downward 26.6 documents
for each heuristic (`document_property` in the sources, shown in Fast
Downward's documentation):

| engine | admissible | consistent | safe | conditional effects | axioms |
|---|---|---|---|---|---|
| `blind` | yes | yes | yes | supported | supported |
| `goalcount` | no | no | yes | supported | supported |
| `hmax` | without axioms | without axioms | yes | supported | rejected |
| `add`, `ff` | no | no | yes | supported | supported |
| `cg`, `cea` | no | no | no | supported | supported |
| `lmcut` | yes | no | yes | rejected | rejected |
| `hm` | without CE or axioms | without CE or axioms | without CE or axioms | rejected | rejected |
| `ipdb`, `cpdbs`, `zopdbs` | yes | yes | yes | rejected | rejected |
| `cegar` | yes | yes | yes | rejected | rejected |
| `merge_and_shrink` | yes | yes | yes | supported | rejected |

Fast Downward does not document goal-awareness. All named engines claim
`GOAL_AWARE` for the following reasons:

- Fast Downward asserts that every heuristic value that is not a dead end is
  non-negative (`heuristic.cc`). An admissible heuristic satisfies
  `h(s) <= h*(s) = 0` on goal states, so its value there is 0.
- `goalcount`, `add`, `ff`, `cg` and `cea` return 0 on goal states by
  construction (for `cg`, see `cg_heuristic.cc`).

Some properties hold only for tasks without axioms or conditional effects
(`hmax`, `hm`). Since the guarantees are static, these engines reject such
tasks, which makes their guarantees hold whenever they return a value at all.

The merge-and-shrink guarantees hold for reachable states only, because the
heuristic prunes unreachable abstract states. This is the same restriction as
in [Which states are meaningful](#which-states-are-meaningful).

### Supported problems

All engines accept the problem kinds of the `fast-downward` planner: classical
problems with typing, negative, disjunctive, existential and universal
conditions, equalities, conditional effects, and plan length or integer action
costs as the metric.

Whether a heuristic can handle a problem depends on the translated task, and
the problem kind does not predict it exactly. For example, a disjunctive goal
makes the translator introduce axioms, while a disjunctive precondition is
split into several operators. The support is therefore checked at two levels.

1. For the engines that do not support conditional effects, `supported_kind`
   drops `CONDITIONAL_EFFECTS` and the kinds that can be written as
   conditional effects (`FORALL_EFFECTS` and fluents in boolean assignments,
   which `PDDLWriter` rewrites into `when` effects), as `fast-downward-opt`
   does. The factory then never selects such an engine for these problems.
   The condition kinds are kept, since only some of them yield axioms.
2. After translation, `_check_supported` raises
   `UPUnsupportedProblemTypeError` if the task has axioms or conditional
   effects that the engine does not support.

### Excluded heuristics

**Landmark heuristics** (`landmark_sum`, `landmark_cost_partitioning`) are
path-dependent: Fast Downward updates which landmarks have been reached along
the path to a state, and the value of a state depends on that path. A single
`value(state)` call carries no path. Evaluating each state as if it were the
initial state would use landmarks of the original initial state, which need
not be landmarks of the evaluated state. That would break admissibility and
could report false dead ends. eval_server rejects every evaluator that reports
a path-dependent component, so these heuristics are not reachable through the
generic engine either. Supporting them would require the Heuristic operation
mode to pass transitions to the engine, which is a change to UP.

**LP-based heuristics** (`operatorcounting`, the potential heuristics) need
CPLEX or SoPlex. Fast Downward only links them when one is found at build
time, and the released wheels are built without either. They have no named
engine, but the generic engine can use them with a build that includes an LP
solver.

## Registration in UP

The engines are registered on the UP side, in a companion change to UP that
follows the release of up_fast_downward 1.1.0. Until then, they can be
registered with `get_environment().factory.add_engine(name, module, class)`.
UP's `DEFAULT_ENGINES` refers to them by dotted module path, e.g.
`("up_fast_downward.fast_downward_heuristic", "FastDownwardLMCutHeuristic")`.
`up_fast_downward/__init__.py` does not import the module, so a UP version
without `HeuristicMixin` can still import up_fast_downward for the planners
and grounders.

In UP's preference list, `fast-downward-ff` comes before `up_goal_counting`,
so `Heuristic(problem)` returns the FF heuristic when up_fast_downward is
installed. FF supports conditional effects and axioms, so the check after
translation never fails for it. All other Fast Downward engines come after
`up_goal_counting` and are selected only by name. If an engine fails, the
error is raised and no other engine is tried.

## Lifecycle, errors and concurrency

- The constructor translates the task, starts the process and waits for
  `@ready`. All precomputation and all configuration errors happen there.
- `destroy` (called when leaving a `with` block) closes stdin, waits one
  second for the process to exit, and kills it otherwise. If the Python
  process dies, the pipe closes and eval_server exits on its own.
- If the process exits during `value`, the engine raises `UPException` with
  the last log lines and does not restart it. Later calls raise the same
  error.
- If a request is interrupted (e.g. by `KeyboardInterrupt`), the engine kills
  the process, since its reply would otherwise be read as the value of the
  next state. Later calls raise `UPException`.
- If the process does not reply `@ready`, the constructor kills it and raises
  `UPException`.
- There is no time limit. The named CEGAR and merge-and-shrink engines bound
  their precomputation by the number of abstract states. A time limit can be
  set through the generic engine, e.g. with `main_loop_max_time` for
  merge-and-shrink.
- An engine handles one request at a time and is not thread-safe. A parallel
  search should create one engine per worker.

## Performance

The cost of `value` is dominated by the state mapping, which calls
`state.get_value` once per translated fact. On the IPC 2023 learning track
task blocksworld/testing/medium/p03 (85 variables, 1849 facts), `value` with
`fast-downward-ff` takes about 1.3 ms. The test file contains a benchmark that
reproduces this measurement:

```
python misc/tests/test-heuristic.py DOMAIN.pddl PROBLEM.pddl
```

If the mapping dominates a search, `_sas_values` could read the values of
UP's own `UPState` directly instead of calling `get_value` per fact, at the
cost of depending on a private UP class.

## Testing

`misc/tests/test-heuristic.py` checks:

- every guarantee that a named engine claims, on the states along an optimal
  plan found by `fast-downward-opt`, for several small problems. The checks
  are selected by calling `guarantees()`, so the table in the code and the
  tests cannot diverge;
- dead-end detection;
- the generic engine;
- the error paths: conditional effects, axioms, path-dependent evaluators and
  trivially unsolvable tasks.

The tests skip themselves if the installed UP has no `HeuristicMixin`.

## Adding a named heuristic

1. Check the heuristic's `document_property` and `document_language_support`
   calls in the Fast Downward sources of the pinned release.
2. Add a subclass of `_NamedHeuristic` with the evaluator string, the engine
   name, the guarantees, and `supports_axioms` and
   `supports_conditional_effects`. Set a flag to `False` if the heuristic does
   not support the feature, or if a guarantee only holds without it.
3. Add the class to `NAMED_HEURISTICS`. The guarantee tests then cover it.
4. Register the engine name in UP's `DEFAULT_ENGINES` and preference list.
5. Add a row to the table in the README.
