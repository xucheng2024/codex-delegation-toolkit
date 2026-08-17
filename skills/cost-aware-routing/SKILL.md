---
name: cost-aware-routing
description: Route ambiguous, cross-cutting, or high-risk software work between the parent agent and specialist agents while controlling model cost and review overhead. Use for tasks involving security, money, persistence, concurrency, public interfaces, unclear scope, multiple subsystems, or explicit requests to decide whether or which model or subagent to use. Do not use for trivial, already-bounded edits or for packaging a handoff after routing is already decided.
---

# Cost-Aware Routing

Keep the parent agent responsible for coordination, implementation, deterministic validation, and final delivery. Delegate only when specialist judgment or genuinely parallel independent work improves the outcome.

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

Stay on the parent when there is no hard trigger and fewer than two soft triggers. Use one deeper planner when any hard trigger or at least two soft triggers apply.

## Control delegation overhead

- Do not delegate ordinary implementation, restatement, sequential work, or routine self-review to an equivalent generalist.
- Permit same-role agents only for independent parallel slices with disjoint ownership, or for an independent high-risk read-only review.
- Keep implementation on the parent after planning unless the work has clearly disjoint parallel slices.
- Use deterministic tests and linters as the primary verifier; do not replace executable validation with more model rounds.
- Use at most one planning pass and, when risk justifies it, one independent review pass followed by one targeted fix pass.

## Prepare every handoff

After deciding to delegate, invoke `$agent-context-budget`. Do not invoke it when the task remains on the parent. Use no-history handoffs for executors and reviewers by default; preserve only bounded recent dialogue when exact user wording affects a planner's decision.

If `$codex-speeder` applies, pass its evidence ID, repository snapshot, relevant sections, and retrieval commands rather than copying source or logs. If the target is not a supported Git repository, use bounded paths, symbols, and exact retrieval commands instead.

Never include credentials, private keys, tokens, cookies, unrelated personal data, or raw secret-bearing logs in a handoff.

## Route the work

1. State the selected specialist role, model, and concrete routing reason before delegation.
2. Ask a planner to independently restate the problem, compare materially different designs, select one, and return an implementation contract with risks, acceptance criteria, and focused validation. Do not seed it with an unlabeled preferred answer.
3. Let the parent implement the contract. If a material architectural or safety deviation becomes necessary, send only that delta for adjudication.
4. Request a read-only independent review only for hard-trigger, cross-subsystem, or public-interface changes.
5. Fix concrete issues once and run final targeted validation. Stop open-ended review loops.

Prefer the environment's strongest planning/review model and a lower-cost capable executor. When configured, use a Sol-class planner/reviewer and a Terra-class parent/executor. If the preferred specialist is unavailable, disclose the fallback and keep the work local unless a capable substitute exists.

In the final response, list models that actually participated and deterministic validation performed.
