"""
Tier 5 — Analytics & Monitoring Dashboard
=============================================
Reads real output from Tier 2 (matches), Tier 3 (review decisions), and the
audit log Tier 4 writes, and serves summary statistics for the dashboard.

Data sources:
- processed_catalog.jsonl       (Tier 1 — item descriptions)
- tier2_match_output.json       (Tier 2 — match records incl. Safety Gate)
- data/processed/review_decisions.jsonl (Tier 3 — human decisions)
- data/processed/audit_log.jsonl        (Tier 4 — full audit trail, if present)
"""

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TIER2_FILE = PROJECT_ROOT / "tier2_match_output.json"
DECISIONS_FILE = PROJECT_ROOT / "data" / "processed" / "review_decisions.jsonl"
AUDIT_FILE = PROJECT_ROOT / "data" / "processed" / "audit_log.jsonl"

app = FastAPI(title="SIH26099 Tier 5 — Analytics Dashboard")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_json_list(path: Path) -> list:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


@app.get("/api/summary")
def get_summary():
    matches = load_json_list(TIER2_FILE)
    decisions = load_jsonl(DECISIONS_FILE)

    auto_linked = sum(1 for m in matches if m.get("status") == "auto_linked")
    needs_review_total = sum(1 for m in matches if m.get("status") == "needs_review")
    safety_blocked = sum(1 for m in matches if m.get("status") == "safety_gate_blocked")

    approved = sum(1 for d in decisions if d.get("reviewer_decision") == "approved")
    rejected = sum(1 for d in decisions if d.get("reviewer_decision") == "rejected")
    decided_ids = {d["match_id"] for d in decisions}
    still_pending = sum(
        1 for m in matches
        if m.get("status") == "needs_review"
        and m.get("match_id", f"{m.get('item_a')}__{m.get('item_b')}") not in decided_ids
    )

    total_confirmed_matches = auto_linked + approved  # these produce a CNMC

    return {
        "total_pairs_evaluated": len(matches),
        "auto_linked": auto_linked,
        "needs_review_total": needs_review_total,
        "pending_review_now": still_pending,
        "human_approved": approved,
        "human_rejected": rejected,
        "safety_gate_blocked": safety_blocked,
        "total_cnmc_generated_estimate": total_confirmed_matches,
    }


@app.get("/api/savings-estimate")
def get_savings_estimate(
    duplicate_pct: float = 1.0,        # combined estimated-saving rate — matches PPT Slide 5's SOM calc
    procurement_value_cr: float = 28000.0,  # pilot procurement value, in Cr — placeholder, replace with real pilot figure
):
    """
    Matches the exact formula used on the Impact & Benefits (TAM/SAM/SOM) slide:
    savings = procurement_value x duplicate_pct
    (duplicate_pct itself is informed by the GeM/World Bank ~10% bulk-discount
    benchmark applied to an assumed duplicate-rate — see Slide 5 for the derivation.
    Kept as ONE rate here, not multiplied twice, to avoid contradicting the slide.)
    """
    savings_cr = procurement_value_cr * (duplicate_pct / 100)
    return {
        "formula": "savings = procurement_value x duplicate_pct",
        "inputs": {
            "duplicate_pct": duplicate_pct,
            "procurement_value_cr": procurement_value_cr,
        },
        "estimated_savings_cr": round(savings_cr, 2),
        "note": "Illustrative until real pilot procurement data is available under NDA. Matches Slide 5's SOM calculation.",
    }


@app.get("/api/cnmc-preview")
def get_cnmc_preview():
    """Lightweight view of confirmed matches, until Tier 4's live DB-backed /api/cnmc is wired in."""
    matches = load_json_list(TIER2_FILE)
    decisions = {d["match_id"]: d for d in load_jsonl(DECISIONS_FILE)}

    confirmed = []
    for m in matches:
        match_id = m.get("match_id", f"{m.get('item_a')}__{m.get('item_b')}")
        if m.get("status") == "auto_linked":
            confirmed.append({
                "match_id": match_id, "item_a": m["item_a"], "item_b": m["item_b"],
                "confidence": m.get("confidence_score"), "merge_type": "auto",
            })
        elif match_id in decisions and decisions[match_id]["reviewer_decision"] == "approved":
            confirmed.append({
                "match_id": match_id, "item_a": m["item_a"], "item_b": m["item_b"],
                "confidence": m.get("confidence_score"), "merge_type": "human_approved",
            })
    return {"count": len(confirmed), "confirmed_matches": confirmed}


static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    def serve_ui():
        return FileResponse(str(static_dir / "index.html"))
