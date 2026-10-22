"""Command line: python -m deepdoc.cli <command>

  generate                 build the demo PDF and its answer key
  ingest [PDF ...]         parse and index PDFs (default: every PDF in data/pdfs)
  ask "question"           answer one question with sources
  eval [--llm] [--limit N] score retrieval (and answers with --llm) on the answer key
  inspect PDF PAGE         print the parsed elements of one page in reading order
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from . import config


def cmd_generate(args) -> None:
    from .generator.build import build
    from .generator.facts import build_world
    from .generator.goldset import locate_pages, questions

    config.ensure_dirs()
    world = build_world(args.seed)
    out = config.PDF_DIR / config.DEMO_PDF_NAME
    t = time.time()
    pages = build(out, world, paras_per_section=args.paras)
    gold = locate_pages(str(out), questions(world))
    missing = [g["id"] for g in gold if not g["pages"]]
    (config.PDF_DIR / config.DEMO_GOLD_NAME).write_text(json.dumps(gold, indent=1, ensure_ascii=False))
    print(f"Built {out} — {pages} pages in {time.time() - t:.0f}s. Answer key: {len(gold)} questions.")
    if missing:
        print(f"WARNING: no page found for questions {missing}")


def cmd_ingest(args) -> None:
    from .ingest.pipeline import ingest_pdf

    config.ensure_dirs()
    paths = args.pdfs or sorted(str(p) for p in config.PDF_DIR.glob("*.pdf"))
    for p in paths:
        ingest_pdf(p, progress=lambda msg: print(msg, flush=True))


def cmd_ask(args) -> None:
    from .generate.answer import answer

    res = answer(args.question, use_llm=not args.no_llm)
    print(res["answer"])
    if res.get("calculator"):
        print(f"\n[0] calculator/lookup: {res['calculator']['text']}")
    print("\nSources:")
    for s in res["sources"]:
        print(f"  [{s['n']}] p.{s['page']} {s['kind']:<8} {s['section'][:60]}  (score {s['score']:.3f})")


def cmd_eval(args) -> None:
    from .eval.run import run_eval

    report = run_eval(use_llm=args.llm, limit=args.limit, types=args.type)
    (config.DATA_DIR / "last_eval.json").write_text(json.dumps(report))
    s = report["summary"]
    cols = ["n", "hit@1", f"hit@{config.TOP_K}", "mrr", "fact_recall"] + (["answer_accuracy"] if args.llm else [])
    print(f"{'type':<16}" + "".join(f"{c:>16}" for c in cols))
    for name, b in list(s["by_type"].items()) + [("OVERALL", s["overall"])]:
        print(f"{name:<16}" + "".join(f"{b[c]:>16}" for c in cols))
    print(f"{s['seconds']} s")
    for r in report["rows"]:
        if not r["fact_in_context"] or (args.llm and not r.get("answer_correct")):
            print(f"MISS [{r['type']}] {r['q']} -> expected {r['answers']} p{r['pages']} got pages {r['top_pages']}"
                  + (f" | answer: {r.get('answer', '')[:200]}" if args.llm else ""))


def cmd_inspect(args) -> None:
    import fitz

    from .ingest.layout import parse_page

    doc = fitz.open(args.pdf)
    for el in parse_page(doc[args.page - 1]).elements:
        print(f"[{el.order:>2}] {el.kind:<8} col={el.column} {tuple(round(v) for v in el.bbox)}")
        print("     " + el.text[:300].replace("\n", " ⏎ "))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="deepdoc")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate"); g.add_argument("--seed", type=int, default=2025); g.add_argument("--paras", type=int, default=12)
    g.set_defaults(fn=cmd_generate)
    i = sub.add_parser("ingest"); i.add_argument("pdfs", nargs="*"); i.set_defaults(fn=cmd_ingest)
    a = sub.add_parser("ask"); a.add_argument("question"); a.add_argument("--no-llm", action="store_true"); a.set_defaults(fn=cmd_ask)
    e = sub.add_parser("eval"); e.add_argument("--llm", action="store_true"); e.add_argument("--limit", type=int, default=0)
    e.add_argument("--type", action="append"); e.set_defaults(fn=cmd_eval)
    n = sub.add_parser("inspect"); n.add_argument("pdf"); n.add_argument("page", type=int); n.set_defaults(fn=cmd_inspect)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
