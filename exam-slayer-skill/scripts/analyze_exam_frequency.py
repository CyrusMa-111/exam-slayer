#!/usr/bin/env python3
"""Analyze extracted exam materials and rank high-frequency topics.

This script is intentionally course-agnostic and uses only the Python standard
library. It works best on text/Markdown files extracted from past papers,
syllabi, notes, and answer keys.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".tsv"}
SKIP_FILENAMES = {"ingest_summary.md", "needs_visual_review.md", "ingest_manifest.json"}
PAST_PAPER_HINTS = ("真题", "历年", "试卷", "past", "paper", "exam", "final", "midterm")
SYLLABUS_HINTS = ("大纲", "题纲", "考纲", "范围", "syllabus", "outline", "scope")
ANSWER_HINTS = ("答案", "解析", "answer", "solution", "key")
KIND_LABELS = {"past_paper": "历年卷/真题", "syllabus": "考纲/范围", "answer_key": "答案/解析", "material": "课程资料"}
PRIORITY_LABELS = {"High": "高", "Medium": "中", "Low": "低", "Unverified": "未验证"}
QTYPE_LABELS = {
    "single_choice": "单选",
    "multiple_choice": "多选",
    "true_false": "判断",
    "calculation": "计算",
    "essay_case": "论述/案例",
    "short_answer": "简答",
    "proof_derivation": "证明/推导",
    "programming": "编程/算法",
    "unknown": "未知",
}

STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "with", "from", "this", "that", "what", "which", "when",
    "where", "how", "why", "are", "is", "was", "were", "will", "shall", "can",
    "could", "should", "would", "into", "about", "between", "in", "on", "of",
    "to", "as", "by", "so", "explain", "describe",
    "compare", "calculate", "define", "discuss", "简述", "说明", "解释", "比较",
    "计算", "判断", "选择", "下列", "关于", "正确", "错误", "答案", "试题", "题目",
    "问题", "分析", "根据", "结合", "要求", "为什么", "是什么", "哪些", "进行",
    "given", "using", "use", "one", "example", "examples", "its", "application",
    "applications", "case", "cases", "failure", "true", "false", "always", "give",
    "perform", "repeatedly", "chooses", "unvisited", "node", "vertices", "orders",
    "来源文件", "来源", "文件",
}


@dataclass
class SourceInfo:
    path: str
    kind: str
    year: int | None
    chars: int


@dataclass
class Topic:
    topic: str
    priority: str
    score: float
    frequency: int
    sources: list[str]
    years: list[int]
    question_types: dict[str, int]
    evidence: list[str]


def read_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = path.read_text(errors="ignore")
    lines = [line for line in text.splitlines() if not line.startswith("# 来源文件：") and not line.startswith("# Extracted from ")]
    return "\n".join(lines)


def iter_text_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS:
            rel_parts = path.relative_to(root).parts
            if any((part.startswith("__cram") or part.startswith("__exam_slayer")) for part in rel_parts):
                continue
            if path.name in SKIP_FILENAMES:
                continue
            yield path


def infer_year(text: str, name: str) -> int | None:
    candidates = re.findall(r"(20\d{2}|19\d{2})", name + "\n" + text[:1000])
    years = [int(y) for y in candidates if 1990 <= int(y) <= 2100]
    return max(years) if years else None


def infer_kind(path: Path) -> str:
    name = path.name.lower()
    if any(h.lower() in name for h in PAST_PAPER_HINTS):
        return "past_paper"
    if any(h.lower() in name for h in SYLLABUS_HINTS):
        return "syllabus"
    if any(h.lower() in name for h in ANSWER_HINTS):
        return "answer_key"
    return "material"


def split_question_blocks(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n")
    patterns = [
        r"(?m)^\s*(?:第\s*)?\d{1,3}\s*[\.、\)]\s+",
        r"(?m)^\s*[（(]\d{1,3}[）)]\s+",
        r"(?m)^\s*Q\d{1,3}\s*[:.]\s+",
    ]
    starts = sorted({m.start() for p in patterns for m in re.finditer(p, normalized)})
    if not starts:
        chunks = [c.strip() for c in re.split(r"\n{2,}", normalized) if len(c.strip()) > 20]
        return chunks[:500]
    blocks = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(normalized)
        block = normalized[start:end].strip()
        if len(block) > 10:
            blocks.append(block)
    return blocks


def infer_question_type(block: str) -> str:
    head = block[:120]
    if re.search(r"单选|single|choose one|A[\.、].*B[\.、].*C[\.、]", head, re.I | re.S):
        return "single_choice"
    if re.search(r"多选|multiple|choose all", head, re.I):
        return "multiple_choice"
    if re.search(r"判断|true|false|对|错", head, re.I):
        return "true_false"
    if re.search(r"计算|calculate|compute|求|公式", head, re.I):
        return "calculation"
    if re.search(r"论述|讨论|discuss|essay|案例|case", head, re.I):
        return "essay_case"
    if re.search(r"简答|简述|explain|describe|define|定义", head, re.I):
        return "short_answer"
    if re.search(r"证明|prove|derive|推导", head, re.I):
        return "proof_derivation"
    if re.search(r"代码|program|algorithm|complexity|Big-?O|函数|class", head, re.I):
        return "programming"
    return "unknown"


def extract_terms(text: str) -> list[str]:
    terms: list[str] = []

    # English technical phrases, e.g. "interest rate parity". Prefer n-grams
    # over standalone words so generic verbs do not dominate the ranking.
    raw_tokens = re.findall(r"\b[A-Za-z][A-Za-z0-9+\-/]*\b", text)
    clean_tokens = [t.lower() for t in raw_tokens]
    for n in (3, 2):
        for i in range(0, max(0, len(clean_tokens) - n + 1)):
            words = clean_tokens[i:i + n]
            if any(w in STOPWORDS for w in words):
                continue
            phrase = " ".join(words)
            if len(phrase) >= 5:
                terms.append(phrase)

    # Keep distinctive acronyms such as BFS or SQL. Capitalized ordinary names
    # are usually captured better by nearby phrases such as "dijkstra algorithm".
    for token in raw_tokens:
        lower = token.lower()
        if lower in STOPWORDS:
            continue
        if token.isupper() and len(token) >= 2:
            terms.append(token)

    # Chinese concept-like chunks. Require at least one CJK character; otherwise
    # English words are handled by the phrase extractor above.
    for match in re.finditer(r"[\u4e00-\u9fffA-Za-z0-9·（）()]{2,16}", text):
        chunk = match.group(0).strip("（）()")
        if len(chunk) < 2:
            continue
        if not re.search(r"[\u4e00-\u9fff]", chunk):
            continue
        if chunk in STOPWORDS:
            continue
        if re.fullmatch(r"[一二三四五六七八九十]+", chunk):
            continue
        terms.append(chunk)

    return terms


def representative_terms(block: str, max_terms: int = 6) -> list[str]:
    counts = Counter(extract_terms(block))
    selected: list[str] = []
    for term, _ in counts.most_common(max_terms * 3):
        # Avoid near-duplicate long phrases when a clearer core phrase exists.
        if any(term != chosen and (term in chosen or chosen in term) for chosen in selected):
            continue
        selected.append(term)
        if len(selected) >= max_terms:
            break
    return selected


def score_topic(freq: int, years: set[int], source_kinds: Counter, qtypes: Counter, latest_year: int | None) -> float:
    frequency_score = min(freq, 10) * 10
    year_score = len(years) * 6
    if latest_year and years:
        recency_score = max(0, 12 - min(latest_year - max(years), 12))
    else:
        recency_score = 0
    source_score = source_kinds["past_paper"] * 5 + source_kinds["syllabus"] * 4 + source_kinds["answer_key"] * 2
    qtype_score = 6 if any(t in qtypes for t in ("calculation", "essay_case", "proof_derivation", "programming")) else 0
    return float(frequency_score + year_score + recency_score + source_score + qtype_score)


def priority_label(score: float, freq: int, years: set[int]) -> str:
    if (freq >= 2 and len(years) >= 2) or freq >= 4 or len(years) >= 3 or score >= 70:
        return "High"
    if freq >= 2 or score >= 35:
        return "Medium"
    if freq == 1:
        return "Low"
    return "Unverified"


def analyze(root: Path) -> dict:
    sources: list[SourceInfo] = []
    topic_counts: Counter[str] = Counter()
    topic_sources: dict[str, set[str]] = defaultdict(set)
    topic_years: dict[str, set[int]] = defaultdict(set)
    topic_qtypes: dict[str, Counter] = defaultdict(Counter)
    topic_evidence: dict[str, list[str]] = defaultdict(list)
    source_kinds_by_topic: dict[str, Counter] = defaultdict(Counter)

    latest_year = None

    for path in iter_text_files(root):
        text = read_text(path)
        kind = infer_kind(path)
        year = infer_year(text, path.name)
        latest_year = max(latest_year or year or 0, year or 0) or None
        rel = str(path.relative_to(root))
        sources.append(SourceInfo(rel, kind, year, len(text)))

        blocks = split_question_blocks(text) if kind in {"past_paper", "answer_key"} else re.split(r"\n{2,}", text)
        for block in blocks:
            qtype = infer_question_type(block)
            for term in representative_terms(block):
                topic_counts[term] += 1
                topic_sources[term].add(rel)
                if year:
                    topic_years[term].add(year)
                topic_qtypes[term][qtype] += 1
                source_kinds_by_topic[term][kind] += 1
                if len(topic_evidence[term]) < 3:
                    snippet = " ".join(block.split())[:180]
                    topic_evidence[term].append(f"{rel}: {snippet}")

    topics: list[Topic] = []
    for term, freq in topic_counts.items():
        if len(term) < 2:
            continue
        years = topic_years[term]
        score = score_topic(freq, years, source_kinds_by_topic[term], topic_qtypes[term], latest_year)
        topics.append(
            Topic(
                topic=term,
                priority=priority_label(score, freq, years),
                score=round(score, 2),
                frequency=freq,
                sources=sorted(topic_sources[term]),
                years=sorted(years),
                question_types=dict(topic_qtypes[term].most_common()),
                evidence=topic_evidence[term],
            )
        )

    topics.sort(key=lambda t: (-t.score, -t.frequency, t.topic))

    return {
        "root": str(root),
        "source_count": len(sources),
        "sources": [asdict(s) for s in sources],
        "topics": [asdict(t) for t in topics[:100]],
        "notes": [
            "本报告只分析已抽取出的文本文件；PDF/PPTX/DOCX/图片请先经过摄取脚本抽取。",
            "考点抽取是学科无关的启发式结果，请结合证据片段核对。",
        ],
    }


def write_report(profile: dict, out_dir: Path) -> None:
    lines = [
        "# 高频考点报告",
        "",
        f"已分析来源数：{profile['source_count']}",
        "",
        "## 资料来源",
        "",
        "| 文件 | 类型 | 年份 | 字符数 |",
        "|------|------|------|------------|",
    ]
    for src in profile["sources"]:
        lines.append(f"| {src['path']} | {KIND_LABELS.get(src['kind'], src['kind'])} | {src.get('year') or ''} | {src['chars']} |")

    lines.extend(["", "## 考点排序", "", "| 排名 | 考点 | 优先级 | 分数 | 出现次数 | 年份 | 主要题型 |", "|------|------|--------|------|----------|------|----------|"])
    for i, topic in enumerate(profile["topics"][:40], 1):
        qtypes = ", ".join(f"{QTYPE_LABELS.get(k, k)}:{v}" for k, v in list(topic["question_types"].items())[:3])
        years = ", ".join(str(y) for y in topic["years"])
        lines.append(f"| {i} | {topic['topic']} | {PRIORITY_LABELS.get(topic['priority'], topic['priority'])} | {topic['score']} | {topic['frequency']} | {years} | {qtypes} |")

    lines.extend(["", "## 证据片段", ""])
    for topic in profile["topics"][:20]:
        lines.append(f"### {topic['topic']}（{PRIORITY_LABELS.get(topic['priority'], topic['priority'])}）")
        for ev in topic["evidence"]:
            lines.append(f"- {ev}")
        lines.append("")

    (out_dir / "high_frequency_topics.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze high-frequency exam topics from extracted text materials.")
    parser.add_argument("materials_dir", help="Directory containing extracted text/Markdown materials.")
    parser.add_argument("--out", default=None, help="Output directory. Defaults to <materials_dir>/__exam_slayer__.")
    args = parser.parse_args()

    root = Path(args.materials_dir).resolve()
    if not root.is_dir():
        raise SystemExit(f"Directory not found: {root}")

    out_dir = Path(args.out).resolve() if args.out else root / "__exam_slayer__"
    out_dir.mkdir(parents=True, exist_ok=True)

    profile = analyze(root)
    (out_dir / "exam_profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(profile, out_dir)

    print(f"[OK] Wrote {out_dir / 'exam_profile.json'}")
    print(f"[OK] Wrote {out_dir / 'high_frequency_topics.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
