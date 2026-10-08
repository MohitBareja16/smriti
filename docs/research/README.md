# Smriti Research Guide

This is the starting point for anyone doing research on Smriti: the questions we study, how we measure them, and the rules that keep results trustworthy.

- **Run an experiment:** `smriti experiment list`, then `smriti experiment run <config>`, as described in [experiments/README.md](../../experiments/README.md)
- **What has been found so far:** [LOG.md](LOG.md)
- **Open work you can pick up:** [TASKS.md](TASKS.md) and the [GitHub issues](https://github.com/MohitBareja16/smriti/issues?q=is%3Aopen+label%3Aresearch)
- **The data:** [evals/data/README.md](../../evals/data/README.md) (datasheet)

## 1. Thesis

> Most agentic RAG systems run an expensive LLM agent on every question. A fast, **calibrated System 1**, made of small typed decisions with confidence scores, can answer many personal-knowledge questions on its own and guard every request. It escalates to a slow **System 2** agent only when it is unsure. This cuts latency and cost **without losing accuracy or safety**.

The terms come from Kahneman's *Thinking, Fast and Slow*. In Smriti:

| | System 1 (`src/smriti/decision/`) | System 2 (`src/smriti/agent/`) |
|---|---|---|
| Output | A typed label plus a probability (intent, yes/no) | Free text with citations |
| Jobs | Routing, direct fact answers, injection guard, grounding check, PII check | Plan, search, reason, answer |
| Cost | Under 1 ms, no LLM | One or more LLM calls, seconds |

The escalation policy (`src/smriti/orchestrator.py`) answers with System 1 when its confidence is at least **τ**, and otherwise escalates.

## 2. Research questions and hypotheses

| ID | Question | Hypothesis | Primary metrics | Experiment type |
|---|---|---|---|---|
| **RQ1** | Can System 1 answer a meaningful share of questions alone, at accuracy comparable to System 2? | For some range of τ, the System-1 share is above 0 and System-1 precision is at least System-2 accuracy | System-1 share, System-1 precision, accuracy vs τ | `tau_sweep` |
| **RQ2** | How much latency and compute does escalation save? | Mean latency and LLM calls fall roughly in proportion to the System-1 share | Mean and p95 latency, LLM calls/q, tokens/q | `tau_sweep` |
| **RQ3** | Does agentic retrieval beat plain RAG? | The agent (planning, course filters, wider retry) improves correctness on compare and exam-prep questions | Correctness, citation accuracy, faithfulness | `baselines` |
| **RQ4** | What do System-1 guardrails catch, and at what cost? | Guardrails cut attack success to near 0 with a false-refusal rate of at most 5% | Attack success, leak rate, false refusals | `baselines` (ablation) |
| **RQ5** | Which System-1 engine is best: rules, SetFit or jeff? | A learned engine (SetFit) beats rules on accuracy **and** calibration (lower ECE) | Router accuracy, ECE, ms/decision | `router_calibration` |

New questions are welcome. Open an issue with the **"Research question / experiment"** template.

## 3. Metrics (definitions live in `src/smriti/research/metrics.py`)

| Metric | Definition |
|---|---|
| **Correct** | Answerable item: every `expect_contains` string appears (case-insensitive) in the answer, its citations or the attachment. Unanswerable item: the system says "I don't know". |
| **Accuracy** | `baselines`: correct / answerable items. `tau_sweep`: correct / **all** items, so abstaining correctly counts. Always state which one you report. |
| **Citation accuracy** | Share of answerable items whose gold source document is among the citations. |
| **System-1 share** | Share of questions answered by System 1 without escalation. |
| **System-1 precision** | Accuracy on the questions System 1 answered alone. |
| **Latency** | Wall-clock ms per question, including System 1. Report the median (p50) and p95. Hardware matters, so `environment.json` records it. |
| **LLM calls / tokens per question** | Calls to the System-2 LLM, and prompt + completion tokens as reported by Ollama. |
| **Attack success** | Share of attack items that were **not** blocked. |
| **Leak rate** | Share of leak/indirect items whose answer contains a forbidden string. |
| **False refusal rate** | Share of benign look-alike items that were blocked. |
| **ECE** | Expected Calibration Error of the router, with 10 equal-width bins: Σ_b (\|b\|/N) · \|accuracy(b) − confidence(b)\|. |

## 4. Protocol (rules that keep results honest)

1. **Dev vs test.** Tune anything (rules, prompts, τ, models) **only on `dev`**. The `test` split is written blind, by someone who has not seen the rules, and is evaluated once per final claim. Today **only `dev` exists** (see TASKS: WP1), so all current results are dev results and must be labelled as such.
2. **Every number comes from a run folder.** Report results only from `experiments/results/<run>/`, which records the config, git commit, dataset fingerprint, model digest and hardware. Never paste numbers from an ad-hoc script.
3. **Commit before you run.** A run made with uncommitted changes is marked "(uncommitted changes)". Such runs are fine while exploring, but not for the report.
4. **Change one thing at a time.** Copy a config, change one setting, and give it a new `name`.
5. **Negative results are results.** Log every run that informed a decision in [LOG.md](LOG.md), including failures.
6. **No real personal data**, ever. Datasets are fictional or openly licensed.
7. **Determinism.** LLM temperature is 0. Expect small run-to-run differences in latency, not in answers. If answers differ between runs, log it.

## 5. Current status (2026-10-07, dev split only)

| Finding | Evidence |
|---|---|
| With qwen2.5:3b, τ = 0.6–0.9 keeps accuracy at 100% while cutting latency −20%, LLM calls −25%, tokens −22% | LOG: qwen τ sweep |
| With the weaker phi3, System 1 also **raises** accuracy (65% → 74%) | LOG: phi3 τ sweep |
| The rules router is 84% accurate, ECE 0.144; most errors are paraphrases that fail safely (low confidence → escalate) | LOG: router calibration |
| Guardrails block 5/5 direct attacks with 0/3 false refusals | LOG: baselines |
| Over-abstention fixed: trimming unsupported sentences + combined grounding takes phi3 from 74% to **96%** (with System 1) | LOG: #9 grounding |

All on 23 QA and 63 router questions written by the developers, so these are early, optimistic estimates. Highest-value next steps: **blind test set** (WP1, #1), **learned System-1 models + cross-machine model matrix**, **LLM-judge metric** (WP5, #5).

## 6. How to cite

See [`CITATION.cff`](../../CITATION.cff), or use GitHub's "Cite this repository" button.
