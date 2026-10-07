# Experiment log

Newest first. Each entry links to its run folder in `experiments/results/`, which has the exact config, commit, data fingerprint and per-item details. **Every result so far is on the `dev` split** (see the protocol in [README.md](README.md) §4), with n = 23 QA / 63 router questions. Treat these as early, optimistic estimates.

### Entry template
```
## YYYY-MM-DD: <short title>
**Run:** experiments/results/<folder>  ·  **RQ:** …  ·  **Split:** dev/test
**Hypothesis:** (copied from the config, written before running)
**Result:** the key numbers (with counts, not only %)
**Interpretation:** supported / not supported / inconclusive, and why
**Next:** what this changes or which issue it feeds
```

---

## 2026-10-07: τ sweep with phi3, and a guardrail side effect
**Run:** [`20261007-192740_tau_sweep_phi3`](../../experiments/results/20261007-192740_tau_sweep_phi3/) · **RQ:** RQ1, RQ2, RQ4 · **Split:** dev (23 items) · **Hardware:** CPU-only laptop

**Hypothesis:** same as the qwen sweep, with the weaker phi3 (3.8B) as System 2.

**Result:**

| | Always System 2 | Smriti, τ = 0.6–0.9 | Change |
|---|---|---|---|
| Accuracy | 65% (15/23) | **74% (17/23)** | **+9 pts** |
| Mean latency | 58.9 s | 51.1 s | −13% |
| LLM calls / question | 1.70 | 1.35 | −21% |
| Tokens / question | 852 | 711 | −17% |

**Interpretation:** **supported, and stronger than with qwen.** With a weaker System 2, System 1 doesn't just save cost, it *raises* accuracy: phi3 got 2 fact questions wrong that System 1 answers correctly (f1, f4). Compared with qwen2.5:3b, phi3 is ~3.3× slower and less accurate on this laptop, so **qwen2.5:3b stays the default**.

**Side effect (RQ4 cost):** 6 of phi3's 8 errors are *"I don't know"* on explain questions the notes do answer (e2–e7). Tracing "What is a TLB?" shows why: phi3's answer was reasonable, but only **1/3 sentences passed the lexical grounding check** (word overlap ≥ 60%). It retried, failed again, and abstained. The grounding guard is **too strict for paraphrasing models**, which causes over-abstention. qwen paraphrases less, so the problem didn't show up there.

