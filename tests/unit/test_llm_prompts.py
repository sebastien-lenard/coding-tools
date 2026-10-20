# tests/unit/test_llm_prompts.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for coding_tools.llm_prompts."""

from pathlib import Path

import pytest

from coding_tools.llm_prompts import (
    build_contents_list,
    generate_coverage_hints,
    load_skill,
)


def test_load_skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test loading a skill file successfully."""
    skills_dir = tmp_path / "config" / "skills"
    skills_dir.mkdir(parents=True)
    skill_file = skills_dir / "test_skill.md"
    skill_file.write_text("Hello skill", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    content = load_skill("test_skill.md")
    assert content == "Hello skill"


def test_load_skill_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test loading a non-existent skill file raises FileNotFoundError."""
    skills_dir = tmp_path / "config" / "skills"
    skills_dir.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError):
        load_skill("non_existent.md")


def test_generate_coverage_hints_no_cover_file(tmp_path: Path) -> None:
    """Test generate_coverage_hints when cover file does not exist."""
    source = tmp_path / "source.py"
    source.write_text("x = 1\n", encoding="utf-8")
    assert generate_coverage_hints(str(source)) == []


def test_generate_coverage_hints_no_source_file(tmp_path: Path) -> None:
    """Test generate_coverage_hints when source file does not exist."""
    source = tmp_path / "source.py"
    cover = tmp_path / "source.py,cover"
    cover.write_text("! x = 1\n", encoding="utf-8")
    assert generate_coverage_hints(str(source)) == []


def test_generate_coverage_hints_idx_out_of_bounds(tmp_path: Path) -> None:
    """Test generate_coverage_hints when cover file has more lines than source file."""
    source = tmp_path / "source.py"
    source.write_text("x = 1\n", encoding="utf-8")
    cover = tmp_path / "source.py,cover"
    cover.write_text("   1: x = 1\n!  2: extra line\n", encoding="utf-8")
    hints = generate_coverage_hints(str(source))
    assert hints == []


def test_generate_coverage_hints_various_lines(tmp_path: Path) -> None:
    """Test generate_coverage_hints with various uncovered code structures."""
    source = tmp_path / "source.py"
    source_content = (
        "x = 1\n"
        "if a and b:\n"
        "    pass\n"
        "if condition:\n"
        "    pass\n"
        "except ValueError:\n"
        "    pass\n"
        "other = 2\n"
    )
    source.write_text(source_content, encoding="utf-8")

    cover_content = (
        "   1: x = 1\n"
        "!  2: if a and b:\n"
        "   3:     pass\n"
        "!  4: if condition:\n"
        "   5:     pass\n"
        "!  6: except ValueError:\n"
        "   7:     pass\n"
        "> 100: out of bounds\n"
    )
    cover = tmp_path / "source.py,cover"
    cover.write_text(cover_content, encoding="utf-8")

    hints = generate_coverage_hints(str(source))
    assert len(hints) > 0


def test_build_contents_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test build_contents_list with caching allowed and disallowed."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "conftest.py").write_text("# conftest\n", encoding="utf-8")

    source = tmp_path / "source.py"
    source.write_text("print('hello')\n", encoding="utf-8")

    monkeypatch.setattr(
        "coding_tools.llm_prompts.is_caching_allowed",
        lambda name: True,
    )
    contents = build_contents_list(
        test_file_path="tests/test_source.py",
        source_file_path=str(source),
        test_content="def test_foo(): pass",
        coverage_content="some coverage",
        pytest_output="some pytest output",
    )
    assert isinstance(contents, list)

    monkeypatch.setattr(
        "coding_tools.llm_prompts.is_caching_allowed",
        lambda name: False,
    )
    contents_no_cache = build_contents_list(
        test_file_path="tests/test_source.py",
        source_file_path=str(source),
        test_content="def test_foo(): pass",
        coverage_content="some coverage",
        pytest_output="some pytest output",
    )
    assert isinstance(contents_no_cache, list)
