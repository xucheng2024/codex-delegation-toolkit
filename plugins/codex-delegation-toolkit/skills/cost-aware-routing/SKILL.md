---
name: cost-aware-routing
description: Route structurally evidenced software work between the parent and specialist agents while controlling cost and review overhead. Use after a bounded impact preflight or for explicit model/delegation decisions. Do not use to package a handoff after routing is decided.
---

# Cost-Aware Routing

Keep the parent responsible for coordination, deterministic validation, and delivery. `quality_first` (Sol) plans and reviews; `balanced` (Terra) implements reviewed work; `economy` (Luna) handles structurally verified fast work. Sol never edits.

## Low-overhead first pass

Use existing bounded evidence once. If none exists, perform one bounded read-only one-hop impact preflight. Do not repeat repository searches already covered by that evidence. Do not run a tool's `capabilities` or `--help`, inspect routing script source, or load a reference merely to restate a known contract.

Classify with:

```bash
python scripts/classify_complexity.py --A <count> --B <count> --U <count> --preflight-complete
```

Use `entry_tier` for workflow shape and first-model selection; use `effective_tier` only for implementation-role compatibility. Permissions and authorization are separate execution constraints, never score inputs. Missing or truncated evidence is incomplete and never fast.

For a bounded fast task:

1. If bounded evidence shows one production symbol, no component-boundary crossing, and no unresolved behavior, treat it as `fast` inline. Otherwise run the classifier once. When an active Terra or Luna parent receives `fast`, implement locally without `select_entry_model.py` or `route_step.py`.
2. Do not invoke `$agent-context-budget` and do not render an execute capsule.
3. Read each relevant source or test region once. Do not run both broad search and `$codex-speeder` for evidence the first result already supplied, and do not rerun `$codex-speeder` review when the exact diff and validation are already known.
4. Preserve successful legacy behavior before adding a fallback. Check language edge cases that cross type boundaries, such as Python `bool` being an `int`.
5. After the final edit, run the smallest focused deterministic validation plus `git diff --check` exactly once. Do not rerun passed checks unless files change. Expand to related or full suites only when risk, failure, or project policy requires it.
6. If validation passes, self-review the diff and finish. Only on `fail` or `incomplete`, read the reviewed workflow and run `python scripts/escalate_step.py --step implement --current-effort medium --verifier <fail|incomplete> --parent <model> --available <models...>`. Do not record per-step metrics unless the caller requested them or supplied a writable metrics destination.

This fast path is the default for a single bounded edit. Do not load the reviewed-workflow, task-graph, workflow-economics, model-routing, or handoff-output references for it.

## Entry selection

For a new non-interactive task, prefer `scripts/launch_codex.py` before the first model call: it reads the Codex model catalog, runs the deterministic selector, pins the model and medium effort, adds a compact routing receipt that prevents duplicate routing, and only then starts `codex exec`. Supply trusted bounded `A`, `B`, and `U` evidence plus the prompt; use `--select-only` to inspect the decision without starting a model. Do not explicitly invoke this skill inside the routed prompt.

```bash
python scripts/launch_codex.py --A 1 --B 0 --U 0 --preflight-complete \
  --prompt "<task>" -- --sandbox workspace-write
```

The lower-level `scripts/select_entry_model.py` remains available to other hosts. The selector is deterministic and invokes no model: a `fast` classification selects Luna at medium effort, `standard` selects Terra at medium effort, and `complex` selects Sol to plan. Entry selection does not enable parallelism. If the selected model is unavailable, stop; never silently substitute a model. This pre-model optimization applies to new CLI `exec` turns; a skill cannot retroactively change the first model in an already-started app or IDE turn.

`--sol-pin` wins over `--terra-permit`. It forces Sol plan plus review; it does not make Sol implement. `--terra-permit` forces direct Terra implementation, validation, and self-review. Otherwise follow the classifier.

## Route

First-pass `route_step` effort is always `medium`. Invoke:

```bash
python scripts/route_step.py --step <plan|plan-review|implement|judge> --parent <model> \
  [--sol-pin] [--terra-permit] [--bounded] [--contract-complete] \
  [--hard-packet] [--independent-review] [--complexity-tier <fast|reviewed>] \
  [--delegation-available] --available <model> [<model> ...]
```

Inspect the tool catalog first. The presence of `wait` alone is not delegation capability. Pass `--delegation-available` only when spawning is callable. Pass the exact runtime parent id when metadata supplies it. If it does not, pass the literal `current`; never guess a role or model id. Honor the script output; do not re-derive the matrix. If action is `parent`, do not invoke `$agent-context-budget`, do not render an execute capsule, and disclose `status=degraded` when present.

After implementation, validate deterministically. Do not use self-reported confidence. Then invoke `scripts/escalate_step.py`. A retry is one Terra high-effort pass. A judge is a fresh review. Terra applies findings once and stops; do not run `escalate_step.py` again. Record decisions directly with `scripts/record_compute.py`; never call its `--help` during normal work and never retry a metrics write blocked outside the workspace.

## Larger workflows

- Effective `fast`: use the low-overhead path above.
- Entry `standard`: Terra plans briefly, implements, validates, and self-reviews.
- Entry `complex`, `--sol-pin`, any `plan-review`, spawned implementation, or judge: read [references/reviewed-workflow.md](references/reviewed-workflow.md) before acting.
- A proposed task graph: also read [references/task-graph.md](references/task-graph.md).
- A proposed multi-task graph or supplied economics: also read [references/workflow-economics.md](references/workflow-economics.md). For one bounded task with no proposed graph and no supplied economics, route it directly with `route_step.py`; do not read the workflow-economics reference.
- Runtime catalog, availability, transport, or effort resolution: read [references/model-routing.md](references/model-routing.md) and `references/model-role-map.json`.
- Output targets, overflow, or reference-based compression only: read [references/handoff-output.md](references/handoff-output.md).

In the final response, list participating models and deterministic validation performed.
