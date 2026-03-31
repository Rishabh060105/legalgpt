import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import main


def _where_key(where):
    return json.dumps(where, sort_keys=True)


def _match(document_id, document_name, citation, distance=0.2, document_text=None, **metadata_overrides):
    return {
        "id": document_id,
        "document": document_text or f"{citation} contains detailed legal context for testing retrieval quality.",
        "metadata": {
            "document": document_name,
            "section": citation.split("Section ")[1].split("(")[0],
            "subsection": "",
            "clause": "",
            "subclause": "",
            "citation": citation,
            "type": "structured",
            "title": "Test title",
            **metadata_overrides,
        },
        "distance": distance,
    }


class FakeCollection:
    def __init__(self, get_map=None, query_matches=None):
        self.get_map = get_map or {}
        self.query_matches = query_matches or []
        self.get_calls = []
        self.query_calls = []

    def get(self, where, include):
        self.get_calls.append(where)
        return self.get_map.get(_where_key(where), {"ids": [], "documents": [], "metadatas": []})

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        matches = list(self.query_matches)
        return {
            "ids": [[match["id"] for match in matches]],
            "documents": [[match["document"] for match in matches]],
            "metadatas": [[match["metadata"] for match in matches]],
            "distances": [[match["distance"] for match in matches]],
        }


