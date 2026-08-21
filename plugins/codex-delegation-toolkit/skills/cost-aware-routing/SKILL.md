---
name: cost-aware-routing
description: Route ambiguous, cross-cutting, or high-risk software work between the parent and specialist agents while controlling cost and review overhead. Use for security, money, persistence, concurrency, public interfaces, unclear scope, multiple subsystems, or explicit model/delegation decisions. Do not use for trivial, already-bounded edits or to package a handoff after routing is decided.
---

# Cost-Aware Routing

Keep the parent responsible for coordination, deterministic validation, and delivery. Route a step by what it must decide or do, not by the parent model. `quality_first` (Sol) plans and independently reviews; `balanced` (Terra) implements. Sol never edits.

Read `references/model-role-map.json` for default ids. Read [references/model-routing.md](references/model-routing.md) only when resolving a runtime catalog, model availability, transport, or effort details.

## Classify

Classify from the user request and already-provided context only (named files, diffs, errors, and constraints already in the thread). Do not read or search the repo, and do not draft an implementation plan, before the routing decision. Count each distinct uncertainty once; file count alone is not a trigger.

Hard triggers: security, authorization, secrets, or destructive operations; billing, money movement, trading execution, or irreversible/high-cost external actions (the action, not every nearby file); concurrency, persistence, migration, recovery, or incident handling; public protocol, interface, schema, or compatibility changes.

Soft triggers, only when not already identifiable from the request or provided context: success criteria are unclear; implementation location is not identifiable; the work plausibly spans more than two subsystems or has broad/uncertain dependency impact; materially different valid designs exist.

`--sol-pin` is an explicit user Sol pin, not a runtime default, family alias, or inherited model. It forces Sol plan plus review; it does not make Sol implement. `--terra-permit` skips the Sol planner; if no Sol plan ran, Terra self-reviews.

## Flow

- Simple (no hard trigger, fewer than two soft triggers, no `--sol-pin`): Terra `--step implement`, runs focused validation, then Terra self-reviews its diff. Do not spawn Sol.
- Hard, two-plus soft, or `--sol-pin`: `--step plan`, Terra `--step implement` from the approved contract with no second plan, focused validation, then a fresh `--step judge`.
- A `quality_first` parent plans itself. A `judge` must be a fresh spawned `quality_first` instance; never resume the planner.

For every `plan`, `implement`, or `judge` step, classify `--sol-pin`, `--terra-permit`, `--bounded`, `--contract-complete`, and `--hard-packet`, then run:

```bash
python scripts/route_step.py --step <plan|implement|judge> --parent <model> \
  [--sol-pin] [--terra-permit] [--bounded] [--contract-complete] \
  [--hard-packet] --available <model> [<model> ...]
```

Honor the script output for action, model, and effort; do not re-derive the matrix. If action is `parent`, do not invoke `$agent-context-budget` and do not render an execute capsule; implement from the Sol contract already in this thread. If the chosen target is unavailable, disclose the gap and ask once or name an explicit degrade; never silently substitute a model.

Use at most one planner. Do not delegate routine restatement or self-review. Use deterministic tests and linters as primary verification. After a Sol plan or review returns, keep only `STATUS` plus the contract or `FINDINGS`; drop spawn tool logs and planner prose before the next step.

## Child skill loading

Each spawned Sol agent must independently discover/load any skill whose trigger matches its task. Do not assume parent skill context is inherited. Do not re-invoke `$cost-aware-routing` or `$agent-context-budget`. Domain and task skills are in scope.

The Sol planner is read-only and may inspect the repo. It loads matching task skills, then writes anchors, scope, and acceptance. Do not invent those fields on the parent to complete a plan packet.

## Review gate

After a Sol-planned or `--sol-pin` path, request one fresh read-only `quality_first` diff review. Do not resume the planner. Pass the approved contract, changed-file list, diff, deterministic results, and focused caller/configuration/test impact references when relevant. The reviewer independently loads matching task skills, then reports any material correctness, security, compatibility, or contract risk, plus regression or missing-test issues; it must not edit or reopen design exploration. Terra applies findings once, reruns focused validation, and stops unless a hard-risk finding or failed validation creates a new delta.

Terra-only simple work: Terra reviews its own diff. Do not spawn Sol for plan or judge.

## Handoffs

After deciding to spawn a child, invoke `$agent-context-budget`; do not invoke it when work remains on the parent, including Terra `--step implement` after a Sol plan. Use no-history planner, executor, and reviewer handoffs unless exact user wording matters. Pass `$codex-speeder` evidence IDs and retrieval commands when available. Never send credentials, secrets, cookies, or raw secret-bearing logs.

Put stable instructions before every task-specific packet. After creating the dynamic capsule, encode its non-empty fields as one JSON object and render it with `scripts/render_cache_handoff.py --kind <plan|execute|review> --dynamic-file <capsule.json>`; pass the result unchanged to the child. The renderer canonicalizes JSON key order and whitespace. The `CACHE_HANDOFF_V1` prefix must be byte-identical across same-kind requests; put task text, diff, logs, failures, evidence IDs, and changed conclusions only after `DYNAMIC_PACKET_JSON`. Do not pad the prefix with filler: one-shot GPT-5.6 calls sharing this prefix still wrote nearly the full input and read 0 cached tokens. For a follow-up on the same child, append a delta message; do not rewrite the original packet.

For agent-to-agent output, use English terse technical prose by default; preserve source text, code, errors, requirements, and user-facing language. Never omit material findings, evidence, validation, or unresolved gaps to meet a token target.

All specialist results start with `STATUS: APPROVE | CHANGES_REQUIRED | INCOMPLETE`. Reviews then use `FINDINGS`, `VALIDATION`, and `OVERFLOW_REASON`; do not restate the task or diff. If necessary information cannot be safely handed off, return `STATUS: INCOMPLETE`; the receiver must not approve, implement, or infer the missing conclusion.

Read [references/handoff-output.md](references/handoff-output.md) only for output targets, overflow detail, delta handoffs, or reference-based compression.

In the final response, list participating models and deterministic validation performed.
