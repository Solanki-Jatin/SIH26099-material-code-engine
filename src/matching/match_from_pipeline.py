"""
Tier 1 -> Tier 2 Integration

Reads Tier 1's actual output (processed_catalog.jsonl), calculates
cross-CPSE similarity, and applies the Tier 2 Safety Gate.

Safety Gate rules:
1. Pressure class mismatch -> BLOCK
2. Material grade mismatch -> BLOCK
3. Blocked matches never become auto_linked or needs_review.
"""

import json
import itertools

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from rapidfuzz import fuzz


CONFIDENCE_THRESHOLD = 0.85

UNIT_EQUIVALENCE = {
    "EA": "EA",
    "Nos": "EA",
    "PCS": "EA",
    "Each": "EA",
    "KG": "KG",
}


def load_tier1_output(path: str) -> list:
    """Load Tier 1 standardized JSONL output."""
    items = []

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))

    return items


def spec_match_score(item_a: dict, item_b: dict) -> float:
    """
    Compare structured Tier 1 specifications.

    Pressure rating and material grade are handled separately by
    the Safety Gate and are not allowed to be overridden by similarity.
    """

    specs_a = item_a.get("specs", {})
    specs_b = item_b.get("specs", {})

    scores = []

    # Size
    size_a = specs_a.get("size")
    size_b = specs_b.get("size")

    if size_a and size_b:
        scores.append(1.0 if size_a.lower() == size_b.lower() else 0.0)

    # Material grade
    material_a = specs_a.get("material_grade")
    material_b = specs_b.get("material_grade")

    if material_a and material_b:
        scores.append(
            1.0 if material_a.lower() == material_b.lower() else 0.0
        )

    # Pressure rating
    pressure_a = specs_a.get("pressure_rating")
    pressure_b = specs_b.get("pressure_rating")

    if pressure_a and pressure_b:
        scores.append(
            1.0 if str(pressure_a) == str(pressure_b) else 0.0
        )

    # Other attributes / standards
    other_a = specs_a.get("other_attrs", {})
    other_b = specs_b.get("other_attrs", {})

    if other_a and other_b:
        common_keys = set(other_a) & set(other_b)

        if common_keys:
            matches = sum(
                1
                for key in common_keys
                if str(other_a[key]).lower() == str(other_b[key]).lower()
            )
            scores.append(matches / len(common_keys))

    if not scores:
        return 0.5

    return sum(scores) / len(scores)


def unit_compat_score(unit_a: str, unit_b: str) -> float:
    """Return unit compatibility score."""
    return (
        1.0
        if UNIT_EQUIVALENCE.get(unit_a) == UNIT_EQUIVALENCE.get(unit_b)
        else 0.4
    )


def safety_gate(item_a: dict, item_b: dict) -> tuple[bool, str | None]:
    """
    Apply mandatory Safety Gate rules.

    Returns:
        (blocked, reason)

    A mismatch is blocked only when both records contain the
    corresponding critical attribute.
    """

    specs_a = item_a.get("specs", {})
    specs_b = item_b.get("specs", {})

    pressure_a = specs_a.get("pressure_rating")
    pressure_b = specs_b.get("pressure_rating")

    material_a = specs_a.get("material_grade")
    material_b = specs_b.get("material_grade")

    # Rule 1: Pressure class mismatch
    if pressure_a and pressure_b and str(pressure_a) != str(pressure_b):
        return (
            True,
            f"Pressure class mismatch: {pressure_a} vs {pressure_b}",
        )

    # Rule 2: Material grade mismatch
    if material_a and material_b and material_a.lower() != material_b.lower():
        return (
            True,
            f"Material grade mismatch: {material_a} vs {material_b}",
        )

    return False, None


