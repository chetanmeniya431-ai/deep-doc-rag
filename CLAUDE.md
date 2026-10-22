# DeepDoc RAG — Sub-project CLAUDE.md

## What this product does

Most RAG tools (systems where the AI first searches your documents, then answers)
break on real business PDFs. They read two-column pages straight across, so
sentences from two columns get mixed. They flatten tables, so numbers lose their
column names. They skip charts, because chart numbers are drawings or pixels, not text.

DeepDoc RAG reads a PDF the way a person does: down each column, table cell by
table cell, and inside charts. Then it answers questions with the exact page and
the spot on the page as proof. It is for developers and small teams who build
AI search over annual reports, research papers, manuals and financial filings.
Everything runs on free models on your own server. There is no per-page or per-question fee.

**Value:** a paid parsing API costs about $0.01–$0.06 per page. A 150-page report
costs $2–$9 each time it is parsed. This product costs $0 per page, and it ships
with a test that shows its accuracy on a hard 131-page PDF.

**Domains (Nirmantra scope):** RAG, Advanced retrieval, Evaluation, Structured output.

## Tech stack (fixed — do not change)

This project is **pure Python**, by owner decision on 2026-10-21. It is an exception to
the Laravel rule, like the Go resume screener: PDF layout work, OCR and ONNX models
are Python-native. Docker is still required.

- Language: Python 3.11 (in Docker; the host has only Python 3.8)
- Web: FastAPI + Jinja2 templates + Tailwind CSS (Play CDN) — no Node build step
- Storage: SQLite (one file) with FTS5 for BM25 keyword search, vectors stored as BLOBs
- PDF: PyMuPDF (reading), reportlab + matplotlib (making the demo PDF)
- OCR: Tesseract (reads text inside chart images)
- Embeddings: `BAAI/bge-small-en-v1.5` via fastembed (ONNX, CPU, about 70 MB)
- Re-ranker: `Xenova/ms-marco-MiniLM-L-6-v2` cross-encoder via fastembed (about 90 MB)
- LLM: `qwen2.5:1.5b` through Ollama (free, local, ~1.1 GB RAM). On the server `llama3.2:3b` is an option.
  Optional vision model (`VLM_MODEL`, e.g. `moondream`)
- No paid API anywhere. No torch (keeps the image small).

## Assigned ports

- APP_PORT: 8012
- DB: none (SQLite file inside the `appdata` volume)

## Docker setup

```bash
cp .env.example .env
docker compose up -d --build   # first start builds the 131-page demo PDF and indexes it in the background (~6 min on the laptop)
open http://localhost:8012
```

- **Laptop:** `docker-compose.override.yml` joins the network of the Ollama container
  that already runs for `universal-rag-platform`, so no models are downloaded twice.
  `.env` sets `OLLAMA_URL=http://universal-rag-platform-ollama-1:11434`.
- **Server:** `docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile ollama up -d`
  then `docker compose exec ollama ollama pull llama3.2:3b`.
- If no LLM is reachable, the app still works in **quote mode** (exact sentences/rows).

## RAM plan (do not break this)

Two machines: this laptop (5.7 GB RAM, 4 cores, no GPU) and an 8 GB KVM server.

| Part | Laptop | Server (8 GB) |
|---|---|---|
| App container (`mem_limit`) | 2 GB, 2.5 CPUs | 2.5 GB, 3 CPUs |
| ONNX threads (`MODEL_THREADS`) | 2 | 3 |
| LLM | qwen2.5:1.5b (~1.1 GB) | qwen2.5:1.5b or llama3.2:3b (~2.6 GB) |
| Ollama cap | shared container | 4 GB, 1 model loaded at a time |

- Measured peak during ingest of the 131-page PDF: see PROGRESS.md.
- The LLM unloads after `LLM_KEEP_ALIVE` (2 min) idle, so RAM comes back.
- On the laptop, stop the other projects first (`docker compose stop` in each folder).
  They are only stopped, not removed: `docker compose start` brings them back.
- Speed is not a goal for the demo. Never raise limits just to go faster on the laptop.

## Layout of the code

```
deepdoc/
  generator/   facts.py (made-up world) · prose.py · charts.py · build.py (PDF) · goldset.py (answer key)
  ingest/      layout.py (one page → typed elements in reading order)
               structure.py (whole-doc: headers/footers, heading levels, tables over pages)
               chunker.py (structure-aware chunks) · pipeline.py (parse → chunk → embed → store)
  index/       store.py (SQLite + FTS5 + vectors) · models.py (fastembed embed + rerank)
  retrieve/    search.py (query analysis → BM25 + dense → RRF → cross-encoder)
  generate/    llm.py (Ollama client) · answer.py (cited answers, quote-mode fallback)
  eval/        run.py (page hit@k, MRR, fact recall, answer accuracy, per content type)
  web/         app.py (FastAPI) · templates/
  cli.py       generate | ingest | ask | eval | inspect
```

