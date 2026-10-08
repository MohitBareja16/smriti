# tau_sweep_phi3_tools

**Research questions:** RQ1, RQ2, RQ3  
**Hypothesis:** System-1-selected tools (facts_lookup for escalated fact questions, library/vault scoping, get_document) raise System-2 accuracy over search-only, at similar LLM cost.  
**Split:** dev · **System 2:** ollama (phi3) · **System 1:** rules · **Commit:** `2e0d6d24`

| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |
|---|---|---|---|---|---|---|
| 0.50 | 100% | 31% | 100% | 43405 | 1.11 | 532 |
| 0.60 | 100% | 27% | 100% | 43888 | 1.15 | 542 |
| 0.70 | 100% | 27% | 100% | 43888 | 1.15 | 542 |
| 0.75 | 100% | 27% | 100% | 43888 | 1.15 | 542 |
| 0.80 | 100% | 27% | 100% | 43888 | 1.15 | 542 |
| 0.85 | 100% | 27% | 100% | 43888 | 1.15 | 542 |
| 0.90 | 100% | 27% | 100% | 43888 | 1.15 | 542 |
| 0.95 | 100% | 0% | – | 51410 | 1.42 | 642 |
| 1.00 | 100% | 0% | – | 51410 | 1.42 | 642 |

Reference, System 2 on every question: accuracy 100%, mean latency 51409 ms.
