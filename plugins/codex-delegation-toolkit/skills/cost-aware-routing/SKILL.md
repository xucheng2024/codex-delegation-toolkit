---
name: cost-aware-routing
description: Route ambiguous, cross-cutting, or high-risk software work between the parent and specialist agents while controlling cost and review overhead. Use for security, money, persistence, concurrency, public interfaces, unclear scope, multiple subsystems, or explicit model/delegation decisions. Do not use for trivial, already-bounded edits or to package a handoff after routing is decided.
---

# Cost-Aware Routing

Keep the parent responsible for coordination, deterministic validation, and delivery. Route a step by what it must decide or do, not by the parent model.

Read `references/model-role-map.json` for default ids. Read [references/model-routing.md](references/model-routing.md) only when resolving a runtime catalog, model availability, transport, or effort details.

## Classify

Hard triggers: security/authorization/secrets/destructive operations; billing or irreversible external action; concurrency, persistence, migration, recovery, or incident; public protocol/interface/backward compatibility.

Soft triggers: unclear success criteria; unknown implementation location; more than two plausible subsystems; uncertain dependency impact; materially different designs.

With no hard trigger and fewer than two soft triggers, stay on the parent. Otherwise use one deeper planner. A `quality_first` parent plans itself; independent review must still use a fresh instance.

## Routing contract

`quality_first` handles architecture, hard risk, and independent review; `balanced` implements and debugs; `economy` handles only bounded, fully specified work.

An explicit user Sol pin applies to all task work unless the user explicitly permits Terra delegation. A runtime default, family alias, or inherited model is not a pin.

A contract is complete only when Objective, Scope, Constraints/Risks, Acceptance, and Retrieve/Escalate are concrete. Economy work requires both `bounded` and `contract_complete`; it runs as a separate top-level thread, never `spawn_agent`.

For every `implement` or `judge` step, classify `--sol-pin`, `--terra-permit`, `--bounded`, `--contract-complete`, and `--hard-packet`, then run:

```bash
python scripts/route_step.py --step <implement|judge> --parent <model> \
  [--sol-pin] [--terra-permit] [--bounded] [--contract-complete] \
  [--hard-packet] --available <model> [<model> ...]
```

Honor the script output for action, model, and effort; do not re-derive the matrix. A `judge` must be a fresh spawned `quality_first` instance. If the chosen target is unavailable, disclose the gap and ask once or name an explicit degrade; never silently substitute a model.

Use at most one planner. Do not delegate routine restatement or self-review. Use deterministic tests and linters as primary verification.

## Review gate

After any non-Sol hard-trigger implementation, request one fresh read-only `quality_first` diff review, even if Sol planned. Also review economy cross-subsystem work. Terra work triggered only by soft complexity may skip it only with a complete contract, no material deviation, and passing deterministic validation.

Pass the approved contract, changed-file list, diff, deterministic results, and focused caller/configuration/test impact references when relevant. The reviewer may report any material correctness, security, compatibility, or contract risk; it must not reopen design exploration. Fix concrete findings once, rerun focused validation, and stop unless a hard-risk finding or failed validation creates a new delta.

## Handoffs

After deciding to delegate, invoke `$agent-context-budget`; do not invoke it when work remains on the parent. Use no-history executor/reviewer handoffs unless exact user wording matters. Pass `$codex-speeder` evidence IDs and retrieval commands when available. Never send credentials, secrets, cookies, or raw secret-bearing logs.

Put stable instructions before every task-specific packet. After creating the dynamic capsule, encode its non-empty fields as one JSON object and render it with `scripts/render_cache_handoff.py --kind <plan|execute|review> --dynamic-file <capsule.json>`; pass the result unchanged to the child. The renderer canonicalizes JSON key order and whitespace. The `CACHE_HANDOFF_V1` prefix must be byte-identical across same-kind requests; put task text, diff, logs, failures, evidence IDs, and changed conclusions only after `DYNAMIC_PACKET_JSON`.

For agent-to-agent output, use English terse technical prose by default; preserve source text, code, errors, requirements, and user-facing language. Never omit material findings, evidence, validation, or unresolved gaps to meet a token target.

All specialist results start with `STATUS: APPROVE | CHANGES_REQUIRED | INCOMPLETE`. Reviews then use `FINDINGS`, `VALIDATION`, and `OVERFLOW_REASON`; do not restate the task or diff. If necessary information cannot be safely handed off, return `STATUS: INCOMPLETE`; the receiver must not approve, implement, or infer the missing conclusion.

Read [references/handoff-output.md](references/handoff-output.md) only for output targets, overflow detail, delta handoffs, or reference-based compression.

In the final response, list participating models and deterministic validation performed.
