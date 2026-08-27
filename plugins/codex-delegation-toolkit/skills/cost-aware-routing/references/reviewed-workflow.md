# Reviewed workflow

Load this reference only for complex, pinned, delegated, or review-gated work. Do not load it for a bounded fast edit.

## Flow and review gates

- Entry `complex`: Sol decomposes the work into a bounded task graph. It does not edit files.
- Each child carries Objective, Owned paths, Dependencies, Acceptance, Validation, and fresh structural complexity evidence. The dispatcher places it in the matching queue.
- Luna executes `fast`; Terra executes `standard`; Sol decomposes `complex` again when delegation depth permits.
- The quality-first parent judges the final diff locally. Do not spawn a separate judge.
- After a Sol-decomposed or `--sol-pin` path, run one read-only quality-first diff review. Include the task graph, changed files, diff, deterministic results, and focused caller/configuration/test impact references. Review material correctness, security, compatibility, contract risk, and missing tests.
- Terra-only simple work: Terra reviews its own diff when escalation says `stop`.

The Sol decomposer is read-only and may inspect the repo. It writes the bounded task graph and acceptance conditions. Each spawned Sol agent must independently discover/load any skill whose trigger matches its task. Do not assume parent skill context is inherited. Do not re-invoke `$codex-delegation-toolkit:cost-aware-routing` or `$codex-delegation-toolkit:agent-context-budget` inside the child.

## Delegation liveness

Treat a route decision as intent, never as proof that a child exists. Spawn exactly once and retain the returned identifier. Never call `wait_agent` unless that call returned a non-empty identifier; an empty receiver set is an immediate transport failure. For a valid child, make at most two `wait_agent` calls of at most 60 seconds each, then interrupt that identifier once and continue with the named parent fallback. Do not retry spawn.

Before delegation, resolve the repository root with `pwd -P` and use that canonical path as the workspace root. Give children repository-relative owned paths and require relative edits; do not construct edit targets from a non-canonical `/tmp` alias. Treat a child as successful only after its declared diff and deterministic validation are visible to the parent.

Use at most one Sol decomposer per complex task. Do not delegate restatement or routine self-review. Keep only `STATUS` plus the task graph or `FINDINGS`.

## Approved task graphs

Read `task-graph.md` and run `scripts/schedule_task_graph.py`. It emits deterministic dependency-aware waves, but execution is temporarily serial and logical owners do not create implementation agents; different functions in the same file remain serial by default. Only complex decomposition may use `--allow-recursive-delegation` when depth permits. Run mandatory integration validation and then a `judge`.

## Handoffs

After deciding to spawn, invoke `$codex-delegation-toolkit:agent-context-budget`; do not invoke it when work remains on the parent. Use no-history handoffs unless exact user wording matters. Keep `fork_turns: "none"`. Never send secrets or raw secret-bearing logs.

After creating the dynamic capsule, encode its non-empty fields as one JSON object and render with `scripts/render_cache_handoff.py`. Keep the `CACHE_HANDOFF_V1` prefix byte-identical and put changing content after `DYNAMIC_PACKET_JSON`. Do not pad the prefix with filler.

For a follow-up on the same child, append a delta message or `codex queue`; do not respawn, do not rebuild the capsule, and do not rewrite the original packet. Use host fork only for an alternate approach and send a short instruction rather than a replacement capsule.

All specialist results begin `STATUS: APPROVE | CHANGES_REQUIRED | INCOMPLETE`. Reviews use `FINDINGS`, `VALIDATION`, and `OVERFLOW_REASON`. If material information is missing, return `STATUS: INCOMPLETE`; the receiver must not approve or infer the missing conclusion. Read [handoff-output.md](handoff-output.md) only for output targets, overflow detail, delta handoffs, or reference-based compression.

## Queue dispatch

Run `scripts/orchestrate_workflow.py` once for an approved task graph. It assigns every task to `fast`, `standard`, or `complex`, resolves the matching model, and emits deterministic dependency waves. No cost estimate or profitability gate is required. Stop dependent tasks after a failure; after all leaves pass, run integration validation and the parent Sol judge.
