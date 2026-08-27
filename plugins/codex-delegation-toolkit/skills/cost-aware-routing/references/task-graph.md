# Task graph scheduler contract

Use `scripts/schedule_task_graph.py` only after an approved task decomposition. It validates a bounded structural DAG; it does not infer tasks or globally optimize a schedule.

The input is exactly:

```json
{
  "schema": "codex-task-graph-v1",
  "tasks": [],
  "integration_validation": ["deterministic command or check"]
}
```

`tasks` and `integration_validation` are non-empty lists. Every task has exactly `id`, `objective`, `owned_paths`, `depends_on`, `acceptance`, `validation`, `A`, `B`, `U`, `preflight_complete`, and `evidence_truncated`; optional boolean controls are `sol_pin` and `terra_permit`. The scheduler rejects unknown fields, duplicate ids or dependencies, self or unknown dependencies, cycles, and incomplete or truncated classifier evidence.

Owned paths are repository-relative POSIX components. Absolute paths and empty, `.`, or `..` components are rejected. Equal paths and ancestor/descendant paths conflict. The scheduler uses sorted Kahn ready sets and emits deterministic maximal greedy pairwise-nonconflicting waves; dependencies serialize work even where owned paths do not conflict.

File paths are the default ownership boundary. Two tasks that edit different functions in the same file must declare the same owned file and therefore run serially. Function-level parallelism is allowed only when an external merge mechanism can prove non-overlapping edits and deterministic integration; this scheduler deliberately does not make that assumption.

The default maximum delegation depth is `2`. Run it with explicit recursive-delegation bounds when a different limit is required:

```bash
python scripts/schedule_task_graph.py --input task-graph.json \
  --current-delegation-depth 0 --max-delegation-depth 1 \
  --allow-recursive-delegation
```

Delegation is permitted only when `--allow-recursive-delegation` is present and the current depth is below the maximum; only then does each task include `next_delegation_depth`. The result preserves the task evidence passed to `classify_complexity.py`, includes the classification, and always ends with `final_steps` of `integration_validation` then `judge`.
