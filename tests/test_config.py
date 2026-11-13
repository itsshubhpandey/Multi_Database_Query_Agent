from pathlib import Path

from backend.app.config import BACKEND_DIR, PROJECT_DIR, Settings


def test_default_env_files_are_absolute_and_include_documented_backend_env() -> None:
    env_files = tuple(Path(path) for path in Settings.model_config["env_file"])

    assert all(path.is_absolute() for path in env_files)
    assert env_files == (PROJECT_DIR / ".env", BACKEND_DIR / ".env")


def test_settings_load_absolute_env_file_independently_of_working_directory(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / "backend.env"
    env_file.write_text("POSTGRES_URL=postgresql://from-backend-env/test\n", encoding="utf-8")
    unrelated_directory = tmp_path / "unrelated"
    unrelated_directory.mkdir()
    monkeypatch.chdir(unrelated_directory)
    monkeypatch.delenv("POSTGRES_URL", raising=False)

    settings = Settings(_env_file=env_file)

    assert settings.postgres_url == "postgresql://from-backend-env/test"
