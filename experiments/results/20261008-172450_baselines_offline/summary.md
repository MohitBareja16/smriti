# baselines_offline

**Research questions:** RQ3, RQ4  
**Hypothesis:** With identical retrieval, adding System-1 guardrails removes attack success without false refusals, and the System-1 fast path does not reduce accuracy.  
**Split:** dev · **System 2:** extractive · **System 1:** rules · **Commit:** `d1c867c6`

| System | Accuracy | Citation acc. | IDK acc. | S1 share | p50 ms | p95 ms | LLM calls/q | Attack success ↓ | Leak rate ↓ | False refusals ↓ | Router acc. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| plain_rag | 70% | 87% | 0% | 0% | 10 | 14 | 0.00 | 100% | 0% | 0% | – |
| s2_only | 87% | 96% | 0% | 0% | 14 | 23 | 0.00 | 0% | 0% | 0% | 100% |
| s1_s2_ours | 87% | 96% | 0% | 27% | 15 | 23 | 0.00 | 0% | 0% | 0% | 100% |
| ours_no_guards | 87% | 100% | 0% | 27% | 12 | 14 | 0.00 | 100% | 0% | 0% | 100% |
