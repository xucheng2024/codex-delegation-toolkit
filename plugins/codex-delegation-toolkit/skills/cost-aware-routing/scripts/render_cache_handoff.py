#!/usr/bin/env python3
"""Render a canonical stable prefix before a task-specific delegation packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PREFIXES = {
    "plan": """CACHE_HANDOFF_V1\nKIND: PLAN\nReturn a decision-ready implementation contract. Preserve hard constraints, name unresolved gaps, and do not invent missing evidence.\nRESULT: STATUS: APPROVE | CHANGES_REQUIRED | INCOMPLETE\nDYNAMIC_PACKET_JSON:\n""",
    "execute": """CACHE_HANDOFF_V1\nKIND: EXECUTE\nImplement only the approved dynamic contract. Do not widen architecture; stop on missing constraints or material deviation. Report deterministic validation.\nRESULT: STATUS: APPROVE | CHANGES_REQUIRED | INCOMPLETE\nDYNAMIC_PACKET_JSON:\n""",
    "review": """CACHE_HANDOFF_V1\nKIND: REVIEW\nReview only the supplied delta and report every material correctness, security, compatibility, or contract risk. Do not narrate unchanged code or reopen design exploration.\nRESULT:\nSTATUS: APPROVE | CHANGES_REQUIRED | INCOMPLETE\nFINDINGS: <none or severity | anchor | risk | mechanism | minimum fix>\nVALIDATION: <focused checks>\nOVERFLOW_REASON: none | <reason>\nDYNAMIC_PACKET_JSON:\n""",
}


def render(kind: str, dynamic_file: Path) -> str:
    try:
        prefix = PREFIXES[kind]
    except KeyError as exc:
        raise ValueError(f"unknown handoff kind: {kind}") from exc
    dynamic = dynamic_file.read_text(encoding="utf-8")
    if not dynamic.strip():
        raise ValueError("dynamic packet must not be empty")
    try:
        packet = json.loads(dynamic)
    except json.JSONDecodeError as exc:
        raise ValueError(f"dynamic packet must be valid JSON: {exc.msg}") from exc
    if not isinstance(packet, dict) or not packet:
        raise ValueError("dynamic packet must be a non-empty JSON object")
    return prefix + json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=sorted(PREFIXES), required=True)
    parser.add_argument("--dynamic-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(render(args.kind, args.dynamic_file), end="")
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
