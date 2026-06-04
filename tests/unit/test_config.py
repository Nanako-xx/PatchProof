from patchproof.core.config import Settings


def test_settings_defaults_are_safe():
    settings = Settings()

    assert settings.provider == "openai_compatible"
    assert settings.max_investigation_tool_calls == 4
    assert settings.max_hypotheses == 3
    assert settings.max_llm_calls == 10
    assert settings.command_timeout_seconds == 60
    assert settings.max_patch_files == 3
    assert settings.max_patch_changed_lines == 100


def test_settings_load_from_environment(monkeypatch):
    monkeypatch.setenv("PATCHPROOF_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("PATCHPROOF_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("PATCHPROOF_API_KEY", "secret-value")
    monkeypatch.setenv("PATCHPROOF_MAX_LLM_CALLS", "7")

    settings = Settings.from_env()

    assert settings.model == "deepseek-v4-pro"
    assert settings.base_url == "https://api.example.com/v1"
    assert settings.api_key == "secret-value"
    assert settings.max_llm_calls == 7
