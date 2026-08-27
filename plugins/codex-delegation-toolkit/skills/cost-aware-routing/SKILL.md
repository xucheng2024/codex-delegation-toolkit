---
name: cost-aware-routing
description: Route structurally evidenced software work between the parent and specialist agents while controlling cost and review overhead. Use after a bounded impact preflight or for explicit model/delegation decisions. Do not use to package a handoff after routing is decided.
---

# Cost-Aware Routing

Keep the parent responsible for coordination, deterministic validation, and delivery. Route a step by what it must decide or do, not by the parent model. `quality_first` (Sol) plans and reviews; `balanced` (Terra) implements reviewed work; `economy` (Luna) implements only fast, structurally verified work. Sol never edits.

Read `references/model-role-map.json` for default ids. Read [references/model-routing.md](references/model-routing.md) only when resolving a runtime catalog, model availability, transport, or effort details.

## Entry model selection

The host or wrapper should run `scripts/select_entry_model.py` before the first model call, using bounded structural counts from the preflight. This selector is deterministic and invokes no model. A complete `fast` classification selects Luna at medium effort, `standard` selects Terra at medium effort, and `complex` selects Sol to plan. `--terra-permit` selects Terra directly. Incomplete or truncated evidence fails upward to Sol. If the selected model is unavailable, stop for explicit input rather than substituting silently.

Entry selection does not enable parallelism. A fast task is always a single execution. Standard or complex work may only become parallel after a plan produces an approved task graph and the scheduler plus economics reducer select DAG execution.

## Classify

First perform a bounded read-only one-hop impact preflight. Then use [references/complexity-model.md](references/complexity-model.md) and `scripts/classify_complexity.py`. Use `entry_tier` for workflow shape and first-model selection; use `effective_tier` only for implementation-role compatibility. Its `fast` implementation selects `economy`; its `reviewed` implementation selects `balanced`. Missing or truncated preflight evidence is incomplete and never fast. Permissions and authorization are separate execution constraints, never score inputs. `--sol-pin` wins over `--terra-permit`: it forces reviewed balanced implementation; otherwise `--terra-permit` forces direct balanced implementation, validation, and self-review.

`--sol-pin` is an explicit user Sol pin, not a runtime default, family alias, or inherited model. It forces Sol plan plus review; it does not make Sol implement. `--terra-permit` skips the Sol planner; if no Sol plan ran, Terra self-reviews.

## Flow

- Effective `fast`: keep an already-active Terra or Luna parent local; otherwise route Luna `--step implement --complexity-tier fast`. This avoids paying a child-start and context-transfer penalty for a small bounded edit. Run focused validation, then honor `escalate_step.py`; if it says `stop`, the implementer self-reviews its diff. Do not spawn Sol for plan.
- Entry `standard`: Terra writes a concise local plan, implements, validates, and self-reviews. It may propose a task graph, but parallel execution still requires scheduler and economics approval.
- Entry `complex`: `--step plan`, then `--step plan-review`, then Terra `--step implement --complexity-tier reviewed` from the approved contract with no second plan, focused validation, then honor `escalate_step.py`. After implement stops or a high retry is exhausted, request a `--step judge` code review.
- `--sol-pin` follows the reviewed path. `--terra-permit` without `--sol-pin` routes Terra directly for implementation, validation, and self-review.
- A `quality_first` parent plans and ordinarily judges locally. A judge from another parent spawns `quality_first`. Use `--independent-review` only when an independent review is explicitly requested; never resume the planner.

`plan-review` is a distinct pre-implementation gate, not a code review. It always spawns a fresh read-only `quality_first` reviewer, even from a `quality_first` parent. The planner and reviewer use a concise contract: Objective, Evidence, Constraints, Change set, and Acceptance; include a Decision model only when it resolves a material choice. Decorative equations are forbidden. If plan review reports `CHANGES_REQUIRED` or `INCOMPLETE`, resolve or disclose the gap before implementation. pause for explicit user approval after plan review only for a materially ambiguous approved plan or explicit request.

