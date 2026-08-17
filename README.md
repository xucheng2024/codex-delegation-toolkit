# Codex Delegation Toolkit

A Codex plugin containing two focused skills:

- `cost-aware-routing` decides whether specialist delegation is justified, then resolves provider-neutral `quality_first`, `balanced`, and `economy` roles from trusted model metadata.
- `agent-context-budget` prepares a bounded, evidence-backed handoff after delegation has been selected.

The skills are distributed together but keep separate trigger boundaries. This avoids loading routing policy for a context-only handoff and prevents version drift between the router and its handoff contract.

Model names and vendor prices are not hard-coded. An optional deterministic resolver accepts a trusted catalog of availability, capability, and normalized cost tiers, validates overrides and ceilings, and fails closed when a role cannot be selected reliably.

## Install

```bash
codex plugin marketplace add xucheng2024/codex-delegation-toolkit --ref main
codex plugin add codex-delegation-toolkit@codex-delegation-toolkit
```

## Safety

The plugin never requests credentials or broadens the user's authority. It requires deterministic validation, bounded evidence, explicit ownership, and privacy-aware handoffs.

## License

MIT
