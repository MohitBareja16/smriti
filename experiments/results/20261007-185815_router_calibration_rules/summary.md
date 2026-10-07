# router_calibration_rules

**Research questions:** RQ1, RQ5  
**Hypothesis:** The rules router's confidence is over-confident (ECE > 0.1), which motivates a learned, calibrated System-1 engine.  
**Split:** dev · **System 2:** extractive · **System 1:** rules · **Commit:** `6daa8e97`

Engine `rules` on 63 questions: accuracy **84%**, ECE **0.144**.

| Confidence bin | Count | Mean confidence | Accuracy |
|---|---|---|---|
| 0.4–0.5 | 15 | 0.47 | 47% |
| 0.5–0.6 | 9 | 0.53 | 89% |
| 0.7–0.8 | 15 | 0.71 | 93% |
| 0.8–0.9 | 4 | 0.84 | 100% |
| 0.9–1.0 | 20 | 0.91 | 100% |
