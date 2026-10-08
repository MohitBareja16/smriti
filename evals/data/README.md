# Datasheet: Alex Demo evaluation data

Following the spirit of *Datasheets for Datasets* (Gebru et al., 2021).

## What is it?

A small, **fully fictional** dataset for developing and evaluating Smriti:

| File | Contents | Items | Split |
|---|---|---|---|
| `alex_demo/` | Documents of a fictional B.Tech student, "Alex Demo": 3 personal (exam timetable, grade card, certificates) and 6 study files (OS notes, DBMS notes, OS past papers, a Galvin chapter summary, a classmate's notes with a planted prompt injection, and two project write-ups). `manifest.json` lists each file's kind, course and semester. | 9 docs | – |
| `qa.jsonl` | Questions with gold answers (`expect_contains`), gold source (`expect_source`) and gold intent. `expect_idk: true` marks unanswerable questions. Items `k1`–`k3` (added 2026-10-08) test knowledge-graph connection questions. | 26 | dev |
| `redteam.jsonl` | `attack` (should be blocked), `indirect` / `leak` (answer must not contain `must_not_contain`), `benign` look-alikes (must **not** be blocked). | 11 | dev |
| `router.jsonl` | Questions labelled only with their intent, for router accuracy and calibration. | 40 | dev |
| `grounding.jsonl` | (answer sentence, evidence document, supported?) pairs for the grounding benchmark (#9). 33 supported (verbatim/paraphrase), 32 unsupported (contradiction, swapped fact, unsupported addition, off-topic). 23 come from real qwen2.5:3b / phi3 answers (`origin`), the rest were written. | 65 | dev |

Intents: `fact_lookup`, `fetch_doc`, `explain`, `compare`, `exam_prep`, `connect`, `other`.

## How was it made?

Written by the project authors. **Important:** `qa.jsonl` and `redteam.jsonl` were written *at the same time as* the rules-based System 1, and `router.jsonl` was written later by the same author, without tuning the rules on it afterwards. All three are therefore **development data**. Results on them show the system works, but they are optimistic estimates. A blind **test** split, written by someone who has not read `src/smriti/decision/rules.py`, is work package WP1 in [docs/research/TASKS.md](../../docs/research/TASKS.md).

All names, numbers, IDs and emails are invented. The "Aadhaar" number `9999 8888 7777` and `alex.demo@example.edu` are deliberately fake test values. The Galvin summary is our own writing, not text from the book.

Labels in `grounding.jsonl` were assigned by the developers (one annotator, no adjudication). "Supported" means *stated in the evidence document*. Correct general knowledge that isn't in the notes counts as **unsupported**, because Smriti must only answer from the user's own material.

## Format

One JSON object per line. Common fields: `id` (unique within the file), `question`, `intent`, `split` (`dev` or `test`; a missing field means `dev`).

```json
{"id": "f1", "question": "When is my DBMS exam?", "intent": "fact_lookup",
 "expect_contains": ["10 December 2026"], "expect_source": "exam_timetable", "split": "dev"}
```

## Rules for adding items

- Keep it **fictional**, with no real people or real documents. Openly licensed textbook excerpts are allowed (cite the license in the file header).
- Give each item a new unique `id`. Never edit or reuse the id of an item that has already been used in a reported result; add a new item instead.
- `expect_contains` should be short and unambiguous: a date, a number or a key term, not a full sentence.
- New `test` items must be written **without** looking at the rules engine or at system outputs.
- Changing any file changes the dataset fingerprint recorded in each run's `dataset.json`, so results always name the exact data they used.

## Known limitations

- Small: 23 QA items is enough to debug, but not to draw statistically solid conclusions. Report counts, not just percentages.
- One fictional student, one domain (Indian B.Tech CSE), English only.
- Correctness is string matching, which favours short factual answers. An LLM-judge metric is planned (WP5).
