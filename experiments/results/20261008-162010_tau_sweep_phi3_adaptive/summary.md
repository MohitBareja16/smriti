# tau_sweep_phi3_adaptive

**Research questions:** RQ1, RQ2, RQ4  
**Hypothesis:** With phi3, adaptive keeps most of trim's recovered accuracy (83% System-2-alone vs 65% with abstain).  
**Split:** dev · **System 2:** ollama (phi3) · **System 1:** rules · **Commit:** `7f2d4107`

| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |
|---|---|---|---|---|---|---|
| 0.50 | 91% | 35% | 100% | 43364 | 1.09 | 560 |
| 0.60 | 91% | 30% | 100% | 43599 | 1.13 | 572 |
| 0.70 | 91% | 30% | 100% | 43599 | 1.13 | 572 |
| 0.75 | 91% | 30% | 100% | 43599 | 1.13 | 572 |
| 0.80 | 91% | 30% | 100% | 43599 | 1.13 | 572 |
| 0.85 | 91% | 30% | 100% | 43599 | 1.13 | 572 |
| 0.90 | 91% | 30% | 100% | 43599 | 1.13 | 572 |
| 0.95 | 83% | 0% | – | 50029 | 1.48 | 713 |
| 1.00 | 83% | 0% | – | 50029 | 1.48 | 713 |

Reference, System 2 on every question: accuracy 83%, mean latency 50027 ms.
