#!/usr/bin/env python3
"""Build a time-boxed Exam Slayer pack from exam_profile.json."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


TIME_LIMITS = {
    "2 hours": {"top": 8, "schedule": [("0:00-0:20", "先背最高频考点、公式和答题模板。"), ("0:20-1:20", "集中刷重复出现的题型。"), ("1:20-1:50", "复盘错题和易错点。"), ("1:50-2:00", "只看最后速览。")], "practice": 6},
    "1 day": {"top": 15, "schedule": [("上午", "高频概念、公式和答题模板。"), ("下午", "按题型练习历年重复考法。"), ("晚上", "自测并修补薄弱点。"), ("考前 30 分钟", "只看速记稿和错题。")], "practice": 12},
    "3 days": {"top": 25, "schedule": [("第 1 天", "掌握高频和中频考点。"), ("第 2 天", "按题型练习，并修补薄弱点。"), ("第 3 天", "模拟卷框架、错题复盘、最后记忆。")], "practice": 20},
    "1 week": {"top": 40, "schedule": [("第 1-2 天", "按高频榜建立知识框架。"), ("第 3-4 天", "练习重复考法和典型模板。"), ("第 5 天", "模拟考试并订正。"), ("第 6 天", "集中补弱和背诵。"), ("第 7 天", "最终复习并保留休息时间。")], "practice": 30},
}

TARGET_LABELS = {"pass": "保过", "good": "中高分", "high": "冲高分"}
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


def normalize_time_budget(value: str) -> str:
    v = value.strip().lower()
    if v in TIME_LIMITS:
        return v
    if "2" in v and ("hour" in v or "小时" in v):
        return "2 hours"
    if "1" in v and ("day" in v or "天" in v):
        return "1 day"
    if "3" in v and ("day" in v or "天" in v):
        return "3 days"
    if "week" in v or "周" in v or "7" in v:
        return "1 week"
    return "1 day"


def load_profile(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def topic_line(topic: dict) -> str:
    years = ", ".join(str(y) for y in topic.get("years", [])) or "仅来源文件"
    qtypes = ", ".join(QTYPE_LABELS.get(k, k) for k in list(topic.get("question_types", {}).keys())[:3]) or "未知"
    priority = PRIORITY_LABELS.get(topic["priority"], topic["priority"])
    return f"- **{topic['topic']}**（优先级：{priority}，分数：{topic['score']}）：出现 {topic['frequency']} 次；年份：{years}；题型：{qtypes}"


def build_slayer_plan(profile: dict, out_dir: Path, time_budget: str, target: str) -> None:
    cfg = TIME_LIMITS[time_budget]
    topics = profile.get("topics", [])[: cfg["top"]]
    lines = [
        "# 期末突击复习计划",
        "",
        f"时间预算：**{time_budget}**",
        f"目标：**{TARGET_LABELS.get(target, target)}**",
        "",
        "## 复习顺序",
        "",
    ]
    if target == "pass":
        lines.append("先复习高优先级考点。低频内容除非很容易拿分或老师反复强调，否则先跳过。")
    elif target == "high":
        lines.append("高频和中频考点都要覆盖；完成练习后，再补低频但高分值或核心概念内容。")
    else:
        lines.append("高频考点要完整掌握，中频考点选择性覆盖。")

    lines.extend(["", "## 时间安排", ""])
    for slot, task in cfg["schedule"]:
        lines.append(f"- **{slot}**: {task}")

    lines.extend(["", "## 优先复习考点", ""])
    lines.extend(topic_line(t) for t in topics)

    lines.extend(["", "## 停止规则", "", "- 当你已经能回答重复出现的题型时，就停止扩展笔记。", "- 不确定的答案先标记，不要盲背。", "- 最后一轮只看速记稿、易错点和做错的练习。"])
    (out_dir / "slayer_plan.md").write_text("\n".join(lines), encoding="utf-8")


def build_quick_review(profile: dict, out_dir: Path, time_budget: str) -> None:
    cfg = TIME_LIMITS[time_budget]
    topics = profile.get("topics", [])[: cfg["top"]]
    lines = ["# 考前速记稿", "", "这份文件用于考前反复快速扫读。", ""]
    for i, topic in enumerate(topics, 1):
        evidence = topic.get("evidence", [])
        lines.extend([
            f"## {i}. {topic['topic']}",
            "",
            f"优先级：**{PRIORITY_LABELS.get(topic['priority'], topic['priority'])}** | 出现次数：**{topic['frequency']}** | 分数：**{topic['score']}**",
            "",
            "需要背会：",
            "- 定义 / 核心意思：",
            "- 公式 / 模板 / 步骤：",
            "- 常见易错点：",
            "- 一句话答案：",
            "",
            "证据：",
        ])
        lines.extend(f"- {ev}" for ev in evidence[:2])
        lines.append("")
    (out_dir / "quick_review.md").write_text("\n".join(lines), encoding="utf-8")


def build_practice(profile: dict, out_dir: Path, time_budget: str) -> None:
    cfg = TIME_LIMITS[time_budget]
    topics = profile.get("topics", [])[: cfg["practice"]]
    lines = ["# 针对性练习题", "", "请结合证据片段和原始历年卷补全或改写这些题目。", ""]
    answers = ["# 练习题答案与采分点", ""]
    for i, topic in enumerate(topics, 1):
        qtypes = topic.get("question_types", {})
        qtype = next(iter(qtypes), "short_answer")
        lines.extend([
            f"## 第 {i} 题：{topic['topic']}",
            "",
            f"题型：`{QTYPE_LABELS.get(qtype, qtype)}`",
            "",
            "题目：",
            "",
            "作答区：",
            "",
        ])
        answers.extend([
            f"## 第 {i} 题：{topic['topic']}",
            "",
            "答案：",
            "",
            "采分点：",
            "-",
            "",
            "证据：",
        ])
        answers.extend(f"- {ev}" for ev in topic.get("evidence", [])[:2])
        answers.append("")
    (out_dir / "practice_set.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "practice_answers.md").write_text("\n".join(answers), encoding="utf-8")


def build_flashcards(profile: dict, out_dir: Path, time_budget: str) -> None:
    cfg = TIME_LIMITS[time_budget]
    topics = profile.get("topics", [])[: cfg["top"]]
    with (out_dir / "flashcards.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["正面", "背面", "优先级", "证据"])
        for topic in topics:
            evidence = " | ".join(topic.get("evidence", [])[:1])
            writer.writerow([f"{topic['topic']} 的核心意思是什么？", "", PRIORITY_LABELS.get(topic["priority"], topic["priority"]), evidence])


def build_risk_report(profile: dict, out_dir: Path) -> None:
    sources = profile.get("sources", [])
    past_papers = [s for s in sources if s.get("kind") == "past_paper"]
    years = sorted({s.get("year") for s in past_papers if s.get("year")})
    lines = ["# 风险报告", ""]
    if not sources:
        lines.append("- 没有发现可分析的文本文件。")
    if not past_papers:
        lines.append("- 没有检测到历年试卷/真题。高频排序证据较弱，只能视为基于资料的复习优先级。")
    if len(years) == 1:
        lines.append(f"- 只检测到一个年份的真题：{years[0]}。无法证明跨年份重复。")
    if not any(s.get("kind") == "syllabus" for s in sources):
        lines.append("- 没有检测到考纲/复习范围。无法验证是否覆盖官方范围。")
    if len(lines) == 2:
        lines.append("- 脚本没有发现明显资料风险，但答案准确性仍建议人工核对。")
    lines.extend(["", "脚本备注："])
    lines.extend(f"- {note}" for note in profile.get("notes", []))
    (out_dir / "risk_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an Exam Slayer pack from exam_profile.json.")
    parser.add_argument("exam_profile", help="Path to exam_profile.json generated by analyze_exam_frequency.py.")
    parser.add_argument("--out", default=None, help="Output directory. Defaults to the profile directory.")
    parser.add_argument("--time-budget", default="1 day", help="2 hours, 1 day, 3 days, or 1 week.")
    parser.add_argument("--target", default="pass", choices=["pass", "good", "high"], help="Target score strategy.")
    args = parser.parse_args()

    profile_path = Path(args.exam_profile).resolve()
    profile = load_profile(profile_path)
    out_dir = Path(args.out).resolve() if args.out else profile_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    time_budget = normalize_time_budget(args.time_budget)

    build_slayer_plan(profile, out_dir, time_budget, args.target)
    build_quick_review(profile, out_dir, time_budget)
    build_practice(profile, out_dir, time_budget)
    build_flashcards(profile, out_dir, time_budget)
    build_risk_report(profile, out_dir)

    print(f"[OK] Wrote Exam Slayer pack to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
