"""从 tool_call 的 input_json 抽出 shell 命令原文。

三条来源（docs/plan.md §3.1）：
1. 标准 JSON 键：`cmd` / `command` / `CommandLine`；
2. Codex 旧格式：命令内嵌在 JS 脚本的 `tools.exec_command({cmd:"..."})`；
3. 明确排除：`write_stdin`（向已有进程轮询）与 `apply_patch`（打补丁），都不是命令。

JS 脚本里的字符串不能用正则一把梭：三种引号 + 转义 + 模板串。
这里用引号感知扫描器，不引入 JS 运行时。
"""

from __future__ import annotations

import json
from typing import Final

from cmdaudit.models import ExtractedCommand

#: 按优先级排列的标准命令键。
COMMAND_KEYS: Final[tuple[str, ...]] = ("cmd", "command", "CommandLine")

#: 这些 tool_name 不承载 shell 命令，必须整条排除。
EXCLUDED_TOOLS: Final[frozenset[str]] = frozenset(
    {"write_stdin", "apply_patch", "kill_shell", "KillBash", "BashOutput"}
)

_WORKDIR_KEYS: Final[tuple[str, ...]] = ("workdir", "cwd", "working_directory")

_JS_MARKER: Final[str] = "exec_command"


_ESCAPES: Final[dict[str, str]] = {"n": "\n", "t": "\t", "r": "\r"}
_LITERAL_ESCAPES: Final[str] = "\"'`\\/"


def _unescape(char: str) -> str:
    """还原字符串字面量里的转义字符。"""
    if char in _ESCAPES:
        return _ESCAPES[char]
    return char if char in _LITERAL_ESCAPES else "\\" + char


class _Scanner:
    """引号感知的极简 JS 扫描器：只找 `cmd` 键对应的字符串字面量。"""

    __slots__ = ("_i", "_n", "_s")

    def __init__(self, text: str) -> None:
        self._s = text
        self._i = 0
        self._n = len(text)

    def _skip_ws(self) -> None:
        while self._i < self._n and self._s[self._i] in " \t\r\n":
            self._i += 1

    def _read_string(self) -> str | None:
        """当前位置必须是引号，返回解码后的内容。"""
        if self._i >= self._n:
            return None
        quote = self._s[self._i]
        if quote not in "\"'`":
            return None
        self._i += 1
        out: list[str] = []
        while self._i < self._n:
            ch = self._s[self._i]
            if ch == "\\":
                # 保留常见转义的语义，其余原样保留反斜杠加字符。
                nxt = self._s[self._i + 1] if self._i + 1 < self._n else ""
                out.append(_unescape(nxt))
                self._i += 2
                continue
            if ch == quote:
                self._i += 1
                return "".join(out)
            out.append(ch)
            self._i += 1
        return None  # 未闭合

    def find_cmd_strings(self) -> list[str]:
        """扫出所有 `cmd:` / `"cmd":` 后面的字符串字面量，按出现顺序。"""
        found: list[str] = []
        while True:
            idx = self._next_cmd_key()
            if idx is None:
                return found
            self._i = idx
            self._skip_ws()
            if self._i < self._n and self._s[self._i] == ":":
                self._i += 1
                self._skip_ws()
                value = self._read_string()
                if value is not None and value.strip():
                    found.append(value)

    def _next_cmd_key(self) -> int | None:
        """找下一个作为对象键出现的 `cmd`，返回键名结束后的偏移。"""
        while self._i < self._n:
            pos = self._s.find("cmd", self._i)
            if pos < 0:
                return None
            self._i = pos + 3
            before = self._s[pos - 1] if pos > 0 else ""
            # 键名必须独立：前面是引号、逗号、花括号或空白。
            if before and (before.isalnum() or before in "_$."):
                continue
            after_quote = self._s[self._i] if self._i < self._n else ""
            if before in "\"'" and after_quote == before:
                return self._i + 1
            if before in "\"'" and after_quote != before:
                continue
            return self._i
        return None


def _first_str(obj: dict[str, object], keys: tuple[str, ...]) -> tuple[str, str] | None:
    for key in keys:
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return key, value
    return None


def extract_commands(tool_name: str, input_json: str | None) -> list[ExtractedCommand]:
    """返回该 tool_call 承载的所有命令；不是命令则返回空列表。"""
    if tool_name in EXCLUDED_TOOLS or not input_json:
        return []

    text = input_json.strip()
    payload: dict[str, object] | None = None
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            payload = parsed

    if payload is not None:
        hit = _first_str(payload, COMMAND_KEYS)
        if hit is not None:
            key, command = hit
            wd = _first_str(payload, _WORKDIR_KEYS)
            return [
                ExtractedCommand(
                    command=command.strip(),
                    workdir=wd[1] if wd else None,
                    slot=0,
                    slot_count=1,
                    input_kind=key,
                )
            ]
        # 是合法 JSON 但没有命令键：不是命令（例如 write_stdin 的轮询参数）。
        return []

    # 非 JSON：Codex 旧格式的 JS 脚本。
    if _JS_MARKER not in text:
        return []
    commands = _Scanner(text).find_cmd_strings()
    total = len(commands)
    return [
        ExtractedCommand(
            command=cmd.strip(),
            workdir=None,
            slot=i,
            slot_count=total,
            input_kind="js_script",
        )
        for i, cmd in enumerate(commands)
        if cmd.strip()
    ]
