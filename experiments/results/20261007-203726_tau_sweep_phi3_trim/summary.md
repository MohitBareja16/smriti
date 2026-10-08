# tau_sweep_phi3_trim

**Research questions:** RQ1, RQ2, RQ4  
**Hypothesis:** With the trim policy, phi3's false 'I don't know' answers on explain questions disappear: accuracy of System 2 alone rises clearly above 65% (the abstain baseline), while answers stay grounded.  
**Split:** dev · **System 2:** ollama (phi3) · **System 1:** rules · **Commit:** `7ad2e12f`

| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |
|---|---|---|---|---|---|---|
| 0.50 | 91% | 35% | 100% | 40837 | 1.09 | 560 |
| 0.60 | 91% | 30% | 100% | 41107 | 1.13 | 572 |
| 0.70 | 91% | 30% | 100% | 41107 | 1.13 | 572 |
| 0.75 | 91% | 30% | 100% | 41107 | 1.13 | 572 |
| 0.80 | 91% | 30% | 100% | 41107 | 1.13 | 572 |
| 0.85 | 91% | 30% | 100% | 41107 | 1.13 | 572 |
| 0.90 | 91% | 30% | 100% | 41107 | 1.13 | 572 |
| 0.95 | 83% | 0% | – | 47117 | 1.48 | 713 |
| 1.00 | 83% | 0% | – | 47117 | 1.48 | 713 |

Reference, System 2 on every question: accuracy 83%, mean latency 47116 ms.