**Next:** WP9 (#9), a semantic (NLI/embedding) grounding check measured against the lexical one: false-abstention rate vs. hallucination catch rate. Until then, report grounding-induced abstentions as a separate metric.

## 2026-10-07: τ sweep with a real local LLM (qwen2.5:3b)
**Run:** [`20261007-190504_tau_sweep_qwen2.5-3b`](../../experiments/results/20261007-190504_tau_sweep_qwen2.5-3b/) · **RQ:** RQ1, RQ2 · **Split:** dev (23 items) · **Hardware:** CPU-only laptop, 8 GB RAM

**Hypothesis:** with a real local LLM as System 2, routing confident questions to System 1 cuts mean latency and LLM calls substantially, at equal or better accuracy.

**Result:**

| | Always System 2 (τ = 1.0) | Smriti, τ = 0.6–0.9 | Change |
|---|---|---|---|
| Accuracy (all 23 items) | 100% (23/23) | 100% (23/23) | ±0 |
| Answered by System 1 | 0 | 7/23 (30%) | |
| Mean latency | 17.7 s | 14.1 s | **−20%** |
| LLM calls / question | 1.22 | 0.91 | **−25%** |
| Tokens / question | 455 | 354 | **−22%** |

At τ = 0.5, System 1 takes 9/23 questions, but accuracy drops to 96% (22/23).

**Interpretation:** **supported on dev.** A plateau of thresholds (0.6–0.9) gives the savings with no accuracy loss, so τ is not fragile on this data. Latency savings (20%) are smaller than the System-1 share (30%) because the questions System 1 can take are also the *cheap* ones for the LLM (mean System-2 latency 11.6 s for those 7 vs. 20.3 s for the other 16). The τ = 0.5 error is instructive: System 1 answered the unanswerable *"What was my GPA in semester 9?"* with the semester-4 CGPA, at exactly the **same confidence (0.528)** as a correct answer (f7). No threshold can separate them, so the fix is better fact matching (detect qualifier mismatches like the semester), not a better τ.

**Next:** repeat on the blind test set (WP1, #1). Add qualifier-mismatch detection to fact matching. Report p95 latency per intent. Run the same sweep with a learned router (WP2, #2).

## 2026-10-07: Router calibration, rules engine
**Run:** [`20261007-185815_router_calibration_rules`](../../experiments/results/20261007-185815_router_calibration_rules/) · **RQ:** RQ1, RQ5 · **Split:** dev (63 questions: 23 QA + 40 router)

**Hypothesis:** the rules router's confidence is over-confident (ECE > 0.1), which motivates a learned, calibrated System-1 engine.

**Result:** accuracy **84% (53/63)**, ECE **0.144**. Reliability: confidence 0.4–0.5 → 47% correct (15 items); 0.5–0.6 → 89% (9); 0.7–0.8 → 93% (15); 0.8–1.0 → 100% (24).

**Interpretation:** **partly supported.** ECE is above 0.1, but the router is mostly *under*-confident in the middle bins, not over-confident. Error analysis: 9 of the 10 errors are paraphrases the rules don't cover ("Tell me my roll no", "pull up my AWS credential document", "Which is better, B+ tree or hash index?"). All 9 fall back to `other` at low confidence (0.47), so they **fail safely** by escalating to System 2. Only 1 error is confident (*"how do I use this app?"* → `explain`, 0.70). The `router.jsonl` items were written after the rules, without tuning; QA items were written alongside them.

**Next:** WP2 (#2), a SetFit router that should fix the paraphrase errors and give better-calibrated probabilities (possibly with temperature scaling).

## 2026-10-07: Baselines and guardrail ablation (offline reasoner)
**Run:** [`20261007-185817_baselines_offline`](../../experiments/results/20261007-185817_baselines_offline/) · **RQ:** RQ3, RQ4 · **Split:** dev (23 QA, 11 red-team) · **System 2:** offline extractive reasoner (no LLM)

**Hypothesis:** with identical retrieval, System-1 guardrails remove attack success without false refusals, and the System-1 fast path does not reduce accuracy.

**Result:** every system scores 80% (16/20) on answerable questions. Attack success: 5/5 without guardrails → **0/5 with guardrails**. False refusals 0/3 for all systems. Leaks 0/3 for all systems. The extractive reasoner never abstains (0/3 unanswerable correct).

**Interpretation:** **supported for RQ4 on this small set.** Guardrails block all direct attacks with no false refusals. Leaks are 0% even *without* the output guard, because sensitive documents are redacted at ingestion, so the leak test currently doesn't isolate the G3 guard (it tests the ingestion design). RQ3 is **inconclusive** here: the offline reasoner can't show agentic gains. It needs LLM runs and harder compare/exam-prep items.

**Next:** rerun `baselines` with qwen2.5:3b. Expand red-team with paraphrased and Hinglish attacks (WP6, #6). Design a leak test that bypasses ingestion redaction to isolate G3.

## 2026-10-07: τ sweep, offline reasoner (pipeline check)
**Run:** [`20261007-185816_tau_sweep_offline`](../../experiments/results/20261007-185816_tau_sweep_offline/) · **RQ:** RQ1 · **Split:** dev

**Result:** τ 0.55–0.90 → System 1 answers 7/23 (30%) with 100% precision. τ = 0.50 → 9/23 with 89% precision. τ ≥ 0.95 → none. Latency is ~1 ms everywhere because there is no LLM.

**Interpretation:** the System-1 part of the curve is the same as with qwen (System 1 doesn't depend on the LLM), which is a useful sanity check. Accuracy differences come from the reasoner, not routing.
