# tau_sweep_phi3

**Research questions:** RQ1, RQ2  
**Hypothesis:** With a real local LLM as System 2, routing confident questions to System 1 cuts mean latency and LLM calls substantially at equal or better accuracy.  
**Split:** dev · **System 2:** ollama (phi3) · **System 1:** rules · **Commit:** `6daa8e97` (uncommitted changes)

| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |
|---|---|---|---|---|---|---|
| 0.50 | 70% | 39% | 89% | 49363 | 1.22 | 655 |
| 0.60 | 74% | 30% | 100% | 51093 | 1.35 | 711 |
| 0.70 | 74% | 30% | 100% | 51093 | 1.35 | 711 |
| 0.75 | 74% | 30% | 100% | 51093 | 1.35 | 711 |
| 0.80 | 74% | 30% | 100% | 51093 | 1.35 | 711 |
| 0.85 | 74% | 30% | 100% | 51093 | 1.35 | 711 |
| 0.90 | 74% | 30% | 100% | 51093 | 1.35 | 711 |
| 0.95 | 65% | 0% | – | 58892 | 1.70 | 852 |
| 1.00 | 65% | 0% | – | 58892 | 1.70 | 852 |

Reference, System 2 on every question: accuracy 65%, mean latency 58890 ms.
