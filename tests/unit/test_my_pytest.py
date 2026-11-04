# tests/unit/test_my_pytest.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Test module for my_pytest functionality."""
from pathlib import Path
from unittest.mock import MagicMock, patch

from coding_tools import my_pytest
from coding_tools.my_run import RunOutput, RunState


def test_clean_log() -> None:
    """Test clean_log returns correct parts."""
    raw = (
        "some header\n"
        f"{my_pytest.COVERAGE_HEADER}\n"
        "cov info\n"
        f"{my_pytest.SUMMARY_HEADER}\n"
        "summary info"
    )
    cleaned = my_pytest.clean_log(raw)
    assert cleaned == "some header"


def test_clean_log_empty() -> None:
    """Test clean_log returns stripped text if no header."""
    assert my_pytest.clean_log("no headers here") == "no headers here"


def test_clean_log_short_parts() -> None:
    """Test clean_log handles short parts."""
    raw = (
        "==========================================================="
        " ERRORS "
        "==========================================================="
    )
    cleaned = my_pytest.clean_log(raw)
    assert "ERRORS" in cleaned


def test_clean_log_with_coverage_and_summary() -> None:
    """Test clean_log cuts coverage and summary headers."""
    raw = "some content\nshort test summary info\nsummary info"
    cleaned = my_pytest.clean_log(raw)
    assert cleaned == "some content"


def test_clean_log_other_mods_called_return() -> None:
    """Test clean_log returns early when other_mods_called succeeds."""
    raw = (
        "pytest tests/unit/test_foo.py\n"
        f"{my_pytest._BLOCK_SEP}\n"
        "ext_file.py:10: in external_func\n"
        "    foo()\n"
    )
    cleaned = my_pytest.clean_log(raw)
    assert "external_func" in cleaned


def test_check_edited() -> None:
    """Test check_edited returns KEPT state."""
    assert my_pytest.check_edited("out", "err") is not None


def test_check_result_pass() -> None:
    """Test check_result with zero exit code."""
    ro = RunOutput(func="test", status=RunState.PRESTART)
    res = my_pytest.check_result("out", "err", 0, ro)
    assert res.status == RunState.PASS


def test_check_result_fail() -> None:
    """Test check_result with non-zero exit code."""
    ro = RunOutput(func="test", status=RunState.PRESTART)
    res = my_pytest.check_result("out", "err", 1, ro)
    assert res.status == RunState.FAIL


@patch("coding_tools.my_subprocess.run")
@patch("coding_tools.my_path.get_pytest_log_path")
def test_run(
    mock_get_log_path: MagicMock,
    mock_sub_run: MagicMock,
    tmp_path: Path,
) -> None:
    """Test run calls subprocess run with correct parameters."""
    log_p = tmp_path / "log.txt"
    mock_get_log_path.return_value = log_p
    ro = RunOutput(func="test", status=RunState.PRESTART)

    my_pytest.run("dummy_path", ro)
    mock_sub_run.assert_called_once()


def test_extract_file_path_from_log() -> None:
    """Test extracting file path from pytest command line."""
    log = "pytest --import-mode=importlib tests/unit/test_foo.py"
    assert my_pytest._extract_file_path_from_log(log) == Path("tests/unit/test_foo.py")
    assert my_pytest._extract_file_path_from_log("invalid log") is None
    assert my_pytest._extract_file_path_from_log("") is None


def test_other_mods_called_no_test_path() -> None:
    """Test other_mods_called returns False when no test path found."""
    assert my_pytest.other_mods_called("no pytest run") == (False, "")


@patch("coding_tools.my_pytest._resolve_target_mod_path")
@patch("coding_tools.my_pytest._process_block")
def test_other_mods_called_with_traceback(
    mock_process_block: MagicMock,
    mock_resolve: MagicMock,
) -> None:
    """Test other_mods_called delegates to _process_block and returns formatted msg."""
    mock_resolve.return_value = "/path/to/mod.py"
    mock_process_block.side_effect = [
        None,
        "- Function external_func (ext_file.py:10)\n",
    ]
    log = (
        "pytest tests/unit/test_foo.py\n"
        f"{my_pytest._BLOCK_ALT}"
        "ext_file.py:10: in external_func\n"
    )
    success, msg = my_pytest.other_mods_called(log)
    assert success is True
    assert "external_func" in msg
    assert mock_process_block.call_count == 2


