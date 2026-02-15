"""BreakCheck output formatters: JSON, SARIF v2.1.0, and plain-text table.

Each formatter exposes a single `format(changes: list[dict]) -> str` method
so the CLI layer stays thin and testable.
"""
import json
from typing import List, Dict


class JsonFormatter:
    """Machine-readable JSON array output for CI pipeline consumption.

    Each element: {kind, target, old_signature, new_signature, severity, file, line, detail}
    """

    def format(self, changes: List[Dict]) -> str:
        results = []
        for c in changes:
            symbol = c.get("symbol", "")
            # Derive file from dotted module path in symbol
            file_path = self._symbol_to_file(symbol)
            results.append({
                "kind": c.get("kind", ""),
                "target": symbol,
                "old_signature": c.get("old_signature", ""),
                "new_signature": c.get("new_signature", ""),
                "severity": c.get("level", "patch"),
                "file": c.get("file", file_path),
                "line": c.get("line", 0),
                "detail": c.get("detail", ""),
            })
        return json.dumps(results, indent=2)

    @staticmethod
    def _symbol_to_file(symbol: str) -> str:
        """Convert dotted symbol like 'api.auth' to 'api.py'."""
        parts = symbol.rsplit(".", 1)
        if len(parts) == 2:
            return parts[0].replace(".", "/") + ".py"
        return ""


class SarifFormatter:
    """SARIF v2.1.0 output for GitHub Code Scanning / Azure DevOps integration."""

    SARIF_SCHEMA = (
        "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/"
        "sarif-2.1/schema/sarif-schema-2.1.0.json"
    )

    def format(self, changes: List[Dict]) -> str:
        rules: Dict[str, dict] = {}
        results = []

        for c in changes:
            rule_id = c.get("kind", "unknown")
            if rule_id not in rules:
                rules[rule_id] = {
                    "id": rule_id,
                    "shortDescription": {
                        "text": rule_id.replace("_", " ").title()
                    },
                    "defaultConfiguration": {
                        "level": self._sarif_level(c.get("level", "patch"))
                    },
                    "helpUri": "https://github.com/breakcheck/breakcheck",
                }

            symbol = c.get("symbol", "")
            file_path = c.get("file", self._symbol_to_file(symbol))
            line = c.get("line", 1)

            result = {
                "ruleId": rule_id,
                "level": self._sarif_level(c.get("level", "patch")),
                "message": {
                    "text": (
                        f"{c.get('kind', '')}: {symbol} — "
                        f"{c.get('detail', '')}"
                    )
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": file_path},
                            "region": {"startLine": line},
                        }
                    }
                ],
            }
            results.append(result)

        sarif = {
            "$schema": self.SARIF_SCHEMA,
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "BreakCheck",
                            "version": "0.1.0",
                            "informationUri": "https://github.com/breakcheck/breakcheck",
                            "rules": list(rules.values()),
                        }
                    },
                    "results": results,
                }
            ],
        }
        return json.dumps(sarif, indent=2)

    @staticmethod
    def _sarif_level(level: str) -> str:
        """Map semver severity to SARIF level."""
        return {"major": "error", "minor": "warning", "patch": "note"}.get(
            level, "note"
        )

    @staticmethod
    def _symbol_to_file(symbol: str) -> str:
        parts = symbol.rsplit(".", 1)
        if len(parts) == 2:
            return parts[0].replace(".", "/") + ".py"
        return "unknown.py"


class TableFormatter:
    """Plain-text table fallback (non-Rich) for string-based output."""

    ICON = {"major": "\U0001f534", "minor": "\U0001f7e1", "patch": "\U0001f7e2"}

    def format(self, changes: List[Dict]) -> str:
        if not changes:
            return "No public API changes detected."

        lines = ["BreakCheck API Diff Report", "=" * 80]
        header = f"{'Level':<12} | {'Kind':<24} | {'Symbol':<36} | Detail"
        lines.append(header)
        lines.append("-" * 80)

        level_rank = {"patch": 0, "minor": 1, "major": 2}
        for c in sorted(changes, key=lambda x: -level_rank.get(x.get("level", "patch"), 0)):
            lv = c.get("level", "patch")
            icon = self.ICON.get(lv, "")
            lines.append(
                f"{icon} {lv:<8} | {c.get('kind', ''):<24} | "
                f"{c.get('symbol', ''):<36} | {c.get('detail', '')}"
            )
        return "\n".join(lines)
