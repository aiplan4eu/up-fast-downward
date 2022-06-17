# Integration of Fast Downward with the Unified Planning Library

![Fast Downard Logo](https://github.com/aibasel/downward/blob/main/misc/images/fast-downward.svg "Fast Downward Logo")

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

You can also install the Fast Downward integration separately (in case, the current version of unified_planning does not include Fast Downward or you want to add it later to your unified planning installation). With

```
pip install up-fast-downward
```

you get the latest version. If you need an older version, you can install it with:

```
pip install up-fast-downward==<version number>
```

### Manual installation

With the manual installation, the installation will obtain the Fast Downward sources and build them from scratch. This will take some time and you have to install the necessary dependencies in advance.

1. Install the dependencies as descibed at the [Fast Downward website](https://www.fast-downward.org/ObtainingAndRunningFastDownward).
    For Windows, you also need to add patch (```pip install patch```).
1. Obtain the integration code from [Github](https://github.com/aiplan4eu/up-fast-downward).
1. Install with ```pip install up-fast-downward/``` (calling pip install on the directory with the code).

## Usage

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

## Current state of the system and ongoing development

- Default configuration
    - ```fast-downward``` engine: lama-first (flexible configuration under development)
    - ```fast-downward-opt``` engine: A* search with LMCut heuristic
- Planning approaches of UP supported: Classical planning
- Operative modes of UP currently supported: One-shot planning
- Operative modes of UP under development: Anytime planning
