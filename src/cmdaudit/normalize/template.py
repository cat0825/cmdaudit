"""命令模板化。

主分桶键是 tree-sitter 给的 `program` + `subcommand`（确定性），
Drain3 聚类只作辅助：它的粒度受输入顺序影响，不适合当唯一主键。
先用确定性规则把字面量替换成占位符，再交给 Drain3，
这样同一模板的稳定性远高于直接喂原文。
"""

from __future__ import annotations

import hashlib
import re
from typing import Final

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

_SUBSTITUTIONS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\bREDACTED\b"), "<secret>"),
    (re.compile(r"\b[0-9a-f]{40}\b"), "<sha>"),
    (re.compile(r"\b[0-9a-f]{7,12}\b(?=\s|$)"), "<sha>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?\b"), "<date>"),
    # URL 必须在 path 之前，否则 https://host/x 会被切成 <path><path>。
    (re.compile(r"\b[a-z][a-z0-9+.\-]*://\S+"), "<url>"),
    (re.compile(r"(?<![\w.])/(?:[\w.@+\-]+/)*[\w.@+\-]*"), "<path>"),
    (re.compile(r"(?<![\w.])~(?:/[\w.@+\-]*)*"), "<path>"),
    (re.compile(r"\b\d+\b"), "<n>"),
)

_WS: Final[re.Pattern[str]] = re.compile(r"\s+")


def canonicalize(command: str) -> str:
    """确定性地把字面量换成占位符。同一形状的命令得到同一结果。"""
    text = command.strip()
    for pattern, placeholder in _SUBSTITUTIONS:
        text = pattern.sub(placeholder, text)
    return _WS.sub(" ", text).strip()


def template_id(program: str, subcommand: str | None, template: str) -> str:
    """稳定短 id。含 program/subcommand 保证不同程序的同形命令不撞桶。"""
    key = f"{program}\x1f{subcommand or ''}\x1f{template}"
    return "t_" + hashlib.blake2b(key.encode("utf-8"), digest_size=6).hexdigest()


class TemplateEngine:
    """Drain3 封装。有状态（聚类会随喂入增长），故不做成纯函数。"""

    __slots__ = ("_miner",)

    def __init__(self, *, similarity_threshold: float = 0.5, max_depth: int = 5) -> None:
        config = TemplateMinerConfig()
        config.drain_sim_th = similarity_threshold
        config.drain_depth = max_depth
        config.drain_max_children = 100
        config.drain_max_clusters = 20000
        config.profiling_enabled = False
        self._miner = TemplateMiner(config=config)

    def fit(self, command: str) -> str:
        """返回聚类后的模板；失败时回落到确定性 canonicalize。"""
        canonical = canonicalize(command)
        if not canonical:
            return ""
        try:
            result = self._miner.add_log_message(canonical)
        except Exception:  # Drain3 内部异常不该中断抽取
            return canonical
        mined = result.get("template_mined") if isinstance(result, dict) else None
        return str(mined) if mined else canonical
