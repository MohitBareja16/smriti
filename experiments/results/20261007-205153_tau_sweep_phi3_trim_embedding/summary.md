# tau_sweep_phi3_trim_embedding

**Research questions:** RQ1, RQ2, RQ4  
**Hypothesis:** Embedding grounding (0.7) plus trim keeps phi3's accuracy gain from trimming while catching more unsupported sentences (it was best on the grounding benchmark).  
**Split:** dev · **System 2:** ollama (phi3) · **System 1:** rules · **Commit:** `7ad2e12f`

| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |
|---|---|---|---|---|---|---|
| 0.50 | 91% | 35% | 100% | 31291 | 0.96 | 495 |
| 0.60 | 91% | 30% | 100% | 31596 | 1.00 | 506 |
| 0.70 | 91% | 30% | 100% | 31596 | 1.00 | 506 |
| 0.75 | 91% | 30% | 100% | 31596 | 1.00 | 506 |
| 0.80 | 91% | 30% | 100% | 31596 | 1.00 | 506 |
| 0.85 | 91% | 30% | 100% | 31596 | 1.00 | 506 |
| 0.90 | 91% | 30% | 100% | 31596 | 1.00 | 506 |
| 0.95 | 78% | 0% | – | 37617 | 1.35 | 647 |
| 1.00 | 78% | 0% | – | 37617 | 1.35 | 647 |

Reference, System 2 on every question: accuracy 78%, mean latency 37616 ms.
