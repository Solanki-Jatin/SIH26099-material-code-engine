# Popeye — SIH26099: AI-Driven Material Code Standardization Across CPSEs

**Problem Statement:** SIH26099 — Ministry of Petroleum & Natural Gas
**Theme:** Smart Automation | **Category:** Software
**Team:** Popeye

## What This Is

Central Public Sector Enterprises (CPSEs) — ONGC, SAIL, Coal India, Oil India, etc. — each
maintain their own material master catalogs, built independently over decades. The same
physical item ends up with different codes, descriptions, and specs across companies,
causing duplicate inventory, fragmented procurement, and missed bulk-buying opportunities.

This project builds an AI-powered engine that:
1. Ingests material data from multiple CPSE catalogs (SAP/ERP exports, spreadsheets)
2. Matches items by **meaning**, not just spelling, using semantic embeddings
3. Scores each match on text similarity + spec compatibility + unit compatibility
4. Auto-links high-confidence matches, routes uncertain ones to human review
5. Generates a **Common National Material Code (CNMC)** with full traceability back to
   every original CPSE code

## Architecture (Top-Down)

```
Multi-CPSE Data (raw catalogs)
        │
        ▼
┌─────────────────────┐
│ TIER 1: Ingestion &  │  src/ingestion/
│ Preprocessing        │  Clean, standardize, parse units/specs
└──────────┬───────────┘
           ▼
┌─────────────────────┐
│ TIER 2: Matching &   │  src/matching/
│ Scoring Engine       │  Semantic embeddings + fuzzy + weighted scoring
│ (core — owned by X)  │  Text 50% + Specs 30% + Units 20%
└──────────┬───────────┘
           ▼
     Confidence Check
     ≥85%          <85%
      │              │
      ▼              ▼
 Auto-link     ┌─────────────────────┐
      │        │ TIER 3: Human Review │  src/review_api/
      │        │ Interface & API      │
      │        └──────────┬───────────┘
      │                   │
      └─────────┬─────────┘
                ▼
┌─────────────────────┐
│ TIER 4: Persistence, │  src/persistence/
│ Mapping & Audit      │  Generate CNMC, store legacy mapping, audit log
└──────────┬───────────┘
           ▼
┌─────────────────────┐
│ TIER 5: Dashboard &  │  src/dashboard/
│ Analytics            │  Duplicate stats, savings estimate, review queue
└─────────────────────┘
```

## Repo Structure

```
sih26099-material-code-engine/
├── README.md                  ← you are here
├── ARCHITECTURE.md            ← detailed data flow + tech decisions
├── docs/                      ← one spec doc per tier — READ BEFORE BUILDING
│   ├── tier1-ingestion.md
│   ├── tier2-matching-engine.md
│   ├── tier3-human-review.md
│   ├── tier4-persistence-audit.md
│   └── tier5-dashboard.md
├── data/
│   ├── raw/                   ← source catalogs (real + sample)
│   └── processed/             ← cleaned output from Tier 1
├── src/
│   ├── ingestion/
│   ├── matching/
│   ├── review_api/
│   ├── persistence/
│   └── dashboard/
├── scripts/                   ← one-off utility scripts (data extraction, etc.)
└── .github/ISSUE_TEMPLATE/    ← template for opening tier-tasks as issues
```

## How to Contribute (Team Workflow)

1. Read `ARCHITECTURE.md` first for the full picture.
2. Read your assigned tier's doc in `docs/` — it has the exact input/output contract,
   deliverables, and acceptance criteria. **Do not start coding before reading it.**
3. Open a GitHub Issue using the tier-task template for the piece you're building.
4. Work in your tier's folder under `src/`. Stick to the contract — someone else's code
   plugs directly into your output, so changing the format without flagging it breaks
   the integration.
5. When done, open a PR referencing your issue. Tag for review before merging to `main`.

## Status Tracking

Progress is tracked via GitHub Issues + a project board, one issue per tier deliverable,
broken into sub-tasks. See the Issues tab for current status.
