"""Tests del módulo ui/evidence.py."""

from __future__ import annotations

from pathlib import Path

from meeting_forge.ui.evidence import SliceResult, _read_file_lines, read_source_slice

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _write_doc(base: Path, rel_path: str, content: str) -> Path:
    target = base / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# read_source_slice()
# ---------------------------------------------------------------------------


class TestReadSourceSlice:
    def test_returns_correct_slice(self, tmp_path: Path) -> None:
        _write_doc(tmp_path, "doc.md", "linea1\nlinea2\nlinea3\nlinea4\nlinea5")
        result = read_source_slice("doc.md", line_start=2, line_end=4, base_dir=tmp_path)
        assert result.found is True
        assert "linea2" in result.text
        assert "linea3" in result.text
        assert "linea4" in result.text
        assert "linea1" not in result.text
        assert "linea5" not in result.text

    def test_single_line_slice(self, tmp_path: Path) -> None:
        _write_doc(tmp_path, "doc.md", "a\nb\nc")
        result = read_source_slice("doc.md", line_start=2, line_end=2, base_dir=tmp_path)
        assert result.found is True
        assert result.text.strip() == "b"

    def test_file_not_found_returns_found_false(self, tmp_path: Path) -> None:
        result = read_source_slice("no_existe.md", line_start=1, line_end=3, base_dir=tmp_path)
        assert result.found is False
        assert result.warning != ""
        assert result.text == ""

    def test_line_start_out_of_range_returns_found_false(self, tmp_path: Path) -> None:
        _write_doc(tmp_path, "doc.md", "linea1\nlinea2")
        result = read_source_slice("doc.md", line_start=10, line_end=10, base_dir=tmp_path)
        assert result.found is False
        assert "fuera de rango" in result.warning

    def test_line_start_zero_returns_found_false(self, tmp_path: Path) -> None:
        _write_doc(tmp_path, "doc.md", "linea1")
        result = read_source_slice("doc.md", line_start=0, line_end=1, base_dir=tmp_path)
        assert result.found is False

    def test_context_lines_extends_slice(self, tmp_path: Path) -> None:
        _write_doc(tmp_path, "doc.md", "a\nb\nc\nd\ne")
        result = read_source_slice(
            "doc.md", line_start=3, line_end=3, base_dir=tmp_path, context_lines=1
        )
        assert result.found is True
        assert "b" in result.text
        assert "c" in result.text
        assert "d" in result.text

    def test_context_lines_clipped_at_file_start(self, tmp_path: Path) -> None:
        _write_doc(tmp_path, "doc.md", "a\nb\nc")
        result = read_source_slice(
            "doc.md", line_start=1, line_end=1, base_dir=tmp_path, context_lines=5
        )
        assert result.found is True
        assert "a" in result.text

    def test_context_lines_clipped_at_file_end(self, tmp_path: Path) -> None:
        _write_doc(tmp_path, "doc.md", "a\nb\nc")
        result = read_source_slice(
            "doc.md", line_start=3, line_end=3, base_dir=tmp_path, context_lines=5
        )
        assert result.found is True
        assert "c" in result.text

    def test_resolved_path_is_populated(self, tmp_path: Path) -> None:
        _write_doc(tmp_path, "sub/doc.md", "linea1")
        result = read_source_slice("sub/doc.md", line_start=1, line_end=1, base_dir=tmp_path)
        assert result.found is True
        assert "sub" in result.resolved_path or "doc.md" in result.resolved_path

    def test_returns_slice_result_instance(self, tmp_path: Path) -> None:
        _write_doc(tmp_path, "doc.md", "x")
        result = read_source_slice("doc.md", line_start=1, line_end=1, base_dir=tmp_path)
        assert isinstance(result, SliceResult)

    def test_missing_file_warning_mentions_path(self, tmp_path: Path) -> None:
        result = read_source_slice("mi_doc.md", line_start=1, line_end=1, base_dir=tmp_path)
        assert "mi_doc.md" in result.warning


# ---------------------------------------------------------------------------
# _read_file_lines() — cache behaviour
# ---------------------------------------------------------------------------


class TestReadFileLines:
    def test_returns_tuple_of_lines(self, tmp_path: Path) -> None:
        p = tmp_path / "f.md"
        p.write_text("a\nb\nc", encoding="utf-8")
        lines = _read_file_lines(str(p))
        assert lines == ("a", "b", "c")

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        lines = _read_file_lines(str(tmp_path / "missing.md"))
        assert lines is None
