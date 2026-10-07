import json

import pytest

from smriti.research.datasets import fingerprint, load_split
from smriti.research.experiments import load_config, make_settings, run_experiment
from smriti.research.metrics import calibration, percentile
from tests.conftest import DATA

CONFIGS = DATA.parent.parent / "experiments" / "configs"


def test_ece_perfect_and_overconfident():
    ece, _ = calibration([0.95, 0.95, 0.05, 0.05], [True, True, False, False], n_bins=10)
    assert ece == pytest.approx(0.05)
    ece, bins = calibration([0.9] * 10, [True] * 5 + [False] * 5, n_bins=10)
    assert ece == pytest.approx(0.4)
    assert sum(b.count for b in bins) == 10


def test_percentile_nearest_rank():
    assert percentile([5, 1, 3], 0.5) == 3 and percentile([], 0.9) == 0.0


def test_splits_and_fingerprint_are_stable():
    assert len(load_split(DATA / "qa.jsonl", "all")) == len(load_split(DATA / "qa.jsonl", "dev")) \
        + len(load_split(DATA / "qa.jsonl", "test"))
    assert fingerprint(DATA)["combined"] == fingerprint(DATA)["combined"]


def test_every_config_is_valid():
    configs = sorted(CONFIGS.glob("*.json"))
    assert configs
    for c in configs:
        cfg = load_config(c)
        make_settings(cfg["settings"])  # raises on unknown settings


def test_unknown_setting_is_rejected():
    with pytest.raises(ValueError):
        make_settings({"not_a_setting": 1})


def test_tau_sweep_matches_real_system_at_each_tau(demo_app):
    """The sweep's shortcut (S1 candidate if confidence >= tau, else S2) must equal handle(tau=...)."""
    orch = demo_app.orchestrator
    for item in load_split(DATA / "qa.jsonl", "dev"):
        cand = orch.system1_candidate(item["question"])
        s2 = orch.handle(item["question"], mode="agent")
        for tau in (0.5, 0.7, 0.9):
            real = orch.handle(item["question"], mode="ours", tau=tau)
            predicted = cand if cand and cand.confidence >= tau else s2
            assert real.text == predicted.text, (item["id"], tau)


def test_run_experiment_writes_reproducible_artifacts(tmp_path, monkeypatch):
    monkeypatch.delenv("SMRITI_PASSPHRASE", raising=False)
    run_dir = run_experiment(CONFIGS / "tau_sweep_offline.json", results_root=tmp_path)
    for name in ["config.json", "environment.json", "dataset.json", "summary.json", "summary.md",
                 "details.jsonl", "tau_curve.csv"]:
        assert (run_dir / name).exists(), name
    env = json.loads((run_dir / "environment.json").read_text())
    assert "passphrase" not in env["settings"] and env["git_commit"]
    curve = json.loads((run_dir / "summary.json").read_text())["curve"]
    assert curve[-1]["s1_share"] <= curve[0]["s1_share"]  # higher tau, fewer System-1 answers
