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

    def test_parse_sections_skips_table_of_contents_restart(self):
        text = """ARRANGEMENT OF SECTIONS
1. Short title and commencement
2. Definitions

An Act to consolidate and amend the law relating to companies.

1. Short title, extent, commencement and application
Body of section 1.
2. Definitions
Body of section 2.
"""

        sections = ingest.parse_sections(text)

        self.assertEqual(sections[0]["section"], None)
        self.assertIn("An Act to consolidate", sections[0]["text"])
        self.assertEqual(sections[1]["section"], "1")
        self.assertIn("Body of section 1.", sections[1]["text"])
        self.assertEqual(sections[2]["section"], "2")
        self.assertIn("Body of section 2.", sections[2]["text"])

    def test_build_hierarchy_preserves_subsection_after_em_dash_boundary(self):
        text = """132. Constitution of National Financial Reporting Authority.—(1) The Central Government may, by notification, constitute a National Financial Reporting Authority.
(2) Notwithstanding anything contained in any other law for the time being in force, the National Financial Reporting Authority shall—
(a) make recommendations to the Central Government on accounting and auditing standards;
(b) monitor and enforce compliance with accounting standards.
"""

        chunks = ingest.build_hierarchy(text, "Indian_Corporate_Act_2013.pdf")
        citations = {chunk["citation_path"] for chunk in chunks}

        self.assertIn("Section 132(2)(a)", citations)
        self.assertIn("Section 132(2)(b)", citations)
        self.assertNotIn("Section 132(a)", citations)

    def test_parse_sections_moves_inline_subsection_text_out_of_title(self):
        text = """132. Constitution of National Financial Reporting Authority.—(1) The Central Government may constitute the authority.
(2) The authority shall perform its duties.
"""

        sections = ingest.parse_sections(text)

        self.assertEqual(sections[0]["title"], "Constitution of National Financial Reporting Authority.")
        self.assertTrue(sections[0]["text"].startswith("(1) The Central Government may"))


if __name__ == "__main__":
    unittest.main()
