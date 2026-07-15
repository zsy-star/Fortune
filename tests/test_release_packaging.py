from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app_version import DATABASE_REVISION, PRODUCT_NAME, RULESET_VERSION, VERSION
from scripts.build_release import _zip_directory, scan_release_tree, sha256_file


def test_release_identity_is_consistent() -> None:
    assert PRODUCT_NAME == "FORTUNE"
    assert VERSION == "1.0.0-rc1"
    assert RULESET_VERSION == "FORTUNE_RULESET_2026_V2"
    assert DATABASE_REVISION == "20260715_0010"
    spec = Path("packaging/fortune_release.spec").read_text(encoding="utf-8")
    version_info = Path("packaging/fortune_version_info.txt").read_text(encoding="utf-8")
    notes = Path(f"docs/RELEASE_NOTES_v{VERSION}.txt").read_text(encoding="utf-8")
    for value in (PRODUCT_NAME, VERSION):
        assert value in spec
        assert value in version_info
        assert value in notes
    assert RULESET_VERSION in notes
    assert DATABASE_REVISION in notes


def test_formal_spec_is_onedir_and_bundles_migrations_without_runtime_data() -> None:
    spec = Path("packaging/fortune_release.spec").read_text(encoding="utf-8")
    assert "COLLECT(" in spec
    assert 'name="FORTUNE"' in spec
    assert 'name="FORTUNE_v1.0.0-rc1"' in spec
    assert "FORTUNE_RELEASE_ICON" in spec
    assert "icon=ICON_FILE" in spec
    assert 'PROJECT_ROOT / "alembic.ini"' in spec
    assert 'PROJECT_ROOT / "alembic" / "env.py"' in spec
    assert "data/fortune.db" not in spec
    assert "data/backups" not in spec
    assert '"tests"' in spec


def _fake_release(tmp_path: Path) -> Path:
    release = tmp_path / "FORTUNE_v1.0.0-rc1"
    internal = release / "_internal"
    (internal / "PySide6" / "plugins" / "platforms").mkdir(parents=True)
    (internal / "PySide6" / "plugins" / "imageformats").mkdir(parents=True)
    (internal / "PySide6" / "plugins" / "platforms" / "qwindows.dll").write_bytes(b"dll")
    (internal / "alembic" / "versions").mkdir(parents=True)
    for source in Path("alembic/versions").glob("*.py"):
        (internal / "alembic" / "versions" / source.name).write_text("# migration\n", encoding="utf-8")
    (internal / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    (release / "FORTUNE.exe").write_bytes(b"exe")
    return release


def test_release_scanner_rejects_database_logs_tests_and_secrets(tmp_path) -> None:
    release = _fake_release(tmp_path)
    assert scan_release_tree(release) == []
    (release / "data").mkdir()
    (release / "data" / "fortune.db").write_bytes(b"private")
    (release / "tests").mkdir()
    (release / "secret.pem").write_text("-----BEGIN PRIVATE KEY-----", encoding="utf-8")
    failures = "\n".join(scan_release_tree(release))
    assert "data" in failures
    assert "fortune.db" in failures
    assert "tests" in failures
    assert "secret.pem" in failures


def test_zip_can_extract_and_sha_matches(tmp_path) -> None:
    release = _fake_release(tmp_path)
    zip_path = tmp_path / "release.zip"
    _zip_directory(release, zip_path)
    digest = sha256_file(zip_path)
    assert len(digest) == 64
    extraction = tmp_path / "extracted"
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extraction)
    assert (extraction / release.name / "FORTUNE.exe").read_bytes() == b"exe"
    manifest = {"zip_sha256": digest}
    assert json.loads(json.dumps(manifest))["zip_sha256"] == sha256_file(zip_path)
