from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from scripts.build_test_release import run_build, sync_release_docs
from scripts.check_test_release import run_check_test_release
from scripts.runtime_init import RUNTIME_DIRECTORIES, ensure_runtime_directories


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = PROJECT_ROOT / "packaging" / "fortune_test.spec"
BUILD_DOC = PROJECT_ROOT / "docs" / "pyinstaller_test_build.md"
STRUCTURE_DOC = PROJECT_ROOT / "docs" / "test_release_structure.md"

FORBIDDEN_SPEC_SNIPPETS = (
    "data/fortune.db",
    "data/backups",
    "exports/",
    ".pytest_tmp",
    ".xlsx",
)


def _write_minimal_project(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "requirements.txt").write_text("PySide6\n", encoding="utf-8")
    (root / "README.md").write_text("# Fortune\n", encoding="utf-8")
    docs = root / "docs"
    docs.mkdir()
    for name in (
        "commercial_test_scope.md",
        "commercial_acceptance_checklist.md",
        "pre_packaging_checklist.md",
        "manual_test_script.md",
        "pyinstaller_test_build.md",
        "test_release_structure.md",
    ):
        (docs / name).write_text(f"# {name}\n", encoding="utf-8")
    packaging = root / "packaging"
    packaging.mkdir()
    (packaging / "fortune_test.spec").write_text(
        "# test spec\n# data/fortune.db must not be bundled\n",
        encoding="utf-8",
    )
    (packaging / "fortune_release.spec").write_text(
        "# formal release spec\n",
        encoding="utf-8",
    )
    (root / "data").mkdir()


