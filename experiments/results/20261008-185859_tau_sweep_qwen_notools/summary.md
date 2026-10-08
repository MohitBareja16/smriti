# tau_sweep_qwen_notools

**Research questions:** RQ1, RQ2, RQ3  
**Hypothesis:** Ablation: the same agent with tools switched off (search only, plus graph for connect).  
**Split:** dev · **System 2:** ollama (qwen2.5:3b) · **System 1:** rules · **Commit:** `2e0d6d24`

| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |
|---|---|---|---|---|---|---|
| 0.50 | 96% | 31% | 100% | 14741 | 0.96 | 330 |
| 0.60 | 92% | 27% | 100% | 15206 | 1.04 | 344 |
| 0.70 | 92% | 27% | 100% | 15206 | 1.04 | 344 |
| 0.75 | 92% | 27% | 100% | 15206 | 1.04 | 344 |
| 0.80 | 92% | 27% | 100% | 15206 | 1.04 | 344 |
| 0.85 | 92% | 27% | 100% | 15206 | 1.04 | 344 |
| 0.90 | 92% | 27% | 100% | 15206 | 1.04 | 344 |
| 0.95 | 92% | 0% | – | 18741 | 1.31 | 433 |
| 1.00 | 92% | 0% | – | 18741 | 1.31 | 433 |

Reference, System 2 on every question: accuracy 92%, mean latency 18740 ms.
