import pytest

from greenwash.settings import Settings

ENV = {
    "GITHUB_APP_ID": " 123 ",
    "GITHUB_PRIVATE_KEY": "-----BEGIN KEY-----\\nabc\\n-----END KEY-----",
    "GITHUB_WEBHOOK_SECRET": "s",
    "TYPESAFE_API_KEY": "k",
}


def test_from_env_reads_and_normalizes():
    settings = Settings.from_env(ENV)
    assert settings.github_app_id == "123"
    assert settings.github_private_key == "-----BEGIN KEY-----\nabc\n-----END KEY-----"
    assert settings.github_webhook_secret == "s"
    assert settings.github_app_slug == "greenwash"
    assert settings.typesafe_model is None


def test_optional_values_are_read():
    settings = Settings.from_env({**ENV, "GITHUB_APP_SLUG": "greenwash-dev", "TYPESAFE_MODEL": "jev-preview"})
    assert (settings.github_app_slug, settings.typesafe_model) == ("greenwash-dev", "jev-preview")


def test_missing_required_values_are_listed():
    with pytest.raises(ValueError, match="GITHUB_WEBHOOK_SECRET, TYPESAFE_API_KEY"):
        Settings.from_env({"GITHUB_APP_ID": "1", "GITHUB_PRIVATE_KEY": "k", "TYPESAFE_API_KEY": " "})
