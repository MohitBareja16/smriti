# tau_sweep_offline

**Research questions:** RQ1, RQ2  
**Hypothesis:** There is a range of tau where System 1 answers a meaningful share of questions with no loss of accuracy compared with always escalating to System 2.  
**Split:** dev · **System 2:** extractive · **System 1:** rules · **Commit:** `90dae7c5`

| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |
|---|---|---|---|---|---|---|
| 0.50 | 81% | 31% | 100% | 1 | 0.00 | 0 |
| 0.55 | 77% | 27% | 100% | 1 | 0.00 | 0 |
| 0.60 | 77% | 27% | 100% | 1 | 0.00 | 0 |
| 0.65 | 77% | 27% | 100% | 1 | 0.00 | 0 |
| 0.70 | 77% | 27% | 100% | 1 | 0.00 | 0 |
| 0.75 | 77% | 27% | 100% | 1 | 0.00 | 0 |
| 0.80 | 77% | 27% | 100% | 1 | 0.00 | 0 |
| 0.85 | 77% | 27% | 100% | 1 | 0.00 | 0 |
| 0.90 | 77% | 27% | 100% | 1 | 0.00 | 0 |
| 0.95 | 77% | 0% | – | 1 | 0.00 | 0 |
| 1.00 | 77% | 0% | – | 1 | 0.00 | 0 |

Reference, System 2 on every question: accuracy 77%, mean latency 1 ms.
