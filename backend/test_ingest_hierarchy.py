import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ingest


class IngestHierarchyTests(unittest.TestCase):
    def test_parse_sections_supports_alphanumeric_section_labels(self):
        text = """3A. Dormant company
This section covers dormant companies.
76A. Punishment for contravention
This section covers punishment.
"""

        sections = ingest.parse_sections(text)

        self.assertEqual(sections[0]["section"], "3A")
        self.assertEqual(sections[0]["title"], "Dormant company")
        self.assertEqual(sections[1]["section"], "76A")
        self.assertEqual(sections[1]["title"], "Punishment for contravention")

    def test_build_hierarchy_keeps_alphanumeric_section_citation(self):
        text = """76A. Punishment for contravention
(1) If a company accepts deposits in contravention of this Chapter, the company shall be punishable.
"""

        chunks = ingest.build_hierarchy(text, "Indian_Corporate_Act_2013.pdf")

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["citation_path"], "Section 76A(1)")
        self.assertEqual(chunks[0]["section"], "76A")


if __name__ == "__main__":
    unittest.main()
