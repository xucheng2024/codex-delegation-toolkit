# Model Routing Catalog

Use the resolver when a runtime or operator provides a trusted catalog of currently available models. The catalog deliberately contains normalized tiers rather than vendor prices, so model renames, new families, and provider changes do not require edits to the skill.

## Catalog schema

```json
{
  "schema": "codex-model-catalog-v1",
  "models": [
    {
      "id": "example-model",
      "available": true,
      "quality_tier": 5,
      "cost_tier": 3,
      "latency_tier": 2,
      "capabilities": ["reasoning", "coding", "general"]
    }
  ],
  "role_requirements": {
    "quality_first": ["reasoning"],
    "balanced": ["coding"]
  },
  "overrides": {
    "balanced": "example-model"
  },
  "max_cost_tier": 4
}
```

Tier values are integers from 1 through 5. Higher `quality_tier` is better; lower `cost_tier` and `latency_tier` are better. `available` must reflect the current runtime and account. `max_cost_tier` and `overrides` are optional. An override must still be available, meet the role capabilities, and stay within the ceiling.

The default role requirements above apply when `role_requirements` is omitted. A catalog may add capabilities and unknown metadata fields for future runtimes, but the resolver ignores them.

## Resolution policy

- `quality_first` maximizes quality, then prefers lower cost and latency.
- `balanced` minimizes a monotonic score combining cost, latency, and squared capability shortfall, then prefers the stronger model.
- Stable model ID ordering breaks exact ties, keeping output deterministic.

The resolver fails closed if a role has no eligible model or if an override is invalid. It never performs network access, changes the catalog, or prints catalog contents.

Do not put live `available` flags in the bundled role map. [model-role-map.json](model-role-map.json) is a default id map only:

- `quality_first` → `gpt-5.6-sol`
- `balanced` → `gpt-5.6-terra`

Both roles use `spawn_agent`. Confirm the target model is available in the current runtime before delegating.

An operator catalog is the only place `available` may claim current runtime or account state. If no catalog is present, use the role map, then confirm each spawn id against runtime metadata. If the target is unavailable or an operator catalog marks it `available: false`, disclose and ask once or apply an explicit named degrade. Do not silently substitute another model, and do not send the whole task to whoever the parent is.

## Safe updates

Generate or edit catalogs outside task routing using trusted runtime metadata and current provider documentation. Benchmark representative workloads before changing tiers. Submit updates as reviewed configuration changes, ideally on a schedule, instead of changing production routing silently.

Run:

```bash
python scripts/resolve_model_roles.py --catalog /trusted/path/model-catalog.json
```

Exit status is `0` when both roles resolve, `2` for an invalid catalog, and `3` when valid data cannot resolve a role.
