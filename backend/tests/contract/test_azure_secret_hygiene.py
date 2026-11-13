from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SENSITIVE_PATTERNS = {
    "*.pem",
    "*.key",
    "*.pfx",
    "*.p12",
    "*.cer",
    "*.crt",
    "*.jks",
    "*.keystore",
    "*token_cache*",
    ".azure/",
    ".azureauth/",
}


def _patterns(name: str) -> set[str]:
    lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")}


def test_git_and_copilot_ignore_protect_azure_credentials_and_keep_example_exception() -> None:
    git_patterns = _patterns(".gitignore")
    copilot_patterns = _patterns(".copilotignore")

    assert SENSITIVE_PATTERNS.issubset(git_patterns)
    assert SENSITIVE_PATTERNS.issubset(copilot_patterns)
    assert ".env.*" in git_patterns
    assert "!.env.example" in git_patterns
    assert ".env*" in copilot_patterns
    assert "!.env.example" in copilot_patterns
    assert "*.env" not in git_patterns
