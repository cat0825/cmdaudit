"""命令抽取：三种键名 + JS 脚本三种引号 + 非命令排除。"""

from __future__ import annotations

import pytest

from cmdaudit.extract.command import extract_commands


@pytest.mark.parametrize(
    ("tool", "payload", "expected_kind", "expected_command"),
    [
        ("exec_command", '{"cmd":"pwd","workdir":"/x"}', "cmd", "pwd"),
        ("Bash", '{"command":"git status","description":"d"}', "command", "git status"),
        ("run_command", '{"CommandLine":"dir C:\\\\"}', "CommandLine", "dir C:\\"),
    ],
)
def test_standard_keys(tool: str, payload: str, expected_kind: str, expected_command: str) -> None:
    result = extract_commands(tool, payload)
    assert len(result) == 1
    assert result[0].input_kind == expected_kind
    assert result[0].command == expected_command


def test_workdir_is_captured() -> None:
    result = extract_commands("exec_command", '{"cmd":"pwd","workdir":"/tmp/x"}')
    assert result[0].workdir == "/tmp/x"


@pytest.mark.parametrize(
    ("script", "expected"),
    [
        (
            'const r = await tools.exec_command({cmd:"sed -n \'1,240p\' /a/b.md"});',
            ["sed -n '1,240p' /a/b.md"],
        ),
        (
            'await tools.exec_command({\n  cmd: "cat /a/SKILL.md",\n  workdir: "/x"\n});',
            ["cat /a/SKILL.md"],
        ),
        (
            "await tools.exec_command({cmd:`echo \"hi\" && ls`});",
            ['echo "hi" && ls'],
        ),
        (
            "await tools.exec_command({cmd:'grep -n \"x\" f'});",
            ['grep -n "x" f'],
        ),
    ],
)
def test_js_script_three_quote_styles(script: str, expected: list[str]) -> None:
    result = extract_commands("exec", script)
    assert [item.command for item in result] == expected
    assert all(item.input_kind == "js_script" for item in result)


def test_js_script_multiple_commands_get_slots() -> None:
    script = (
        'await tools.exec_command({cmd:"echo a"});'
        'await tools.exec_command({cmd:"echo b"});'
        'await tools.exec_command({cmd:"echo c"});'
    )
    result = extract_commands("exec", script)
    assert [item.command for item in result] == ["echo a", "echo b", "echo c"]
    assert [item.slot for item in result] == [0, 1, 2]
    assert {item.slot_count for item in result} == {3}


def test_js_escape_sequences_are_decoded() -> None:
    result = extract_commands("exec", 'await tools.exec_command({cmd:"echo \\"q\\" && ls"});')
    assert result[0].command == 'echo "q" && ls'


@pytest.mark.parametrize(
    ("tool", "payload"),
    [
        # write_stdin 是向已有进程轮询，不是命令。
        ("write_stdin", '{"session_id":123,"yield_time_ms":5000,"max_output_tokens":10}'),
        ("apply_patch", '{"patch":"*** Begin Patch"}'),
        # 合法 JSON 但没有命令键。
        ("exec_command", '{"session_id":9,"max_output_tokens":10}'),
        # 非 JSON 且不含 exec_command 标记。
        ("exec", 'await tools.apply_patch({patch:"..."})'),
        ("Bash", None),
        ("Bash", ""),
    ],
)
def test_non_commands_are_excluded(tool: str, payload: str | None) -> None:
    assert extract_commands(tool, payload) == []


def test_unclosed_string_is_dropped_not_crashed() -> None:
    assert extract_commands("exec", 'await tools.exec_command({cmd:"unterminated') == []


def test_cmd_substring_in_identifier_is_not_a_key() -> None:
    assert extract_commands("exec", 'await tools.exec_command({mycmdx:"echo a"});') == []
