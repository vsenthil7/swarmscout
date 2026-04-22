#!/usr/bin/env python
"""Export Pydantic models to JSON Schema files under web/lib/schemas/generated/.

Used both by the schema-drift CI gate (TC-I11) and by the zod generator.
Output is deterministic: keys sorted, newline at EOF.
"""

from __future__ import annotations

import json
from pathlib import Path

from agents.common.schemas.envelope import AgentName, Envelope, StreamName
from agents.common.schemas.payloads import (
    AlphaBrief,
    ChainMetrics,
    HumanReviewRequest,
    RiskVerdict,
    SocialScore,
    TokenCandidate,
)

MODELS = [
    ("envelope", Envelope),
    ("token_candidate", TokenCandidate),
    ("social_score", SocialScore),
    ("chain_metrics", ChainMetrics),
    ("risk_verdict", RiskVerdict),
    ("alpha_brief", AlphaBrief),
    ("human_review_request", HumanReviewRequest),
]

ENUMS = {
    "agent_name": [a.value for a in AgentName],
    "stream_name": [s.value for s in StreamName],
}


def main() -> None:
    """Write JSON Schema + enum files deterministically."""
    out_dir = Path("web/lib/schemas/generated")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, model in MODELS:
        schema = model.model_json_schema()
        path = out_dir / f"{name}.schema.json"
        path.write_text(json.dumps(schema, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path}")
    for name, values in ENUMS.items():
        path = out_dir / f"{name}.enum.json"
        path.write_text(json.dumps(sorted(values), indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
