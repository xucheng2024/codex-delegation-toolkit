---
name: keep-plot
description: Save what still matters in this thread, then compact without losing the plot. Use when the user invokes $keep-plot, a phase just finished and the next task changed, or the user asked to compact this chat. Do not use for $codex-speeder repo retrieval, $agent-context-budget child handoffs, model routing, ordinary short work, failing tests, uncertain root cause, a half-finished refactor, or files just inspected that are about to be edited. Do not auto-trigger on token percent, elapsed time, or turn count.
---

# Keep Plot

Compact at semantic boundaries, not token boundaries. Token use is an auxiliary signal.

This skill does not call `/compact`, measure tokens, or remove system, tool, or hidden runtime context. Write the checkpoint in this thread, ask the user to compact via the host, then self-check.

After actually running this skill, emit one non-blocking English cue. Do not ask the user to acknowledge it:

`↳ Keep Plot: <action>; <reason>; next: <next_step>`

`action` is `compact`, `skip`, `veto`, or `restore`. Keep `reason` short and factual. Do not put token, billing, time, or quality scores in the cue.

When the recorder is available, append the same outcome. If the script is missing, keep the cue and skip recording:

```bash
python "$CODEX_HOME/skills/keep-plot/scripts/record_outcome.py" record \
  --action <compact|skip|veto|restore> --reason "<short>" --post-check <pass|fail|na>
```

If the user asks whether this skill is working, run `record_outcome.py stats`. Do not edit this skill from stats. A rising `restore` count means the last checkpoint dropped state.

Do not rescan the repository. Use current conversation evidence and existing `$codex-speeder` evidence IDs. Read [references/percent-bands.md](references/percent-bands.md) only for optional percent heuristics.

## Decide

Score qualitatively. Each signal is Low, Medium, or High.

- Pressure: file reads, searches, test output, diffs, and review cycles already in this thread.
- Obsolete ratio: how much of that history cannot change the next action.
- Task-boundary: whether the current phase is actually closed.

Compact only when obsolete ratio and task-boundary are High and pressure is at least Medium.

- Low pressure, any obsolete/boundary: skip.
- High pressure, Low obsolete, Low boundary: skip. Still implementing.
- High pressure, Medium obsolete, Low boundary: forbid. Debug is open.
- Medium or High pressure, High obsolete, High boundary: compact after the checkpoint.

Good compact points: implementation complete with targeted tests passing; user accepted or abandoned a decision; review complete; next work is unrelated. Bad compact points: failing tests, uncertain root cause, mid-refactor, or unresolved design alternatives.

Veto compact when any of these hold: tests still failing; root cause uncertain; refactor half-done; about to edit files just inspected; unresolved design alternatives; ordinary short work.

## Checkpoint

Emit this block before compacting. Omit inapplicable fields. Keep rejected approaches as one-line verdicts, not research dumps.

```text
CURRENT OBJECTIVE
- What we are trying to achieve

DECISIONS
- Accepted architecture decisions
- Rejected approaches and why

SAFETY INVARIANTS
- Things that must not be changed

REPO STATE
- Files modified
- Important untouched files
- Current branch/worktree assumptions

VALIDATION
- Tests run
- Passing/failing
- Known regressions

OPEN ISSUES
- Remaining TODO
- Hypotheses not yet proven

NEXT STEP
- Exact next action
```

Then ask the user to run the host compact command (`/compact` in Codex, or the equivalent). Do not claim this skill compacted anything.

Do not invoke `$agent-context-budget` or `$codex-speeder` from this skill.

## After compact

Answer all five before doing more work:

1. What is the current objective?
2. What must not change?
3. What files were changed?
4. What tests passed or failed?
5. What is the next step?

If every answer is present, record `--post-check pass`. If any answer is missing, cue `restore`, reread the checkpoint or the named files, and record `--post-check fail`. Do not continue blind.
