"""
Tier 1 — Data Ingestion & Preprocessing
Reads raw multi-CPSE catalog files (different column names per source) and
outputs a standardized list of items matching the schema in ARCHITECTURE.md.
"""

import re
import json
import pandas as pd

# Config: maps each CPSE's actual column names to our standard field names.
# Adding a new CPSE source = adding one entry here, no code changes needed.
COLUMN_MAP = {
    "ONGC": {"id": "Material Code", "desc": "Description", "unit": "UOM"},
    "SAIL": {"id": "Item No", "desc": "Material Description", "unit": "Unit"},
}

# Simple abbreviation expansion for cleaning
ABBREVIATIONS = {
    r"\bWN\b": "Weld Neck",
    r"\bRF\b": "Raised Face",
    r"\bSO\b": "Slip-On",
    r"\bSS\b": "Stainless Steel",
    r"\bCS\b": "Carbon Steel",
}

SPEC_PATTERNS = [
    r"\d+#", r"class\s?\d+", r"\d+\s?(in|inch|IN|NB)", r"A\d{3}(\s?[A-Z0-9]+)?",
    r"F\d{3}", r"WCB", r"api\s?6d", r"asme\s?b16\.\d+", r"\d+\s?(hp|HP)", r"\d+\s?(v|V)",
]

UNIT_EQUIVALENCE = {
    "EA": "EA", "Nos": "EA", "PCS": "EA", "Each": "EA", "KG": "KG",
}


def clean_description(raw_desc: str) -> str:
    """Expand common abbreviations, normalize whitespace."""
    cleaned = raw_desc
    for pattern, expansion in ABBREVIATIONS.items():
        cleaned = re.sub(pattern, expansion, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def extract_specs(desc: str) -> dict:
    """Pull out size/pressure-class/material-grade style tokens."""
    found = []
    for pattern in SPEC_PATTERNS:
        found.extend(re.findall(pattern, desc, flags=re.IGNORECASE))
    return {"raw_tokens": [str(f) for f in found]} if found else {}


def normalize_unit(unit: str) -> str:
    return UNIT_EQUIVALENCE.get(unit.strip(), unit.strip())


def load_catalog(filepath: str, cpse: str) -> list:
    """Load one CPSE's catalog file and return standardized records."""
    if cpse not in COLUMN_MAP:
        raise ValueError(f"No column mapping configured for {cpse}. Add one to COLUMN_MAP.")

    cols = COLUMN_MAP[cpse]
    df = pd.read_csv(filepath) if filepath.endswith(".csv") else pd.read_excel(filepath)

    records = []
    for _, row in df.iterrows():
        raw_desc = str(row[cols["desc"]])
        records.append({
            "item_id": str(row[cols["id"]]),
            "source_cpse": cpse,
            "raw_description": raw_desc,
            "clean_description": clean_description(raw_desc),
            "specs": extract_specs(raw_desc),
            "unit_of_measure": normalize_unit(str(row[cols["unit"]])),
            "category_hint": None,
        })
    return records


if __name__ == "__main__":
    all_items = []
    all_items += load_catalog("sample_ongc_catalog.csv", "ONGC")
    all_items += load_catalog("sample_sail_catalog.csv", "SAIL")

    print(f"Loaded and standardized {len(all_items)} items from {len(COLUMN_MAP)} different CPSE catalog formats\n")
    for item in all_items:
        print(json.dumps(item, indent=2))
        print()

    with open("processed_catalog.jsonl", "w") as f:
        for item in all_items:
            f.write(json.dumps(item) + "\n")
    print(f"Saved standardized output to processed_catalog.jsonl — ready for Tier 2")