## Features (MVP scope)

1. **Layout-aware parsing.** Two-column reading order (full-width items cut the page into
   bands; each band is read left column then right column). Running headers and footers
   are found by repetition and removed. Headings get levels from font size and the PDF outline.
2. **Deep tables.** Finds tables drawn with only horizontal rules (PyMuPDF's own finder misses
   these), rebuilds columns from white space, joins multi-row and merged headers
   ("Result" over "2024 | 2025" → "Result 2024", "Result 2025"), joins tables that continue
   on the next page, and indexes every row as "column: value" pairs.
3. **Charts and side boxes.** Vector bar charts: each bar is paired with its value label and
   category ("Q3: 802.5"). Raster charts: Tesseract OCR reads titles, labels and notes.
   Side boxes and footnotes become their own chunks. Optional vision model describes charts.
4. **Hybrid search with citations.** BM25 + vectors, fused with RRF (reciprocal rank fusion,
   a way to merge two ranked lists), then a cross-encoder re-ranks. Answers cite numbered
   sources; the UI highlights the exact box on the rendered page. Comparison questions
   ("which region had the most…") take the best chunk from every chapter. Small exact tools
   (table max/min, chart value lookup, table cell lookup, cross-chapter compare) give the
   small LLM exact numbers, and an output check replaces an answer that disagrees with them.
5. **Built-in evaluation.** The demo PDF comes with a 187-question answer key, split by
   where the answer lives (two-column text, table, vector chart, raster chart, side box,
   footnote, landscape table, multi-hop). The Evaluate page and `cli eval` score it.

## Synthetic data plan

`python -m deepdoc.cli generate` builds **"Velmora Regional Infrastructure Authority —
Integrated Annual Review 2025"**: a 131-page report about a made-up country.
Every name and number is invented and comes from a fixed random seed.

It holds: cover, contents, chair's letter, an executive summary with a 2×3 key-figure grid,
12 regional chapters (band page with a merged-header KPI table, two-column text,
a side box, a footnote, a raster line chart, a vector bar chart, a project table),
a finance chapter (merged headers, totals row), a safety chapter (table + pie chart),
a landscape page with a 14-column table, a project register that runs over several pages,
and a two-column glossary. Two facts are split across a page break on purpose.

## Current results (CPU laptop)

Retrieval on all 187 questions: right page in top 6 = 99.5%, exact fact in sources = 98.9%.
LLM answers (qwen2.5:1.5b, 24 mixed questions, 2 per content type): 100% (24 of 24). Details in PROGRESS.md.

## Design

Inherits the Nirmantra design system. Accent colour: **emerald**.
Sidebar + main content, Inter font, Heroicons inline SVG, `rounded-lg` cards with `shadow-sm`,
buttons `px-4 py-2 text-sm`, tables with `text-xs uppercase tracking-wide text-gray-500` headers.
Product-specific: the Ask page shows the answer, the sources, and the page image with the
cited box highlighted. The Inspect page draws every parsed element on the page, coloured by type,
numbered in reading order.

## Quality checklist

- [x] Cold start works with docker compose up only (demo PDF is made on first start)
- [x] Works end-to-end on seeded synthetic data
- [x] No hard-coded credentials or localhost in code
- [x] .env.example documents every variable
- [x] Manually tested on the demo PDF, uploads and bad files (scanned/rotated/password PDFs still open — see PROGRESS.md)
- [x] All assets properly licensed (DejaVu fonts: free licence; models: Apache-2.0 / MIT; Heroicons: MIT)
- [ ] Live demo deployment (needs the server)

## Things to check on the server (not possible on this laptop)

The laptop has 4 CPU cores, 5.7 GB RAM, no GPU and little free disk.

- Full `eval --llm` on all 187 questions (slow on the laptop).
- `llama3.2:3b` or `qwen2.5:3b` for better comparison answers (fits the 8 GB server; a 7B model does not fit safely).
- `VLM_MODEL=moondream` (about 1.7 GB) to describe raster charts during ingest.
- A larger re-ranker (`BAAI/bge-reranker-base`) if CPU time allows.
- Ingest speed on the server's CPUs.

## Rules for this sub-project

- Free models only. Never add a paid API.
- Synthetic data only. Never index a real company's private document in the demo.
- Keep everything configurable through `.env`.
- Writing style for all user-facing text: short sentences, simple words, explain jargon.
