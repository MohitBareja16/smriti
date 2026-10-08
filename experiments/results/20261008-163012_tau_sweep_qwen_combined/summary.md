# tau_sweep_qwen_combined

**Research questions:** RQ1, RQ2, RQ4  
**Hypothesis:** With combined grounding, qwen2.5:3b recovers the ACID answer lost to trimming, returning to 100% System-2 accuracy.  
**Split:** dev · **System 2:** ollama (qwen2.5:3b) · **System 1:** rules · **Commit:** `f3c102ba`

| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |
|---|---|---|---|---|---|---|
| 0.50 | 96% | 35% | 100% | 14439 | 0.83 | 322 |
| 0.60 | 96% | 30% | 100% | 14614 | 0.87 | 333 |
| 0.70 | 96% | 30% | 100% | 14614 | 0.87 | 333 |
| 0.75 | 96% | 30% | 100% | 14614 | 0.87 | 333 |
| 0.80 | 96% | 30% | 100% | 14614 | 0.87 | 333 |
| 0.85 | 96% | 30% | 100% | 14614 | 0.87 | 333 |
| 0.90 | 96% | 30% | 100% | 14614 | 0.87 | 333 |
| 0.95 | 96% | 0% | – | 18588 | 1.17 | 434 |
| 1.00 | 96% | 0% | – | 18588 | 1.17 | 434 |

Reference, System 2 on every question: accuracy 96%, mean latency 18588 ms.