First-pass `route_step` effort is always `medium`. After `implement`, run focused deterministic validation (tests, compiler, linters, schema, or `STATUS: INCOMPLETE`). Do not use self-reported confidence. Then run:

```bash
python scripts/escalate_step.py --step implement --current-effort <medium|high> \
  --verifier <pass|fail|incomplete> --parent <model> --available <model> [<model> ...]
```

Honor that output; do not re-derive an upgrade. `action=retry` is one Terra `implement` at `high`, then validate and run `escalate_step.py` again. `action=spawn` is a fresh `--step judge`. After judge `CHANGES_REQUIRED`, Terra applies findings once and stops; do not run `escalate_step.py` again. Record each decision with `scripts/record_compute.py` (no prompts, diffs, paths, or secrets).

For every `plan`, `plan-review`, `implement`, or `judge` step, classify `--sol-pin`, `--terra-permit`, `--bounded`, `--contract-complete`, and `--hard-packet`, then run:

```bash
python scripts/route_step.py --step <plan|plan-review|implement|judge> --parent <model> \
  [--sol-pin] [--terra-permit] [--bounded] [--contract-complete] \
  [--hard-packet] [--independent-review] [--complexity-tier <fast|reviewed>] \
  [--delegation-available] \
  --available <model> [<model> ...]
```

Before routing, inspect the current tool catalog. Pass `--delegation-available` only when `spawn_agent` is actually callable; the presence of `wait` alone is not delegation capability. Pass the exact current model id as `--parent` when runtime metadata supplies it. If it does not, pass the literal `current`; never guess a role or model id. A `fast` task stays on `current`. Omitting the delegation flag is the fail-safe default: any would-be spawn becomes a named `degraded` parent action. Honor the script output for action, model, and effort; do not re-derive the matrix. Omitting `--complexity-tier` preserves legacy balanced implementation routing. First-pass effort is `medium`; later effort comes only from `escalate_step.py`. If action is `parent`, do not invoke `$agent-context-budget` and do not render an execute capsule; implement or review inline, and disclose `status=degraded` when present. If economy is unconfigured, the script asks with that distinct reason; if its configured target is unavailable, it asks with `target unavailable`. never silently substitute a model.

Use at most one planner. Do not delegate routine restatement or self-review. Use deterministic tests and linters as primary verification. After a Sol plan or review returns, keep only `STATUS` plus the contract or `FINDINGS`; drop spawn tool logs and planner prose before the next step.

## Approved task graphs

For an approved bounded decomposition, read [references/task-graph.md](references/task-graph.md) and run `scripts/schedule_task_graph.py` before spawning task implementers. It rejects invalid or incomplete graph evidence, uses deterministic dependency-aware waves, and preserves each task's classifier fields. Parallel tasks must be in the same ready wave, have no dependency relation, and own non-overlapping file paths; different functions in the same file remain serial by default. Recursive delegation requires both `--allow-recursive-delegation` and depth headroom. After all waves, run the graph's mandatory integration validation and then a `judge`; do not omit the final judge because individual task validation passed.

## Workflow economics and measurement

For one bounded task with no proposed graph and no supplied economics, route it directly with `route_step.py`; do not read the workflow-economics reference or invoke `orchestrate_workflow.py`. For a proposed multi-task graph or supplied economics, read [references/workflow-economics.md](references/workflow-economics.md) for the required reducer use order, expected-score formula, conservative fallback, and privacy-safe workflow recording command. Then use `scripts/orchestrate_workflow.py` to reduce the validated plan and follow its `execution_mode` and `next_action`; an approved supplied graph proceeds to implementation and is never planned again. Use `scripts/record_compute.py record-workflow` only after completion. Do not duplicate or invent schema fields.

## Child skill loading

Each spawned Sol agent must independently discover/load any skill whose trigger matches its task. Do not assume parent skill context is inherited. Do not re-invoke `$cost-aware-routing` or `$agent-context-budget`. Domain and task skills are in scope.

