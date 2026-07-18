from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO / "skills" / "xbs-booksource-workflow"
SKILL_FILE = SKILL_DIR / "SKILL.md"


class SkillStructureTests(unittest.TestCase):
    def test_canonical_skill_has_discoverable_frontmatter(self) -> None:
        text = SKILL_FILE.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL)
        self.assertIsNotNone(match)
        frontmatter = match.group(1)
        self.assertIn("name: xbs-booksource-workflow", frontmatter)
        self.assertRegex(frontmatter, r"(?m)^description:\s*\S")
        self.assertLessEqual(len(text.splitlines()), 500)

    def test_skill_references_and_openai_metadata_exist(self) -> None:
        expected = [
            SKILL_DIR / "agents" / "openai.yaml",
            SKILL_DIR / "references" / "xbs-2561-contract.md",
            SKILL_DIR / "references" / "verification-and-delivery.md",
        ]
        self.assertTrue(all(path.is_file() for path in expected))

    def test_legacy_skill_entries_point_to_canonical_skill(self) -> None:
        legacy_entries = [
            REPO / "skills" / "global" / "xbs-booksource-workflow.SKILL.md",
            REPO / "skills" / "local" / "website-to-booksource.SKILL.md",
            REPO / "skills" / "local" / "xiangse-booksource.SKILL.md",
        ]
        for entry in legacy_entries:
            with self.subTest(entry=entry.name):
                text = entry.read_text(encoding="utf-8")
                self.assertIn("skills/xbs-booksource-workflow/SKILL.md", text)


if __name__ == "__main__":
    unittest.main()
