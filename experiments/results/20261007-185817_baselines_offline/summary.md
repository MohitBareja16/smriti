# baselines_offline

**Research questions:** RQ3, RQ4  
**Hypothesis:** With identical retrieval, adding System-1 guardrails removes attack success without false refusals, and the System-1 fast path does not reduce accuracy.  
**Split:** dev · **System 2:** extractive · **System 1:** rules · **Commit:** `6daa8e97`

| System | Accuracy | Citation acc. | IDK acc. | S1 share | p50 ms | p95 ms | LLM calls/q | Attack success ↓ | Leak rate ↓ | False refusals ↓ | Router acc. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| plain_rag | 80% | 100% | 0% | 0% | 0 | 1 | 0.00 | 100% | 0% | 0% | – |
| s2_only | 80% | 90% | 0% | 0% | 1 | 3 | 0.00 | 0% | 0% | 0% | 100% |
| s1_s2_ours | 80% | 90% | 0% | 30% | 1 | 3 | 0.00 | 0% | 0% | 0% | 100% |
| ours_no_guards | 80% | 95% | 0% | 30% | 1 | 1 | 0.00 | 100% | 0% | 0% | 100% |
