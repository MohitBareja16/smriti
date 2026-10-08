# tau_sweep_qwen_notools

**Research questions:** RQ1, RQ2, RQ3  
**Hypothesis:** Ablation: the same agent with tools switched off (search only, plus graph for connect).  
**Split:** dev · **System 2:** ollama (qwen2.5:3b) · **System 1:** rules · **Commit:** `c77ad6b3`

| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |
|---|---|---|---|---|---|---|
| 0.50 | 96% | 31% | 100% | 15153 | 0.96 | 340 |
| 0.60 | 92% | 27% | 100% | 15518 | 1.04 | 354 |
| 0.70 | 92% | 27% | 100% | 15518 | 1.04 | 354 |
| 0.75 | 92% | 27% | 100% | 15518 | 1.04 | 354 |
| 0.80 | 92% | 27% | 100% | 15518 | 1.04 | 354 |
| 0.85 | 92% | 27% | 100% | 15518 | 1.04 | 354 |
| 0.90 | 92% | 27% | 100% | 15518 | 1.04 | 354 |
| 0.95 | 92% | 0% | – | 18710 | 1.31 | 443 |
| 1.00 | 92% | 0% | – | 18710 | 1.31 | 443 |

Reference, System 2 on every question: accuracy 92%, mean latency 18710 ms.
