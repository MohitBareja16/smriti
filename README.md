# Personal Agentic RAG

A free, open-source, local-first **agentic RAG** for a student's study material (notes, books, slides, past papers) and personal documents (marksheets, certificates, exam dates).

The core idea is **System 1 + System 2 thinking**. Fast, calibrated System-1 decisions route questions, answer simple facts and run guardrails. They escalate to a slow System-2 LLM agent only when deeper reasoning is needed. Everything is traced (Arize Phoenix) and evaluated against baselines on public data.

> **Core principle:** *Handle your documents safely and securely.*

**Status:** planning (PRD v0.2). Nothing to install yet.

## Docs
- [Product Requirements (PRD)](docs/PRD.md)
- [Project synopsis](docs/SYNOPSIS.md)
- Synopsis slides: [`docs/synopsis/deck.pdf`](docs/synopsis/deck.pdf). Or open `docs/synopsis/deck.html` in a browser (← → to navigate, F for fullscreen); after editing a slide, rebuild it with `python docs/synopsis/build_deck.py`.

## Team
Mohit & Kunal · Professor: Dr. Neetu Verma · DCRUST, Murthal

## Contributing
The project is modular: each part (ingestion, GitHub connector, study library, retrieval, agent, UI) is a separate module with a clear interface, so contributors can each own one. Contribution guidelines will come with the first code milestone.

**Never commit real personal documents.** Use the demo dataset for development and tests.
