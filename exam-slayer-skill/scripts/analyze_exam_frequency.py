#!/usr/bin/env python3
"""Analyze extracted exam materials and rank high-frequency topics.

This script is intentionally course-agnostic and uses only the Python standard
library. It works best on text/Markdown files extracted from past papers,
syllabi, notes, and answer keys.
"""

from __future__ import annotations

import argparse
import json
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
    "briefly", "state", "list", "identify", "following", "according", "answer",
    "question", "questions", "property", "properties", "effect", "role", "feature",
    "features", "advantage", "advantages", "disadvantage", "disadvantages",
    "请", "试", "试述", "论述", "讨论", "辨析", "列举", "指出", "写出", "说出",
    "并", "以及", "及其", "其", "主要", "基本", "核心", "常见", "相关",
    "作用", "特点", "特征", "优点", "缺点", "区别", "联系", "意义", "原因",
    "过程", "步骤", "方法", "方式", "内容", "概念", "知识点",
}

CHINESE_LEADING_NOISE = (
    "请简述", "请说明", "请解释", "请比较", "请分析", "请论述", "请列举",
    "简述", "说明", "解释", "比较", "分析", "论述", "讨论", "列举",
    "指出", "写出", "说出", "根据", "结合", "关于", "下列", "试述",
    "并说明", "并解释", "并分析", "并比较", "并简述", "以及说明",
)
CHINESE_TRAILING_NOISE = (
    "的作用", "的特点", "的特征", "的优点", "的缺点", "的区别", "的联系",
    "的意义", "的原因", "的过程", "的步骤", "的方法", "的方式", "的内容",
    "作用", "特点", "特征", "优点", "缺点", "区别", "联系", "意义", "原因",
)
CHINESE_CONCEPT_SUFFIXES = (
    "算法", "模型", "定理", "公式", "协议", "特性", "级别", "结构", "机制",
    "模式", "方法", "函数", "系统", "框架", "原则", "理论", "技术", "过程",
    "事务", "索引", "范式", "复杂度", "策略", "分类", "定义", "证明",
)
LOW_INFO_CHINESE_PATTERNS = (
    r"^[是否对错正确错误]+$",
    r"^(是什么|为什么|有哪些|如何|怎样|怎么)$",
    r"^(进行|根据|结合|关于|下列|上述|以下)",
    r"(是什么|有哪些|为什么)$",
)


def has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def normalize_term(term: str) -> str:
    term = re.sub(r"\s+", " ", term.strip())
    term = term.strip("，。；：、,.!?！？;:（）()[]【】<>《》\"'")
    term = re.sub(r"\s*（\s*", "（", term)
    term = re.sub(r"\s*）\s*", "）", term)
    term = re.sub(r"\s*\(\s*", "(", term)
    term = re.sub(r"\s*\)\s*", ")", term)
    return term.strip()


def strip_chinese_noise(term: str) -> str:
    term = normalize_term(term)
    changed = True
    while changed:
        changed = False
        for prefix in CHINESE_LEADING_NOISE:
            if term.startswith(prefix) and len(term) > len(prefix) + 1:
                term = term[len(prefix):]
                changed = True
        term = term.lstrip("的之和与及并、：，。 ")
        for suffix in CHINESE_TRAILING_NOISE:
            if term.endswith(suffix) and len(term) > len(suffix) + 1:
                term = term[:-len(suffix)]
                changed = True
        term = term.rstrip("的之和与及并、：，。 ")
    return normalize_term(term)


def is_low_info_chinese(term: str) -> bool:
    if term in STOPWORDS or len(term) < 2:
        return True
    if re.fullmatch(r"[一二三四五六七八九十\d]+", term):
        return True
    if not has_cjk(term):
        return False
    if len(term) <= 2 and not any(term.endswith(suffix) for suffix in CHINESE_CONCEPT_SUFFIXES):
        return True
    return any(re.search(pattern, term) for pattern in LOW_INFO_CHINESE_PATTERNS)


def looks_like_concept(term: str) -> bool:
    if not term or term in STOPWORDS:
        return False
    if re.search(r"\b[A-Z][A-Z0-9+\-/]{1,}\b", term):
        return True
    if has_cjk(term):
        return not is_low_info_chinese(term) and (
            len(term) >= 4
            or any(term.endswith(suffix) for suffix in CHINESE_CONCEPT_SUFFIXES)
            or "（" in term
            or "(" in term
        )
    words = term.lower().split()
    return len(words) >= 2 and not any(word in STOPWORDS for word in words)


def add_term(terms: list[str], term: str) -> None:
    term = strip_chinese_noise(term) if has_cjk(term) else normalize_term(term)
    if looks_like_concept(term):
        terms.append(term)


def term_key(term: str) -> str:
    key = normalize_term(term).lower()
    key = re.sub(r"\s+", " ", key)
    key = re.sub(r"[（）()]", "", key)
    key = key.replace("的", "")
    return key


def terms_overlap(shorter: str, longer: str) -> bool:
    short_key = term_key(shorter)
    long_key = term_key(longer)
    if not short_key or not long_key or short_key == long_key:
        return False
    if short_key in long_key:
        return True
    short_tokens = set(short_key.split())
    long_tokens = set(long_key.split())
    return bool(short_tokens) and short_tokens.issubset(long_tokens)