The Sol planner is read-only and may inspect the repo. It loads matching task skills, then writes anchors, scope, and acceptance. Do not invent those fields on the parent to complete a plan packet. The fresh plan reviewer is also read-only; it reviews the proposed contract and evidence, then approves, requests the minimum change, or returns `INCOMPLETE`.

## Review gate

After a Sol-planned or `--sol-pin` path, request one read-only `quality_first` diff review. It stays on a `quality_first` parent by default; use `--independent-review` for high-risk work or when independent review is requested, which spawns a fresh reviewer rather than resuming the planner. Pass the approved contract, changed-file list, diff, deterministic results, and focused caller/configuration/test impact references when relevant. The reviewer independently loads matching task skills, then reports any material correctness, security, compatibility, or contract risk, plus regression or missing-test issues; it must not edit or reopen design exploration. Terra applies findings once, reruns focused validation, and stops unless a hard-risk finding or failed validation creates a new delta.

Terra-only simple work: Terra reviews its own diff when `escalate_step.py` says `stop`. Do not spawn Sol for plan on the simple path. Spawn Sol for judge only when `escalate_step.py` says `spawn`.

## Handoffs

After deciding to spawn a child, invoke `$agent-context-budget`; do not invoke it when work remains on the parent, including Terra `--step implement` after a Sol plan. Use no-history planner, plan-reviewer, executor, and reviewer handoffs unless exact user wording matters. Pass `$codex-speeder` evidence IDs and retrieval commands when available. Never send credentials, secrets, cookies, or raw secret-bearing logs. Keep `fork_turns: "none"` for plan, plan-review, spawned execute, and independent review.

### Delegation liveness

Treat a route decision as intent, never as proof that a child exists. Call `spawn_agent` exactly once for that step and capture its returned agent identifier. Never call `wait_agent` unless that call returned a non-empty identifier; an empty receiver set is an immediate transport failure, not pending work. On spawn failure, missing identifier, unavailable spawn tool, or an empty wait result, use the route's named `degraded` parent action and perform the bounded step inline. Do not retry spawn.

For a valid child, make at most two `wait_agent` calls of at most 60 seconds each. If the child still has not completed, interrupt that identifier once, disclose the timeout, and continue with the bounded inline fallback. Never wait without an identifier, never wait indefinitely, and never start another child for the same step.

Put stable instructions before every task-specific packet. After creating the dynamic capsule, encode its non-empty fields as one JSON object and render it with `scripts/render_cache_handoff.py --kind <plan|plan-review|execute|review> --dynamic-file <capsule.json>`; pass the result unchanged to the child. The renderer canonicalizes JSON key order and whitespace. The `CACHE_HANDOFF_V1` prefix must be byte-identical across same-kind requests; put task text, diff, logs, failures, evidence IDs, and changed conclusions only after `DYNAMIC_PACKET_JSON`. Do not pad the prefix with filler: one-shot GPT-5.6 calls sharing this prefix still wrote nearly the full input and read 0 cached tokens. For a follow-up on the same child, append a delta message or `codex queue`; do not respawn, do not rebuild the capsule, and do not rewrite the original packet. Use host `fork` or `fork_turns: "all"` only to branch an alternate approach from the current session; send a short new instruction, not a replacement capsule.

For agent-to-agent output, use English terse technical prose by default; preserve source text, code, errors, requirements, and user-facing language. Never omit material findings, evidence, validation, or unresolved gaps to meet a token target.

All specialist results start with `STATUS: APPROVE | CHANGES_REQUIRED | INCOMPLETE`. Reviews then use `FINDINGS`, `VALIDATION`, and `OVERFLOW_REASON`; do not restate the task or diff. If necessary information cannot be safely handed off, return `STATUS: INCOMPLETE`; the receiver must not approve, implement, or infer the missing conclusion.

Read [references/handoff-output.md](references/handoff-output.md) only for output targets, overflow detail, delta handoffs, or reference-based compression.

In the final response, list participating models and deterministic validation performed.
