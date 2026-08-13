from pathlib import Path

from scripts.build_manifest import canonical_content as build_content
from scripts.verify_manifest import canonical_content as verify_content


def test_text_manifest_content_is_line_ending_independent(tmp_path: Path) -> None:
    path = tmp_path / "example.json"
    path.write_bytes(b'{\r\n  "status": "PASS"\r\n}\r\n')
    expected = b'{\n  "status": "PASS"\n}\n'
    assert build_content(path) == expected
    assert verify_content(path) == expected


def test_binary_manifest_content_is_not_rewritten(tmp_path: Path) -> None:
    path = tmp_path / "evidence.png"
    content = b"\x89PNG\r\n\x1a\n"
    path.write_bytes(content)
    assert build_content(path) == content
    assert verify_content(path) == content