def _mock_imports_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    real_find_spec = importlib.util.find_spec

    def _find_spec(name: str, package: str | None = None):
        if name in {"PySide6", "sqlalchemy", "openpyxl"}:
            return object()
        return real_find_spec(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", _find_spec)


def test_fortune_test_spec_exists() -> None:
    assert SPEC_PATH.is_file()


@pytest.mark.parametrize("snippet", FORBIDDEN_SPEC_SNIPPETS)
def test_fortune_test_spec_does_not_bundle_forbidden_paths(snippet: str) -> None:
    content = SPEC_PATH.read_text(encoding="utf-8")
    if snippet in ("data/backups", "exports/"):
        assert f'"{snippet}' not in content
        assert f"'{snippet}" not in content
    elif snippet == "data/fortune.db":
        assert "data/fortune.db" in content  # mentioned in comments as forbidden
        assert ('"data/fortune.db"' not in content) and ("'data/fortune.db'" not in content)
    else:
        assert snippet not in content or "禁止" in content or "切勿" in content


def test_build_test_release_module_importable() -> None:
    from scripts import build_test_release  # noqa: F401

    assert callable(build_test_release.run_build)


def test_build_dry_run_does_not_invoke_pyinstaller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_minimal_project(tmp_path)
    _mock_imports_ok(monkeypatch)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("PyInstaller should not be invoked in dry-run")

    monkeypatch.setattr("scripts.build_test_release.subprocess.run", _fail_if_called)

    result = run_build(
        tmp_path,
        Path("packaging/fortune_test.spec"),
        Path("dist/Fortune"),
        Path("build/fortune_test"),
        dry_run=True,
    )

    assert result["ok"] is True
    assert result["dry_run"] is True


def test_build_rejects_when_pre_release_check_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_minimal_project(tmp_path)
    (tmp_path / "requirements.txt").unlink()
    _mock_imports_ok(monkeypatch)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("PyInstaller should not run when pre_release_check fails")

    monkeypatch.setattr("scripts.build_test_release.subprocess.run", _fail_if_called)

    result = run_build(
        tmp_path,
        Path("packaging/fortune_test.spec"),
        Path("dist/Fortune"),
        Path("build/fortune_test"),
        dry_run=False,
    )

    assert result["ok"] is False
    assert "pre_release_check" in result["message"]


def test_check_test_release_module_importable() -> None:
    from scripts import check_test_release  # noqa: F401

    assert callable(check_test_release.run_check_test_release)


def test_check_test_release_accepts_internal_docs(tmp_path: Path) -> None:
    release = tmp_path / "Fortune"
    internal_docs = release / "_internal" / "docs"
    internal_docs.mkdir(parents=True)
    (internal_docs / "manual_test_script.md").write_text("# test\n", encoding="utf-8")
    (release / "Fortune.exe").write_bytes(b"MZ")

    result = run_check_test_release(release)

    assert result["ok"] is True
    assert result["checks"]["docs"] == "ok"
    assert any("_internal/docs/" in item for item in result["warnings"])


def test_sync_release_docs_copies_to_release_root(tmp_path: Path) -> None:
    release = tmp_path / "Fortune"
    internal_docs = release / "_internal" / "docs"
    internal_docs.mkdir(parents=True)
    (internal_docs / "readme.md").write_text("# doc\n", encoding="utf-8")

    assert sync_release_docs(release) is True
    assert (release / "docs" / "readme.md").read_text(encoding="utf-8") == "# doc\n"


def test_check_test_release_detects_missing_exe(tmp_path: Path) -> None:
    release = tmp_path / "Fortune"
    release.mkdir()
    (release / "docs").mkdir()

    result = run_check_test_release(release)

    assert result["ok"] is False
    assert any("Fortune.exe" in item for item in result["failures"])


def test_check_test_release_detects_forbidden_fortune_db(tmp_path: Path) -> None:
    release = tmp_path / "Fortune"
    (release / "data").mkdir(parents=True)
    (release / "data" / "fortune.db").write_bytes(b"sqlite")
    (release / "Fortune.exe").write_bytes(b"MZ")
    (release / "docs").mkdir()

    result = run_check_test_release(release)

    assert result["ok"] is False
    assert any("fortune.db" in item for item in result["failures"])


def test_check_test_release_does_not_delete_files(tmp_path: Path) -> None:
    release = tmp_path / "Fortune"
    (release / "data").mkdir(parents=True)
    db = release / "data" / "fortune.db"
    db.write_bytes(b"keep")
    xlsx = release / "leak.xlsx"
    xlsx.write_bytes(b"PK")

    before = {p.relative_to(release) for p in release.rglob("*") if p.is_file()}

    run_check_test_release(release)

    after = {p.relative_to(release) for p in release.rglob("*") if p.is_file()}
    assert before == after
    assert db.read_bytes() == b"keep"


def test_pyinstaller_test_build_doc_exists_with_key_steps() -> None:
    content = BUILD_DOC.read_text(encoding="utf-8")
    for keyword in (
        "pre_release_check",
        "dry-run",
        "--build",
        "dist/Fortune",
        "fortune.db",
        "data/backups",
        "exports",
    ):
        assert keyword in content


def test_test_release_structure_doc_forbids_real_data() -> None:
    content = STRUCTURE_DOC.read_text(encoding="utf-8")
    assert "fortune.db" in content
    assert "不要" in content or "禁止" in content
    assert "backups" in content
    assert ".xlsx" in content or "xlsx" in content


def test_ensure_runtime_directories_creates_only_dirs(tmp_path: Path) -> None:
    created = ensure_runtime_directories(tmp_path)

    assert len(created) == len(RUNTIME_DIRECTORIES)
    for relative in RUNTIME_DIRECTORIES:
        assert (tmp_path / relative).is_dir()
    assert not (tmp_path / "data" / "fortune.db").exists()


def test_ensure_runtime_directories_does_not_overwrite_fortune_db(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    db = data / "fortune.db"
    db.write_bytes(b"existing-db")

    ensure_runtime_directories(tmp_path)

    assert db.read_bytes() == b"existing-db"


def test_ensure_runtime_directories_does_not_delete_backups_or_xlsx(tmp_path: Path) -> None:
    backups = tmp_path / "data" / "backups"
    exports = tmp_path / "exports"
    backups.mkdir(parents=True)
    exports.mkdir(parents=True)
    backup = backups / "fortune_backup.db"
    backup.write_bytes(b"backup")
    xlsx = exports / "orders.xlsx"
    xlsx.write_bytes(b"PK")

    ensure_runtime_directories(tmp_path)

    assert backup.read_bytes() == b"backup"
    assert xlsx.read_bytes() == b"PK"
