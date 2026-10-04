# Project Synopsis: Personal Agentic RAG

**Title:** Personal Agentic RAG: A Private, Open-Source AI Assistant for Personal Documents, Academics and Career Profiles
**Students:** Mohit & Kunal · **Professor:** Dr. Neetu Verma · **Institute:** DCRUST, Murthal
**Repository:** https://github.com/MohitBareja16/personal-agentic-rag
**Core principle:** *Handle your documents safely and securely.*

## 1. Abstract
Students and professionals keep the same information in many disconnected places: resume versions, GitHub repositories, LinkedIn, scanned certificates, marksheets, **lecture notes, textbooks, slides, past papers**, and exam or application deadlines. Keeping these up to date is slow, manual and error-prone. Existing AI assistants can help, but only after the user uploads private documents to a third-party company.

This project builds a **self-hosted, open-source Agentic RAG (Retrieval-Augmented Generation) system** that knows one person's documents and projects. It answers questions about them with cited sources, retrieves documents on request, acts as a **study companion** that answers questions from the student's own notes and books with page-level citations, and (in later phases) generates flashcards and quizzes and tailors the resume to a job description. All AI models run locally, documents are encrypted, and the assistant never acts on the user's behalf without explicit approval.

## 2. Problem Statement
1. Personal and career information is scattered across many platforms and file locations.
2. Updating one source (e.g. finishing a new project) means manually updating every other source.
3. Official documents are hard to find quickly when needed.
4. Study material (notes, books, slides, past papers) is spread across folders and phones. General AI chatbots answer from the internet, not from the student's own syllabus and notes, and they don't cite the page.
5. Cloud AI tools need sensitive personal data to leave the user's control.

## 3. Objectives
1. Build an **encrypted document vault** that can read PDFs, Word files and scanned images (OCR).
2. Build an **agentic RAG pipeline** that answers questions about the user's data with citations, or says "I don't know" when no source supports an answer.
3. Build a **study library** (semester → course → topic) for notes, books, slides and past papers, with answers that cite the book or notes and page number.
4. Ingest **GitHub repositories** so the assistant can describe the user's projects and skills.
5. Build a **knowledge graph** linking the person, projects, skills, certifications, courses and topics, so it can connect academics with career (course → topic → skill → project).
6. Add **guardrails** against prompt injection and private-data leakage, plus evaluation and observability.
7. Keep the system **modular, open source and free to run**, so any student can deploy their own copy.

## 4. Scope
**Phase 1 (this project):** document vault, OCR, study library with page-cited answers, GitHub connector, agentic chat with citations, simple knowledge graph, security layers, evaluation. Runs on a laptop.
**Future work:** summaries, flashcards, practice quizzes, a study planner tied to exam dates, handwritten-notes OCR, deadline tracker, job description match score, auto-tailored resume, browser automation for job forms and LinkedIn drafts (user approves and submits), mobile app, cloud deployment.

## 5. Methodology
1. **Ingestion:** documents are parsed with Docling, scanned pages go through OCR, private data is detected with Presidio, and the text is split into chunks and embedded. Books and notes keep chapter and page numbers for citations.
2. **Storage:** files are encrypted at rest. Embeddings are stored in PostgreSQL + pgvector, and entities and relationships are stored as a graph.
3. **Agent:** a LangGraph agent with a router. A fast "System-1" decision model classifies the request, the agent calls search tools (vector, graph, document, GitHub) as many times as needed, and a grounding check confirms the answer is supported before it is returned.
4. **Security:** passkey login, private-network access only, local models, audit log.
5. **Evaluation:** a 50-question test set over a fictional demo student and open-licensed textbooks (e.g. OpenStax), scored for accuracy and faithfulness (Ragas), plus prompt-injection tests and latency measurements.

## 6. Tools and Technologies (all open source)
Python, FastAPI, LangGraph, Ollama (local LLMs), Docling + OCR, PostgreSQL + pgvector, Microsoft Presidio, Langfuse, Ragas, Next.js, Docker.

## 7. Expected Outcomes
- A working private assistant that answers questions about the user's documents, projects and study material, with sources.
- A study companion that answers from the student's own notes and books, with page citations.
- Measured answer accuracy, faithfulness and injection resistance on a public demo dataset.
- An open-source, modular codebase that other students can extend and deploy for free.

## 8. Novelty
It combines **privacy (local models, encryption)**, **agentic retrieval over a personal knowledge graph that links academics to career**, a **study companion grounded in the student's own material**, and **human-approved automation** in one free, open-source system aimed at students.
