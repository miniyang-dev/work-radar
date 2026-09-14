"""Unit tests for TextNoteRepository, backed by a real file under tmp_path."""
from __future__ import annotations

from work_radar.infrastructure.storage.text_note_repository import TextNoteRepository


def test_read_returns_empty_string_when_the_file_does_not_exist(tmp_path):
    repository = TextNoteRepository(tmp_path / "note.txt")

    assert repository.read() == ""


def test_write_then_read_round_trips(tmp_path):
    path = tmp_path / "nested" / "note.txt"
    repository = TextNoteRepository(path)

    repository.write("本季重點方向：\n第一項、第二項")

    assert repository.read() == "本季重點方向：\n第一項、第二項"


def test_write_overwrites_previous_content(tmp_path):
    repository = TextNoteRepository(tmp_path / "note.txt")

    repository.write("first")
    repository.write("second")

    assert repository.read() == "second"


def test_crlf_from_an_html_form_is_normalised_on_write(tmp_path):
    """Forms submit textareas with CRLF, but reading the file back
    translates them to LF — so the stored bytes never matched what was
    read, and the generated overview mixed both endings.
    """
    path = tmp_path / "note.txt"
    repository = TextNoteRepository(path)

    repository.write("first\r\nsecond\rthird\n")

    assert path.read_bytes() == b"first\nsecond\nthird\n"
    assert repository.read() == "first\nsecond\nthird\n"
