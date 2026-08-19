"""状态三级判定与失败归因。核心是那条红线：exit_code=0 不看文本。"""

from __future__ import annotations

import pytest

from cmdaudit.extract.status import classify_failure, decide_outcome, parse_exit_code


def test_exit_code_zero_never_reads_text() -> None:
    """原型报错率从 20.3% 虚高降到 15.6% 就靠这一条。"""
    text = "Wall time: 0.1 seconds\nProcess exited with code 0\nOutput:\nsrc/a.py:3: error: bad"
    outcome = decide_outcome(text, None)
    assert outcome.status == "ok"
    assert outcome.status_source == "exit_code"
    assert outcome.failure_kind is None


def test_exit_code_zero_overrides_errored_result_event() -> None:
    text = "Process exited with code 0\nOutput:\nfatal: something"
    assert decide_outcome(text, "errored").status == "ok"


@pytest.mark.parametrize(
    ("text", "expected_code"),
    [
        ("Process exited with code 128", 128),
        ("Exit code: 1", 1),
        ("exit code 2", 2),
        ("no code here", None),
    ],
)
def test_exit_code_formats(text: str, expected_code: int | None) -> None:
    assert parse_exit_code(text) == expected_code


@pytest.mark.parametrize(
    ("text", "expected_kind"),
    [
        ("Process exited with code 28\ncurl: (28) Operation timed out", "timeout"),
        ("Process exited with code 6\ncurl: (6) Could not resolve host", "network"),
        ("Process exited with code 1\n{\"error\":\"401 Unauthorized\"}", "permission"),
        ("Process exited with code 127\nbash: rg: command not found", "not_found"),
        ("Process exited with code 128\nfatal: not a git repository", "not_found"),
        ("Process exited with code 1\n3 tests failed", "test"),
        ("Process exited with code 2\nsrc/a.ts(3,1): error TS2304: x", "build"),
        ("Process exited with code 1\nsomething odd happened", "other"),
    ],
)
def test_failure_kinds(text: str, expected_kind: str) -> None:
    outcome = decide_outcome(text, None)
    assert outcome.status == "failed"
    assert outcome.failure_kind == expected_kind
    assert outcome.error_snippet


@pytest.mark.parametrize(
    ("code", "expected_kind"),
    [
        (124, "timeout"),
        (137, "timeout"),
        (126, "permission"),
        (127, "not_found"),
        (130, "interrupted"),
    ],
)
def test_signal_codes_are_classified_without_text(code: int, expected_kind: str) -> None:
    assert classify_failure(None, code) == expected_kind


def test_result_event_used_when_no_exit_code() -> None:
    outcome = decide_outcome("some output", "errored")
    assert outcome.status == "failed"
    assert outcome.status_source == "result_event"
    assert outcome.exit_code is None


def test_result_event_completed_is_ok() -> None:
    outcome = decide_outcome("some output", "completed")
    assert outcome.status == "ok"
    assert outcome.status_source == "result_event"


def test_text_heuristic_is_last_resort() -> None:
    outcome = decide_outcome("Error: boom\nstack", None)
    assert outcome.status == "failed"
    assert outcome.status_source == "text_heuristic"


def test_interruption_is_its_own_kind() -> None:
    outcome = decide_outcome("<turn_aborted> user interrupted", None)
    assert outcome.failure_kind == "interrupted"


def test_no_evidence_is_unknown_not_failed() -> None:
    outcome = decide_outcome("hello world", None)
    assert outcome.status == "unknown"
    assert outcome.status_source == "none"
    assert outcome.failure_kind is None
