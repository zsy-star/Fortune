from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from scripts.pre_release_check import main, run_pre_release_check


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
    (packaging / "fortune_test.spec").write_text("# spec\n", encoding="utf-8")
    (packaging / "fortune_release.spec").write_text("# formal spec\n", encoding="utf-8")
    data = root / "data"
    data.mkdir()
    (data / "backups").mkdir()
    (root / "exports").mkdir()


def _mock_imports_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    real_find_spec = importlib.util.find_spec

    def _find_spec(name: str, package: str | None = None):
        if name in {"PySide6", "sqlalchemy", "openpyxl"}:
            return object()
        return real_find_spec(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", _find_spec)


def _mock_imports_missing(monkeypatch: pytest.MonkeyPatch, missing: str) -> None:
    real_find_spec = importlib.util.find_spec

    def _find_spec(name: str, package: str | None = None):
        if name == missing:
            return None
        if name in {"PySide6", "sqlalchemy", "openpyxl"}:
            return object()
        return real_find_spec(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", _find_spec)


def test_pre_release_check_module_importable() -> None:
    from scripts import pre_release_check  # noqa: F401

    assert callable(pre_release_check.run_pre_release_check)
    assert callable(pre_release_check.main)


def test_run_pre_release_check_returns_clear_structure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_minimal_project(tmp_path)
    _mock_imports_ok(monkeypatch)

    result = run_pre_release_check(tmp_path)

    assert isinstance(result, dict)
    assert "ok" in result
    assert "failures" in result
    assert "warnings" in result
    assert "info" in result
    assert "checks" in result
    assert result["ok"] is True
    assert result["checks"]["requirements_txt"] == "ok"
    assert result["checks"]["import_pyside6"] == "ok"


def test_missing_requirements_txt_is_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_minimal_project(tmp_path)
    (tmp_path / "requirements.txt").unlink()
    _mock_imports_ok(monkeypatch)

    result = run_pre_release_check(tmp_path)

    assert result["ok"] is False
    assert any("requirements.txt" in item for item in result["failures"])


def test_missing_key_dependency_is_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_minimal_project(tmp_path)
    _mock_imports_missing(monkeypatch, "openpyxl")

    result = run_pre_release_check(tmp_path)

    assert result["ok"] is False
    assert any("openpyxl" in item for item in result["failures"])
    assert result["checks"]["import_openpyxl"] == "missing"


def test_pytest_tmp_cursor_dirs_report_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_minimal_project(tmp_path)
    (tmp_path / ".pytest_tmp_cursor99").mkdir()
    _mock_imports_ok(monkeypatch)

    result = run_pre_release_check(tmp_path)

    assert result["ok"] is True
    assert any(".pytest_tmp_cursor" in item for item in result["warnings"])
    assert ".pytest_tmp_cursor99" in result["checks"]["pytest_tmp_cursor_dirs"]


def test_xlsx_files_report_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_minimal_project(tmp_path)
    (tmp_path / "exports" / "test_export.xlsx").write_bytes(b"PK")
    (tmp_path / "root_export.xlsx").write_bytes(b"PK")
    _mock_imports_ok(monkeypatch)

    result = run_pre_release_check(tmp_path)

    assert result["ok"] is True
    assert any("exports/" in item and ".xlsx" in item for item in result["warnings"])
    assert any("项目根目录" in item and ".xlsx" in item for item in result["warnings"])


def test_script_does_not_delete_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_minimal_project(tmp_path)
    (tmp_path / ".pytest_tmp_cursor_keep").mkdir()
    xlsx = tmp_path / "exports" / "keep.xlsx"
    xlsx.write_bytes(b"PK")
    db_file = tmp_path / "data" / "fortune.db"
    db_file.write_bytes(b"sqlite")
    _mock_imports_ok(monkeypatch)

    before = {p.relative_to(tmp_path) for p in tmp_path.rglob("*")}

    run_pre_release_check(tmp_path)
    main(["--project-root", str(tmp_path)])

    after = {p.relative_to(tmp_path) for p in tmp_path.rglob("*")}
    assert before == after
    assert db_file.read_bytes() == b"sqlite"
    assert xlsx.exists()
    assert (tmp_path / ".pytest_tmp_cursor_keep").is_dir()


def test_main_returns_nonzero_when_required_files_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_imports_ok(monkeypatch)

    exit_code = main(["--project-root", str(tmp_path)])

    assert exit_code != 0


def test_main_returns_zero_when_basics_ok_with_only_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_minimal_project(tmp_path)
    (tmp_path / ".pytest_tmp_cursor_warn").mkdir()
    _mock_imports_ok(monkeypatch)

    exit_code = main(["--project-root", str(tmp_path)])

    assert exit_code == 0