def better_representative(left: str, right: str, counts: Counter[str]) -> str:
    left_key = term_key(left)
    right_key = term_key(right)
    if left_key in right_key and counts[right] >= max(1, counts[left] // 2):
        return right
    if right_key in left_key and counts[left] >= max(1, counts[right] // 2):
        return left
    left_score = (counts[left], len(left_key), looks_like_concept(left))
    right_score = (counts[right], len(right_key), looks_like_concept(right))
    return left if left_score >= right_score else right


def merge_topic_aliases(topic_counts: Counter[str]) -> dict[str, str]:
    terms = sorted(topic_counts, key=lambda t: (-topic_counts[t], -len(term_key(t)), t))
    aliases = {term: term for term in terms}

    for short in terms:
        target = aliases[short]
        for long in terms:
            if short == long:
                continue
            if terms_overlap(short, long):
                target = better_representative(target, long, topic_counts)
        aliases[short] = target

    changed = True
    while changed:
        changed = False
        for term, target in list(aliases.items()):
            next_target = aliases.get(target, target)
            if next_target != target:
                aliases[term] = next_target
                changed = True
    return aliases


def append_unique(items: list[str], value: str, limit: int | None = None) -> None:
    if value in items:
        return
    if limit is not None and len(items) >= limit:
        return
    items.append(value)


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
    aliases: list[str]


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
            add_term(terms, phrase)

    # Keep distinctive acronyms such as BFS or SQL. Capitalized ordinary names
    # are usually captured better by nearby phrases such as "dijkstra algorithm".
    for token in raw_tokens:
        lower = token.lower()
        if lower in STOPWORDS:
            continue
        if token.isupper() and len(token) >= 2:
            add_term(terms, token)

    # Mixed exam terms such as "ACID 特性" are common in Chinese CS papers.
    for match in re.finditer(r"([A-Z][A-Z0-9+\-/]{1,})\s*(?:的)?\s*([\u4e00-\u9fff]{2,8})", text):
        suffix = strip_chinese_noise(match.group(2))
        if suffix:
            add_term(terms, f"{match.group(1)} {suffix}")

    # Chinese concept-like chunks. Require at least one CJK character; otherwise
    # English words are handled by the phrase extractor above.
    for match in re.finditer(r"[\u4e00-\u9fffA-Za-z0-9·（）()]{2,16}", text):
        chunk = match.group(0)
        if not has_cjk(chunk):
            continue

        # Split common connector patterns so "数据库事务的 ACID 特性，并说明隔离级别的作用"
        # yields compact concepts instead of one long prompt fragment.
        parts = re.split(r"的|并|以及|和|与|、|，|。|；|:", chunk)
        if len(parts) == 1:
            add_term(terms, chunk)
        for part in parts:
            add_term(terms, part)

    return terms


def representative_terms(block: str, max_terms: int = 6) -> list[str]:
    counts = Counter(extract_terms(block))
    selected: list[str] = []
    ranked_terms = sorted(counts, key=lambda t: (-counts[t], -len(term_key(t)), t))
    for term in ranked_terms[:max_terms * 3]:
        # Avoid near-duplicate long phrases when a clearer core phrase exists.
        replaced = False
        for index, chosen in enumerate(selected):
            if term == chosen:
                replaced = True
                break
            if terms_overlap(chosen, term):
                selected[index] = better_representative(chosen, term, counts)
                replaced = True
                break
            if terms_overlap(term, chosen):
                if re.fullmatch(r"[A-Z][A-Z0-9+\-/]{1,}", term):
                    continue
                replaced = True
                break
        if replaced:
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


def alias_label(topic: dict) -> str:
    aliases = topic.get("aliases") or []
    if not aliases:
        return ""
    shown = "、".join(aliases[:3])
    if len(aliases) > 3:
        shown += f" 等 {len(aliases)} 个"
    return f"（合并词：{shown}）"


def analyze(root: Path) -> dict:
    sources: list[SourceInfo] = []
    topic_counts: Counter[str] = Counter()
    topic_sources: dict[str, set[str]] = defaultdict(set)
    topic_years: dict[str, set[int]] = defaultdict(set)
    topic_qtypes: dict[str, Counter] = defaultdict(Counter)
    topic_evidence: dict[str, list[str]] = defaultdict(list)
    source_kinds_by_topic: dict[str, Counter] = defaultdict(Counter)
    topic_aliases: dict[str, set[str]] = defaultdict(set)

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

    alias_map = merge_topic_aliases(topic_counts)
    if alias_map:
        merged_counts: Counter[str] = Counter()
        merged_sources: dict[str, set[str]] = defaultdict(set)
        merged_years: dict[str, set[int]] = defaultdict(set)
        merged_qtypes: dict[str, Counter] = defaultdict(Counter)
        merged_evidence: dict[str, list[str]] = defaultdict(list)
        merged_source_kinds: dict[str, Counter] = defaultdict(Counter)

        for term, target in alias_map.items():
            merged_counts[target] += topic_counts[term]
            merged_sources[target].update(topic_sources[term])
            merged_years[target].update(topic_years[term])
            merged_qtypes[target].update(topic_qtypes[term])
            merged_source_kinds[target].update(source_kinds_by_topic[term])
            if term != target:
                topic_aliases[target].add(term)
            for ev in topic_evidence[term]:
                append_unique(merged_evidence[target], ev, limit=3)

        topic_counts = merged_counts
        topic_sources = merged_sources
        topic_years = merged_years
        topic_qtypes = merged_qtypes
        topic_evidence = merged_evidence
        source_kinds_by_topic = merged_source_kinds

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
                aliases=sorted(topic_aliases[term]),
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
        topic_name = f"{topic['topic']}{alias_label(topic)}"
        lines.append(f"| {i} | {topic_name} | {PRIORITY_LABELS.get(topic['priority'], topic['priority'])} | {topic['score']} | {topic['frequency']} | {years} | {qtypes} |")

    lines.extend(["", "## 证据片段", ""])
    for topic in profile["topics"][:20]:
        lines.append(f"### {topic['topic']}（{PRIORITY_LABELS.get(topic['priority'], topic['priority'])}）{alias_label(topic)}")
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
