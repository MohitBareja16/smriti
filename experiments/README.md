# Experiments

Every result in Smriti's reports comes from a run in this folder.

```bash
smriti experiment list                                 # all configs
smriti experiment run tau_sweep_offline.json           # runs in seconds, no model needed
smriti experiment run tau_sweep_qwen.json              # needs Ollama + `ollama pull qwen2.5:3b`
```

For plots, install the research extra once: `pip install -e ".[research]"`.

## Layout

```
experiments/
  configs/        one JSON file per experiment (commit these)
  results/        one folder per run (commit runs you cite; delete throwaway ones)
    20261007-185359_tau_sweep_offline/
      config.json        the exact config
      environment.json   git commit, platform, model digest, settings (no secrets)
      dataset.json       SHA-256 fingerprint of every dataset file
      summary.json/.md   headline numbers (the .md is ready for the report)
      details.jsonl      one row per question, for error analysis
      *.csv, *.png       curves and plots
```

## Config format

```json
{
  "name": "tau_sweep_qwen2.5-3b",
  "type": "tau_sweep",
  "research_questions": ["RQ1", "RQ2"],
  "hypothesis": "What you expect to see, written BEFORE running.",
  "dataset": "evals/data",
  "split": "dev",
  "settings": {"llm_backend": "ollama", "llm_model": "qwen2.5:3b", "s1_engine": "rules"},
  "params": {"taus": [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]}
}
```

- `settings` accepts any field of `smriti.config.Settings` (unknown keys are rejected).
- `split`: `dev` (tune here), `test` (final claims only) or `all`.

| Type | Answers | Params |
|---|---|---|
| `baselines` | RQ3, RQ4 | `systems`: subset of `plain_rag`, `s2_only`, `s1_s2_ours`, `ours_no_guards` |
| `tau_sweep` | RQ1, RQ2 | `taus`: thresholds to evaluate (computed exactly from one pass) |
| `router_calibration` | RQ1, RQ5 | `bins`; `router_file`: extra labelled questions (default `router.jsonl`) |
| `grounding_benchmark` | RQ4, RQ3 | `file` (default `grounding.jsonl`); `grid`: thresholds per rule (lexical, nli, embedding, hybrid). Needs the `ml` extra |

## Adding a new experiment type

1. Write `def exp_<name>(cfg, data_dir, settings) -> dict` in `src/smriti/research/experiments.py`. It returns `summary` (JSON-able), `markdown`, `details` (list of rows) and, optionally, `csv` and `plot`.
2. Register it in `EXPERIMENTS`.
3. Add a config in `configs/` and a test in `tests/test_research.py`.
4. Run it, then add an entry to [docs/research/LOG.md](../docs/research/LOG.md).
