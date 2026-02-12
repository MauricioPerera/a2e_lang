"""Tests for a2e_lang.cli."""

import json
import os
import tempfile

import pytest

from a2e_lang.cli import main


def _write_temp_file(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".a2e")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


VALID_SOURCE = '''
workflow "cli-test"

fetch = ApiCall {
    method: "GET"
    url: "https://api.example.com"
    -> /workflow/data
}

run: fetch
'''

INVALID_SOURCE = '''
workflow "bad"
op = ApiCall {}
'''


class TestCliCompile:

    def test_compile_success(self, capsys):
        path = _write_temp_file(VALID_SOURCE)
        try:
            rc = main(["compile", path])
            assert rc == 0
            output = capsys.readouterr().out
            lines = output.strip().split("\n")
            assert len(lines) == 2
            json.loads(lines[0])  # Valid JSON
            json.loads(lines[1])  # Valid JSON
        finally:
            os.unlink(path)

    def test_compile_pretty(self, capsys):
        path = _write_temp_file(VALID_SOURCE)
        try:
            rc = main(["compile", "--pretty", path])
            assert rc == 0
            output = capsys.readouterr().out
            assert "  " in output  # Indented
        finally:
            os.unlink(path)

    def test_compile_validation_failure(self, capsys):
        path = _write_temp_file(INVALID_SOURCE)
        try:
            rc = main(["compile", path])
            assert rc == 1
        finally:
            os.unlink(path)

    def test_compile_file_not_found(self, capsys):
        rc = main(["compile", "nonexistent.a2e"])
        assert rc == 1


class TestCliValidate:

    def test_validate_success(self, capsys):
        path = _write_temp_file(VALID_SOURCE)
        try:
            rc = main(["validate", path])
            assert rc == 0
            output = capsys.readouterr().out
            assert "Valid" in output
        finally:
            os.unlink(path)

    def test_validate_failure(self, capsys):
        path = _write_temp_file(INVALID_SOURCE)
        try:
            rc = main(["validate", path])
            assert rc == 1
        finally:
            os.unlink(path)


class TestCliAst:

    def test_ast_output(self, capsys):
        path = _write_temp_file(VALID_SOURCE)
        try:
            rc = main(["ast", path])
            assert rc == 0
            output = capsys.readouterr().out
            assert "Workflow:" in output
            assert "fetch" in output
        finally:
            os.unlink(path)


class TestCliNoCommand:

    def test_no_command_returns_1(self, capsys):
        rc = main([])
        assert rc == 1
