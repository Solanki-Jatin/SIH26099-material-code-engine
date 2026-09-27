import json
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..persistence.database import get_db
from ..persistence.models import AuditLog, CNMCRegistry

router = APIRouter(prefix="/api", tags=["Tier 5 Dashboard"])

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TIER2_FILE = PROJECT_ROOT / "tier2_match_output.json"


def load_tier2_matches() -> list:
    if not TIER2_FILE.exists():
        return []
    with TIER2_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    """
    Real numbers, queried from the same database Tier 3 and Tier 4 write to,
    not a separate file. This is what makes the dashboard trustworthy: it
    reflects the actual system state, not a snapshot that can drift out of sync.
    """
    matches = load_tier2_matches()
    needs_review_total = sum(1 for m in matches if m.get("status") == "needs_review")

    auto_linked = db.execute(
        select(func.count()).select_from(CNMCRegistry).where(CNMCRegistry.merge_type == "auto")
    ).scalar_one()

    human_approved = db.execute(
        select(func.count()).select_from(CNMCRegistry).where(CNMCRegistry.merge_type == "human_approved")
    ).scalar_one()

    safety_gate_blocked = db.execute(
        select(func.count()).select_from(AuditLog).where(AuditLog.action == "safety_gate_blocked")
    ).scalar_one()

    total_cnmc = db.execute(select(func.count()).select_from(CNMCRegistry)).scalar_one()

    # Note: rejected reviews are not currently written to audit_log by Tier 3,
    # so "pending" here is an upper bound (needs_review minus approved), not
    # an exact live count. Flagged honestly rather than silently assumed exact.
    pending_review_estimate = max(needs_review_total - human_approved, 0)

    return {
        "total_pairs_evaluated": len(matches),
        "auto_linked": auto_linked,
        "human_approved": human_approved,
        "pending_review_estimate": pending_review_estimate,
        "safety_gate_blocked": safety_gate_blocked,
        "total_cnmc_generated": total_cnmc,
    }


@router.get("/savings-estimate")
def get_savings_estimate(
    duplicate_pct: float = Query(default=1.0),
    procurement_value_cr: float = Query(default=28000.0),
):
    """
    Matches the exact formula used on the Impact & Benefits (TAM/SAM/SOM) slide:
    savings = procurement_value x duplicate_pct
    Kept as one rate, not multiplied twice, to stay consistent with the deck.
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


@router.get("/cnmc-preview")
def get_cnmc_preview(db: Session = Depends(get_db)):
    """Lightweight table view — same data as /api/cnmc, shaped for the dashboard UI."""
    rows = db.execute(
        select(CNMCRegistry).order_by(CNMCRegistry.created_at.desc()).limit(50)
    ).scalars().all()

    return {
        "count": len(rows),
        "confirmed_matches": [
            {
                "cnmc_code": r.cnmc_code,
                "canonical_description": r.canonical_description,
                "confidence": r.confidence_at_merge,
                "merge_type": r.merge_type,
                "mapped_codes": [
                    {"cpse": m.source_cpse, "original_code": m.original_code}
                    for m in r.mappings
                ],
            }
            for r in rows
        ],
    }
