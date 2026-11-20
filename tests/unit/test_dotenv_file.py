from pathlib import Path

from policypulse_ingest.dotenv_file import upsert_env_value

KEY = "RAG_CORPUS_RESOURCE_NAME"
VALUE = "projects/demo/locations/us-east4/ragCorpora/123"


def test_creates_the_file_when_it_is_missing(tmp_path: Path):
    # Arrange
    env_file = tmp_path / ".env"

    # Act
    upsert_env_value(env_file, KEY, VALUE)

    # Assert
    assert env_file.read_text() == f"{KEY}={VALUE}\n"


def test_replaces_an_existing_value_and_keeps_other_lines_and_comments(tmp_path: Path):
    # Arrange
    env_file = tmp_path / ".env"
    env_file.write_text(f"# project settings\nGOOGLE_CLOUD_PROJECT=demo\n{KEY}=\nOTHER=1\n")

    # Act
    upsert_env_value(env_file, KEY, VALUE)

    # Assert
    assert env_file.read_text() == (
        f"# project settings\nGOOGLE_CLOUD_PROJECT=demo\n{KEY}={VALUE}\nOTHER=1\n"
    )


def test_a_second_identical_write_leaves_the_file_byte_identical(tmp_path: Path):
    # Arrange
    env_file = tmp_path / ".env"
    env_file.write_text("GOOGLE_CLOUD_PROJECT=demo\n")
    upsert_env_value(env_file, KEY, VALUE)
    first = env_file.read_bytes()

    # Act
    upsert_env_value(env_file, KEY, VALUE)

    # Assert
    assert env_file.read_bytes() == first


def test_appends_the_key_on_its_own_line_when_the_file_lacks_a_trailing_newline(tmp_path: Path):
    # Arrange
    env_file = tmp_path / ".env"
    env_file.write_text("GOOGLE_CLOUD_PROJECT=demo")

    # Act
    upsert_env_value(env_file, KEY, VALUE)

    # Assert
    assert env_file.read_text() == f"GOOGLE_CLOUD_PROJECT=demo\n{KEY}={VALUE}\n"


def test_does_not_touch_a_key_that_only_starts_with_the_same_text(tmp_path: Path):
    # Arrange
    env_file = tmp_path / ".env"
    env_file.write_text(f"{KEY}_BACKUP=keep\n")

    # Act
    upsert_env_value(env_file, KEY, VALUE)

    # Assert
    assert env_file.read_text() == f"{KEY}_BACKUP=keep\n{KEY}={VALUE}\n"


def test_leaves_no_temporary_file_behind(tmp_path: Path):
    # Arrange
    env_file = tmp_path / ".env"

    # Act
    upsert_env_value(env_file, KEY, VALUE)

    # Assert
    assert [path.name for path in tmp_path.iterdir()] == [".env"]
