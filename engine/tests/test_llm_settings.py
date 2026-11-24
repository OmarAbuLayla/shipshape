from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from shipshape.cli import app
from shipshape.llm.client import _cached_tokens, _limit
from shipshape.llm.settings import SettingsError, load_settings

FAKE_KEY = "fake-key-for-tests-only-0000"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "SHIPSHAPE_LLM_PROVIDER",
        "SHIPSHAPE_LLM_MODEL",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "SHIPSHAPE_LLM_API_KEY",
        "SHIPSHAPE_LLM_BASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)


def test_defaults_without_any_configuration() -> None:
    settings = load_settings(read_dotenv=False)

    assert (settings.provider, settings.model) == ("deepseek", "deepseek-flash")
    assert settings.api_key is None
    assert "missing" in settings.key_status()


def test_environment_overrides_and_key_is_never_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHIPSHAPE_LLM_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)

    settings = load_settings(read_dotenv=False)

    assert settings.model == "deepseek-v4-pro"
    assert FAKE_KEY not in settings.key_status()
    assert FAKE_KEY not in repr(settings.key_status())


def test_unknown_provider_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHIPSHAPE_LLM_PROVIDER", "nope")

    with pytest.raises(SettingsError):
        load_settings(read_dotenv=False)


def test_llm_check_reports_missing_key(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)  # no .env anywhere above a temp folder

    result = CliRunner().invoke(app, ["llm-check"])

    assert result.exit_code == 1
    assert "missing" in result.output


def test_llm_check_never_prints_the_key(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)

    result = CliRunner().invoke(app, ["llm-check"])

    assert result.exit_code == 0
    assert FAKE_KEY not in result.output
    assert "set (" in result.output


def test_openai_needs_a_model_and_uses_max_completion_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHIPSHAPE_LLM_PROVIDER", "openai")
    with pytest.raises(SettingsError, match="SHIPSHAPE_LLM_MODEL"):
        load_settings(read_dotenv=False)

    monkeypatch.setenv("SHIPSHAPE_LLM_MODEL", "some-model")
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    settings = load_settings(read_dotenv=False)

    assert settings.base_url == "https://api.openai.com/v1"
    assert settings.api_key == FAKE_KEY
    assert _limit(settings, 100) == {"max_completion_tokens": 100}


def test_openai_compatible_needs_an_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHIPSHAPE_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("SHIPSHAPE_LLM_MODEL", "llama3.1")
    with pytest.raises(SettingsError, match="SHIPSHAPE_LLM_BASE_URL"):
        load_settings(read_dotenv=False)

    monkeypatch.setenv("SHIPSHAPE_LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("SHIPSHAPE_LLM_API_KEY", FAKE_KEY)
    settings = load_settings(read_dotenv=False)

    assert (settings.provider, settings.key_var) == ("openai-compatible", "SHIPSHAPE_LLM_API_KEY")
    assert _limit(settings, 100) == {"max_tokens": 100}


def test_cached_tokens_in_both_usage_formats() -> None:
    assert _cached_tokens(SimpleNamespace(prompt_cache_hit_tokens=7)) == 7
    nested = SimpleNamespace(prompt_tokens_details=SimpleNamespace(cached_tokens=5))
    assert _cached_tokens(nested) == 5
    assert _cached_tokens(SimpleNamespace()) == 0
