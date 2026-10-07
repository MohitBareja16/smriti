# Work packages

Self-contained tasks for contributors. Each one says **why** it matters (which research question), **what** to deliver, and **how we'll know it's done**. Each has a matching [GitHub issue](https://github.com/MohitBareja16/smriti/issues). Comment there to claim one.

Before you start, read [docs/research/README.md](README.md) (especially §4, the protocol) and [CONTRIBUTING.md](../../CONTRIBUTING.md).

| WP | Title | RQ | Size | Good first? |
|---|---|---|---|---|
| WP1 | Blind test set | all | M | ✅ (no coding) |
| WP2 | SetFit System-1 router | RQ5, RQ1 | M | |
| WP3 | jeff System-1 engine | RQ5 | M | |
| WP4 | Hybrid retrieval (BM25 + vectors) | RQ3 | M | |
| WP5 | LLM-judge correctness and faithfulness | RQ3 | M | |
| WP6 | Red-team expansion and guard benchmark | RQ4 | S–M | ✅ |
| WP7 | OCR for scanned documents | – | M | |
| WP8 | Phoenix tracing and per-step cost accounting | RQ2 | S | ✅ |

---

## WP1: Blind test set
**Why:** all current data is `dev` and was written alongside the rules, so results are optimistic. Every final claim needs a blind test set.
**Do:**
- Without reading `src/smriti/decision/` or running Smriti, write **≥ 100 QA items** (balanced across intents, with **≥ 15 unanswerable**) and **≥ 40 red-team items** (attacks, leaks, benign look-alikes) for the Alex Demo documents.
- Add **≥ 100 router-only questions**.
- Use `"split": "test"` and ids prefixed `t-`. You may *read* `evals/data/alex_demo/` and add new fictional documents.
**Done when:** files pass `pytest`, `evals/data/README.md` is updated with counts and how the items were written, and nobody has run the system on the test items before merge.

## WP2: SetFit System-1 router
**Why:** RQ5. The rules router is right 84% of the time but poorly calibrated (ECE 0.144, see LOG 2026-10-07). A learned router should be more accurate and better calibrated.
**Do:** implement `SetFitEngine` in `src/smriti/decision/setfit_engine.py`, implementing the `DecisionEngine` protocol (`route` returns label probabilities). Train on **dev** data only (router, QA and synthetic paraphrases you generate), and save the model under `models/`. `is_injection` / `is_supported` may delegate to the rules engine at first. Register it in `ENGINES` behind an optional extra.
**Experiment:** `router_calibration` and `tau_sweep` configs with `"s1_engine": "setfit"`. Compare against rules on dev (and on test once WP1 lands).
**Done when:** the engine runs on CPU in under 20 ms per decision, has tests, has configs, and has a LOG entry.

## WP3: jeff System-1 engine
**Why:** RQ5 asks whether a general "System One" model (jeff, a self-hosted implementation of the Jev decision API) can replace hand-written rules.
**Do:** run jeff locally, write `JeffEngine` implementing `DecisionEngine` (route via a typed multiple-choice question, `is_injection` and `is_supported` via yes/no questions), and document setup in `docs/research/jeff.md`.
**Done when:** the same experiments as WP2 can be run with `"s1_engine": "jeff"`, and a LOG entry compares rules, SetFit and jeff.

## WP4: Hybrid retrieval
**Why:** RQ3. BM25 misses paraphrases ("convoy effect" vs. "slow first-come scheduling").
**Do:** add local embeddings (e.g. a small sentence-transformers model) with LanceDB or sqlite-vec next to FTS5, and merge the rankings with reciprocal rank fusion. Make it a setting (`retrieval: bm25 | hybrid`).
**Done when:** a `baselines` comparison of bm25 vs hybrid (same LLM) is logged, with citation accuracy and latency.

## WP5: LLM-judge correctness and faithfulness
**Why:** string matching (`expect_contains`) under-rates correct paraphrased answers. RQ3 needs faithfulness too.
**Do:** add an optional judge in `src/smriti/research/metrics.py`. The judge is a local model by default, and a stronger free API is allowed **only on public eval data**. It scores correctness (0/1) and faithfulness (claims supported by retrieved text). Validate it against 30 hand-labelled answers and report agreement.
**Done when:** `baselines` can report judge metrics next to string metrics, and judge agreement is logged.

## WP6: Red-team expansion and guard benchmark
**Why:** RQ4 claims need more than 11 cases. Rules-based guards are likely brittle against paraphrased attacks.
**Do:** grow `redteam.jsonl` (dev) to **≥ 80 items**: paraphrased, multilingual (Hindi/Hinglish), and indirect attacks via documents. Include benign look-alikes. Then compare the rules guard against an LLM-based guard (small model, yes/no) in a new experiment type.
**Done when:** a LOG entry reports attack success and false refusals for both guards, with examples of failures.

## WP7: OCR for scanned documents
**Why:** most real marksheets and certificates are scans. Today, PDFs without a text layer are skipped.
**Do:** use Docling (or Tesseract) in `src/smriti/ingest/parsers.py` behind an `ocr` extra, keeping page numbers. Add a scanned fictional certificate to the demo data.
**Done when:** the scanned certificate's facts are extracted, and a test covers it.

## WP8: Phoenix tracing and cost accounting
**Why:** RQ2 needs per-step latency and token costs, and Phoenix gives a visual trace for the report.
**Do:** verify `SMRITI_TRACING=phoenix` end to end, add token counts to spans, and write `docs/research/tracing.md` with screenshots.
**Done when:** a traced `tau_sweep` run is visible in Phoenix, and the doc explains how to reproduce it.