def run_matching(items: list) -> list:
    """
    Generate cross-CPSE match candidates and apply Safety Gate.
    """

    descriptions = [it["clean_description"] for it in items]

    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4),
    )

    tfidf_matrix = vectorizer.fit_transform(descriptions)
    sim_matrix = cosine_similarity(tfidf_matrix)

    results = []

    for i, j in itertools.combinations(range(len(items)), 2):

        a = items[i]
        b = items[j]

        # Only compare items from different CPSEs
        if a["source_cpse"] == b["source_cpse"]:
            continue

        # Similarity calculation
        text_sim = float(sim_matrix[i][j])

        fuzzy_sim = (
            fuzz.token_sort_ratio(
                a["clean_description"],
                b["clean_description"],
            )
            / 100.0
        )

        text_score = 0.7 * text_sim + 0.3 * fuzzy_sim

        spec_score = spec_match_score(a, b)

        unit_score = unit_compat_score(
            a["unit_of_measure"],
            b["unit_of_measure"],
        )

        confidence = (
            0.5 * text_score
            + 0.3 * spec_score
            + 0.2 * unit_score
        )

        # ---------------------------------------------------------
        # SAFETY GATE
        # ---------------------------------------------------------

        blocked, block_reason = safety_gate(a, b)

        if blocked:
            status = "safety_gate_blocked"
        elif confidence >= CONFIDENCE_THRESHOLD:
            status = "auto_linked"
        else:
            status = "needs_review"

        result = {
            "match_id": f"M-{a['item_id']}-{b['item_id']}",
            "item_a": a["item_id"],
            "item_b": b["item_id"],
            "source_cpse_a": a["source_cpse"],
            "source_cpse_b": b["source_cpse"],
            "confidence_score": round(confidence, 3),
            "score_breakdown": {
                "text_similarity": round(text_score, 3),
                "spec_match": round(spec_score, 3),
                "unit_compatibility": round(unit_score, 3),
            },
            "status": status,
        }

        if blocked:
            result["block_reason"] = block_reason

        results.append(result)

    results.sort(
        key=lambda r: -r["confidence_score"]
    )

    return results


if __name__ == "__main__":

    items = load_tier1_output(
    "processed_catalog.jsonl"
)
    print(
        f"Loaded {len(items)} real items from Tier 1's actual output\n"
    )

    matches = run_matching(items)

    print(
        f"{'=' * 90}\n"
        f"MATCH RESULTS — {len(matches)} cross-CPSE pairs\n"
        f"Tier 1 -> Tier 2 -> Safety Gate\n"
        f"{'=' * 90}\n"
    )

    id_to_desc = {
        it["item_id"]: it["clean_description"]
        for it in items
    }

    for match in matches:

        print(
            f"[{match['status']:20}] "
            f"confidence={match['confidence_score']} "
            f"{match['score_breakdown']}"
        )

        print(
            f"    A: {match['item_a']} "
            f"({match['source_cpse_a']}) — "
            f"\"{id_to_desc[match['item_a']]}\""
        )

        print(
            f"    B: {match['item_b']} "
            f"({match['source_cpse_b']}) — "
            f"\"{id_to_desc[match['item_b']]}\""
        )

        if match["status"] == "safety_gate_blocked":
            print(
                f"    >>> SAFETY GATE BLOCKED: "
                f"{match['block_reason']}"
            )

        print()

    with open(
        "tier2_match_output.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(matches, f, indent=2)

    print(
        "Saved match records to tier2_match_output.json"
    )

    auto = sum(
        1
        for m in matches
        if m["status"] == "auto_linked"
    )

    review = sum(
        1
        for m in matches
        if m["status"] == "needs_review"
    )

    blocked = sum(
        1
        for m in matches
        if m["status"] == "safety_gate_blocked"
    )

    print("\n" + "=" * 90)
    print("TIER 2 SUMMARY")
    print("=" * 90)
    print(f"Auto-linked          : {auto}")
    print(f"Needs review         : {review}")
    print(f"Safety Gate blocked  : {blocked}")
    print(f"Total pairs          : {len(matches)}")