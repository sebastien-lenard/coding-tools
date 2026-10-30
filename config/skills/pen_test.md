<!-- config/skills/fix_unit_test.md -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

1. Create or fix unit tests using pytest. Handle issues in this order: (1) errors, (2) fails, (3) warnings, (4) source coverage.
2. Don't edit code or clear comments or clear docstrings outside of your edits to address the issues.

## Examples of accepted pens and fixes:
```python
def test_live_path_errors(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        my_file.live_path(tmp_path / "missing", "*.txt")

    sub = tmp_path / "empty"
    sub.mkdir()
    with pytest.raises(FileNotFoundError):
        my_file.live_path(sub, "*.txt")
```

```python
try:
   raise ValueError("Error")
except ValueError:
   logger.exception(target, "Message")
```

```python
def test_main_entry_run_failure() -> None:
    """Test failure run via the main CLI."""
    test_args = ["bundle_sources.py", "missing_dir"]
    with patch("sys.argv", test_args), pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
```

```python
@pytest.mark.parametrize(
    ("target", "full_path", "expected"),
    [
        (None, False, ""),
        (None, True, ""),
        ("", False, ""),
        ("", True, ""),
        (Path("file.py"), False, "file: "),
        (Path("file.py"), True, "file.py: "),
        (Path("folder") / "file.py", False, "file: "),
        (Path("folder") / "file.py", True, f"{Path('folder') / 'file.py'}: "),
        (Path("other.txt"), False, "other.txt: "),
        (Path("other.txt"), True, "other.txt: "),
    ],
)
def test_fmt(
    target: str | Path | None,
    full: bool,
    expected: str,
) -> None:
    """Test target formatting handles paths and extensions."""
    assert MyFormatter.fmt(target, full=full) == expected
```

```python
def test_read_config_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test good reading of config."""
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.jsonc"
    config_file.write_text('{"default": "model-a"}', encoding="utf-8")

    cfg = read_config()
    assert cfg["default"] == "model-a"
```

```python
def test_run_mod_as_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checks module run using runpy path loading."""
    script = tmp_path / "main.py"
    script.write_text("pass", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["show_license", str(script), "--no-license"],
    )

    target_path = str(Path(ws_module.__file__).resolve())

    with pytest.raises(SystemExit) as sysexit:
        runpy.run_path(target_path, run_name="__main__")
    assert sysexit.value.code == 0
```

```python
class MockAPIError(Exception):
    """Global mock replacement for APIError."""

    def __init__(
        self,
        message: str | None = None,
        code: int = 400,
        status: str = "INVALID",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status

@patch("this_project.this_client.Client")
    def test_cleanup_files(self, mock_client_cls: MagicMock) -> None:
        """Test cleanup_files handles APIError."""
        adapter = ClientAdapter()
        file_mock = MagicMock()
        file_mock.name = "file_name"
        api_err = MockAPIError(message="Del Fail", code=400)
        mock_client_cls.return_value.files.delete.side_effect = api_err
        with patch("this_project.this_client.errors.APIError", MockAPIError):
            adapter.cleanup_files([file_mock], "TEST")
        mock_client_cls.return_value.files.delete.assert_called_once_with(
            name="file_name",
        )
```

```python
except ServerError as e:
    if e.code == HTTP_SERVICE_UNAVAILABLE:
       this_msg = "Failed. HTTP 503"
       logger.exception(None, this_msg)
    msg = getattr(e, "message", None) or str(e)
```
