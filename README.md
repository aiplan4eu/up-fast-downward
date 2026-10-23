# Integration of Fast Downward with the Unified Planning Library

![Fast Downward Logo](https://github.com/aibasel/downward/blob/main/misc/images/fast-downward.svg "Fast Downward Logo")

The aim of this project is to make the [Fast
Downward](https://www.fast-downward.org/) planning engine available in the
[unified_planning library](https://github.com/aiplan4eu/unified-planning) by
the [AIPlan4EU project](https://www.aiplan4eu-project.eu/). Fast Downward is
one of the most successful planning systems for classical planning (full
information, non-numeric, deterministic instantaneous actions).

## Installation

We recommend the installation from PyPi because it has pre-built wheels for all common operating systems.

### Installation from Python Package Index PyPi

To automatically get a version that works with your version of the unified planning framework, you can list it as a solver in the pip installation of ```unified_planning```:

```
pip install unified-planning[fast-downward]
```

If you need several solvers, you can list them all within the brackets.

You can also install the Fast Downward integration separately (in case the current version of unified_planning does not include Fast Downward or you want to add it later to your unified planning installation). With

```
pip install up-fast-downward
```

you get the latest version. If you need an older version, you can install it with:

```
pip install up-fast-downward==<version number>
```

### Manual installation

The manual installation will obtain the Fast Downward sources and build them from scratch. This will take some time and you have to install the necessary dependencies in advance.

1. Install the dependencies as described at the [Fast Downward website](https://www.fast-downward.org/ObtainingAndRunningFastDownward).
1. Obtain the integration code from [Github](https://github.com/aiplan4eu/up-fast-downward).
1. Install with ```pip install up-fast-downward/``` (calling pip install on the directory with the code).

## Usage

### Solving a planning problem

The integration adds Fast Downward with two solver engines in the unified planning framework:

- ```fast-downward``` currently runs Fast Downward in the ```lama-first``` configuration. It does not provide a guarantee on the plan quality but usually find plans quickly (depending on the task).
- ```fast-downward-opt``` guarantees optimal plan quality but the solving process can take some time. It does not support some features of classical planning, e.g. conditional effects.

You can for example call it as follows:

```
from unified_planning.shortcuts import *
from unified_planning.engines import PlanGenerationResultStatus

problem = Problem('myproblem')
# specify the problem (e.g. fluents, initial state, actions, goal)
...

planner = OneshotPlanner(name="fast-downward")
result = planner.solve(problem)
if result.status == PlanGenerationResultStatus.SOLVED_SATISFICING:
    print(f'{Found a plan.\nThe plan is: {result.plan}')
else:
    print("No plan found.")
```

### Grounding a planning problem

The integration adds two grounding compilers based on Fast Downward to the unified planning framework:
- ```fast-downward-reachability-grounder``` uses the reachability analysis of Fast Downward to determine the action parameters that need to be instantiated and does not further transform the actions.
- ```fast-downward-grounder``` grounds a task applying all normalizing transformations also done by the Fast Downward planning system.

Details on the reachability analysis and the normalization can be found in Malte Helmert. [Concise finite-domain representations for PDDL planning tasks](https://ai.dmi.unibas.ch/papers/helmert-aij2009.pdf). Artificial Intelligence 173 (5-6), pp. 503-535. 2009).
  
**Note**: Both grounding methods depend on the initial state and do not create some actions that are not reachable from this state. Use the grounded problem only with states of which you know that they are reachable from your original initial state.

**Note**: Do not ground the problem if you subsequently want to use it with a Fast Downward solver. Otherwise it will only repeat some work and some internal processing of Fast Downward (i.e. the invariant synthesis) will be slower than with the ungrounded problem.

### Evaluating heuristics

The integration adds the heuristics of Fast Downward as engines of the Heuristic operation mode. Each engine translates the problem once and keeps a Fast Downward process that evaluates the states passed to `value`:

```
from unified_planning.shortcuts import *

with SequentialSimulator(problem) as simulator, Heuristic(problem, name="fast-downward-lmcut") as h:
    print(h.value(simulator.get_initial_state()))  # None if a dead end is detected
```

| engine | Fast Downward evaluator | guarantees | conditional effects | axioms |
|---|---|---|---|---|
| `fast-downward-blind` | `blind()` | admissible, consistent, goal-aware, safe | yes | yes |
| `fast-downward-goalcount` | `goalcount()` | goal-aware, safe | yes | yes |
| `fast-downward-hmax` | `hmax()` | admissible, consistent, goal-aware, safe | yes | no |
| `fast-downward-add` | `add()` | goal-aware, safe | yes | yes |
| `fast-downward-ff` | `ff()` | goal-aware, safe | yes | yes |
| `fast-downward-cg` | `cg()` | goal-aware | yes | yes |
| `fast-downward-cea` | `cea()` | goal-aware | yes | yes |
| `fast-downward-lmcut` | `lmcut()` | admissible, goal-aware, safe | no | no |
| `fast-downward-hm` | `hm(m=2)` | admissible, consistent, goal-aware, safe | no | no |
| `fast-downward-ipdb` | `ipdb()` | admissible, consistent, goal-aware, safe | no | no |
| `fast-downward-cpdbs` | `cpdbs()` | admissible, consistent, goal-aware, safe | no | no |
| `fast-downward-zopdbs` | `zopdbs()` | admissible, consistent, goal-aware, safe | no | no |
| `fast-downward-cegar` | `cegar()` | admissible, consistent, goal-aware, safe | no | no |
| `fast-downward-merge_and_shrink` | bisimulation, SCC-DFP, `max_states=50k` | admissible, consistent, goal-aware, safe | yes | no |
| `fast-downward-heuristic` | any, via the `fast_downward_heuristic` parameter | none | yes | yes |

The guarantees are those documented by Fast Downward 26.6. Fast Downward introduces axioms for some problems, e.g. with universally quantified conditions or non-conjunctive goals; the engines that do not support them raise `UPUnsupportedProblemTypeError` for such problems. Values are measured in the action costs of the problem's metric, or in plan length if it has none.

`fast-downward-heuristic` accepts any Fast Downward evaluator, e.g. `Heuristic(problem, name="fast-downward-heuristic", params={"fast_downward_heuristic": "max([hmax(), lmcut()])"})`. Heuristics that need an LP solver (`operatorcounting`, the potential heuristics) only work if Fast Downward was built with one, which the released wheels are not.

**Note**: The values are computed on the task produced by the Fast Downward translator, which drops facts that are unreachable from the initial state. They are only meaningful for states that are reachable from the initial state of the problem.

**Note**: The landmark heuristics (`landmark_sum`, `landmark_cost_partitioning`) depend on the path to a state, not only on the state, and are therefore rejected.


## Current state of the system
- Fast Downward version: 26.6
    - since up-fast-downward 1.0.0: 26.6
    - since up-fast-downward 0.5.2: 24.06.1+ (ba6ffb79757da3590f8d9e844a5e940a3e94601e)
    - since up-fast-downward 0.5.0: 24.06
    - up-fast-downward 0.3.x, 0.4.x: 23.06
- Default configuration
    - ```fast-downward``` engine: lama-first for One-Shot planning, seq-sat-lama-2011 for Anytime planning
    - ```fast-downward-opt``` engine: A* search with LMCut heuristic
- Planning approaches of UP supported: Classical planning
- Operative modes of UP currently supported: One-shot planning, Anytime planning, Grounding, Heuristic
