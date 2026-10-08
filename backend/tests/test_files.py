"""Context validation rejects binary, mismatched and malformed input."""

import pytest
from app.core.config import get_settings
from app.services.files import FileError, validate_text_file


@pytest.mark.parametrize(
    ("name", "mime", "content"),
    [
        ("x.exe", "text/plain", b"hello"),
        ("x.txt", "image/png", b"hello"),
        ("x.json", "application/json", b"{bad}"),
        ("x.json", "application/json", b"NaN"),
        ("x.json", "application/json", b"Infinity"),
        ("x.txt", "text/plain", b"\xff"),
        ("x.txt", "text/plain", b"hello\x00"),
        ("x.txt", "text/plain", b"  \n"),
        ("x\r\n.txt", "text/plain", b"text"),
    ],
)
def test_invalid_context(name: str, mime: str, content: bytes) -> None:
    with pytest.raises(FileError):
        validate_text_file(name, mime, content)


@pytest.mark.parametrize(
    ("name", "mime", "content", "canonical"),
    [
        ("../brief.txt", "text/plain; charset=utf-8", b"\xef\xbb\xbfhello", "text/plain"),
        ("C:\\temp\\brief.MD", "application/octet-stream", b"# Heading", "text/markdown"),
        ("data.json", "text/plain", b'{"valid": true}', "application/json"),
    ],
)
def test_valid_context(name: str, mime: str, content: bytes, canonical: str) -> None:
    filename, media_type, text = validate_text_file(name, mime, content)
    assert "/" not in filename and "\\" not in filename
    assert media_type == canonical
    assert text and not text.startswith("\ufeff")


def test_file_size_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTEXT_FILE_MAX_BYTES", "4")
    get_settings.cache_clear()
    assert validate_text_file("brief.txt", "text/plain", b"1234")[2] == "1234"
    with pytest.raises(FileError) as error:
        validate_text_file("brief.txt", "text/plain", b"12345")
    assert error.value.status_code == 413
