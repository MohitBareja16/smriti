# router_benchmark

**Research questions:** RQ5, RQ1  
**Hypothesis:** A learned embedding router (MiniLM + logistic regression, cross-validated) routes paraphrases better than the rules engine (higher accuracy and macro-F1) and is better calibrated (lower ECE); the zero-shot NLI router needs no training data but is less accurate than the trained one.  
**Split:** dev · **System 2:** extractive · **System 1:** rules · **Commit:** `1d810865`

66 labelled questions (dev), 5-fold cross-validation for trained engines. 'Confident' = probability ≥ τ = 0.75.

| Engine | Accuracy | Macro-F1 | ECE ↓ | Confident share | Accuracy when confident | ms/decision |
|---|---|---|---|---|---|---|
| rules | 85% | 0.84 | 0.162 | 42% | 100% | 0.0 |
| embedding | 59% | 0.37 | 0.086 | 42% | 82% | 12.0 |
| zeroshot | 24% | 0.18 | 0.343 | 20% | 62% | 218.8 |
