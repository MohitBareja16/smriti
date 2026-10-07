# tau_sweep_offline

**Research questions:** RQ1, RQ2  
**Hypothesis:** There is a range of tau where System 1 answers a meaningful share of questions with no loss of accuracy compared with always escalating to System 2.  
**Split:** dev · **System 2:** extractive · **System 1:** rules · **Commit:** `6daa8e97`

| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |
|---|---|---|---|---|---|---|
| 0.50 | 74% | 39% | 89% | 1 | 0.00 | 0 |
| 0.55 | 70% | 30% | 100% | 1 | 0.00 | 0 |
| 0.60 | 70% | 30% | 100% | 1 | 0.00 | 0 |
| 0.65 | 70% | 30% | 100% | 1 | 0.00 | 0 |
| 0.70 | 70% | 30% | 100% | 1 | 0.00 | 0 |
| 0.75 | 70% | 30% | 100% | 1 | 0.00 | 0 |
| 0.80 | 70% | 30% | 100% | 1 | 0.00 | 0 |
| 0.85 | 70% | 30% | 100% | 1 | 0.00 | 0 |
| 0.90 | 70% | 30% | 100% | 1 | 0.00 | 0 |
| 0.95 | 70% | 0% | – | 1 | 0.00 | 0 |
| 1.00 | 70% | 0% | – | 1 | 0.00 | 0 |

Reference, System 2 on every question: accuracy 70%, mean latency 1 ms.
