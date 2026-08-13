from pathlib import Path

from market_state_observatory.validators import audit_public_tree

ROOT = Path(__file__).resolve().parents[1]

def test_public_site_contains_no_secrets():
    assert audit_public_tree(ROOT / "public") == []

def test_secret_pattern_is_detected(tmp_path):
    name = "APCA_API_" + "SECRET_KEY"
    (tmp_path / "bad.txt").write_text(f'{name}="super-secret-value"')
    assert audit_public_tree(tmp_path)

def test_original_repo_is_not_targeted():
    text = (ROOT / "README.md").read_text()
    assert "does **not** replace or modify" in text
