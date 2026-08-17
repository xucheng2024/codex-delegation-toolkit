# Codex Delegation Toolkit

A Codex plugin containing two focused skills:

- `cost-aware-routing` decides whether specialist delegation is justified and controls planning and review depth.
- `agent-context-budget` prepares a bounded, evidence-backed handoff after delegation has been selected.

The skills are distributed together but keep separate trigger boundaries. This avoids loading routing policy for a context-only handoff and prevents version drift between the router and its handoff contract.

## Safety

The plugin never requests credentials or broadens the user's authority. It requires deterministic validation, bounded evidence, explicit ownership, and privacy-aware handoffs.

## License

MIT
