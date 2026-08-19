---
name: cost-aware-routing
description: Route ambiguous, cross-cutting, or high-risk software work between the parent agent and specialist agents while controlling model cost and review overhead. Use for tasks involving security, money, persistence, concurrency, public interfaces, unclear scope, multiple subsystems, or explicit requests to decide whether or which model or subagent to use. Do not use for trivial, already-bounded edits or for packaging a handoff after routing is already decided.
---

# Cost-Aware Routing

Keep the parent agent responsible for coordination, decision, deterministic validation, and final delivery. Route each step by what that step must do, not by which model the parent thread happens to be. Delegate only when specialist judgment or genuinely parallel independent work improves the outcome.

Read `references/model-role-map.json` for default role ids. Use an operator catalog with `scripts/resolve_model_roles.py --catalog <path>` only when that catalog includes live availability. Catalog format is in `references/model-routing.md`.

## Classify the task

Treat any of these as a hard trigger for a deeper planning or review pass:

- security, authorization, secrets, or destructive operations;
- billing, accounting, financial loss, or irreversible external actions;
- concurrency, persistence, schema migration, recovery, or production incidents;
- public interfaces, protocols, or backward compatibility.

Treat these as soft triggers:

- unclear requirements or success criteria;
- unknown implementation location;
- more than two plausible affected subsystems;
- uncertain dependency impact;
- multiple materially different designs.

Stay on the parent when there is no hard trigger and fewer than two soft triggers. Use one deeper planner when any hard trigger or at least two soft triggers apply. Staying on the parent assigns ownership of the decision and delivery, not who writes the code.

## Control delegation overhead

- Do not delegate ordinary implementation, restatement, sequential work, or routine self-review to an equivalent generalist.
- Permit same-role agents only for independent parallel slices with disjoint ownership, or for an independent high-risk read-only review.
- Use at most one `quality_first` specialist pass per task unless the user pinned Sol for all work. Prefer a planner over a reviewer when only one Sol pass is justified.
- Use deterministic tests and linters as the primary verifier; do not replace executable validation with more model rounds.
- Use at most one planning pass and, when risk justifies it, one independent review pass followed by one targeted fix pass.

## Spawn contract

An explicit user Sol pin applies to all task work unless the user explicitly permits delegation to Terra. A runtime default, family alias, or leftover parent model is not a pin.

Durable roles:

- `quality_first`: architecture tradeoff, security/compatibility risk, or one independent review
- `balanced`: implementation, debugging, and test loops
- `economy`: bounded intake, classification, and high-volume low-risk work

Default spawn ids when no operator catalog is present:

```text
quality_first spawn_agent:
  model: gpt-5.6-sol
  model_reasoning_effort: medium
  fork_turns: none

balanced spawn_agent:
  model: gpt-5.6-terra
  model_reasoning_effort: medium
  fork_turns: none
```

Never omit `model` on `spawn_agent`. Never inherit the parent model or `default_subagent_model`.

Execution after the pin check:

- No Sol pin, parent is Terra: implement on the parent.
- No Sol pin, parent is Sol: parent coordinates only; spawn a Terra executor. Do not let an unpinned Sol parent run the long coding loop.
- Sol pin without Terra-delegation permission: all slices stay on Sol, including implementation.

Before every spawn, confirm the target id is available in current runtime or account metadata. If an operator catalog marks that id `available: false`, treat it as unavailable. If the target is unavailable: disclose the gap; ask once, or apply an explicit named degrade the user can see. Do not silently substitute another model.

Do not fail closed to the parent for the entire task merely because a catalog file is missing. Missing catalog still uses this Terra/Sol map, then the runtime availability check.

Honor a stated cost ceiling unless the user says the named choice may exceed it. Treat catalog cost tiers as operator-provided classifications, not live price claims. Do not scrape pricing.

## Prepare every handoff

After deciding to delegate, invoke `$agent-context-budget`. Do not invoke it when the task remains on the parent. Use no-history handoffs for executors and reviewers by default; preserve only bounded recent dialogue when exact user wording affects a planner's decision.

If `$codex-speeder` applies, pass its evidence ID, repository snapshot, relevant sections, and retrieval commands rather than copying source or logs. If the target is not a supported Git repository, use bounded paths, symbols, and exact retrieval commands instead.

Never include credentials, private keys, tokens, cookies, unrelated personal data, or raw secret-bearing logs in a handoff.

## Route the work

1. State the selected specialist role, spawn `model`, and concrete routing reason before delegation.
2. For a justified planner, independently restate the problem, compare materially different designs, select one, and return an implementation contract with risks, acceptance criteria, and focused validation. Do not seed it with an unlabeled preferred answer.
3. Implement per the spawn contract. If a material architectural or safety deviation becomes necessary, send only that delta for adjudication.
4. Request a read-only independent Sol review only for hard-trigger, cross-subsystem, or public-interface changes, and only when a Sol pass has not already been used unless the user pinned Sol.
5. Fix concrete issues once and run final targeted validation. Stop open-ended review loops.

In the final response, list models that actually participated and deterministic validation performed.
