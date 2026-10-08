# tau_sweep_phi3_notools

**Research questions:** RQ1, RQ2, RQ3  
**Hypothesis:** Ablation: the same agent with tools switched off (search only, plus graph for connect).  
**Split:** dev · **System 2:** ollama (phi3) · **System 1:** rules · **Commit:** `c77ad6b3`

| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |
|---|---|---|---|---|---|---|
| 0.50 | 100% | 31% | 100% | 37788 | 1.11 | 527 |
| 0.60 | 100% | 27% | 100% | 38102 | 1.15 | 535 |
| 0.70 | 100% | 27% | 100% | 38102 | 1.15 | 535 |
| 0.75 | 100% | 27% | 100% | 38102 | 1.15 | 535 |
| 0.80 | 100% | 27% | 100% | 38102 | 1.15 | 535 |
| 0.85 | 100% | 27% | 100% | 38102 | 1.15 | 535 |
| 0.90 | 100% | 27% | 100% | 38102 | 1.15 | 535 |
| 0.95 | 96% | 0% | – | 43664 | 1.42 | 640 |
| 1.00 | 96% | 0% | – | 43664 | 1.42 | 640 |

Reference, System 2 on every question: accuracy 96%, mean latency 43664 ms.
