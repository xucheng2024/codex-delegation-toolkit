---
name: agent-context-budget
description: Prepare compact, evidence-backed context for a child agent or model after delegation has already been chosen. Use for multi-agent handoffs, specialist planning or review, and large tool, search, test, or log results. Do not use for ordinary single-agent work or to decide whether or which model to delegate to.
---

# Agent Context Budget

Budget only the context deliberately supplied in a handoff. Do not claim to remove system instructions, tool metadata, hidden runtime context, or history already inherited by the recipient.

## Choose history scope

- Use `fork_turns: "none"` for executors, economy top-level threads, and independent reviewers by default.
- For planners or adjudicators, preserve the user's material wording and use the smallest bounded recent history that affects the decision.
- Use full history only when compaction would create material ambiguity and privacy permits sharing it.
- Follow the active routing policy. Do not select the agent, model, or delegation strategy here.

## Send one complete capsule

Use these labels exactly and in this order. Include a field only when it changes the recipient's allowed action. Omit inapplicable fields; do not fill them with `None — <reason>`. Kind already implies `History scope: none` for execute, review, and economy threads.

```text
History scope: none | bounded (<reason>) | full (<reason>)
Budget tier: Routine | Expanded — <reason>
User request (verbatim):
Objective:
Deliverable:
Scope: owned files, symbols, systems, read/write authority, and non-goals
Anchors: accessible locators plus retrieval actions
Evidence: Observed / Inference / Decision, with source and freshness
Parent hypothesis: None | explicitly non-binding hypothesis to challenge
Constraints/Risks:
Acceptance:
Retrieve/Escalate: first retrieval action, escalation triggers, and delta limit
```

For plan, execute, and economy packets, Objective, Scope, Constraints/Risks, Acceptance, and Retrieve/Escalate must be concrete. Include Anchors and Evidence when they exist. Include User request (verbatim) when the wording affects the decision.

Use `Routine` for bounded, reversible, single-component work; target at most roughly 800 capsule tokens and eight anchors. Use `Expanded` for public interfaces, security, privacy, financial, persistence, concurrency, compatibility, destructive actions, or material ambiguity; target roughly 1,500 capsule tokens and twelve anchors. These are soft handoff defaults, not hard correctness limits or claims about total recipient context.

## Pass evidence instead of bulk context

- Label claims as `Observed`, `Inference`, or `Decision`.
- Make every anchor retrievable: path and symbol, bounded command, artifact ID, or URL with freshness information.
- Pass commands, artifact paths, exit status, relevant time window, and a short summary instead of raw output.
- Mark truncation, stale snapshots, omissions, and uncertain coverage.
- Keep a parent preference only in `Parent hypothesis`, label it non-binding, and ask a planner to challenge it independently.
- When `$codex-speeder` is available, pass its evidence IDs and exact `expand` or `read-source` command. Otherwise use bounded paths, symbols, searches, and commands.
- For an independent reviewer, do not forward the planner or executor capsule. Send only Scope, Constraints/Risks, Acceptance, and Anchors (diff locator). Include deterministic results when present. Omit every other field. Do not include implementation narrative, planner reasoning, or a parent hypothesis. If the diff text is already in the packet, do not invoke `$codex-speeder` or other skills.

Never include credentials, tokens, private keys, session data, cookies, secret-bearing environment values, unrelated conversation, customer data, or unnecessary personal information.

## Escalate by delta

Require the recipient to retrieve accessible evidence before requesting more. Add a focused delta only when an anchor is inaccessible, a named ambiguity could change the result, evidence is stale or truncated, or direct proof is needed for elevated risk.

Allow at most two focused delta rounds by default. Each delta must name the blocker, smallest missing fact, and expected effect. Keep the original packet message and append the delta; do not rewrite the first packet. After two unresolved deltas, report the gap and let the parent rescope or explicitly expand the budget.

## Validate the handoff

Before sending, verify required live fields for the kind are present and concrete, omitted fields are truly inapplicable, user wording is bounded and preserved when included, scope and authority are explicit, observed claims have fresh locators, hypotheses remain non-binding, acceptance is testable, and privacy is protected.

Ask the recipient to report its outcome, evidence consulted, validation performed, and unresolved gaps. Keep final integration and deterministic validation with the parent. For an economy top-level thread, treat Objective, Scope, Constraints/Risks, Acceptance, and Retrieve/Escalate as a stop-or-guess contract: name the finished state, in-scope files, forbidden changes, proof of completion, and the missing decision that must halt work. Do not fill those fields with `None —` unless genuinely inapplicable; a missing required field means the contract is incomplete.
