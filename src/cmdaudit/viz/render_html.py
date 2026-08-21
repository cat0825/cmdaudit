"""把 Payload 注入编译好的工作台外壳，产出单文件离线 HTML。

设计前提：
读者的动作是「顺着队列下钻到命令原文，判断值不值得写进 AGENTS.md」，
所以页面是可操作的工作台（队列 / 看板 / 抽屉 / ⌘K），不是 KPI 大屏。

架构：
- 外壳 `shell.html` 由 `web/` 子工程（Vite + React + Tailwind + Motion + Recharts）
  预编译成单文件，已内联 CSS、JS 与 Geist 字体，随包分发；
  终端用户装 `cmdaudit` 不需要 Node。
- Python 侧只做**一次**字符串替换：把 payload JSON 塞进外壳里的
  `<script type="application/json" id="cmdaudit-payload">` 占位符。

安全约束：
- payload 里全是外部数据（命令原文、错误片段）。`serialize.payload_to_json`
  已把 `<` `>` `&` 与 U+2028/9 转成 `\\uXXXX`，因此外部数据无法提前闭合 script
  标签，也进不了 HTML 解析上下文。这是唯一的文本出口。
- 无 CDN、无外部字体、无埋点、无服务端；`file://` 双击可用。
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Final

from cmdaudit.viz.model import Payload
from cmdaudit.viz.serialize import payload_to_json

#: 外壳里等待替换的占位符。与 `web/index.html` 保持一致，改一处要改两处。
PAYLOAD_PLACEHOLDER: Final[str] = "__CMDAUDIT_PAYLOAD__"

#: 预编译外壳。缺失说明包没构建完整，属于打包错误。
SHELL_PATH: Final[Path] = Path(__file__).with_name("shell.html")


class ShellMissing(RuntimeError):
    """找不到编译好的工作台外壳。"""


class PlaceholderMissing(RuntimeError):
    """外壳里没有 payload 占位符，注入无处落地。"""


def _esc(value: Any) -> str:
    """HTML 文本转义。

    保留给 `<title>` 这类**必须**进 HTML 解析上下文的少量文本；
    payload 数据一律走 `payload_to_json`，不经这里。
    `None` 渲染成破折号，避免把 "None" 当成数据打出去。
    """
    if value is None:
        return "—"
    return html.escape(str(value), quote=True)


def _esc_attr(value: Any) -> str:
    """属性值转义。与 `_esc` 同源，独立命名是为了让调用点自解释。"""
    return _esc(value)


def load_shell(path: Path | None = None) -> str:
    """读取预编译外壳并校验占位符存在。"""
    shell_path = path or SHELL_PATH
    try:
        shell = shell_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ShellMissing(
            f"找不到工作台外壳 {shell_path}。请在 web/ 下运行 `npm ci && npm run build`，"
            "再把 dist/index.html 复制为 src/cmdaudit/viz/shell.html。"
        ) from exc
    if PAYLOAD_PLACEHOLDER not in shell:
        raise PlaceholderMissing(
            f"外壳 {shell_path} 里没有 {PAYLOAD_PLACEHOLDER}，无法注入数据。"
        )
    return shell


def render_html(payload: Payload, *, shell_path: Path | None = None) -> str:
    """把 payload 注入外壳，返回可直接落盘的完整 HTML。"""
    shell = load_shell(shell_path)
    # 只替换一次：占位符在外壳里唯一，多次替换意味着外壳被改坏了。
    return shell.replace(PAYLOAD_PLACEHOLDER, payload_to_json(payload), 1)
