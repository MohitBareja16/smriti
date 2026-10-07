import pytest

from smriti import cli
from smriti.llm import ollama_status


@pytest.fixture()
def demo_env(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "DEMO_DIR", tmp_path / "demo")
    monkeypatch.setenv("SMRITI_LLM", "extractive")
    monkeypatch.delenv("SMRITI_DATA_DIR", raising=False)
    monkeypatch.delenv("SMRITI_PASSPHRASE", raising=False)
    return tmp_path / "demo"


def test_ask_demo_loads_demo_and_answers_with_system1(demo_env, capsys):
    assert cli.main(["ask", "--demo", "When is my DBMS exam?"]) == 0
    out = capsys.readouterr().out
    assert "Loading the demo student" in out
    assert "10 December 2026" in out and "System 1" in out
    assert (demo_env / "smriti.db").exists()


def test_demo_is_loaded_only_once(demo_env, capsys):
    cli.main(["demo"])
    capsys.readouterr()
    cli.main(["docs", "--demo"])
    out = capsys.readouterr().out
    assert "Loading" not in out and "exam_timetable" in out


def test_ui_launches_chainlit_with_packaged_config(demo_env, monkeypatch):
    pytest.importorskip("chainlit")
    calls = {}
    monkeypatch.setattr(cli.subprocess, "call", lambda cmd, env: calls.update(cmd=cmd, env=env) or 0)
    assert cli.main(["ui", "--demo", "--no-browser", "--port", "8123"]) == 0
    assert calls["cmd"][1:4] == ["-m", "chainlit", "run"]
    assert "8123" in calls["cmd"] and "--headless" in calls["cmd"]
    assert calls["env"]["CHAINLIT_APP_ROOT"] == str(cli.UI_DIR)
    assert (cli.UI_DIR / ".chainlit" / "config.toml").exists()
    assert calls["env"]["SMRITI_DATA_DIR"] == str(demo_env)


def test_offline_fallback_when_ollama_is_missing(monkeypatch, capsys):
    monkeypatch.setenv("SMRITI_LLM", "ollama")
    monkeypatch.setenv("SMRITI_OLLAMA_URL", "http://127.0.0.1:9")  # nothing listens here
    cli._choose_llm()
    assert "offline mode" in capsys.readouterr().out
    assert cli.os.environ["SMRITI_LLM"] == "extractive"


def test_ollama_status_reports_unreachable_server():
    ok, msg = ollama_status("qwen2.5:3b", "http://127.0.0.1:9", timeout=0.5)
    assert not ok and "not running" in msg
