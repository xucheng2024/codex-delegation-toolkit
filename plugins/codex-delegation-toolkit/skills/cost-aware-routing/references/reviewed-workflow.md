# Reviewed workflow

Load this reference only for complex, pinned, delegated, or review-gated work. Do not load it for a bounded fast edit.

## Flow and review gates

- Entry `complex`: `plan`, then `plan-review`, then Terra `implement` from the approved contract with no second plan, deterministic validation, and `judge`.
- `plan-review` is a distinct pre-implementation gate and always spawns a fresh read-only `quality_first` reviewer. The planner and reviewer use Objective, Evidence, Constraints, Change set, and Acceptance. Decorative equations are forbidden. After review, pause for explicit user approval after plan review only when the approved plan remains materially ambiguous or approval was requested.
- A quality-first parent ordinarily judges locally. Use `--independent-review` only when explicitly requested or required for high risk; never resume the planner.
- After a Sol-planned or `--sol-pin` path, run one read-only quality-first diff review. Include the approved contract, changed files, diff, deterministic results, and focused caller/configuration/test impact references. Review material correctness, security, compatibility, or contract risk and missing tests.
- Terra-only simple work: Terra reviews its own diff when escalation says `stop`.

The Sol planner is read-only and may inspect the repo. It writes anchors, scope, and acceptance. Each spawned Sol agent must independently discover/load any skill whose trigger matches its task. Do not assume parent skill context is inherited. Do not re-invoke `$cost-aware-routing` or `$agent-context-budget` inside the child.

## Delegation liveness

Treat a route decision as intent, never as proof that a child exists. Spawn exactly once and retain the returned identifier. Never call `wait_agent` unless that call returned a non-empty identifier; an empty receiver set is an immediate transport failure. For a valid child, make at most two `wait_agent` calls of at most 60 seconds each, then interrupt that identifier once and continue with the named parent fallback. Do not retry spawn.

Use at most one planner. Do not delegate restatement or routine self-review. After Sol planning or review, keep only `STATUS` plus the contract or `FINDINGS`.

## Approved task graphs

Read `task-graph.md` and run `scripts/schedule_task_graph.py`. It uses deterministic dependency-aware waves. Parallel tasks must be in one ready wave with non-overlapping owned paths; different functions in the same file remain serial by default. Recursive delegation requires `--allow-recursive-delegation` and depth headroom. Run mandatory integration validation and then a `judge`.

## Handoffs

After deciding to spawn, invoke `$agent-context-budget`; do not invoke it when work remains on the parent. Use no-history handoffs unless exact user wording matters. Keep `fork_turns: "none"`. Never send secrets or raw secret-bearing logs.

After creating the dynamic capsule, encode its non-empty fields as one JSON object and render with `scripts/render_cache_handoff.py`. Keep the `CACHE_HANDOFF_V1` prefix byte-identical and put changing content after `DYNAMIC_PACKET_JSON`. Do not pad the prefix with filler.

For a follow-up on the same child, append a delta message or `codex queue`; do not respawn, do not rebuild the capsule, and do not rewrite the original packet. Use host fork only for an alternate approach and send a short instruction rather than a replacement capsule.

All specialist results begin `STATUS: APPROVE | CHANGES_REQUIRED | INCOMPLETE`. Reviews use `FINDINGS`, `VALIDATION`, and `OVERFLOW_REASON`. If material information is missing, return `STATUS: INCOMPLETE`; the receiver must not approve or infer the missing conclusion. Read [handoff-output.md](handoff-output.md) only for output targets, overflow detail, delta handoffs, or reference-based compression.

## Workflow economics

For an approved multi-task graph, read `workflow-economics.md`, follow its required reducer use order and conservative fallback, then run `scripts/orchestrate_workflow.py`. An approved supplied graph proceeds to implementation and is never planned again. After completion, use `scripts/record_compute.py record-workflow`.
