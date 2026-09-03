"""
Tier 1 -> Tier 2 Integration
Reads Tier 1's actual output (processed_catalog.jsonl) and runs the matching
engine on it — no hardcoded item list. This is the first real end-to-end link
in the pipeline, per the contract in ARCHITECTURE.md.
"""

import json
import itertools
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from rapidfuzz import fuzz

CONFIDENCE_THRESHOLD = 0.85
UNIT_EQUIVALENCE = {"EA": "EA", "Nos": "EA", "PCS": "EA", "Each": "EA", "KG": "KG"}


def load_tier1_output(path: str) -> list:
    items = []
    with open(path) as f:
        for line in f:
            items.append(json.loads(line))
    return items


def spec_match_score(item_a: dict, item_b: dict) -> float:
    """Uses Tier 1's already-extracted spec tokens, not raw text re-parsing."""
    tokens_a = set(t.strip().lower() for t in item_a["specs"].get("raw_tokens", []) if t.strip())
    tokens_b = set(t.strip().lower() for t in item_b["specs"].get("raw_tokens", []) if t.strip())
    if not tokens_a and not tokens_b:
        return 0.5
    if not tokens_a or not tokens_b:
        return 0.3
    overlap = len(tokens_a & tokens_b)
    total = len(tokens_a | tokens_b)
    return overlap / total if total else 0.5


def unit_compat_score(unit_a: str, unit_b: str) -> float:
    return 1.0 if UNIT_EQUIVALENCE.get(unit_a) == UNIT_EQUIVALENCE.get(unit_b) else 0.4


def run_matching(items: list) -> list:
    descriptions = [it["clean_description"] for it in items]
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    tfidf_matrix = vectorizer.fit_transform(descriptions)
    sim_matrix = cosine_similarity(tfidf_matrix)

    results = []
    for i, j in itertools.combinations(range(len(items)), 2):
        a, b = items[i], items[j]
        if a["source_cpse"] == b["source_cpse"]:
            continue  # only cross-CPSE matches matter for deduplication

        text_sim = float(sim_matrix[i][j])
        fuzzy_sim = fuzz.token_sort_ratio(a["clean_description"], b["clean_description"]) / 100.0
        text_score = 0.7 * text_sim + 0.3 * fuzzy_sim
        spec_score = spec_match_score(a, b)
        unit_score = unit_compat_score(a["unit_of_measure"], b["unit_of_measure"])

        confidence = 0.5 * text_score + 0.3 * spec_score + 0.2 * unit_score
        status = "auto_linked" if confidence >= CONFIDENCE_THRESHOLD else "needs_review"

        results.append({
            "match_id": f"M-{a['item_id']}-{b['item_id']}",
            "item_a": a["item_id"], "item_b": b["item_id"],
            "confidence_score": round(confidence, 3),
            "score_breakdown": {
                "text_similarity": round(text_score, 3),
                "spec_match": round(spec_score, 3),
                "unit_compatibility": round(unit_score, 3),
            },
            "status": status,
        })

    results.sort(key=lambda r: -r["confidence_score"])
    return results


if __name__ == "__main__":
    items = load_tier1_output("processed_catalog.jsonl")
    print(f"Loaded {len(items)} real items from Tier 1's actual output\n")

    matches = run_matching(items)
    print(f"{'='*90}\nMATCH RESULTS — {len(matches)} cross-CPSE pairs (Tier 1 -> Tier 2, end-to-end)\n{'='*90}\n")

    id_to_desc = {it["item_id"]: it["clean_description"] for it in items}
    for m in matches:
        print(f"[{m['status']:12}] confidence={m['confidence_score']}  {m['score_breakdown']}")
        print(f"    A: {m['item_a']} — \"{id_to_desc[m['item_a']]}\"")
        print(f"    B: {m['item_b']} — \"{id_to_desc[m['item_b']]}\"")
        print()

    with open("tier2_match_output.json", "w") as f:
        json.dump(matches, f, indent=2)
    print("Saved match records to tier2_match_output.json — ready for Tier 3/4")

    auto = sum(1 for m in matches if m["status"] == "auto_linked")
    print(f"\nSUMMARY: {auto} auto-linked, {len(matches)-auto} need review, out of {len(matches)} pairs")
