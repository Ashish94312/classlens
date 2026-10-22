import os

from classlens.config import load_env_file


def test_load_env_file(tmp_path, monkeypatch):
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


def test_missing_env_file_is_fine(tmp_path):
    load_env_file(tmp_path / "absent.env")
