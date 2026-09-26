"""
Tier 3 — Human Review Interface & API
=========================================
Serves matches that need human review (status == "needs_review" from Tier 2),
lets a reviewer approve/reject, and records the decision.

Data sources (matching what's already real in this repo):
- processed_catalog.jsonl  (Tier 1 output — item descriptions)
- tier2_match_output.json  (Tier 2 output — match records incl. Safety Gate results)

Decisions are appended to data/processed/review_decisions.jsonl as a durable,
auditable log. Tier 4's integration script can pick these up the same way it
already picks up Tier 2's auto-linked and safety_gate_blocked records.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TIER1_FILE = PROJECT_ROOT / "processed_catalog.jsonl"
TIER2_FILE = PROJECT_ROOT / "tier2_match_output.json"
DECISIONS_FILE = PROJECT_ROOT / "data" / "processed" / "review_decisions.jsonl"
DECISIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="SIH26099 Tier 3 — Human Review API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ReviewDecision(BaseModel):
    match_id: str
    reviewer_decision: str  # "approved" | "rejected"
    reviewer_id: str
    notes: Optional[str] = None


def load_catalog() -> dict:
    catalog = {}
    if not TIER1_FILE.exists():
        return catalog
    with TIER1_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            catalog[item["item_id"]] = item
    return catalog


def load_matches() -> list:
    if not TIER2_FILE.exists():
        return []
    with TIER2_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_decisions() -> dict:
    """Returns {match_id: decision_record} for already-reviewed matches."""
    decisions = {}
    if not DECISIONS_FILE.exists():
        return decisions
    with DECISIONS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            decisions[record["match_id"]] = record
    return decisions


@app.get("/api/pending-reviews")
def get_pending_reviews():
    """Matches with status == 'needs_review' that haven't been decided yet."""
    catalog = load_catalog()
    matches = load_matches()
    decisions = load_decisions()

    pending = []
    for m in matches:
        if m.get("status") != "needs_review":
            continue
        match_id = m.get("match_id", f"{m.get('item_a')}__{m.get('item_b')}")
        if match_id in decisions:
            continue  # already reviewed

        item_a = catalog.get(m.get("item_a"), {})
        item_b = catalog.get(m.get("item_b"), {})

        pending.append({
            "match_id": match_id,
            "item_a": m.get("item_a"),
            "item_b": m.get("item_b"),
            "description_a": item_a.get("clean_description", "(description unavailable)"),
            "description_b": item_b.get("clean_description", "(description unavailable)"),
            "confidence_score": m.get("confidence_score"),
            "score_breakdown": m.get("score_breakdown", {}),
        })

    return {"count": len(pending), "pending_reviews": pending}


@app.post("/api/review-decision")
def submit_review_decision(decision: ReviewDecision):
    if decision.reviewer_decision not in ("approved", "rejected"):
        raise HTTPException(400, "reviewer_decision must be 'approved' or 'rejected'")

    record = {
        "match_id": decision.match_id,
        "reviewer_decision": decision.reviewer_decision,
        "reviewer_id": decision.reviewer_id,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "notes": decision.notes,
    }

    with DECISIONS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    return {"status": "recorded", "record": record}


@app.get("/api/review-decisions")
def get_all_decisions():
    """All decisions made so far — used by Tier 4/5 and for the review screen's history view."""
    return {"decisions": list(load_decisions().values())}


# Serve the review UI
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    def serve_ui():
        return FileResponse(str(static_dir / "index.html"))
