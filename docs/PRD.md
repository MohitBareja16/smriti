# PRD — Personal Agentic RAG ("one place for everything about you")

| | |
|---|---|
| Status | Draft v0.1 |
| Date | 2026-10-04 |
| Owner | Single user (open-source from day one, self-hosted per person) |
| Builder | Primarily AI coding agent (Claude Code), human-reviewed |

---

## 1. Vision

A private, self-hosted AI assistant that knows everything about **one person**: their documents, projects, certifications, deadlines and career profiles, **plus their academic life (notes, books, lecture slides, past papers, courses and exams)**. It answers questions, fetches documents, helps them study from their own material, and (in later phases) keeps the resume, GitHub and LinkedIn up to date. It drafts every change, and nothing goes live until the owner approves it.

**Core principle: _Handle your documents safely and securely._**
Every design decision is checked against this principle. When convenience and privacy conflict, privacy wins.

It is open source. Anyone can deploy their own copy with their own data, and no data is shared with the project or with anyone else.

## 2. Goals and non-goals

### Goals (overall product)
1. One chat interface to ask anything about yourself and get answers that cite their sources.
2. A secure, encrypted vault for official documents that you can search and retrieve with plain-language requests.
3. Understanding of GitHub projects (what was built, with which tech, and its impact).
4. **Academic companion:** a personal library of notes, books, slides and past papers. You can ask questions with page-level citations, and later get summaries, flashcards, practice quizzes and a study plan tied to exam dates.
5. Career automation: a JD match score, a tailored resume, and LinkedIn updates. **Always draft-then-approve.**
6. A fully self-hosted model stack, with no personal data sent to third-party AI APIs.
7. A modular design, so each capability is a plug-in module that can be built, tested and shipped on its own.

### Non-goals
- Multi-user or SaaS hosting (single-user only, for now).
- Auto-submitting job applications or auto-publishing to LinkedIn. **The agent never clicks the final submit or publish button.**
- Scraping other people's data.
- Use as a general-purpose chatbot. It answers questions about the owner.

## 3. Key decisions (from discovery)

| Topic | Decision | Reason |
|---|---|---|
| Hosting | **Development: own laptop first.** Later: one rented cloud GPU server | Free while building. The same Docker setup moves to the cloud later |
| Budget | **Minimum cost, affordable for any student.** Free tools only; cloud through student credits later | v1 has to run on small models on an ordinary laptop |
| Open source | **Public repo from day one** | Contributors (including juniors) can join early |
| Team | **Modular**, so juniors can each own one module | Clear interfaces, a demo dataset, and good-first-issue tasks per module |
| Network access | **Private network only** (Tailscale); no public URL | The server can't be attacked from the internet. Phone access also works through it later |
| Login | **Passkey** (fingerprint/Face ID) | No passwords to leak, and resistant to phishing |
| Interface | Web app in v1; mobile (PWA) later | Mobile can reuse the same backend |
| Models | Laptop dev (no GPU, ~8 GB RAM): ~1–4B quantized models via Ollama, or an optional free hosted endpoint used **only with demo data**. Cloud: **small (≤12B) vision-capable open-weight model**; 26–31B models later (e.g. the ones in the Jev Decision Index) | Fits a free or cheap GPU. Models are a config setting, so upgrading is a one-line change |
| System-1 decisions (routing, guardrails, scoring) | **Self-hosted `jeff`** (an MIT-licensed open-source copy of the Jev API) | TypeSafe's Jev is a closed, hosted API, and sending data to it would break the privacy principle |
| Retrieval | Vector search + **simple knowledge graph** in v1; full Graph RAG in v2 | Gets something working sooner while the data model stays graph-ready |
| Multimodal | **OCR + vision in v1** | Most official documents are scans or photos |
| Autonomy | **Draft, user approves each action** | Safety, and lower risk of LinkedIn account bans |
| Browser automation (later) | Playwright / browser-use / jev-ultrafast, using the self-hosted vision model | Open source. The LinkedIn and job-portal UIs are well known |
| Builder | Claude Code, guided by this PRD and `docs/BUILD_PLAN.md` | Small milestones that can each be tested |

