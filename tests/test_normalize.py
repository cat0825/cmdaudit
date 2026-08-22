"""分组、脱敏、模板化。"""

from __future__ import annotations

import pytest

from cmdaudit.normalize.group import classify_group
from cmdaudit.normalize.redact import redact
from cmdaudit.normalize.template import TemplateEngine, canonicalize, template_id


@pytest.mark.parametrize(
    ("program", "programs", "expected"),
    [
        # 等待独立成组：混进 proc_sys 会掩盖最大的时间黑洞。
        ("sleep", ("sleep", "tail"), "wait"),
        ("git", ("git",), "vcs"),
        ("npm", ("npm",), "pkg"),
        ("pytest", ("pytest",), "test"),
        ("curl", ("curl",), "net"),
        ("rg", ("rg",), "search_read"),
        # 主程序未知时看复合命令里的已知程序。
        ("unknownbin", ("unknownbin", "rg"), "search_read"),
        ("unknownbin", ("unknownbin",), "other"),
    ],
)
def test_classify_group(program: str, programs: tuple[str, ...], expected: str) -> None:
    assert classify_group(program, programs) == expected


@pytest.mark.parametrize(
    "command",
    [
        'curl -H "Authorization: Bearer sk-ant-abcdefghij1234567890" https://x',
        'curl -H "x-api-key: abc123def456ghi" https://x',
        "mysql -u root -p Sup3rSecretPass -e 'select 1'",
        "git clone https://user:ghp_abcdefghijklmnop1234@github.com/o/r.git",
        "export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI1K7MDENG",
        "export API_KEY=abcdef123456789",
    ],
)
def test_credentials_are_redacted(command: str) -> None:
    out, hit = redact(command)
    assert hit
    assert "REDACTED" in out


@pytest.mark.parametrize(
    "command",
    [
        # `_` 也是词字符，`\b` 锚点会放过 `GITHUB_TOKEN=` 这类变量名前缀。
        "export GITHUB_TOKEN=ghp_fake00000000000000",
        "NPM_TOKEN=npm_abcdef0123456789abcdef0123456789abcdef",
        "export MY_SERVICE_API_KEY=skfake0123456789abcdef",
        "export STRIPE_SECRET_KEY=sk_fake_0000000000000000",
        # Slack / npm / HuggingFace 令牌前缀。
        "curl -H 'Authorization: Bearer xoxb-123456789012345678901234' https://slack.com",
        "curl -H 'Authorization: Bearer xoxp-12345678901234567890-12345678901234567890-abcdefghijkl' https://slack.com",  # noqa: E501
        "curl -H 'Authorization: Bearer hf_abcdefghijklmnopqrstuvwxyz123456' https://hf.co",
        # 选项形式。
        "aws s3 cp a.txt s3://b --token=faketoken123456",
        "curl --token faketoken123456 https://x",
    ],
)
def test_prefixed_and_option_credentials_are_redacted(command: str) -> None:
    """`*_TOKEN` / `*_API_KEY` / `*_SECRET` 前缀与 `--token` 选项都要脱敏。"""
    out, hit = redact(command)
    assert hit
    assert "REDACTED" in out
    # 凭据本体必须消失，只留前缀。
    for fragment in ("ghp_fake", "npm_abcdef", "skfake", "sk_fake", "xoxb-1234", "faketoken123456"):
        assert fragment not in out


@pytest.mark.parametrize(
    "command",
    [
        # -p 是路径不是密码；误伤会连带破坏程序名解析。
        "mkdir -p /Users/x/papers",
        # -p 是端口。
        "redis-cli -h h -p 6379 ping",
        "psql -h h -p 5432 -U u db",
        "ssh -p 2222 host",
        # 选项里含关键词但本身不是凭据。
        "git push --set-upstream origin main",
        "docker service create --secret config-secret redis",
        "npm run build -- --flag",
        "echo hello world",
    ],
)
def test_benign_commands_are_untouched(command: str) -> None:
    out, hit = redact(command)
    assert not hit
    assert out == command


def test_placeholder_is_shell_safe() -> None:
    """占位符不能含 < 或 >，否则破坏 bash 语法。"""
    out, _ = redact('curl -H "Authorization: Bearer sk-abcdefghij123456" https://x')
    assert "<" not in out
    assert ">" not in out


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git log --oneline -12", "git log --oneline -<n>"),
        ("rg -n 'foo' /Users/me/proj/a.ts", "rg -n 'foo' <path>"),
        # URL 规则必须先于 path，否则 https://h/x 会变成 <path><path>。
        ("curl -s https://api.example.com/v1/x?a=1", "curl -s <url>"),
        ("sleep 180; tail -5 /tmp/x/a.txt", "sleep <n>; tail -<n> <path>"),
    ],
)
def test_canonicalize(command: str, expected: str) -> None:
    assert canonicalize(command) == expected


def test_same_shape_commands_share_template() -> None:
    engine = TemplateEngine()
    first = engine.fit("git log --oneline -12")
    second = engine.fit("git log --oneline -30")
    assert first == second
    assert template_id("git", "log", first) == template_id("git", "log", second)


def test_different_programs_do_not_share_template_id() -> None:
    assert template_id("git", "log", "x <n>") != template_id("hg", "log", "x <n>")


def test_empty_command_yields_empty_template() -> None:
    assert TemplateEngine().fit("   ") == ""


def test_redaction_keeps_prefix_but_drops_the_credential() -> None:
    """保留前缀便于人工识别类型，凭据本体必须消失。

    因此「命令里还含 `sk-ant-`」不能作为脱敏失败的判据 ——
    真实判据是前缀后是否仍跟着 16 位以上的凭据字符。
    """
    out, hit = redact("export ANTHROPIC_API_KEY=sk-ant-abcdefghij1234567890")
    assert hit
    assert "abcdefghij1234567890" not in out
    assert "REDACTED" in out


def test_grep_patterns_mentioning_key_prefixes_are_not_credentials() -> None:
    """`rg 'ghp_|api_key'` 这类搜索模式不是密钥，不该被当成泄漏。"""
    command = "rg -n 'ghp_|github_pat_|api[_-]?key|secret' src"
    out, hit = redact(command)
    assert not hit
    assert out == command
