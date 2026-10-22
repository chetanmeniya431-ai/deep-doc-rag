# DeepDoc RAG

Ask questions about long, complex PDFs: two-column pages, tables with merged headers,
tables that run over several pages, charts, side boxes and footnotes.
Every answer shows the page and the exact spot on the page.
Free models only. Runs on your own machine or server.

## Quick start

```bash
cp .env.example .env
docker compose up -d --build   # first start builds the 131-page demo PDF and indexes it in the background (~6 min)
# open http://localhost:8012
```

No LLM? Leave `OLLAMA_URL` empty. The app then answers in **quote mode**: it shows the best
matching sentences or table rows, word for word.

On the server, the app shares one Ollama with the other demos. Put this in `.env`:

```bash
COMPOSE_FILE=docker-compose.yml:docker-compose.shared-ollama.yml:docker-compose.prod.yml
OLLAMA_URL=http://ollama:11434
LLM_MODEL=llama3.2:3b
```

Then run `docker compose up -d --build`. The prod file turns on the public demo guards:
the demo PDF cannot be deleted, uploads are capped, and LLM answers run as background jobs
so a slow CPU answer never hits a proxy timeout.

## Command line

| Command | What it does |
|---|---|
| `python -m deepdoc.cli generate` | Build the demo PDF and its 187-question answer key |
| `python -m deepdoc.cli ingest [file.pdf]` | Parse, chunk, embed and index PDFs |
| `python -m deepdoc.cli ask "question" [--no-llm]` | Answer one question with sources |
| `python -m deepdoc.cli eval [--llm] [--limit 30]` | Score search (and answers) on the answer key |
| `python -m deepdoc.cli inspect file.pdf 7` | Show how page 7 was parsed, in reading order |

Run them inside the container: `docker compose exec app <command>`.

## Web pages

- **Ask** — question box, example questions for each content type, answer with numbered
  citations, source cards, and the page image with the cited box highlighted.
- **Documents** — upload PDFs, see what was found (tables, charts, boxes, footnotes).
- **Inspect** — every parsed element drawn on the page, coloured by type and numbered in reading order.
- **Evaluate** — run the answer-key test and see scores by content type.

## How it works

1. **Layout** (`deepdoc/ingest/layout.py`): words and lines with font data → graphics
   (rules, fills, boxes) → tables, side boxes, charts, images → text blocks → headings,
   captions, footnotes → reading order (full-width items cut the page into bands; each band
   is read left column, then right column).
2. **Whole document** (`structure.py`): drop lines that repeat at the top or bottom of many
   pages, give headings levels, give each element its section path, join tables that continue.
3. **Chunks** (`chunker.py`): section text as one stream cut on sentence ends (~150 words);
   tables as Markdown plus one chunk per row; figures and boxes as their own chunks.
   Each chunk starts with "document › section" before it is embedded.
4. **Search** (`retrieve/search.py`): BM25 (SQLite FTS5) + vectors (bge-small) → RRF → cross-encoder.
5. **Answer** (`generate/answer.py`): qwen2.5:1.5b with numbered sources, or quote mode.
   Comparison questions ("which region had the most…") pull the best chunk from every chapter.

## Free models used

| Job | Model | Licence |
|---|---|---|
| Embeddings | BAAI/bge-small-en-v1.5 (ONNX) | MIT |
| Re-ranking | Xenova/ms-marco-MiniLM-L-6-v2 (ONNX) | Apache-2.0 |
| OCR | Tesseract 5 | Apache-2.0 |
| Answers | qwen2.5:1.5b via Ollama (default) | Apache-2.0 |
| Answers (server option) | llama3.2:3b via Ollama | Llama 3.2 Community Licence |
| Charts (optional) | moondream via Ollama | Apache-2.0 |

## Tests

```bash
docker compose run --rm app python -m pytest -q
```

## RAM and CPU

The app container is capped (`APP_MEM_LIMIT=2g`, `APP_CPUS=2.5`, `MODEL_THREADS=2`) so a big PDF
cannot freeze a small laptop. The LLM leaves RAM after 2 idle minutes (`LLM_KEEP_ALIVE`).
On an 8 GB server use `docker-compose.prod.yml`: app 2.5 GB + Ollama 4 GB.
