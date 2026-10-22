# DeepDoc RAG — Progress

## Status (2026-10-21): working end to end on the laptop

Everything below was run on the laptop: 5.7 GB RAM, 4 cores, no GPU.
Other local projects were stopped (`docker compose stop`) during the runs.

## What was tested

| Test | Result |
|---|---|
| Unit tests (`pytest`) | 14 passed |
| Cold start: empty data folder → `up` → demo PDF made → indexed → answers | Works. Index ready in 355 s |
| Ingest of the 131-page demo PDF | 347–358 s. App peak about 1 GB RAM. Laptop never under 3 GB free RAM |
| Upload: non-PDF file / fake PDF | Rejected with a clear message (400) |
| Upload: new 1-page two-column PDF | Indexed in 10 s, then removed with "Remove" |
| All web pages (Ask, Documents, Inspect, Evaluate, page images, PDF download) | HTTP 200 |
| A restart during ingest | Document shows "Interrupted by a restart. Click Index again." |

## Parsing found in the demo PDF

32 table parts, 25 charts (12 vector bar, 12 raster line, 1 raster pie), 13 side boxes,
12 footnotes, 138 headings. 260 running header/footer lines removed.
1,109 chunks: 719 text, 34 table, 306 table rows, 25 figure, 13 side box, 12 footnote.

## Retrieval score — all 187 questions (no LLM, top 6 sources)

| Where the answer lives | n | Right page first | Right page in top 6 | Exact fact in sources |
|---|---|---|---|---|
| Two-column text | 48 | 98% | 100% | 100% |
| Tables (KPI, projects) | 48 | 94% | 100% | 96% → 100% after the broken-word fix |
| Vector bar charts | 12 | 100% | 100% | 100% |
| Raster charts (OCR) | 13 | 100% | 100% | 100% |
| Side boxes | 12 | 100% | 100% | 100% |
| Footnotes | 12 | 100% | 100% | 100% |
| Finance table (merged headers) | 12 | 100% | 100% | 100% |
| Safety table | 12 | 100% | 100% | 100% |
| Landscape 14-column table | 12 | 92% | 100% | 100% |
| Multi-hop (compare all regions) | 2 | 50% | 100% | 100% |
| Glossary / summary | 4 | 25% | 75% | 100% |
| **Overall** | **187** | **95%** | **99.5%** | **98.9%** (before the fix) |

"Right page first" is low for glossary/summary because the same fact is also on the
contents page or the key-figure grid. The fact itself is always found.

## Answer score with the LLM (qwen2.5:1.5b, 24 mixed questions)

- Before the exact tools: 87% (13 of 15) and then 96% (23 of 24).
- After adding the table cell lookup: 100% (24 of 24) — see the last section.

The small model made three kinds of mistakes. Each now has an exact Python tool:

| Mistake | Tool |
|---|---|
| "Which region has the highest capex?" — read the first row | `table_extreme`: max/min of a table column |
| Chart Q3 value — copied a wrong number | `chart_lookup`: exact label → value from the parsed chart |
| Comparing 12 numbers across 12 chapters | `text_extreme`: best sentence per chapter, compare in Python |
| Wide table — read the wrong column | `table_cell_lookup`: row name + column name → cell |

An output check replaces the LLM answer when it does not match the exact tool result.

## Bugs found and fixed during testing

- Justified text was cut into one-word "lines" → lines on one baseline are glued.
- Merged header "Result" over "2024 | 2025" only reached one column → short rules under a label, and empty upper cells, mark a merged cell.
- A false merge ("Total Grants received") → a label counts for a column only if 35%+ of it sits over that column.
- The bar chart's axes were read as a table grid → charts with bars are found before grid tables.
- A sentence split over a page break kept only its second page → both pages and both boxes are kept.
- Words broken inside narrow cells ("Complete|d", "CAL-18|5") → glued back (1–2 letter or digit fragments only, never "of", "the" …).
- One-line footnotes got lost inside long chunks → each footnote is also its own chunk.

## Still open (needs the server)

- [ ] Deploy to the 8 GB server (`docker-compose.prod.yml`, own Ollama capped at 4 GB).
- [ ] Full `eval --llm` on all 187 questions (about 50 min on the laptop; quicker on the server).
- [ ] Try `llama3.2:3b` on the server and compare with qwen2.5:1.5b.
- [ ] Try `VLM_MODEL=moondream` for raster charts (about 1.7 GB; not enough disk on the laptop).
- [ ] Edge cases not covered by the demo PDF: scanned PDFs (no text layer), rotated pages, password PDFs.
- [ ] Screenshots for the listing.

## Last LLM run

2026-10-21, qwen2.5:1.5b, 24 mixed questions (2 per content type), with all exact tools:
**answer accuracy 100% (24 of 24)**, exact fact in sources 100%, right page in top 6 96%.
Took 1,533 s (about 64 s per answer on the laptop CPU). Lowest free RAM on the laptop during the run: 1.16 GB.