class CoreFlowTests(unittest.TestCase):
    def test_extract_citation_reference_supports_alphanumeric_sections(self):
        reference = main._extract_citation_reference("Explain Section 76A(2)(a)")

        self.assertEqual(
            reference,
            {
                "section": "76A",
                "subsection": "2",
                "clause": "a",
                "subclause": None,
            },
        )

    def test_query_intent_classification(self):
        self.assertEqual(
            main._classify_query_intent("Explain Section 132(2)(a)", {"section": "132"}),
            "statute",
        )
        self.assertEqual(
            main._classify_query_intent("What did the court hold about independent directors?", None),
            "precedent",
        )
        self.assertEqual(
            main._classify_query_intent("What does Section 132 say, and has any court interpreted it?", {"section": "132"}),
            "mixed",
        )

    def test_staged_exact_lookup_prefers_primary_document(self):
        base_filter = {"section": "132"}
        primary_filter = {"$and": [base_filter, {"document": main.PRIMARY_DOCUMENT}]}
        collection = FakeCollection(
            get_map={
                _where_key(primary_filter): {
                    "ids": ["act-1"],
                    "documents": ["Primary act section text"],
                    "metadatas": [
                        {
                            "document": main.PRIMARY_DOCUMENT,
                            "section": "132",
                            "subsection": "",
                            "clause": "",
                            "subclause": "",
                            "citation": "Section 132",
                            "type": "structured",
                        }
                    ],
                },
                _where_key(base_filter): {
                    "ids": ["precedent-1"],
                    "documents": ["Precedent section text"],
                    "metadatas": [
                        {
                            "document": "Precedent_1.pdf",
                            "section": "132",
                            "subsection": "",
                            "clause": "",
                            "subclause": "",
                            "citation": "Section 132",
                            "type": "structured",
                        }
                    ],
                },
            }
        )

        matches = main._fetch_staged_exact_matches(collection, base_filter)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["metadata"]["document"], main.PRIMARY_DOCUMENT)
        self.assertEqual(collection.get_calls[0], primary_filter)

    def test_exact_lookup_prefers_richer_duplicate_chunk_for_same_citation(self):
        base_filter = {"section": "83"}
        primary_filter = {"$and": [base_filter, {"document": main.PRIMARY_DOCUMENT}]}
        collection = FakeCollection(
            get_map={
                _where_key(primary_filter): {
                    "ids": ["bad-83", "good-83"],
                    "documents": [
                        "company.",
                        (
                            "The Registrar may, on evidence being given to his satisfaction, enter a memorandum "
                            "of satisfaction in the register of charges."
                        ),
                    ],
                    "metadatas": [
                        {
                            "document": main.PRIMARY_DOCUMENT,
                            "section": "83",
                            "subsection": "",
                            "clause": "",
                            "subclause": "",
                            "citation": "Section 83",
                            "type": "structured",
                            "title": "Power of Registrar to make entries of satisfaction",
                        },
                        {
                            "document": main.PRIMARY_DOCUMENT,
                            "section": "83",
                            "subsection": "",
                            "clause": "",
                            "subclause": "",
                            "citation": "Section 83",
                            "type": "structured",
                            "title": "Power of Registrar to make entries of satisfaction",
                        },
                    ],
                },
                _where_key(base_filter): {"ids": [], "documents": [], "metadatas": []},
            }
        )

        matches = main._fetch_staged_exact_matches(collection, base_filter)

        self.assertEqual(matches[0]["id"], "good-83")

    def test_precedent_queries_route_to_precedent_matches_first(self):
        collection = FakeCollection(
            query_matches=[
                _match("precedent-1", "Precedent_1.pdf", "Section 140", 0.18),
                _match("act-1", main.PRIMARY_DOCUMENT, "Section 149", 0.12),
            ]
        )

        retrieval = main._retrieve_matches(collection, "What did the court hold about independent directors?")

        self.assertEqual(retrieval["intent"], "precedent")
        self.assertTrue(retrieval["context_matches"])
        self.assertEqual(retrieval["context_matches"][0]["metadata"]["document"], "Precedent_1.pdf")

    def test_mixed_queries_keep_exact_statute_and_add_precedent_support(self):
        exact_filter = {"$and": [{"section": "132"}, {"document": main.PRIMARY_DOCUMENT}]}
        fallback_filter = {"section": "132"}
        collection = FakeCollection(
            get_map={
                _where_key(exact_filter): {
                    "ids": ["act-1"],
                    "documents": ["Primary act section text"],
                    "metadatas": [
                        {
                            "document": main.PRIMARY_DOCUMENT,
                            "section": "132",
                            "subsection": "",
                            "clause": "",
                            "subclause": "",
                            "citation": "Section 132",
                            "type": "structured",
                        }
                    ],
                },
                _where_key(fallback_filter): {"ids": [], "documents": [], "metadatas": []},
            },
            query_matches=[
                _match("precedent-1", "Precedent_1.pdf", "Section 140", 0.21),
                _match("act-2", main.PRIMARY_DOCUMENT, "Section 132(2)(a)", 0.17),
            ],
        )

        retrieval = main._retrieve_matches(
            collection,
            "What does Section 132 say, and has any court interpreted it?",
        )

        self.assertEqual(retrieval["intent"], "mixed")
        self.assertEqual(retrieval["context_matches"][0]["metadata"]["document"], main.PRIMARY_DOCUMENT)
        self.assertIn("Precedent_1.pdf", [match["metadata"]["document"] for match in retrieval["source_matches"]])

    def test_semantic_reranking_prefers_richer_opc_chunks_over_short_fragments(self):
        collection = FakeCollection(
            query_matches=[
                _match(
                    "bad-83",
                    main.PRIMARY_DOCUMENT,
                    "Section 83",
                    0.18,
                    document_text="company.",
                    title="Power of Registrar to make entries of satisfaction and release in absence of intimation from",
                ),
                _match(
                    "opc-4f",
                    main.PRIMARY_DOCUMENT,
                    "Section 4(f)(i)",
                    0.39,
                    document_text=(
                        "In the case of One Person Company, the name of the nominee who becomes the member on the "
                        "death of the subscriber must be stated in the memorandum."
                    ),
                    subsection="1",
                    clause="f",
                    subclause="i",
                    title="Memorandum",
                ),
                _match(
                    "opc-3c",
                    main.PRIMARY_DOCUMENT,
                    "Section 3(c)",
                    0.31,
                    document_text=(
                        "One person may form a company to be One Person Company by subscribing the memorandum and "
                        "complying with the requirements of this Act."
                    ),
                    subsection="1",
                    clause="c",
                    title="Formation of company",
                ),
            ]
        )

        retrieval = main._retrieve_matches(collection, "Explain One person company in detail")

        self.assertNotEqual(retrieval["context_matches"][0]["metadata"]["citation"], "Section 83")
        self.assertIn(
            retrieval["context_matches"][0]["metadata"]["citation"],
            {"Section 3(c)", "Section 4(f)(i)"},
        )

    def test_context_builder_respects_character_budget(self):
        matches = []
        for index in range(20):
            matches.append(
                {
                    "id": f"doc-{index}",
                    "document": "A" * 900,
                    "metadata": {
                        "document": main.PRIMARY_DOCUMENT,
                        "section": str(index + 1),
                        "subsection": "",
                        "clause": "",
                        "subclause": "",
                        "citation": f"Section {index + 1}",
                        "type": "structured",
                    },
                    "distance": 0.1,
                }
            )

        context_text = main._build_context_text(matches)

        self.assertLessEqual(len(context_text), main.MAX_CONTEXT_CHARS)
        self.assertIn("Section 1", context_text)

    def test_section_sort_key_orders_alphanumeric_sections_correctly(self):
        ordered = sorted(
            ["76A", "3A", "10", "3", "76", "3B"],
            key=main._section_sort_key,
        )

        self.assertEqual(ordered, ["3", "3A", "3B", "10", "76", "76A"])

    def test_limit_semantic_matches_keeps_best_results_when_threshold_filters_everything(self):
        matches = [
            _match("doc-1", main.PRIMARY_DOCUMENT, "Section 2(62)", 1.42),
            _match("doc-2", "Precedent_1.pdf", "Section 149", 1.55),
            _match("doc-3", main.PRIMARY_DOCUMENT, "Section 18", 1.63),
            _match("doc-4", main.PRIMARY_DOCUMENT, "Section 149(1)", 1.71),
        ]

        selected = main._limit_semantic_matches(matches, limit=6)

        self.assertEqual([match["id"] for match in selected], ["doc-1", "doc-2", "doc-3"])

    def test_build_sources_deduplicates_same_citation_and_keeps_richer_chunk(self):
        sources = main._build_sources(
            [
                _match(
                    "good-83",
                    main.PRIMARY_DOCUMENT,
                    "Section 83",
                    0.2,
                    document_text=(
                        "The Registrar may, on evidence being given to his satisfaction, enter a memorandum of "
                        "satisfaction in the register of charges."
                    ),
                    title="Power of Registrar to make entries of satisfaction",
                ),
                _match(
                    "bad-83",
                    main.PRIMARY_DOCUMENT,
                    "Section 83",
                    0.18,
                    document_text="company.",
                    title="Power of Registrar to make entries of satisfaction",
                ),
            ]
        )

        self.assertEqual(len(sources), 1)
        self.assertIn("Registrar", sources[0].full_text)


if __name__ == "__main__":
    unittest.main()
