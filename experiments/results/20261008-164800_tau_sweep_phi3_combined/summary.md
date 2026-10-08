# tau_sweep_phi3_combined

**Research questions:** RQ1, RQ2, RQ4  
**Hypothesis:** With combined grounding, phi3 loses fewer correct reworded sentences, so its accuracy improves beyond the 83% seen with lexical trim.  
**Split:** dev · **System 2:** ollama (phi3) · **System 1:** rules · **Commit:** `f3c102ba`

| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |
|---|---|---|---|---|---|---|
| 0.50 | 96% | 35% | 100% | 38741 | 1.00 | 519 |
| 0.60 | 96% | 30% | 100% | 39031 | 1.04 | 531 |
| 0.70 | 96% | 30% | 100% | 39031 | 1.04 | 531 |
| 0.75 | 96% | 30% | 100% | 39031 | 1.04 | 531 |
| 0.80 | 96% | 30% | 100% | 39031 | 1.04 | 531 |
| 0.85 | 96% | 30% | 100% | 39031 | 1.04 | 531 |
| 0.90 | 96% | 30% | 100% | 39031 | 1.04 | 531 |
| 0.95 | 83% | 0% | – | 46164 | 1.39 | 672 |
| 1.00 | 83% | 0% | – | 46164 | 1.39 | 672 |

Reference, System 2 on every question: accuracy 83%, mean latency 46163 ms.
