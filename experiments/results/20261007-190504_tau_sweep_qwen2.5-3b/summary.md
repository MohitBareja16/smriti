# tau_sweep_qwen2.5-3b

**Research questions:** RQ1, RQ2  
**Hypothesis:** Same as tau_sweep_phi3, with the project's default model qwen2.5:3b.  
**Split:** dev · **System 2:** ollama (qwen2.5:3b) · **System 1:** rules · **Commit:** `6daa8e97`

| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |
|---|---|---|---|---|---|---|
| 0.50 | 96% | 39% | 89% | 13535 | 0.83 | 326 |
| 0.60 | 100% | 30% | 100% | 14131 | 0.91 | 354 |
| 0.70 | 100% | 30% | 100% | 14131 | 0.91 | 354 |
| 0.75 | 100% | 30% | 100% | 14131 | 0.91 | 354 |
| 0.80 | 100% | 30% | 100% | 14131 | 0.91 | 354 |
| 0.85 | 100% | 30% | 100% | 14131 | 0.91 | 354 |
| 0.90 | 100% | 30% | 100% | 14131 | 0.91 | 354 |
| 0.95 | 100% | 0% | – | 17664 | 1.22 | 455 |
| 1.00 | 100% | 0% | – | 17664 | 1.22 | 455 |

Reference, System 2 on every question: accuracy 100%, mean latency 17664 ms.
