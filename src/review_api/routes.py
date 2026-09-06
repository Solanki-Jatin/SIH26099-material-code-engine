import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..persistence.database import SessionLocal
from ..persistence.service import process_match


router = APIRouter(prefix="/api", tags=["Tier 3 Review"])


class ReviewDecisionRequest(BaseModel):
    match_id: str
    reviewer_decision: str
    reviewer_id: str
    reviewed_at: datetime
    notes: str = ""


review_decisions = {}


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TIER1_FILE = PROJECT_ROOT / "processed_catalog.jsonl"
TIER2_FILE = PROJECT_ROOT / "tier2_match_output.json"


def load_tier1_catalog():
    """Load Tier 1 standardized catalog."""
    if not TIER1_FILE.exists():
        raise HTTPException(
            status_code=500,
            detail="Tier 1 output file not found.",
        )

    catalog = {}

    with TIER1_FILE.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line:
                continue

            item = json.loads(line)
            catalog[item["item_id"]] = item

    return catalog


def load_tier2_matches():
    """Load the actual Tier 2 match output."""
    if not TIER2_FILE.exists():
        raise HTTPException(
            status_code=500,
            detail="Tier 2 output file not found.",
        )

    with TIER2_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def find_match(match_id: str):
    """Find a Tier 2 match using its match_id."""
    matches = load_tier2_matches()

    for match in matches:
        if match.get("match_id") == match_id:
            return match

    return None


def enrich_match(match: dict):
    """
    Add Tier 1 information required by Tier 4.

    The first item's standardized description is used as the
    canonical description for the approved merge.
    """
    catalog = load_tier1_catalog()

    item_a = catalog.get(match["item_a"])
    item_b = catalog.get(match["item_b"])

    if not item_a:
        raise HTTPException(
            status_code=404,
            detail=f"Tier 1 item not found: {match['item_a']}",
        )

    if not item_b:
        raise HTTPException(
            status_code=404,
            detail=f"Tier 1 item not found: {match['item_b']}",
        )

    enriched_match = dict(match)

    enriched_match["source_cpse_a"] = item_a["source_cpse"]
    enriched_match["source_cpse_b"] = item_b["source_cpse"]

    enriched_match["canonical_description"] = item_a["clean_description"]

    enriched_match["description_a"] = item_a["clean_description"]
    enriched_match["description_b"] = item_b["clean_description"]

    enriched_match["specs_a"] = item_a.get("specs", {})
    enriched_match["specs_b"] = item_b.get("specs", {})

    enriched_match["unit_a"] = item_a.get("unit_of_measure")
    enriched_match["unit_b"] = item_b.get("unit_of_measure")

    return enriched_match


@router.post("/review-decision")
def submit_review_decision(decision: ReviewDecisionRequest):

    if decision.reviewer_decision not in {"approved", "rejected"}:
        raise HTTPException(
            status_code=400,
            detail="reviewer_decision must be 'approved' or 'rejected'",
        )

    match = find_match(decision.match_id)

    if not match:
        raise HTTPException(
            status_code=404,
            detail=f"Tier 2 match not found: {decision.match_id}",
        )

    review_decisions[decision.match_id] = decision.model_dump(
        mode="json"
    )

    # Rejected matches do not create CNMC records.
    if decision.reviewer_decision == "rejected":
        return {
            "status": "review_recorded",
            "match_id": decision.match_id,
            "reviewer_decision": "rejected",
            "reviewer_id": decision.reviewer_id,
            "reviewed_at": decision.reviewed_at,
            "notes": decision.notes,
            "cnmc_code": None,
            "message": "Match rejected. No CNMC or mapping was created.",
        }

    # Enrich Tier 2 data with Tier 1 information.
    enriched_match = enrich_match(match)

    # Convert Tier 3 approval into a Tier 4 human-approved merge.
    enriched_match["status"] = "human_approved"

    db = SessionLocal()

    try:
        result = process_match(
            db,
            enriched_match,
            actor=decision.reviewer_id,
        )

        return {
            "status": "review_recorded",
            "match_id": decision.match_id,
            "reviewer_decision": "approved",
            "reviewer_id": decision.reviewer_id,
            "reviewed_at": decision.reviewed_at,
            "notes": decision.notes,
            "cnmc_code": result["cnmc_code"],
            "canonical_description": enriched_match[
                "canonical_description"
            ],
            "merge_type": result["merge_type"],
            "confidence_score": result["confidence_score"],
            "message": (
                "Tier 3 approval successfully created "
                "Tier 4 CNMC record."
            ),
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Tier 4 persistence failed: {exc}",
        ) from exc

    finally:
        db.close()