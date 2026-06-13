#!/usr/bin/env python3
"""Check generated Markdown files for common LaTeX delimiter mistakes."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from output_names import LATEX_VALIDATION_REPORT_MD, PACK_MARKDOWN_FILES

DEFAULT_FILES = PACK_MARKDOWN_FILES


@dataclass
class Issue:
    path: str
    line: int
    message: str
    text: str


def iter_markdown_files(root: Path):
    if root.is_file():
        yield root
        return
    for name in DEFAULT_FILES:
        path = root / name
        if path.exists():
            yield path


def strip_display_delimiters(line: str) -> str:
    return line.replace("$$", "")


def count_unescaped(text: str, token: str) -> int:
    return len(re.findall(rf"(?<!\\){re.escape(token)}", text))


def validate_file(path: Path, root: Path) -> list[Issue]:
    issues: list[Issue] = []
    in_fence = False
    display_open_line: int | None = None

    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        if count_unescaped(line, "$$") % 2 == 1:
            if display_open_line is None:
                display_open_line = line_no
            else:
                display_open_line = None

        inline_area = strip_display_delimiters(line)
        if count_unescaped(inline_area, "$") % 2 == 1:
            issues.append(Issue(str(path.relative_to(root)), line_no, "未配对的 inline math `$` 定界符", stripped))

        if count_unescaped(line, r"\(") != count_unescaped(line, r"\)"):
            issues.append(Issue(str(path.relative_to(root)), line_no, "`\\(` 和 `\\)` 数量不匹配", stripped))

        if count_unescaped(line, r"\[") != count_unescaped(line, r"\]"):
            issues.append(Issue(str(path.relative_to(root)), line_no, "`\\[` 和 `\\]` 数量不匹配", stripped))

    if display_open_line is not None:
        issues.append(Issue(str(path.relative_to(root)), display_open_line, "未闭合的 display math `$$` 块", "$$"))
    return issues


def write_report(root: Path, issues: list[Issue]) -> None:
    lines = ["# LaTeX 渲染检查报告", ""]
    if not issues:
        lines.append("没有发现常见 LaTeX 定界符问题。")
    else:
        lines.extend([
            "发现可能导致公式无法渲染的问题，请先修复再交付：",
            "",
            "| 文件 | 行号 | 问题 | 原文 |",
            "|------|------|------|------|",
        ])
        for issue in issues:
            text = issue.text.replace("|", "\\|")
            lines.append(f"| {issue.path} | {issue.line} | {issue.message} | `{text}` |")
    (root / LATEX_VALIDATION_REPORT_MD).write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Markdown LaTeX delimiters in an Exam Slayer output directory.")
    parser.add_argument("path", help="Exam Slayer output directory or a single Markdown file.")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.exists():
        raise SystemExit(f"Path not found: {root}")

    report_root = root if root.is_dir() else root.parent
    issues: list[Issue] = []
    for path in iter_markdown_files(root):
        issues.extend(validate_file(path, report_root))
    write_report(report_root, issues)

    if issues:
        print(f"[WARN] Found {len(issues)} LaTeX delimiter issues; see {report_root / LATEX_VALIDATION_REPORT_MD}")
        return 1
    print(f"[OK] LaTeX delimiter check passed: {report_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
