# tau_sweep_qwen_trim

**Research questions:** RQ1, RQ2, RQ4  
**Hypothesis:** With qwen2.5:3b, which already had 100% accuracy, trim causes no accuracy loss.  
**Split:** dev · **System 2:** ollama (qwen2.5:3b) · **System 1:** rules · **Commit:** `7ad2e12f`

| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |
|---|---|---|---|---|---|---|
| 0.50 | 96% | 35% | 100% | 15613 | 0.87 | 343 |
| 0.60 | 96% | 30% | 100% | 16050 | 0.91 | 354 |
| 0.70 | 96% | 30% | 100% | 16050 | 0.91 | 354 |
| 0.75 | 96% | 30% | 100% | 16050 | 0.91 | 354 |
| 0.80 | 96% | 30% | 100% | 16050 | 0.91 | 354 |
| 0.85 | 96% | 30% | 100% | 16050 | 0.91 | 354 |
| 0.90 | 96% | 30% | 100% | 16050 | 0.91 | 354 |
| 0.95 | 96% | 0% | – | 20954 | 1.22 | 455 |
| 1.00 | 96% | 0% | – | 20954 | 1.22 | 455 |

Reference, System 2 on every question: accuracy 96%, mean latency 20953 ms.
