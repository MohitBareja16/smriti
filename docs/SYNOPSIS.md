# Project Synopsis (v0.2): Smriti (स्मृति), Personal Agentic RAG

**Title:** Smriti: Fast and Slow Thinking (System 1 + System 2) for a Private, Grounded Student Assistant
**Students:** Mohit & Kunal · **Professor:** Dr. Neetu Verma · **Institute:** DCRUST, Murthal
**Repository:** https://github.com/MohitBareja16/smriti
**Core principle:** *Handle your documents safely and securely.*

## 1. Abstract
Students keep their academic material (lecture notes, textbooks, slides, past papers) and personal documents (marksheets, certificates, exam timetables) in many disconnected places. General AI chatbots can help, but they answer from the internet rather than the student's own material, rarely cite the exact page, and need private documents uploaded to a third party.

This project builds a **free, open-source, local-first agentic RAG system** for one student's own material. Its central idea is **System 1 + System 2 thinking** (Kahneman, 2011):
- A fast **System-1** layer of small models makes typed decisions with a confidence score. It routes questions, answers simple facts directly, and runs safety and grounding checks.
- It **escalates** to a slow **System-2** LLM agent only when deeper reasoning is needed.

The system is fully traced (observability), protected by guardrails, and evaluated against baselines on a public, reproducible dataset.

## 2. Problem Statement
1. Study material and personal documents are scattered across folders and devices.
2. Important facts (exam dates, results, certificates) are hard to find quickly.
3. General chatbots are not grounded in the student's own syllabus and notes, and do not cite pages.
4. Cloud AI tools require private documents to leave the student's control.
5. Agentic RAG systems are often slow and opaque, with no measurement of when deep reasoning is actually needed.

## 3. Objectives
1. Build a **study library** (notes, books, slides, past papers) and an **encrypted personal vault**, with OCR and page-aware indexing.
2. Build a **System-1 layer** for routing and escalation, direct fast answers, input/output guardrails, and grounding checks.
3. Build a **System-2 agent** that plans, searches several sources, and answers with page-level citations.
4. Add **observability**: every decision and step is traced.
5. **Evaluate** the system against baselines on public data, answering the five research questions below.
6. Keep it **free and open source**, runnable on an ordinary 8 GB laptop.

## 4. Research Questions
| ID | Question |
|---|---|
| RQ1 | Can System 1 answer a meaningful share of questions without an LLM, at accuracy close to System 2? |
| RQ2 | How much latency and compute does System-1 → System-2 escalation save? |
| RQ3 | Does agentic retrieval outperform plain RAG on academic and personal questions? |
| RQ4 | How much do System-1 guardrails reduce prompt-injection and data-leak attacks, and at what false-refusal cost? |
| RQ5 | Which System-1 engine performs better: jeff (an open-source Jev-API implementation) or a small classifier we train ourselves (SetFit)? |

## 5. Scope
**In scope (this semester):** study library, encrypted vault with a facts table, the System-1 layer, the System-2 agent, three guardrails, Phoenix tracing, a Chainlit demo UI, the evaluation harness and a red-team suite.
**Future work:** flashcards, quizzes and a study planner; career features (job-match score, resume tailoring, LinkedIn drafts, always approved by the user); cloud hosting with passkey login; a mobile app.

## 6. Methodology
1. **Ingestion:** Docling parses documents, OCR handles scans, and Presidio detects private data. Text is chunked page-aware and embedded locally. Facts such as exam dates and CGPA are extracted into a table.
2. **System 1:** an input guard and a router produce an intent and a confidence p. If p ≥ τ and the fact exists, it answers directly from the facts table with no LLM call. Otherwise it escalates.
3. **System 2:** a LangGraph agent plans, calls search tools over the library and vault, and drafts an answer with citations.
4. **Output checks (System 1):** a grounding check (is every claim supported?) and a PII-leak check. If they fail, the agent retries once and otherwise answers "I don't know".
5. **Observability:** OpenTelemetry traces go to Arize Phoenix, and each answer links to its trace.
6. **Evaluation:** a synthetic student ("Alex Demo") plus openly licensed textbooks, about 200 questions with gold answers and pages, and about 100 red-team attacks. The compared systems are plain RAG, System 2 only, **System 1 + System 2 (ours)**, ours without guardrails, and the two System-1 engines against each other.

## 7. Evaluation Metrics
Answer correctness, faithfulness and context recall (Ragas), page-citation accuracy, share of questions answered by System 1, latency (p50/p95), LLM calls per question, router accuracy and calibration (ECE), injection success rate, PII leak rate, and false refusal rate.

## 8. Tools and Technologies (all free and open source)
Python, Chainlit, LangGraph, Ollama (local LLM), jeff, SetFit, Docling, Presidio, SQLite, LanceDB, Arize Phoenix, Ragas.

## 9. Work Division
- **Mohit (knowledge + System 2):** ingestion and OCR, study library, encrypted vault and facts table, System-2 agent, Chainlit UI.
- **Kunal (System 1 + trust):** System-1 engines and calibration, escalation policy, guardrails, Phoenix tracing, evaluation and red-team suite.

## 10. Timeline (about 14 weeks)
| Week | Milestone |
|---|---|
| 4 | Plain RAG baseline and first evaluation numbers |
| 6 | System-1 fast answers working |
| 8 | Mid-term demo: System-2 agent + guardrails |
| 12 | Full results and report draft |
| 14 | Final demo and viva |

## 11. Expected Outcomes
- A working, private assistant that answers from the student's own notes, books and documents, with page citations.
- Measured evidence of when fast System-1 decisions can replace slow System-2 reasoning, and what they save.
- Measured effectiveness of the guardrails against attacks.
- An open-source, reproducible codebase and benchmark that other students can run for free.

## 12. Novelty
Instead of treating agentic RAG as "always run the LLM agent", this project uses **calibrated fast System-1 decisions to route, answer, and guard**, and escalates to System 2 only when needed. It measures that trade-off openly, on a private, student-focused domain that combines academics with personal documents.

## References
1. Kahneman, D. (2011). *Thinking, Fast and Slow*. Farrar, Straus and Giroux.
2. Lewis, P. et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *NeurIPS*.
3. Yao, S. et al. (2023). ReAct: Synergizing Reasoning and Acting in Language Models. *ICLR*.
4. Es, S. et al. (2024). RAGAS: Automated Evaluation of Retrieval Augmented Generation. *EACL (demo)*.
5. Tunstall, L. et al. (2022). Efficient Few-Shot Learning Without Prompts (SetFit). *arXiv:2209.11055*.
