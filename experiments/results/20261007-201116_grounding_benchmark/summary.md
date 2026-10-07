# grounding_benchmark

**Research questions:** RQ4, RQ3  
**Hypothesis:** The lexical grounding check (word overlap >= 0.6) wrongly rejects many correct paraphrased sentences; a model-based check (NLI, embedding or hybrid) cuts false rejections substantially while catching at least as many unsupported sentences.  
**Split:** dev · **System 2:** extractive · **System 1:** rules · **Commit:** `7ad2e12f`

33 supported and 32 unsupported sentences · signal time 626 ms/sentence

| Rule | Threshold | False rejection ↓ | Catch rate ↑ | Balanced accuracy ↑ |
|---|---|---|---|---|
| lexical | 0.4 | 3% | 22% | 59% |
| lexical | 0.5 | 3% | 28% | 63% |
| lexical **(current)** | 0.6 | 3% | 50% | 73% |
| lexical | 0.7 | 6% | 59% | 77% |
| nli | 0.1 | 39% | 81% | 71% |
| nli | 0.3 | 52% | 84% | 66% |
| nli | 0.5 | 52% | 84% | 66% |
| nli | 0.7 | 58% | 91% | 67% |
| embedding | 0.5 | 0% | 22% | 61% |
| embedding | 0.6 | 3% | 50% | 73% |
| embedding **(best)** | 0.7 | 9% | 75% | 83% |
| embedding | 0.8 | 30% | 88% | 79% |
| hybrid | 0.5 | 64% | 84% | 60% |
| hybrid | 0.6 | 64% | 91% | 63% |
| hybrid | 0.7 | 67% | 97% | 65% |
