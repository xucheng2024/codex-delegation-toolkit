# Codex Delegation Toolkit

A public Codex marketplace with two plugins:

- `codex-delegation-toolkit` contains two focused skills:
  - `cost-aware-routing` decides whether specialist delegation is justified, then resolves provider-neutral `quality_first`, `balanced`, and `economy` roles from trusted model metadata.
  - `agent-context-budget` prepares a bounded, evidence-backed handoff after delegation has been selected.
- `keep-plot` is a separate explicit-only skill. It checkpoints a closed parent thread before compact and does not retrieve repositories or package child handoffs.

The toolkit skills are distributed together but keep separate trigger boundaries. This avoids loading routing policy for a context-only handoff and prevents version drift between the router and its handoff contract.

Model names and vendor prices are not hard-coded. An optional deterministic resolver accepts a trusted catalog of availability, capability, and normalized cost tiers, validates overrides and ceilings, and fails closed when a role cannot be selected reliably.

## Pre-model CLI routing

For a new non-interactive task, the bundled launcher selects the entry model before `codex exec` makes its first model call. It reads the local Codex model catalog, uses trusted bounded structural counts, and adds a small routing receipt so the selected agent does not repeat the routing workflow:

```bash
python plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/launch_codex.py \
  --A 1 --B 0 --U 0 --preflight-complete \
  --prompt "Fix the named parser edge case and run its focused tests." \
  -- --sandbox workspace-write
```

`A`, `B`, and `U` follow the definitions in `references/complexity-model.md`. Use `--select-only` to inspect the selection without starting Codex. The launcher is intentionally limited to new `codex exec` turns; an already-started desktop or IDE conversation has already paid for its first model call. The routing skill supports automatic discovery and explicit `$codex-delegation-toolkit:cost-aware-routing` use.

## Install

```bash
codex plugin marketplace add xucheng2024/codex-delegation-toolkit --ref main
codex plugin add codex-delegation-toolkit@codex-delegation-toolkit
codex plugin add keep-plot@codex-delegation-toolkit
```

Plugin users do not need PyYAML or any other development dependency. Those dependencies are pinned in `requirements-dev.txt` and used only for repository validation.

## Development validation

Run one command from the repository root:

```bash
./scripts/validate
```

The first run creates a fingerprinted environment under `.validation-envs/` and installs every pinned development dependency there. Later runs reuse that exact environment. Changing the dependency set or Python version selects a fresh isolated environment, so removed dependencies cannot remain and mask an undeclared import. Nothing is installed into the system Python. When Codex system validators are available they run automatically; use `--require-official` when their absence must fail the command.

Use `./scripts/validate --offline` when validation must never create an environment or contact a package index. It succeeds only when a ready environment already matches the current Python and complete dependency file. GitHub Actions uses the same validation entry point with its pre-installed cached dependencies; the Codex-only validators remain a local `--require-official` check because they are not present on hosted runners.

Dependabot checks the pinned Python development dependencies and GitHub Actions weekly, opening reviewable pull requests instead of silently merging upgrades.

## Safety

The plugin never requests credentials or broadens the user's authority. It requires deterministic validation, bounded evidence, explicit ownership, and privacy-aware handoffs.

## License

MIT
