# Project learning workflow

Before continuing a lesson, implementation, or verification task, read
`docs/learning-plan.md`. It is the source of truth for the learning roadmap,
current checkpoint, completion criteria, evidence, and deferred topics.

- Follow the current checkpoint when the user says to continue.
- Teaching defaults to learner execution: explain the goal and tradeoffs, give one
  bounded set of instructions, let the user edit/run/observe, then review the result.
- A bare "continue" advances the lesson, not permission to implement, operate services,
  run checks, or commit/push on the user's behalf. Do those when explicitly requested.
- Read-only inspection and explicitly requested learning-record updates may support
  teaching. Do not require approval for each ordinary explanatory step.
- Teach in Chinese; skip generic basics already covered.
- Advance one bounded step. Do not turn optional performance research into a prerequisite.
- Use only the minimum verification needed for the current acceptance criteria.
- Distinguish explained, implemented, configured, and actually verified behavior.
- After completing a step, update the checkpoint, evidence, unverified limits,
  and commit/push status in the plan before proposing the next roadmap item.
- Record tangents in the deferred list; do not pursue them without user direction
  unless they block the current step.
- Preserve user edits, private credentials, and running services. Explain service
  interruption before applying a change that requires it.
- User instructions override this workflow. Do not add recurring approval gates.
