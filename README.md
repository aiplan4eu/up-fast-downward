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


## Current state of the system and ongoing development

- Default configuration
    - ```fast-downward``` engine: lama-first (flexible configuration under development)
    - ```fast-downward-opt``` engine: A* search with LMCut heuristic
- Planning approaches of UP supported: Classical planning
- Operative modes of UP currently supported: One-shot planning, Grounding
- Operative modes of UP under development: Anytime planning