### A note on Jev
- **Jev (TypeSafe AI)** is a "System One" model. You give it text and a list of typed questions, and it returns typed answers with probabilities. That makes it a good fit for routing, guardrails, classification and scoring.
- It is **closed-weight and hosted only** (early access), so it can't be self-hosted.
- **`jeff`** is an MIT-licensed, self-hostable implementation of the same API, running on a ~400M-parameter model. It is cheap enough to run next to the main LLM. Its quality must be checked with evals in Milestone 0.
- The code talks to a **`DecisionEngine` interface**, so anyone who chooses to can switch to real Jev with one config flag. The default is self-hosted.

## 4. Users and core use cases

**Primary user:** one person (the owner), technical or not, who manages their career and documents.

### v1 use cases (must have)
| ID | As the owner, I want to… | Example |
|---|---|---|
| U1 | Upload documents (PDF, DOCX, images, scans) into an encrypted vault | Drag in a degree certificate photo |
| U2 | Ask questions about my data and get answers with sources | "What was my CGPA in semester 5?" → answer + link to marksheet |
| U3 | Fetch a document by describing it | "Give me my AWS certificate" → download button |
| U4 | Connect GitHub (public + private) and ask about my projects | "Which of my projects used FastAPI?" |
| U5 | See how things are connected (simple knowledge map) | "What skills do my certifications and projects share?" |
| U6 | Log in with a passkey, from my devices only | Fingerprint login over Tailscale |
| U7 | See what the system did and why (audit log) | "Who accessed which document, when" |
| U8 | Upload notes, books, lecture slides and past papers into a **study library** organised by course | Upload "OS Unit 3 notes.pdf" and tag it to the Operating Systems course |
| U9 | Ask questions about my study material and get answers with **page citations** | "Explain deadlock using my OS notes" → answer + "OS notes, p. 12" |

### Later use cases (roadmap)
| ID | Use case | Phase |
|---|---|---|
| L1 | Deadlines and exams tracker with reminders | v2 |
| L2 | JD (text or link) → match score + gap analysis | v2 |
| L3 | Auto-tailored resume draft (dynamic artifact) from the JD | v2 |
| L4 | Keep the resume up to date automatically when new projects or certifications are added (draft) | v2 |
| L5 | Fill job application forms with browser automation; **the user submits** | v3 |
| L6 | LinkedIn: draft posts, update banner/photo/projects; **the user approves and publishes** | v3 |
| L7 | Gmail/Calendar ingestion for deadlines | v3 |
| L8 | MCP server exposing the vault to other AI apps (Claude, Cursor) | v2 |
| L9 | Mobile app (PWA) | v3 |
| L10 | Summaries, flashcards and practice quizzes generated from my notes and past papers | v2 |
| L11 | Study planner: split the syllabus into daily topics before each exam date | v2 |
| L12 | "What did I miss?": compare the syllabus with my notes and list topics not yet covered | v2 |
| L13 | Handwritten notes (phone photos) made searchable through OCR + vision | v2 |
| L14 | Spaced-repetition review of flashcards (Anki export) | v3 |

## 5. Functional requirements: v1

