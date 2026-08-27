# Structural Complexity Model

Run `scripts/classify_complexity.py` only after a bounded one-hop impact preflight. Its input excludes permissions and authorization, which remain separate execution constraints.

Count only production code and configuration, never tests or documentation:

- `A` is the number of deduplicated production symbols, configuration keys, schema objects, and entrypoints in the change plus their direct consumers. Canonical IDs are `path::qualified-name`.
- `B` is the number of deduplicated directed edges crossing declared component or package boundaries.
- `U` is the number of deduplicated affected behaviors or unresolved dynamic paths without a named deterministic validation command.

The preflight must be complete and untruncated. Missing or truncated evidence returns `status: incomplete`, never a fast route. The deterministic score is `C = log2(1 + A) + B + 2U`. Entry routing uses three bands: `C < 4` is `fast`, `4 <= C < 8` is `standard`, and `C >= 8` is `complex`. Missing or truncated evidence fails upward to `complex`.

The classifier returns the legacy `structural_tier` and `effective_tier` fields for implementation-role compatibility, plus `entry_tier`, `queue`, and `entry_role`. `fast` selects economy, `standard` selects balanced, and `complex` selects quality-first. `--sol-pin` forces the complex decomposition queue. `--terra-permit`, unless Sol is pinned, forces the standard queue.

```bash
python scripts/classify_complexity.py --A 1 --B 0 --U 0 --preflight-complete
```

Use `queue` to dispatch work. Pass `effective_tier` to `route_step.py --complexity-tier` only when routing implementation.

To select the first model before any model tokens are spent, run:

```bash
python scripts/select_entry_model.py --A 1 --B 0 --U 0 \
  --preflight-complete \
  --available gpt-5.6-sol gpt-5.6-terra gpt-5.6-luna
```

The entry selector uses Luna at medium effort for complete fast work, Terra at medium effort for standard work, and Sol for complex or incomplete work. It never enables parallel execution before an approved task graph exists.
