# 🔍 BreakCheck

**Stop shipping breaking changes disguised as patches.**

BreakCheck performs AST-level diffing of your Python public API surface between two versions and auto-determines the correct semver bump. Use it as a CI gate to block releases when changes exceed your declared version bump.

## The Problem

- Tag `v2.3.1` but removed a function parameter → 500 downstream CIs go red
- `fix: refactor auth` auto-tagged as patch, but `user_id: int` became `user_id: str`
- Platform team ships "minor" → 3 cross-team incidents from signature changes
- OSS maintainer publishes patch → GitHub Issues flooded by angry users

## 🚀 Quick Start

```bash
pip install typer rich

# Compare two source directories
python breakcheck.py compare ./old_src ./new_src

# Gate a release (exit 1 if breaking changes in a declared "patch")
python breakcheck.py gate ./old_src ./new_src --declared patch

# JSON output for CI
python breakcheck.py compare ./old_src ./new_src --format json
```

## What It Detects

| Change Type | Semver Level |
|---|---|
| Function/class/method removed | 🔴 major |
| Parameter removed | 🔴 major |
| Parameter type changed | 🔴 major |
| Return type changed | 🔴 major |
| Required parameter added | 🔴 major |
| Class attribute removed | 🔴 major |
| Default value removed (now required) | 🔴 major |
| Optional parameter added | 🟡 minor |
| Function/class/method added | 🟡 minor |
| Default value changed | 🟢 patch |

## 💰 Pricing

| Feature | Free (OSS) | Pro $49/mo | Enterprise $299/mo |
|---|---|---|---|
| Python API diff | ✅ | ✅ | ✅ |
| CLI `compare` + `gate` | ✅ | ✅ | ✅ |
| JSON output | ✅ | ✅ | ✅ |
| TypeScript + Go + Rust | — | ✅ | ✅ |
| GitHub Action / GitLab CI | — | ✅ | ✅ |
| PR comment bot | — | ✅ | ✅ |
| Custom rules & policies | — | ✅ | ✅ |
| Multi-repo dashboard | — | — | ✅ |
| Slack/Teams alerts | — | — | ✅ |
| SSO/SAML + audit trail | — | — | ✅ |
| Priority support + SLA | — | — | ✅ |

## 📊 Why Pay?

**One breaking-change incident = 4-8 eng hours × $150/hr = $600-$1,200 wasted.**

At $49/mo, BreakCheck pays for itself after preventing **one** incident. Enterprise teams with 50+ internal packages report 3-5 incidents/month — that's **$1,800-$6,000/month** in wasted time.

## GitHub Actions (Pro)

```yaml
- uses: breakcheck/action@v1
  with:
    old-ref: ${{ github.event.pull_request.base.sha }}
    new-ref: ${{ github.sha }}
    declared-bump: patch
```

## License

MIT (core CLI) | Commercial license for Pro/Enterprise features