### 5.1 Ingestion module
- **FR-1** Accept PDF, DOCX, PNG/JPG/HEIC and Markdown/TXT uploads through the web UI.
- **FR-2** Parse documents into text plus structure (headings, tables) with **Docling**. Scanned pages and images go through OCR (Docling's OCR backends, or PaddleOCR/Tesseract).
- **FR-3** Images and photos also get a **vision-model description** (e.g. "Photo of AWS Solutions Architect certificate, issued to X, dated Y").
- **FR-4** Auto-classify each document (certificate, marksheet, ID, resume, offer letter, **lecture notes, book, slides, past paper, syllabus**, other) using the **DecisionEngine** (jeff). The user can correct the label.
- **FR-5** Extract key fields (name, issuer, issue/expiry date, grade, ID number) as structured metadata.
- **FR-6** Detect PII and mark sensitive documents (ID numbers, passport, bank) with **Microsoft Presidio**. Sensitive documents get stricter rules (see 6.3).
- **FR-7** Split text into chunks, embed it with a self-hosted embedding model, and store it in pgvector.
- **FR-8** Deduplicate: re-uploading the same file is detected by its hash.

### 5.2 GitHub connector
- **FR-9** Connect using a **fine-grained personal access token with read-only access**, stored encrypted.
- **FR-10** Ingest repo metadata, READMEs, languages, topics, stars and recent commit summaries. Code files are ingested only for repos the user opts in.
- **FR-11** Sync manually (a button) in v1, with a scheduled sync in v2.

### 5.3 Knowledge graph (simple)
- **FR-12** Maintain entities: `Person, Project, Skill, Certification, Organization, Document, Education, Event/Deadline, Course, Topic, Book, Note, Exam`.
- **FR-13** Maintain edges: `BUILT, USES_SKILL, ISSUED_BY, PROVES, STUDIED_AT, HAS_DEADLINE, MENTIONED_IN, ENROLLED_IN, COVERS (course/note/book → topic), TESTS (exam → topic), TEACHES_SKILL (topic → skill)`. This connects academics with career: e.g. the DBMS course → SQL skill → a project that used SQL.
- **FR-14** Entities are extracted by the LLM during ingestion. Every entity links back to its source chunk or document.
- **FR-15** Store the graph in Postgres tables (no separate graph database in v1). The schema stays compatible with LightRAG or a Neo4j migration in v2.
- **FR-16** Show the graph as a simple visual "knowledge map" page.

### 5.4 Study library (academics)
- **FR-12a** A "Library" area separate from official documents. It is organised as **Semester → Course → Unit/Topic**, and the user can create and edit courses.
- **FR-12b** Ingest notes (PDF, DOCX, Markdown), books (PDF/EPUB), lecture slides (PDF/PPTX) and past question papers. Long books are split chapter by chapter, and each chunk keeps its **page number and chapter** for citations.
- **FR-12c** Scope questions to the library: "only from my OS notes" or "only from Galvin" filters retrieval to that course or book.
- **FR-12d** Answers about study material cite the exact source as **book/notes name + page**.
- **FR-12e** Library content is **not** treated as sensitive PII, but it stays in the same encrypted store. Users must only upload material they legally own or have access to. The project ships no books and never shares them.
- **FR-12f** (v2) Generate summaries, flashcards and practice quizzes from a chosen course or unit. Past papers are used to find frequently asked topics.

### 5.4b Agentic query (the chat)
- **FR-17** A chat UI with streaming answers.
- **FR-18** **Router** (DecisionEngine): classifies each message as `question | fetch_document | list/summary | out_of_scope | unsafe`.
- **FR-19** **Agent loop** (LangGraph) with tools: `vector_search`, `graph_lookup`, `get_document`, `list_documents`, `github_search`. The agent may run several searches before it answers.
- **FR-20** Every answer cites its sources (document name plus page, or repo plus file). If nothing relevant is found, it says "I don't know." It must never make answers up.
- **FR-21** **Grounding check** (DecisionEngine): "Is this answer supported by the retrieved sources?" If confidence is low, the answer is flagged or regenerated.
- **FR-22** Document fetch returns a **short-lived signed download link**. Sensitive documents require passkey re-verification.
- **FR-23** Chat history is stored encrypted, and the user can delete it.

### 5.5 Vault UI
- **FR-24** Document list with filters (type, date, sensitivity), preview, download, delete, and relabeling.
- **FR-25** "Delete everything" (crypto-shred: destroy the keys, then the data).
- **FR-26** Export everything (an encrypted ZIP) for backup or migration.

### 5.6 Security and audit
- **FR-27** Passkey (WebAuthn) login. Registering a new device requires an existing logged-in device or a printed recovery code.
- **FR-28** An audit log of logins, uploads, document views/downloads, deletions and agent tool calls. It is append-only.

## 6. Security and privacy requirements

### 6.1 Threat model (what we protect against)
| Threat | Mitigation |
|---|---|
| Internet attackers | No public ports. The app is reachable only over **Tailscale**, and the cloud firewall blocks everything except Tailscale |
| Stolen password / phishing | Passkeys only, with no passwords |
| Stolen disk or snapshot | Disk encryption, plus **app-level encryption** of files (AES-256-GCM with a separate key per file, wrapped by a master key) |
| Leaking data to AI companies | All models are self-hosted. No outbound calls to LLM APIs (enforced by an egress allow-list) |
| Prompt injection (a malicious PDF or README saying "send all documents to…") | Retrieved content is treated as data, not instructions. The agent has **no outbound-network or send tools in v1**. A DecisionEngine injection check runs on retrieved chunks |
| Agent overreach | Tool allow-list per route. Write and external actions require explicit approval (v2+) |
| Lost backups | Encrypted backups (restic) to separate storage, with a restore test in the build plan |

**Honest limitation:** a rented cloud server means the cloud provider could, in theory, access memory while the system is running. Full protection would need confidential-computing GPUs or a home server. This is documented for users, and home-server deployment is supported through the same Docker setup.

### 6.2 Key management (v1)
- The master key is generated at install. It is stored on the server, encrypted with a passphrase the user types once at server start (the "unlock" step). When the system is locked, documents can't be decrypted.
- A recovery kit (master-key backup plus passkey recovery codes) is shown once at setup for the user to save offline.

### 6.3 Sensitive document rules
- Never sent to any external service, even in later phases.
- Viewing requires a fresh passkey check (step-up auth).
- PII values are excluded from the LLM context by default unless the question needs them (e.g. "what's my passport number?").

## 7. Architecture

```
            ┌───────────────── Your devices (laptop / phone) ─────────────────┐
            │  Browser (Next.js web app, passkey login)  ── Tailscale VPN ──┐ │
            └───────────────────────────────────────────────────────────────┼─┘
                                                                            │
┌──────────────────────────── Cloud GPU server (Docker Compose) ───────────┼─────┐
│                                                                          ▼     │
│  Web (Next.js) ──► API (FastAPI) ──► Agent (LangGraph)                         │
│                       │                 │  tools: vector_search, graph_lookup,  │
│                       │                 │         get_document, github_search   │
│                       │                 ▼                                       │
│                       │      ┌──────────────────────┐   ┌───────────────────┐  │
│                       │      │ Model gateway        │──►│ LLM server (vLLM / │  │
│                       │      │ (LiteLLM)            │   │ Ollama) ≤12B VLM   │  │
│                       │      └──────────────────────┘   └───────────────────┘  │
│                       │      ┌──────────────────────┐   ┌───────────────────┐  │
│                       ├─────►│ DecisionEngine (jeff)│   │ Embeddings server │  │
│                       │      └──────────────────────┘   └───────────────────┘  │
│                       ▼                                                        │
│  Ingestion worker (Docling + OCR + Presidio)                                   │
│                       ▼                                                        │
│  Postgres (+pgvector, graph tables, audit log)    Encrypted file store (disk) │
│  Langfuse (observability, self-hosted)            restic → encrypted backups  │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 7.1 Modules (each one a separate package with a clear interface)
| Module | Responsibility | Interface |
|---|---|---|
| `core` | Config, encryption, auth, audit log | — |
| `ingest` | Parse, OCR, classify, chunk, embed | `ingest(file) -> DocumentId` |
| `connectors/github` | GitHub sync | `Connector.sync()` |
| `retrieval` | Vector + graph search | `search(query) -> [Chunk]` |
| `graph` | Entity and edge extraction and storage | `upsert_entities()`, `neighbors()` |
| `decision` | System-1 decisions (jeff, or Jev optionally) | `decide(text, questions) -> typed answers` |
| `agent` | LangGraph orchestration and tools | `chat(message) -> stream` |
| `models` | LLM, VLM and embedding access through LiteLLM | OpenAI-compatible |
| `web` | UI | — |
| `academics` | Library structure (semester/course/topic), page-aware chunking for books, scoped retrieval; v2: flashcards, quizzes, planner | `Library.add(file, course)`, `study(course, mode)` |
| _(v2+)_ `career` | JD scoring, resume tailoring, artifact generation | — |
| _(v3)_ `automation` | Browser agent (Playwright/browser-use/jev-ultrafast) | Produces drafts only |
| _(v2)_ `mcp` | MCP server exposing read-only tools | MCP protocol |

New connectors (LinkedIn export, Gmail, Drive) implement the same `Connector` interface, so the core never changes when one is added.

## 8. Tech stack (open-source first)

| Layer | Choice | License / notes |
|---|---|---|
| Frontend | Next.js + Tailwind + shadcn/ui | MIT. Can be turned into a PWA later for mobile |
| Backend API | Python FastAPI | MIT |
| Agent orchestration | LangGraph | MIT |
| Document parsing / OCR | **Docling** (+ PaddleOCR / Tesseract) | MIT / Apache-2.0 |
| PII detection | Microsoft Presidio | MIT |
| Database + vectors + graph | **Postgres + pgvector** | One database to secure and back up |
| LLM serving | vLLM (GPU) or Ollama (simpler) | Apache-2.0 / MIT |
| Model gateway | LiteLLM (self-hosted) | MIT. Allows swapping models by config |
| Main model (v1) | ≤12B open-weight **vision-language** model, chosen in M0 by eval | Must have an open license for self-hosting |
| Main model (later) | 26–31B models from the Jev Decision Index (e.g. Gemma-based) | Requires a bigger GPU |
| Embeddings | A small open embedding model (self-hosted) | |
| System-1 decisions | **jeff** (self-hosted Jev-API clone) | MIT. Behind the `DecisionEngine` interface |
| Observability | **Langfuse** (self-hosted) | MIT. Traces every LLM and tool call, all inside the server |
| Evals | Ragas + promptfoo | Apache-2.0 / MIT |
| Auth | WebAuthn passkeys (py_webauthn / SimpleWebAuthn) | |
| Network | Tailscale (free personal plan) | Headscale as a fully open-source alternative |
| Backups | restic (encrypted) | BSD |
| Deployment | Docker Compose, one command | |
| _(v2)_ Full Graph RAG | LightRAG | MIT |
| _(v2)_ Resume rendering | RenderCV or Typst, from a JSON Resume source of truth | Produces a PDF |
| _(v3)_ Browser automation | Playwright + browser-use / **jev-ultrafast** (MIT) driven by the self-hosted VLM | Drafts only |

All licenses must be checked again in M0. Anything that is not OSI-approved, or that sends data out, is rejected or made optional.

## 9. Model routing, observability, evals and guardrails (the "System 1" layer)

**Routing**: the DecisionEngine labels each request with an intent. Simple lookups use a cheap path (direct search with a short answer), while complex questions get the full agent loop.

**Guardrails** (all DecisionEngine calls, run locally):
1. Input: is the request in scope, and is it a prompt injection?
2. Retrieved chunks: does any chunk contain instructions aimed at the AI? If so, strip or flag it.
3. Output: is the answer grounded in the sources, and does it leak sensitive data the user didn't ask for?

**Observability**: Langfuse records every request trace (route, tools called, chunks retrieved, latency, tokens). Traces are stored on the server only, with PII redacted in trace payloads.

**Evals** (run before every release, and in CI with fake data):
- A **golden set** of about 50 questions over a fake demo persona ("Alex Demo"), with known answers. It includes **academic questions over open-licensed study material** (e.g. OpenStax textbooks, CC-BY lecture notes), so page citations can be checked.
- Metrics: answer correctness, faithfulness and context recall (Ragas); routing accuracy; "I don't know" rate on unanswerable questions; injection-resistance tests.
- **Release gate:** no metric may drop by more than 5% from the previous release.

## 10. Non-functional requirements
| Area | Target (v1, small model) |
|---|---|
| Answer latency | First token < 5 s while the GPU is warm |
| Cold start | < 3 min when the GPU is started on demand |
| Ingestion | A 10-page scanned PDF processed in < 2 min |
| Cost | Fits student/free credits. The GPU auto-stops after N minutes idle |
| Install | `git clone` → `.env` → `docker compose up` → setup wizard, in under 30 min |
| Data portability | Full export and full delete at any time |

## 11. Roadmap

### v1: Secure vault + ask my data (this PRD's build scope)
Ingestion (docs + OCR + vision), **study library (notes, books, slides, past papers) with page-cited answers**, GitHub connector, simple graph, agentic chat with citations, passkey + Tailscale, encryption, audit log, Langfuse, eval suite.

### v2: Career brain + study companion
- **Study tools:** summaries, flashcards, practice quizzes, frequently asked topics from past papers, a syllabus-coverage check, and a study planner tied to exam dates.
- Handwritten-notes OCR.
- Deadlines and exams tracker, with reminders sent to the user's own channel (e.g. a self-hosted ntfy).
- **JD match**: paste a JD or link → score (0–100) from the DecisionEngine's typed checks per requirement (has skill X? years ≥ Y?), plus a gap list.
- **Resume as data**: a JSON Resume "source of truth" built from the knowledge graph → rendered to PDF (RenderCV/Typst) → tailored versions per JD, shown as a **diff for approval**.
- Auto-update the resume draft when a new project or certification is added.
- Full Graph RAG (LightRAG), plus an MCP server (read-only tools) to use the vault from other AI apps.
- LinkedIn **data-export** ingestion (official ZIP).

### v3: Hands (browser automation, always draft-only)
- Job application form filling with Playwright/browser-use/jev-ultrafast. **The agent stops before submit**, and the user reviews and submits.
- LinkedIn: draft posts, banner/photo/projects updates prepared in the browser. **The user clicks publish.** Includes rate limits and human-like pacing. ⚠️ LinkedIn's User Agreement prohibits automation, so the account could be restricted. This module is off by default, with a clear warning.
- Gmail/Calendar ingestion, plus the mobile PWA.

## 12. Build milestones for v1 (for Claude Code)

Each milestone ends with something you can test yourself. Details go in `docs/BUILD_PLAN.md`.

| # | Milestone | You can verify by… |
|---|---|---|
| M0 | Repo skeleton, Docker Compose, model selection eval (pick the ≤12B VLM + embeddings; test jeff quality) | `docker compose up` shows a hello page; short model report |
| M1 | Passkey login + Tailscale-only access + audit log | Logging in from your phone over Tailscale works; the public IP refuses connections |
| M2 | Encrypted vault: upload, list, download, delete | Files on disk are unreadable without the key |
| M3 | Ingestion: Docling + OCR + vision description + classification + PII flag | Upload a scanned certificate → correct type and fields shown |
| M3b | Study library: courses, page-aware book/notes ingestion, scoped search | "Explain deadlock from my OS notes" → answer with page number |
| M4 | Retrieval + chat with citations (no agent yet) | "What's my CGPA?" → correct answer + source link |
| M5 | Agent loop (LangGraph) + router + guardrails | Multi-step questions work; a planted injection PDF is ignored |
| M6 | GitHub connector | "Which projects use Python?" → correct list |
| M7 | Simple knowledge graph + map page | The graph shows you → projects → skills |
| M8 | Langfuse traces + eval suite + backups/restore test | The eval report passes the release gate; restore works |
| M9 | Open-source readiness: README, setup wizard, demo persona, SECURITY.md, license | A fresh user installs it from the README |

## 13. Open-source project hygiene
- License: **AGPL-3.0** (keeps hosted forks open) or Apache-2.0 (easier adoption). _Decision pending._
- A demo persona dataset, so contributors never need real personal data.
- `SECURITY.md` with responsible disclosure. No telemetry, ever.
- CI: lint, tests, evals on demo data, and dependency/license scanning.

## 14. Open questions
1. Exact v1 model: which ≤12B vision-language model fits the free-credit GPU best (decided in M0).
2. Does `jeff` reach acceptable accuracy for routing and guardrails? Fallback: use the main LLM with structured (JSON) output for these decisions.
3. Which cloud gives the best student/free GPU credits (to compare in M0)?
4. Project license: AGPL-3.0 or Apache-2.0?
5. Project name.

## 15. References
- Jev Decision Index (HF Space): https://huggingface.co/spaces/multimodalart/jev-decision-index
- jeff (self-hosted Jev API, MIT): https://www.everydev.ai/tools/jeff/llms.txt
- Jev is closed-weight / hosted: https://www.modemguides.com/blogs/ai-news/jev-typesafe-reality-check-run-locally
- jev-ultrafast (browser-use + TypeSafe, MIT): https://www.activepieces.com/blog/what-is-jev-ultrafast-agent-browser-automation-in-2026.md
- jev-mcp: https://github.com/legostin/jev-mcp
