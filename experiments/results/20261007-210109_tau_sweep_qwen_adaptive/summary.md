# tau_sweep_qwen_adaptive

**Research questions:** RQ1, RQ2, RQ4  
**Hypothesis:** With qwen2.5:3b, adaptive keeps the 100% accuracy of the abstain policy (no paraphrase lost to trimming).  
**Split:** dev · **System 2:** ollama (qwen2.5:3b) · **System 1:** rules · **Commit:** `7f2d4107`

| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |
|---|---|---|---|---|---|---|
| 0.50 | 96% | 35% | 100% | 14603 | 0.87 | 343 |
| 0.60 | 96% | 30% | 100% | 14782 | 0.91 | 354 |
| 0.70 | 96% | 30% | 100% | 14782 | 0.91 | 354 |
| 0.75 | 96% | 30% | 100% | 14782 | 0.91 | 354 |
| 0.80 | 96% | 30% | 100% | 14782 | 0.91 | 354 |
| 0.85 | 96% | 30% | 100% | 14782 | 0.91 | 354 |
| 0.90 | 96% | 30% | 100% | 14782 | 0.91 | 354 |
| 0.95 | 96% | 0% | – | 18308 | 1.22 | 455 |
| 1.00 | 96% | 0% | – | 18308 | 1.22 | 455 |

Reference, System 2 on every question: accuracy 96%, mean latency 18308 ms.
