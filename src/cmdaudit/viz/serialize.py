"""Payload → JSON。

工作台前端是编译产物，Python 侧只做一次数据注入，因此这里是两侧唯一的契约面。
规则：

1. 只序列化 dataclass 里已有的字段，不在此处做新的聚合或推断；
2. 字段名保持 snake_case，与 `model.py` 对齐，避免两套命名；
3. 输出必须是可安全嵌进 ``<script type="application/json">`` 的文本 ——
   ``</script>`` 与 U+2028/U+2029 一律转义，否则外部命令原文能提前闭合标签。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Final

from cmdaudit.viz.model import Payload

#: 注入前必须中和的字符。前两个防标签提前闭合，后两个防 JS 行分隔符解析差异。
_ESCAPES: Final[tuple[tuple[str, str], ...]] = (
    ("<", "\\u003c"),
    (">", "\\u003e"),
    ("&", "\\u0026"),
    ("\u2028", "\\u2028"),
    ("\u2029", "\\u2029"),
)


def payload_to_dict(payload: Payload) -> dict[str, Any]:
    """dataclass → 普通 dict。tuple 会被 asdict 转成 list，JSON 可直接吃。"""
    return asdict(payload)


def payload_to_json(payload: Payload) -> str:
    """序列化为可直接内嵌 HTML 的 JSON 文本。

    `ensure_ascii=False` 保留中文原文（项目名、错误片段常含中文），
    体积也比 \\uXXXX 转义小；随后逐字符中和标签相关符号。
    """
    text = json.dumps(payload_to_dict(payload), ensure_ascii=False, separators=(",", ":"))
    for raw, escaped in _ESCAPES:
        text = text.replace(raw, escaped)
    return text
