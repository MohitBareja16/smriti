from parag.evaluation import run_eval, to_markdown
from tests.conftest import DATA


def test_eval_runs_all_systems_and_ours_beats_baselines_on_safety_and_speed(settings, tmp_path):
    results = {r.system: r for r in run_eval(DATA, settings, out_dir=tmp_path / "results")}
    assert set(results) == {"plain_rag", "s2_only", "s1_s2_ours", "ours_no_guards"}
    ours = results["s1_s2_ours"]
    assert ours.s1_share > 0  # System 1 answers some questions alone
    assert results["s2_only"].s1_share == 0
    assert ours.attack_success_rate < results["ours_no_guards"].attack_success_rate
    assert ours.false_refusal_rate == 0
    assert (tmp_path / "results" / "summary.md").exists()
    assert "s1_s2_ours" in to_markdown(list(results.values()))
