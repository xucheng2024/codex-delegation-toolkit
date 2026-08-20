# Compact Handoffs

Use this reference only when composing an agent-to-agent handoff or specialist output. Optimize for decision equivalence, not shortest prose: retain a field if omitting it could change the receiver's allowed action, hide an unverified assumption, or prevent focused validation.

## Targets and overflow

- `APPROVE` review: target 200 tokens.
- `CHANGES_REQUIRED` review: target 600; soft ceiling 1,200.
- Planning or architecture contract: target 1,200; soft ceiling 2,000.

These are targets, never truncation rules. Include all necessary material beyond a soft ceiling and set `OVERFLOW_REASON`. If a complete safe handoff is impossible, return `STATUS: INCOMPLETE`; the receiver must stop rather than infer the omission.

## Compression rules

1. Share references, not duplicated context: cite a stable path, symbol, diff hunk, evidence ID, command, or artifact hash instead of unchanged source, logs, or history.
2. Review the delta only: use the contract, changed-file list, diff, deterministic results, and focused impact references—not the full repository or implementation conversation.
3. In later rounds, keep the original packet and append only conclusions added, changed, or invalidated, with anchors for retained facts. Do not rewrite the first packet.
4. Use progressive disclosure: include the decision, required action, and accessible anchors. If the receiver cannot retrieve an anchor, include the necessary detail or return `INCOMPLETE`.
5. Rank presentation by `impact × uncertainty × actionability`; this is an ordering heuristic, not a calibrated value or a reason to omit a material lower-ranked issue.

The canonical status and review fields are in `SKILL.md`. Emit `FINDINGS: none` for approval. List every material finding; prioritize rather than silently dropping any. Do not narrate the diff or restate the plan.
