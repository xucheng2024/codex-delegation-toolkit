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

Stay on the parent when there is no hard trigger and fewer than two soft triggers. Use one deeper planner when any hard trigger or at least two soft triggers apply. If the parent is already the `quality_first` model, plan on the parent; do not spawn a second planner. Independent review still uses a fresh `quality_first` instance. Staying on the parent assigns ownership of the decision and delivery, not who writes the code.

## Control delegation overhead

- Do not delegate ordinary implementation, restatement, sequential work, or routine self-review to an equivalent generalist.
- Do not send the `economy` model through `spawn_agent`. Codex native subagent routing does not treat it as a first-class worker; start a separate top-level thread instead.
- Permit same-role agents only for independent parallel slices with disjoint ownership, or for an independent high-risk read-only review.
- Use at most one `quality_first` planner pass per task unless the user pinned Sol for all work. Prefer a planner over a reviewer when only one Sol pass is justified.
- After an economy implement of hard-trigger, cross-subsystem, or public-interface work, request one fresh read-only `quality_first` review of the diff even if a planner pass already ran. Do not add that extra review after a Terra implement when a planner pass already ran, unless the user pinned Sol.
- Use deterministic tests and linters as the primary verifier; do not replace executable validation with more model rounds.
- Use at most one planning pass and, when the review rule above applies, one independent review pass followed by one targeted fix pass.

## Spawn contract

An explicit user Sol pin applies to all task work unless the user explicitly permits delegation to Terra. A runtime default, family alias, or leftover parent model is not a pin.

Durable roles:

- `quality_first`: architecture tradeoff, security/compatibility risk, or one independent review
- `balanced`: implementation, debugging, and test loops
- `economy`: bounded, fully specified implementation, intake, classification, and high-volume low-risk work

Default spawn and thread ids when no operator catalog is present:

```text
quality_first spawn_agent:
  model: gpt-5.6-sol
  reasoning_effort: medium
  fork_turns: none

balanced spawn_agent:
  model: gpt-5.6-terra
  reasoning_effort: medium
  fork_turns: none

economy top-level thread:
  model: gpt-5.6-luna
  reasoning_effort: xhigh
  fork_turns: none
```

Never omit `model` on `spawn_agent`. Never inherit the parent model or `default_subagent_model`. Never place the `economy` model on `spawn_agent`. Raise economy effort to `max` only when the packet is both tightly specified and genuinely hard. Do not use `max` as the default.

A stop-or-guess contract is complete only when Objective, Scope, Constraints/Risks, Acceptance, and Retrieve/Escalate are concrete, not `None —`. After a justified planner returns that contract, treat the implement step as specified.

Execution after the pin check:

- No Sol pin, parent is Terra: implement on the parent.
- No Sol pin, parent is Sol, specified work: parent coordinates only; start an economy top-level thread at `xhigh` and accept its result after tests, plus a hard-trigger review when required. Use `max` only if that packet is also hard. Do not use `spawn_agent`.
- No Sol pin, parent is Sol, incomplete contract or a debug/exploration loop: parent coordinates only; spawn a Terra executor. Do not let an unpinned Sol parent run the long coding loop.
- Sol pin with Terra-delegation permission: implement on Terra. Do not send that work to an economy thread.
- Sol pin without Terra-delegation permission: all slices stay on Sol, including implementation.

Before every spawn or thread, confirm the target id is available in current runtime or account metadata. If an operator catalog marks that id `available: false`, treat it as unavailable. If the target is unavailable: disclose the gap; ask once, or apply an explicit named degrade the user can see. Do not silently substitute another model.

Do not fail closed to the parent for the entire task merely because a catalog file is missing. Missing catalog still uses this Terra/Sol/Luna map, then the runtime availability check.

Honor a stated cost ceiling unless the user says the named choice may exceed it. Treat catalog cost tiers as operator-provided classifications, not live price claims. Do not scrape pricing.

## Prepare every handoff

After deciding to delegate, invoke `$agent-context-budget`. Do not invoke it when the task remains on the parent. Use no-history handoffs for executors and reviewers by default; preserve only bounded recent dialogue when exact user wording affects a planner's decision.

If `$codex-speeder` applies, pass its evidence ID, repository snapshot, relevant sections, and retrieval commands rather than copying source or logs. If the target is not a supported Git repository, use bounded paths, symbols, and exact retrieval commands instead.

Never include credentials, private keys, tokens, cookies, unrelated personal data, or raw secret-bearing logs in a handoff.

## Route the work

1. State the selected specialist role, spawn or thread `model`, and concrete routing reason before delegation.
2. For a justified planner, independently restate the problem, compare materially different designs, select one, and return an implementation contract with risks, acceptance criteria, and focused validation. Do not seed it with an unlabeled preferred answer. If the parent is already `quality_first`, do this on the parent.
3. If that contract is complete, implement on an economy top-level thread. If any required field is missing, or the work is still a debug or exploration loop, spawn Terra. If a material architectural or safety deviation becomes necessary, send only that delta for adjudication. Do not let an economy thread widen scope or invent architecture.
4. After an economy thread completes hard-trigger, cross-subsystem, or public-interface work, request a read-only independent Sol review of the diff even if Sol already planned. After a Terra implement, request that review only when a Sol pass has not already been used unless the user pinned Sol. Package the review with `$agent-context-budget` as a diff-only handoff.
5. Fix concrete issues once and run final targeted validation. Stop open-ended review loops.

In the final response, list models that actually participated and deterministic validation performed.
