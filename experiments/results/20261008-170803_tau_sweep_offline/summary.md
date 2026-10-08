# tau_sweep_offline

**Research questions:** RQ1, RQ2  
**Hypothesis:** There is a range of tau where System 1 answers a meaningful share of questions with no loss of accuracy compared with always escalating to System 2.  
**Split:** dev · **System 2:** extractive · **System 1:** rules · **Commit:** `46d92775`

| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |
|---|---|---|---|---|---|---|
| 0.50 | 78% | 35% | 100% | 1 | 0.00 | 0 |
| 0.55 | 74% | 30% | 100% | 1 | 0.00 | 0 |
| 0.60 | 74% | 30% | 100% | 1 | 0.00 | 0 |
| 0.65 | 74% | 30% | 100% | 1 | 0.00 | 0 |
| 0.70 | 74% | 30% | 100% | 1 | 0.00 | 0 |
| 0.75 | 74% | 30% | 100% | 1 | 0.00 | 0 |
| 0.80 | 74% | 30% | 100% | 1 | 0.00 | 0 |
| 0.85 | 74% | 30% | 100% | 1 | 0.00 | 0 |
| 0.90 | 74% | 30% | 100% | 1 | 0.00 | 0 |
| 0.95 | 74% | 0% | – | 1 | 0.00 | 0 |
| 1.00 | 74% | 0% | – | 1 | 0.00 | 0 |

Reference, System 2 on every question: accuracy 74%, mean latency 1 ms.
