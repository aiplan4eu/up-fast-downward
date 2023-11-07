# Release notes
UP Fast Downward 0.3.3
- fix bug in fast-downward-reachability grounder
- silence output in grounders

UP Fast Downward 0.3.2
- support UP problem kind version 2

UP Fast Downward 0.3.1
- fix windows wheel

UP Fast Downward 0.3.0
- use Fast Downward 23.06

UP Fast Downward 0.2.3
- follow changes in up:
  added support to native forall over effects

UP Fast Downward 0.2.2
- exploit better support for anytime planners in the up: this is not
  a functional change but most of the necessary functionality is now provided
  by the up library, so we du not have to duplicate it in the engine
  integration.

UP Fast Downward 0.2.1
- follow changes in up:
  add and rename fluents in problem kind; This enables the Fast Downward
  integration to use the values of static numeric fluents for action costs.
- add MinimizeActionsCost metric to both grounders

UP Fast Downward 0.2.0
- FastDownwardPDDLPlanner:
  - support anytime operation mode
  - support specification of aliases and search configurations to be used by
    Fast Downward
  - support specification of translator options to be used by Fast Downward
  - support specification of search time limit for Fast Downward (necessary
    for usage of portfolios)
  - support setting the log level used by Fast Downward
- FastDownwardOptimalPDDLPlanner:
  - support setting the log level used by Fast Downward
- FastDownwardGrounder:
  - follow changes made in UP
- credits: mention people behind the heuristics we use in the default
  configurations
- use latest Fast Downward version
- common base class for satisficing and optimal solver engines
- code quality improvements: typing information and style fixes
- added jupyter notebook with examples

UP Fast Downward 0.1.2
- follow change in up:
  rename problem.env into problem.environment

UP Fast Downward 0.1.1
- fix broken setup.py

UP Fast Downward 0.1.0
- add grounders

UP Fast Downward 0.0.7
- use Fast Downward 22.12

UP Fast Downward 0.0.6
- support new plan result semantics of unified planning library

UP Fast Downward 0.0.5
- declare support for hierachical typing
- build wheels for Mac and Windows with cibuildwheel

UP Fast Downward 0.0.4
- consider return value of planner in result status
- use newer Fast Downward version to avoid patching
