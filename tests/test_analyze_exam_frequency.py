from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "exam-slayer-skill" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


analyzer = load_script("analyze_exam_frequency")
builder = load_script("build_slayer_pack")


class AnalyzeExamFrequencyTests(unittest.TestCase):
    def test_chinese_prompt_fragments_are_cleaned_into_concepts(self) -> None:
        text = "1. 请简述数据库事务的 ACID 特性，并说明隔离级别的作用。\n"
        terms = analyzer.representative_terms(text, max_terms=10)

        self.assertIn("数据库事务", terms)
        self.assertIn("ACID 特性", terms)
        self.assertIn("隔离级别", terms)
        self.assertNotIn("请简述数据库事务", terms)
        self.assertNotIn("并说明隔离级别", terms)

    def test_chinese_alias_merge_preserves_years_sources_and_qtypes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "2023期末真题.txt").write_text(
                "1. 请简述数据库事务的 ACID 特性，并说明隔离级别的作用。\n",
                encoding="utf-8",
            )
            (root / "2024期末真题.txt").write_text(
                "1. 简述事务 ACID 特性。\n2. 说明数据库事务的隔离级别。\n",
                encoding="utf-8",
            )

            profile = analyzer.analyze(root)

        by_name = {topic["topic"]: topic for topic in profile["topics"]}
        self.assertIn("ACID 特性", by_name)
        acid = by_name["ACID 特性"]
        self.assertEqual(acid["years"], [2023, 2024])
        self.assertEqual(sorted(acid["sources"]), ["2023期末真题.txt", "2024期末真题.txt"])
        self.assertGreaterEqual(acid["question_types"].get("short_answer", 0), 2)
        self.assertIn("ACID", acid["aliases"])

        with tempfile.TemporaryDirectory() as report_tmp:
            out_dir = Path(report_tmp)
            analyzer.write_report(profile, out_dir)
            report = (out_dir / "high_frequency_topics.md").read_text(encoding="utf-8")
            self.assertIn("合并词", report)

        topic_names = {topic["topic"] for topic in profile["topics"][:20]}
        self.assertNotIn("请简述数据库事务", topic_names)
        self.assertNotIn("并说明隔离级别", topic_names)

    def test_contained_english_aliases_do_not_duplicate_top_topics(self) -> None:
        counts = analyzer.Counter({"binary search tree": 2, "search tree": 2, "tree traversal": 1})
        aliases = analyzer.merge_topic_aliases(counts)

        self.assertEqual(aliases["search tree"], "binary search tree")

    def test_builder_accepts_profile_with_aliases(self) -> None:
        profile = {
            "sources": [{"kind": "past_paper", "year": 2024}],
            "notes": [],
            "topics": [
                {
                    "topic": "ACID 特性",
                    "priority": "High",
                    "score": 88.0,
                    "frequency": 3,
                    "sources": ["2024期末真题.txt"],
                    "years": [2024],
                    "question_types": {"short_answer": 3},
                    "evidence": ["2024期末真题.txt: 简述事务 ACID 特性。"],
                    "aliases": ["ACID", "事务 ACID 特性"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            builder.build_slayer_plan(profile, out_dir, "1 day", "pass")
            builder.build_quick_review(profile, out_dir, "1 day")
            builder.build_practice(profile, out_dir, "1 day")
            builder.build_flashcards(profile, out_dir, "1 day")
            builder.build_risk_report(profile, out_dir)

            self.assertTrue((out_dir / "slayer_plan.md").exists())
            self.assertTrue((out_dir / "quick_review.md").exists())
            self.assertTrue((out_dir / "practice_answers.md").exists())


if __name__ == "__main__":
    unittest.main()
