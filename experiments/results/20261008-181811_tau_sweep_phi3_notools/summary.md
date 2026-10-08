# tau_sweep_phi3_notools

**Research questions:** RQ1, RQ2, RQ3  
**Hypothesis:** Ablation: the same agent with tools switched off (search only, plus graph for connect).  
**Split:** dev · **System 2:** ollama (phi3) · **System 1:** rules · **Commit:** `2e0d6d24`

| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |
|---|---|---|---|---|---|---|
| 0.50 | 96% | 31% | 100% | 31830 | 1.08 | 504 |
| 0.60 | 96% | 27% | 100% | 32119 | 1.11 | 512 |
| 0.70 | 96% | 27% | 100% | 32119 | 1.11 | 512 |
| 0.75 | 96% | 27% | 100% | 32119 | 1.11 | 512 |
| 0.80 | 96% | 27% | 100% | 32119 | 1.11 | 512 |
| 0.85 | 96% | 27% | 100% | 32119 | 1.11 | 512 |
| 0.90 | 96% | 27% | 100% | 32119 | 1.11 | 512 |
| 0.95 | 92% | 0% | – | 37379 | 1.39 | 618 |
| 1.00 | 92% | 0% | – | 37379 | 1.39 | 618 |

Reference, System 2 on every question: accuracy 92%, mean latency 37379 ms.
