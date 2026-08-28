# Task graph scheduler contract

Use `scripts/schedule_task_graph.py` only after an approved task decomposition. Sol-produced graphs must first pass through `scripts/sol_decompose.py`, which validates them immediately and permits one same-thread schema-only correction. It never manually rewrites a graph or resumes an unknown thread. The scheduler validates a bounded structural DAG; it does not infer tasks or globally optimize a schedule.

The input is exactly:

```json
{
  "schema": "codex-task-graph-v1",
  "tasks": [],
  "integration_validation": ["deterministic command or check"]
}
```

`tasks` and `integration_validation` are non-empty lists. Every task has exactly `id`, `objective`, `owned_paths`, `depends_on`, `acceptance`, `validation`, `A`, `B`, `U`, `preflight_complete`, and `evidence_truncated`; optional controls are `sol_pin`, `terra_permit`, and `resources`. `resources` is a list of non-whitespace semantic resource names such as `db:schema` or `public-api:orders`; tasks that claim the same resource are serialized even if their file paths differ. The scheduler rejects unknown fields, duplicate ids or dependencies, self or unknown dependencies, cycles, and incomplete or truncated classifier evidence.

Owned paths are repository-relative POSIX components. Absolute paths and empty, `.`, or `..` components are rejected. Equal paths and ancestor/descendant paths conflict. The scheduler uses sorted Kahn ready sets and emits deterministic maximal greedy pairwise-nonconflicting waves; dependencies serialize work even where owned paths do not conflict.

File paths are the default ownership boundary. Two tasks that edit different functions in the same file must declare the same owned file and therefore run serially. Function-level parallelism is allowed only when an external merge mechanism can prove non-overlapping edits and deterministic integration; this scheduler deliberately does not make that assumption.

The default maximum delegation depth is `2`. Run it with explicit recursive-delegation bounds when a different limit is required:

```bash
python scripts/schedule_task_graph.py --input task-graph.json \
  --current-delegation-depth 0 --max-delegation-depth 1 \
  --allow-recursive-delegation
```

Delegation is permitted only when `--allow-recursive-delegation` is present and the current depth is below the maximum; only then does each task include `next_delegation_depth`. The result preserves the task evidence passed to `classify_complexity.py`, includes the classification, and assigns each task a `queue` and `work_type`. `fast` and `standard` tasks use `implement`; `complex` tasks use `decompose`. The `queues` object lists task ids by queue. The workflow always ends with `integration_validation` then `judge`.

Process waves in order. The queue set is fixed to `fast`, `standard`, and `complex`; never create queues dynamically. Each non-empty queue gets exactly one logical owner for the workflow, regardless of queue length. By default, waves execute serially and do not spawn implementation agents from the graph. A host may opt into `max_parallelism > 1`; it must acquire every task's `lease_resources` atomically with `scripts/resource_leases.py`, run each worker in an isolated worktree, and verify that its diff remains within `owned_paths` before merge. The lease manager detects equal and ancestor/descendant `path:` claims plus equal semantic `resource:` claims, expires abandoned leases, and makes conflicted work wait. Never reserve every path in a future wave: acquire immediately before starting a ready task and release after validation/merge. A failed task blocks every dependent task. The Sol parent performs the final judge after integration validation.

`scripts/parallel_execute.py` is the opt-in executor for a `parallel-leased` graph dispatch. It requires a clean caller checkout, creates temporary worker and integration worktrees, runs at most `max_parallelism` implementation leaves in a wave, validates owned paths and task checks, and applies the final integrated diff to the caller only after every wave and integration check pass. It rejects `complex` leaves: Sol must decompose them first.
