import io
import os

import pytest

from classlens import config
from classlens.config import direct_download_url, load_env_file

DRIVE_LINK = "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/view?usp=sharing"


@pytest.fixture
def no_eval_key(monkeypatch):
    monkeypatch.setattr(config, "EVAL_KEY_URL", "")


def test_load_env_file(tmp_path, monkeypatch, no_eval_key):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\nFIRST=one\nexport SECOND='two'\nTHIRD=\"three\"\nnot a setting\nKEPT=from-file\n",
        encoding="utf-8",
    )
    for key in ("FIRST", "SECOND", "THIRD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("KEPT", "from-shell")

    load_env_file(env)

    assert (os.environ["FIRST"], os.environ["SECOND"], os.environ["THIRD"]) == ("one", "two", "three")
    assert os.environ["KEPT"] == "from-shell"


def test_missing_env_file_is_fine(tmp_path, no_eval_key):
    load_env_file(tmp_path / "absent.env")


def fake_download(monkeypatch, body: bytes | Exception) -> list[str]:
    """Replace the network call (no real key, no network); returns the URLs requested."""
    requested = []

    def urlopen(url, timeout):
        requested.append(url)
        if isinstance(body, Exception):
            raise body
        return io.BytesIO(body)

    monkeypatch.setattr(config.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(config, "EVAL_KEY_URL", DRIVE_LINK)
    return requested


def test_eval_key_fills_a_missing_key_only(tmp_path, monkeypatch):
    requested = fake_download(monkeypatch, b"ANTHROPIC_API_KEY=sk-ant-test\nAPP_ACCESS_CODE=ignored\n")
    monkeypatch.delenv(config.API_KEY_ENV, raising=False)
    monkeypatch.delenv(config.ACCESS_CODE_ENV, raising=False)

    load_env_file(tmp_path / "absent.env")

    assert os.environ[config.API_KEY_ENV] == "sk-ant-test"
    assert config.ACCESS_CODE_ENV not in os.environ  # only the Claude key is taken from the file
    assert requested == ["https://drive.google.com/uc?export=download&id=1AbCdEfGhIjKlMnOpQrStUvWxYz"]


def test_configured_key_wins_and_nothing_is_fetched(tmp_path, monkeypatch):
    requested = fake_download(monkeypatch, b"ANTHROPIC_API_KEY=sk-ant-other\n")
    monkeypatch.setenv(config.API_KEY_ENV, "sk-ant-mine")
    load_env_file(tmp_path / "absent.env")
    assert os.environ[config.API_KEY_ENV] == "sk-ant-mine" and requested == []


@pytest.mark.parametrize("body", [b"<html>Sign in</html>", b"ANTHROPIC_API_KEY=not-a-key\n", OSError("offline")])
def test_unusable_download_leaves_no_key(tmp_path, monkeypatch, body):
    fake_download(monkeypatch, body)
    monkeypatch.delenv(config.API_KEY_ENV, raising=False)
    load_env_file(tmp_path / "absent.env")
    assert config.API_KEY_ENV not in os.environ


def test_direct_download_url():
    file_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz"
    assert direct_download_url(f"https://drive.google.com/open?id={file_id}").endswith(f"id={file_id}")
    assert direct_download_url("https://example.com/key.env") == "https://example.com/key.env"
