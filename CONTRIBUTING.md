# Contributing

Thanks for helping! The project is split into small modules with clear interfaces, so you can own one piece without understanding everything.

## Setup
```bash
uv venv && uv pip install -e ".[dev]"
make test lint
```
Tests run offline (`PARAG_LLM=extractive`), so you don't need a GPU or a model.

## Rules
1. **Never commit real personal documents or data.** Use `evals/data/alex_demo` (fictional) or add new fictional files.
2. Every change needs a test. `make test` and `make lint` must pass.
3. Keep modules independent: talk to other modules only through their public interface (listed below).
4. If you change behaviour, run `parag eval` and paste the before/after table in your PR.

## Modules and owners

| Module | Interface | Owner |
|---|---|---|
| `ingest/` | `ingest_file(path, db, vault, course=, kind=)` | Mohit |
| `vault/` | `Vault.put / get` | Mohit |
| `storage/` | `Database.search / all_facts / audit` | Mohit |
| `agent/` (System 2) | `System2Agent.run(question, tracer, intent=)` | Mohit |
| `ui/` | Chainlit app | Mohit |
| `decision/` (System 1) | `DecisionEngine.route / is_injection / is_supported` | Kunal |
| `guardrails/` | `check_input / filter_chunks / check_grounding / check_pii` | Kunal |
| `orchestrator.py` | `Orchestrator.handle(question, mode=, guardrails=)` | Kunal |
| `observability.py` | `Tracer.span(name)` | Kunal |
| `evaluation.py` + `evals/` | `run_eval(data_dir, settings)` | Kunal |

## Good first issues
- **SetFit System-1 engine:** implement `DecisionEngine` in `decision/setfit_engine.py`, train it on a router dataset, and register it in `decision/ENGINES`.
- **jeff engine:** an HTTP client for a self-hosted jeff server implementing `DecisionEngine`.
- **Hybrid search:** add LanceDB vectors next to the FTS5 BM25 index and merge the rankings.
- **OCR:** use Docling for scanned PDFs in `ingest/parsers.py`.
- **More eval data:** add questions to `evals/data/qa.jsonl` and red-team cases to `redteam.jsonl`.
- **Calibration:** a reliability diagram / ECE for the router, plus a τ sweep plot.
- **LangGraph:** port `System2Agent` to a LangGraph state machine, keeping the same `run()` interface.
