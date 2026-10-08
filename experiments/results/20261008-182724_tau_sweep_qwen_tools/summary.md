# tau_sweep_qwen_tools

**Research questions:** RQ1, RQ2, RQ3  
**Hypothesis:** System-1-selected tools (facts_lookup for escalated fact questions, library/vault scoping, get_document) raise System-2 accuracy over search-only, at similar LLM cost.  
**Split:** dev · **System 2:** ollama (qwen2.5:3b) · **System 1:** rules · **Commit:** `2e0d6d24`

| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |
|---|---|---|---|---|---|---|
| 0.50 | 96% | 31% | 100% | 13578 | 1.04 | 344 |
| 0.60 | 96% | 27% | 100% | 13837 | 1.08 | 352 |
| 0.70 | 96% | 27% | 100% | 13837 | 1.08 | 352 |
| 0.75 | 96% | 27% | 100% | 13837 | 1.08 | 352 |
| 0.80 | 96% | 27% | 100% | 13837 | 1.08 | 352 |
| 0.85 | 96% | 27% | 100% | 13837 | 1.08 | 352 |
| 0.90 | 96% | 27% | 100% | 13837 | 1.08 | 352 |
| 0.95 | 96% | 0% | – | 17934 | 1.35 | 439 |
| 1.00 | 96% | 0% | – | 17934 | 1.35 | 439 |

Reference, System 2 on every question: accuracy 96%, mean latency 17933 ms.
