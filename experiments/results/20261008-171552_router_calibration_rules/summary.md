# router_calibration_rules

**Research questions:** RQ1, RQ5  
**Hypothesis:** The rules router's confidence is over-confident (ECE > 0.1), which motivates a learned, calibrated System-1 engine.  
**Split:** dev · **System 2:** extractive · **System 1:** rules · **Commit:** `90dae7c5`

Engine `rules` on 66 questions: accuracy **85%**, ECE **0.162**.

| Confidence bin | Count | Mean confidence | Accuracy |
|---|---|---|---|
| 0.4–0.5 | 15 | 0.43 | 47% |
| 0.5–0.6 | 9 | 0.50 | 89% |
| 0.6–0.7 | 14 | 0.68 | 93% |
| 0.7–0.8 | 1 | 0.76 | 100% |
| 0.8–0.9 | 4 | 0.83 | 100% |
| 0.9–1.0 | 23 | 0.90 | 100% |
