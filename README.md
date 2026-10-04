# Personal Agentic RAG

A private, self-hosted, open-source AI assistant that knows **one person**: their study material (notes, books, slides, past papers), documents, certificates, GitHub projects, deadlines and career profiles.

> **Core principle:** *Handle your documents safely and securely.*
> All models run locally, documents are encrypted, and the assistant never acts without your approval.

**Status:** planning / pre-alpha. Nothing to install yet.

## What it will do
- **Study:** ask questions from your own notes and books and get answers with page numbers. Later: flashcards, quizzes and a study planner.
- **Ask:** questions about your documents and projects, answered with cited sources.
- **Fetch:** "give me my AWS certificate" finds the file in your encrypted vault.
- **Track:** exams, certificate expiries and application deadlines.
- **Tailor (later):** paste a job description to get a match score and a tailored resume draft. You review and submit.

## Docs
- [Product Requirements (PRD)](docs/PRD.md)
- [Project synopsis](docs/SYNOPSIS.md)
- Synopsis slides: [`docs/synopsis/deck.pdf`](docs/synopsis/deck.pdf). Or open `docs/synopsis/deck.html` in a browser (← → to navigate, F for fullscreen); after editing a slide, rebuild it with `python docs/synopsis/build_deck.py`.

## Team
Mohit & Kunal · Professor: Dr. Neetu Verma · DCRUST, Murthal

## Contributing
The project is modular: each part (ingestion, GitHub connector, study library, retrieval, agent, UI) is a separate module with a clear interface, so contributors can each own one. Contribution guidelines will come with the first code milestone.

**Never commit real personal documents.** Use the demo dataset for development and tests.
