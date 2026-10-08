# router_benchmark

**Research questions:** RQ5, RQ1  
**Hypothesis:** A learned embedding router (MiniLM + logistic regression, cross-validated) routes paraphrases better than the rules engine and is better calibrated; a cascade (rules when confident, else embedding) beats both; zero-shot NLI is weakest.  
**Split:** dev · **System 2:** extractive · **System 1:** rules · **Commit:** `8d921b01`

66 labelled questions (dev), 5-fold cross-validation for trained engines. 'Confident' = probability ≥ τ = 0.75.

| Engine | Accuracy | Macro-F1 | ECE ↓ | Confident share | Accuracy when confident | ms/decision |
|---|---|---|---|---|---|---|
| rules | 85% | 0.84 | 0.162 | 42% | 100% | 0.0 |
| embedding | 71% | 0.65 | 0.131 | 52% | 82% | 13.4 |
| cascade | 89% | 0.89 | 0.164 | 50% | 94% | 2.5 |
| zeroshot | 24% | 0.18 | 0.343 | 20% | 62% | 193.3 |
