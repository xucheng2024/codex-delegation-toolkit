# Workflow economics and measurement

Use `scripts/orchestrate_workflow.py` as the unified reducer. It validates the
plan, classifies complexity, schedules an approved graph, evaluates the
single-versus-DAG policy, and then delegates through the existing routing
contract. It is deterministic and does not invoke a model or persist state.

## Required use order

1. Gather bounded preflight evidence.
2. If decomposition is proposed, obtain an approved graph and include it in
   the plan; otherwise omit the graph.
3. Invoke `orchestrate_workflow.py plan` once with the plan and (when
   available) economics. It internally classifies and schedules; follow its
   `execution_mode` and `next_action`. A supplied graph is already approved,
   so the reducer routes it to implementation without another planning pass.
4. Run focused validation, then invoke `orchestrate_workflow.py
   after-implement` with the verifier result. Record each compute decision
   with `record_compute.py`.
5. Record the completed aggregate with `record_compute.py record-workflow`.

Do not bypass routing, schedule an unapproved graph, or infer estimates from
missing fields. The scheduler's mandatory integration validation and final
`judge` remain required for DAG execution.

## Expected-cost reducer

The reducer uses `latency_weight` to put milliseconds into the same score as
cost units. For a policy with cost `K`, latency `L`, and success probability
`p`, its expected score is:

```
expected_score = (K + latency_weight * L) / p
```

For `single`, `K` and `L` are `single.cost_units` and
`single.latency_ms`. For a scheduled DAG:

```
K = dag.overhead_cost_units + sum(task.cost_units)
L = dag.overhead_latency_ms + sum(max(task.latency_ms in wave) for wave)
```

The reducer selects `dag` only when its score is strictly lower, its gain
ratio meets `minimum_gain_ratio`, and the single score is nonzero:
`gain_ratio = (single_score - dag_score) / single_score`.

Economics are optional. If the complete economics object is unavailable, the
conservative fallback is `single` with status `insufficient`; no savings are
claimed. If economics are present, every required field and every scheduled
task estimate must be supplied and valid; partial or mismatched estimates are
rejected rather than guessed.

The reducer's input and output schemas, field names, and validation rules are
defined by the implementation; this reference explains their use without
duplicating those schemas.

## Recording outcomes

After the workflow completes, record only privacy-safe aggregates:

```bash
python scripts/record_compute.py record-workflow \
  --complexity-bucket fast|reviewed --policy single|dag \
  --task-count N --dependency-count N --critical-path-length N \
  --total-cost-units N --total-latency-ms N \
  --final-pass --rework-count N
```

Omit `--final-pass` when the final workflow did not pass. The command writes
the fixed `codex-workflow-outcome-v1` event to the local privacy-safe cache;
it does not measure or imply savings.
