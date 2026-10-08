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

## 2026-10-09: Learned System-1 routers: a rules → embedding cascade wins (#20)
**Run:** [`20261008-200328_router_benchmark`](../../experiments/results/20261008-200328_router_benchmark/) · **RQ:** RQ5, RQ1 · **Split:** dev (66 router-labelled questions), **5-fold cross-validation** for trained engines

**Hypothesis (before running):** a learned embedding router beats the rules on accuracy and calibration; zero-shot NLI is weakest.

**Result:**

| Router | Accuracy | Macro-F1 | ECE ↓ | Accuracy when confident (p ≥ 0.75) | ms/decision |
|---|---|---|---|---|---|
| rules (hand-written) | 85% | 0.84 | 0.162 | **100%** | 0.0 |
| embedding (MiniLM + logistic regression) | 71% | 0.65 | **0.131** | 82% | 13 |
| **cascade** (rules if p ≥ 0.5, else embedding) | **89%** | **0.89** | 0.164 | 94% | 2.5 |
| zero-shot NLI (deberta-v3-xsmall) | 24% | 0.18 | 0.343 | 62% | 193 |

On `router.jsonl` alone (40 questions written after the rules, so a fairer test of the rules): rules 75%, embedding 68%, **cascade 82%**.

**Interpretation:** **not supported as stated; a better design emerged.** With about 53 training questions per fold, the learned router alone loses to hand-written rules, which encode the domain directly. Its first version reached only 59% (L2 = 0.01 underfit; defaults retuned on dev CV, so 71% is slightly optimistic). The two fail *differently*: the rules miss paraphrases but **know when they're unsure** (they fall to `other` at p ≈ 0.47), and the embedding model handles paraphrases. The cascade (cheap rules first, the learned model only when unsure) is "fast and slow thinking" inside System 1 itself, and beats both. Tradeoff: when the cascade is confident it's right 94% of the time vs 100% for the rules, which matters for the fast path. The model matrix (#21) measures the end-to-end effect before any default changes. Zero-shot with a 22M-parameter NLI model is not viable. A bigger NLI model on GPU machines is a matrix question.

**Next:** more and blind router data (WP1) is the main lever for learned routers; end-to-end cascade vs rules in the model matrix.

## 2026-10-09: LangGraph agent with System-1-selected tools (#19), and a latency confound
**Runs (final, commit c77ad6b, each starting from a cold prompt cache):** [`20261008-190839_tau_sweep_qwen_notools`](../../experiments/results/20261008-190839_tau_sweep_qwen_notools/) · [`20261008-191711_tau_sweep_qwen_tools`](../../experiments/results/20261008-191711_tau_sweep_qwen_tools/) · [`20261008-193636_tau_sweep_phi3_notools`](../../experiments/results/20261008-193636_tau_sweep_phi3_notools/) · [`20261008-195630_tau_sweep_phi3_tools`](../../experiments/results/20261008-195630_tau_sweep_phi3_tools/) · earlier confounded runs kept in `20261008-17*`–`18*` · **RQ:** RQ2, RQ3 · **Split:** dev (26 items) · **Hardware:** CPU-only, 8 GB

**Change:** System 2 is now a LangGraph state machine (plan → act → broaden → tools → guard → answer). **System 1 selects the tools** from the intent: escalated fact questions get `facts_lookup` + `vault_search`; study questions use `library_search` (personal documents stay out unless nothing is found); `fetch_doc` gets `get_document`; `connect` keeps `graph_lookup`. The LLM never picks tools, which keeps small local models reliable and saves calls. Step 1 (the port alone) was verified **per-item identical** offline. The compiled graph is reused per configuration (LangGraph overhead ≈ 4 ms per question).

**Hypothesis:** tools raise System-2 accuracy over search-only at similar LLM cost.

**Result (tools off → on):**

| | System 2 alone | with System 1 (τ 0.75) |
|---|---|---|
| qwen2.5:3b accuracy | 92% → **96%** | 92% → **96%** |
| qwen2.5:3b mean latency | 18.7 s → 19.3 s | 15.5 s → 15.4 s |
| phi3 accuracy | 96% → **100%** | 100% → 100% |
| phi3 mean latency | 43.7 s → 45.3 s | 38.1 s → 39.4 s |

LLM calls and tokens are within ±3%. The fixed items are exactly escalated fact questions (qwen f7, phi3 f1), which `facts_lookup` now answers from structured facts.

**Interpretation:** **supported:** +4 points of System-2 accuracy for ≤ 4% latency. With System 1 in front, most fact questions never reach System 2, so the gain there is smaller (phi3: 100% either way). Caveat: answers vary slightly between runs at temperature 0 (phi3 without tools got 92% in an earlier run and 96% here), so ±1 item on n = 26 is within noise.

**Methodology finding (important):** the first comparison showed tools costing +75% latency, but with *identical tokens* (exam_prep: 527 vs 527 tokens, 19.5 s vs 6.0 s). Cause: **Ollama's prompt cache.** The no-tools run directly followed the tools run on the same model and reused cached prompt prefixes. Rerunning no-tools with a cold cache gave 18.7 s instead of 10.8 s. **Fix:** the runner now unloads and reloads the model before every LLM experiment (protocol rule 7). Latency comparisons made back-to-back on the same model before 2026-10-09, including the earlier trim/adaptive/combined runs, may carry this bias. Their accuracy numbers are unaffected.

## 2026-10-08: A knowledge graph answers connection questions plain RAG can't (#17)
**Runs:** [`20261008-171553_baselines_offline`](../../experiments/results/20261008-171553_baselines_offline/) · [`20261008-171552_router_calibration_rules`](../../experiments/results/20261008-171552_router_calibration_rules/) · [`20261008-171554_tau_sweep_offline`](../../experiments/results/20261008-171554_tau_sweep_offline/) · **RQ:** RQ3, RQ1 · **Split:** dev · offline reasoner

**Change:** a deterministic knowledge graph (courses, topics, skills, projects, certifications, exams, with cited edges) and a `graph_lookup` tool. A new System-1 intent `connect` routes questions like *"Which skills from my DBMS course have I used in projects?"* to it. **Dataset change:** Alex Demo gained a project write-up (`library/projects.md`) and `qa.jsonl` gained k1–k3 (26 items), so the dataset fingerprint changed and overall percentages are not directly comparable with earlier entries.

**Hypothesis:** connection questions need facts spread over several documents, so the graph enables answers plain retrieval can't give, with no change on existing questions.

**Result:**
- Graph questions k1–k3: **plain RAG 0/3, agent 3/3** (System 2 alone and with System 1), each citing the graph facts' source pages.
- **No item changed** on the original 23 questions (per-item diff against the previous run). Router predictions are identical on all 63 earlier router items; the 3 new items are routed to `connect`.
- Router ECE rose from 0.144 to **0.162**: a 7th intent spreads the softmax, lowering confidences slightly.

**Interpretation:** **supported** (on 3 items, written by us: small and optimistic). The graph turns multi-document reasoning into a lookup. Plain RAG retrieved relevant passages but never combined DBMS notes with project write-ups. The calibration drop is another argument for a learned, calibrated System-1 model.

**Next:** LLM-based System 2 on k1–k3; blind graph questions in WP1; skill extraction is vocabulary-based, so its recall on real student documents is unknown (extendable `SKILLS`).

## 2026-10-08: Topic-aware chunks improve retrieval (#15)
**Runs:** [`20261008-170803_baselines_offline`](../../experiments/results/20261008-170803_baselines_offline/) · [`20261008-170803_tau_sweep_offline`](../../experiments/results/20261008-170803_tau_sweep_offline/) · **RQ:** RQ3 · **Split:** dev · offline reasoner

**Change:** chunks now split at headings and carry their topic (Semester → Course → Topic library). The agent also filters by semester when the question names one, and broadens if nothing matches.

**Hypothesis:** a regression check: no accuracy loss from the new chunk boundaries.

**Result:** better than "no loss". Agent accuracy on answerable questions went from 80% to **85% (17/20)**, citation accuracy from 90% to **95%**, and the τ-sweep accuracy from 70% to 74% at every τ. The one changed item is c2 (*"Compare how my notes and Galvin explain paging"*): with heading-aligned chunks, the paging passages of both sources come back as clean, single-topic chunks. System-1 results are unchanged.

**Interpretation:** structure-aware chunking helps comparison questions. One item on n = 20 is small, so recheck on the blind test set and with an LLM System 2.

## 2026-10-08: Grounding without over-abstention: trim policy + combined check (#9)
**Runs:** [`grounding_benchmark`](../../experiments/results/20261008-162303_grounding_benchmark/) · [`tau_sweep_qwen_combined`](../../experiments/results/20261008-163012_tau_sweep_qwen_combined/) · [`tau_sweep_phi3_combined`](../../experiments/results/20261008-164800_tau_sweep_phi3_combined/) · intermediate: `*_trim`, `*_trim_embedding`, `*_adaptive` (20261007–08) · **RQ:** RQ4, RQ3, RQ1 · **Split:** dev

**Hypothesis (from #9):** the lexical grounding check wrongly rejects correct reworded answers. A model-based check should cut false rejections while catching at least as many unsupported sentences.

**What we found, step by step:**
1. **The sentence-level check was not the main problem.** On a labelled benchmark of 65 sentence/evidence pairs (23 from real qwen/phi3 answers), lexical@0.6 wrongly rejects only 3% of supported sentences. Tracing phi3's "What is a TLB?" showed its extra sentences were *genuinely not in the notes* (correct general knowledge). The check was right; the **all-or-nothing policy** then threw away the whole answer.
2. **Policy.** `trim` (drop unsupported sentences, abstain only if none survive) raised phi3 System-2 accuracy from 65% to 83%. `adaptive` (keep the whole answer if ≥ 50% is supported, else trim) gave identical results to `trim` for both models, so we kept the simpler, stricter `trim`.
3. **Check.** On the benchmark (false rejection ↓ / catch rate ↑): lexical@0.6 3% / 50%; **strict NLI** (deberta-v3-xsmall) 52% / 84%, so it rejects most paraphrases; **hybrid** (NLI + embedding) 64% / 84%, because the small NLI model finds spurious contradictions; embedding@0.7 9% / 75%; **combined** (lexical ≥ 0.7 OR embedding ≥ 0.7) **0% / 53%**. Lexical and embedding fail on *different* sentences (reworded vs short or technical), so either one accepting is strong evidence. We chose `combined` for **zero false rejections**: over-abstention was the observed harm. embedding@0.7 is the option if catching hallucinations matters more.
4. **Bug found on the way:** the sentence splitter broke numbered lists ("1. Deadlock … 2. Paging"); fixed.

**End-to-end result (System 2 alone / with System 1 at τ 0.6–0.9):**

| | Before #9 (lexical, abstain) | After #9 (combined, trim) |
|---|---|---|
| phi3 | 65% / 74% | **83% / 96%** |
| qwen2.5:3b | 100% / 100% | 96% / 96% |

**Interpretation:** **supported for weak/verbose models, with a small cost for strong ones.** The one qwen loss (e3, ACID) comes from a single heavily compressed sentence ("atomic (all-or-nothing), consistent…") that scores just below both thresholds (lexical 0.50, embedding 0.62). The exact-string metric also expects "Atomicity", which the answer doesn't contain, so it is partly a measurement limit, which WP5 (LLM judge) addresses. LLM outputs also varied between runs despite temperature 0 (retries change the context), so single-item differences should not be over-read on n = 23.

**Decision:** default `grounding=auto` (combined if the ml extra is installed, else lexical), `grounding_policy=trim`. **Next:** confirm on the blind test set (WP1); report the "abstained because nothing was grounded" rate as its own metric; try a larger NLI model on GPU machines (model matrix).

## 2026-10-08: Conflicting numbers no longer fool the fact matcher (#10)
**Run:** [`20261007-194501_tau_sweep_offline`](../../experiments/results/20261007-194501_tau_sweep_offline/) · **RQ:** RQ1 · **Split:** dev · **PR:** fixes #10

**Hypothesis:** rejecting facts whose numbers conflict with the question ("semester 9" vs "Semester 4") removes System 1's only confident wrong answer, without losing any correct System-1 answers.

**Result:** at τ = 0.50, System 1 now answers 8/23 with **100% precision** (before: 9/23 at 89%). The dropped answer is u1, *"What was my GPA in semester 9?"*, which System 1 had answered with the semester-4 CGPA. τ = 0.55–0.90 is unchanged (7/23, 100%).

**Interpretation:** **supported.** The τ = 0.5 failure was a matching bug, not a calibration limit. u1 now escalates to System 2. In the earlier qwen2.5:3b run, System 2 already answered u1 correctly ("I don't know"), and System 2 doesn't depend on this change, so with qwen the τ = 0.50 point should now also reach 100% accuracy. Confirm in the next qwen sweep.

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
