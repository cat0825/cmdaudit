"""候选的数据契约（docs/plan.md §5.3）。

这个模块的全部意义是**让越界在构造时就失败**。

cmdaudit 不判定「某条命令是否必要」—— 那个问题只能由「删掉它之后
故障是否漏掉」来回答，需要反事实实验。所以本工具的输出是待验证假设，
不是结论。契约由三条不变量守住：

1. `evidence_class` 恒为 `exploratory`，禁止出现 `observed_benchmark`；
2. `status` 恒为 `unverified`，只能由外部实验改写；
3. 措辞不得是判决式（「不必要」「应删除」），必须是「疑似」「待验证」。

第 3 条用词表检查。它拦不住所有情况，但能拦住最容易犯的那类
—— 顺手把「疑似冗余」写成「冗余」。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Final, Literal

EvidenceClass = Literal["exploratory"]
CandidateStatus = Literal["unverified"]
VerificationMethod = Literal["counterfactual_run", "manual_inspection"]

#: 下游消费方（Observatory）只接受这两种证据等级进 cohort。
#: cmdaudit 的输出两者都不是，所以出现它们即为契约违规。
FORBIDDEN_EVIDENCE_CLASSES: Final[frozenset[str]] = frozenset(
    {"observed_benchmark", "planning", "verified", "confirmed"}
)

#: 判决式措辞。命中即拒绝构造。
VERDICT_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"(?<!疑似)(?<!可能)不必要"),
    re.compile(r"应(?:该)?(?:删除|移除|去掉|禁止)"),
    re.compile(r"(?<!疑似)冗余(?!\?)(?!性)"),
    re.compile(r"(?:确认|证实|已验证|已证明)(?:是|为)?(?:冗余|无用|多余)"),
    re.compile(r"\b(?:unnecessary|redundant|should be removed|proven)\b", re.IGNORECASE),
    re.compile(r"可以安全(?:删除|移除|跳过)"),
)

#: 必须出现的限定词之一，确保措辞停在假设层面。
HEDGE_WORDS: Final[tuple[str, ...]] = ("疑似", "待验证", "可能", "或许", "值得验证", "假设")


class ContractViolation(ValueError):
    """候选越过了证据等级边界。"""


def _reject_verdict(field_name: str, text: str) -> None:
    for pattern in VERDICT_PATTERNS:
        match = pattern.search(text)
        if match:
            raise ContractViolation(
                f"{field_name} 含判决式措辞 {match.group(0)!r}："
                "cmdaudit 只输出待验证假设，结论由反事实实验给出"
            )


@dataclass(frozen=True, slots=True)
class Verification:
    """怎么验证这条假设。给不出验证方式的候选没有价值，直接丢弃。"""

    method: VerificationMethod
    design: str
    oracle: str

    def __post_init__(self) -> None:
        if not self.design.strip():
            raise ContractViolation("verification.design 不能为空")
        if not self.oracle.strip():
            raise ContractViolation("verification.oracle 不能为空")
        _reject_verdict("verification.design", self.design)


@dataclass(frozen=True, slots=True)
class Candidate:
    """一条待验证假设。"""

    candidate_id: str
    source_rule: str
    command_shape: str
    program: str
    observed: dict[str, Any]
    hypothesis: str
    verification: Verification
    priority: float
    evidence_class: EvidenceClass = "exploratory"
    status: CandidateStatus = "unverified"
    caveats: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        if self.evidence_class != "exploratory":
            raise ContractViolation(
                f"evidence_class 只能是 exploratory，收到 {self.evidence_class!r}"
            )
        if self.status != "unverified":
            raise ContractViolation(
                f"status 只能是 unverified，收到 {self.status!r}；"
                "验证结果只能由外部反事实实验写入"
            )
        if not self.hypothesis.strip():
            raise ContractViolation("hypothesis 不能为空")
        _reject_verdict("hypothesis", self.hypothesis)
        if not any(word in self.hypothesis for word in HEDGE_WORDS):
            raise ContractViolation(
                f"hypothesis 必须含限定词之一 {HEDGE_WORDS}，"
                "否则读者会把假设当结论"
            )
        if not self.observed:
            raise ContractViolation("observed 不能为空：候选必须有可复现的观测依据")

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "source_rule": self.source_rule,
            "command_shape": self.command_shape,
            "program": self.program,
            "observed": dict(self.observed),
            "hypothesis": self.hypothesis,
            "verification": {
                "method": self.verification.method,
                "design": self.verification.design,
                "oracle": self.verification.oracle,
            },
            "priority": self.priority,
            "evidence_class": self.evidence_class,
            "status": self.status,
            "caveats": list(self.caveats),
        }