@patch("coding_tools.my_pytest._resolve_target_mod_path")
@patch("coding_tools.my_pytest._process_block")
def test_other_mods_called_filtering(
    mock_process_block: MagicMock,
    mock_resolve: MagicMock,
) -> None:
    """Test other_mods_called returns False when _process_block yields no items."""
    mock_resolve.return_value = "/path/to/mod.py"
    mock_process_block.return_value = None

    log = (
        "pytest tests/unit/test_foo.py\n"
        "_________________________________________________________________________________\n"
        "/path/to/mod.py:20: in target_func\n"
        "    pass\n"
    )
    success, msg = my_pytest.other_mods_called(log)
    assert success is False
    assert msg == ""


@patch("coding_tools.my_pytest._extract_file_path_from_log")
@patch("coding_tools.my_pytest._resolve_target_mod_path")
@patch("coding_tools.my_pytest._process_block")
def test_other_mods_called_snippet_branch(
    mock_process_block: MagicMock,
    mock_resolve: MagicMock,
    mock_extract: MagicMock,
) -> None:
    """Test other_mods_called handles resolve correctly."""
    mock_extract.return_value = Path("tests/unit/test_foo.py")
    mock_resolve.return_value = ""
    mock_process_block.side_effect = [
        None,
        "- Function external_func (ext_file.py:10)\n",
    ]

    log = (
        "pytest tests/unit/test_foo.py\n"
        "_________________________________________________________________________________\n"
        "ext_file.py:10: in external_func\n"
        "    bar()\n"
    )
    success, msg = my_pytest.other_mods_called(log)
    assert success is True
    assert "Function external_func" in msg
    assert mock_process_block.call_count == 2


def test_strip_block_noise() -> None:
    """Test _strip_block_noise removes log calls and exception causes."""
    block = (
        f"{my_pytest.LOG_CALL_TAG}\n"
        f"{my_pytest.LOG_CALL_SEP}\n"
        f"{my_pytest.EXC_CAUSE_SEP}\n"
        "traceback content"
    )
    cleaned = my_pytest._strip_block_noise(block)
    assert cleaned == "traceback content"


def test_find_external_match() -> None:
    """Test _find_external_match ignores tests and target module."""
    block = (
        "tests/unit/test_foo.py:5: in test_something\n"
        "    foo()\n"
        "mod.py:10: in target_func\n"
        "    bar()\n"
        "ext_file.py:15: in external_func\n"
        "    baz()\n"
    )
    target_path = Path("mod.py").resolve().as_posix().lower()
    match = my_pytest._find_external_match(block, target_path)
    assert match is not None
    assert match.group(3) == "external_func"


def test_resolve_target_mod_path() -> None:
    """Test _resolve_target_mod_path calls src_path or handles OSError."""
    with patch("coding_tools.my_path.src_path") as mock_src:
        mock_src.return_value = Path("src/mod.py")
        res = my_pytest._resolve_target_mod_path(Path("tests/unit/test_mod.py"))
        assert "mod.py" in res

    with patch("coding_tools.my_path.src_path") as mock_src:
        mock_src.side_effect = OSError("error")
        res = my_pytest._resolve_target_mod_path(Path("tests/unit/test_mod.py"))
        assert res == ""


def test_process_block_full_coverage() -> None:
    """Test _process_block returns formatted string when valid match exists."""
    block = "ext_file.py:15: in external_func\n    baz()\n"
    target_path = Path("mod.py").resolve().as_posix().lower()
    res = my_pytest._process_block(block, target_path)
    assert res is not None
    assert "external_func" in res

    block_no_match = "line without function name\nother line\n"
    match = next(iter(
        my_pytest._TRACE_PAT.finditer("ext_file.py:15: in external_func"),
    ))
    res_no_break = my_pytest._format_external_match(block_no_match, match)
    assert "external_func" in res_no_break
