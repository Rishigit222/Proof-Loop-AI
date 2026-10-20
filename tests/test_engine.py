import unittest

from proofloop.engine import (
    CandidateClaim,
    ProofLoopEngine,
    Source,
    VerificationStatus,
    extract_candidate_claims,
    generate_repair_proposals,
)


class CandidateExtractionTests(unittest.TestCase):
    def test_candidate_offsets_preserve_original_text(self):
        text = "Intro. Alice is a researcher.\nBob works remotely!"
        claims = extract_candidate_claims(text, source_id="draft")

        self.assertEqual([claim.text for claim in claims], ["Intro.", "Alice is a researcher.", "Bob works remotely!"])
        for claim in claims:
            self.assertEqual(text[claim.start : claim.end], claim.text)
        self.assertEqual(claims[1].source_id, "draft")


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.engine = ProofLoopEngine()

    def test_direct_support(self):
        report = self.engine.verify(
            ["The sky is blue."],
            [Source("weather", "The sky is blue.")],
        )

        result = report.results[0]
        self.assertEqual(result.status, VerificationStatus.SUPPORTED.value)
        self.assertEqual(result.confidence, 1.0)
        self.assertEqual(result.evidence[0].relation, VerificationStatus.SUPPORTED.value)

    def test_unrelated_claim_is_unsupported(self):
        report = self.engine.verify(
            ["The moon is made of cheese."],
            [{"id": "facts", "text": "The sky is blue."}],
        )

        self.assertEqual(report.results[0].status, VerificationStatus.UNSUPPORTED.value)
        self.assertEqual(report.results[0].evidence, ())

    def test_explicit_negation_is_contradiction(self):
        report = self.engine.verify(
            ["The server is online."],
            [{"id": "status", "text": "The server is not online."}],
        )

        result = report.results[0]
        self.assertEqual(result.status, VerificationStatus.CONTRADICTED.value)
        self.assertEqual(result.evidence[0].source_id, "status")

    def test_support_and_negation_from_different_sources_needs_review(self):
        report = self.engine.verify(
            ["The server is online."],
            [
                {"id": "a", "text": "The server is online."},
                {"id": "b", "text": "The server is not online."},
            ],
        )

        self.assertEqual(report.results[0].status, VerificationStatus.NEEDS_REVIEW.value)
        self.assertEqual({item.source_id for item in report.results[0].evidence}, {"a", "b"})

    def test_ambiguous_evidence_needs_review(self):
        report = self.engine.verify(
            ["The launch is successful."],
            [{"id": "briefing", "text": "The launch may be successful."}],
        )

        result = report.results[0]
        self.assertEqual(result.status, VerificationStatus.NEEDS_REVIEW.value)
        self.assertIn("hedge", result.evidence[0].reason)

    def test_evidence_provenance_offsets_are_source_offsets(self):
        source_text = "Background. Alice is a researcher. End."
        report = self.engine.verify(
            [CandidateClaim("Alice is a researcher.", 20, 43)],
            [Source("paper-7", source_text)],
        )

        evidence = report.results[0].evidence[0]
        self.assertEqual(source_text[evidence.start : evidence.end], evidence.text)
        self.assertEqual(evidence.source_id, "paper-7")
        self.assertEqual(evidence.provenance, {"source_id": "paper-7", "start": 12, "end": 34})

    def test_metrics_are_transparent(self):
        report = self.engine.verify(
            ["A is true.", "B is true.", "C is true.", "D is true."],
            [
                {"id": "support", "text": "A is true."},
                {"id": "contradiction", "text": "B is not true."},
                {"id": "ambiguous", "text": "C may be true."},
            ],
        )

        metrics = report.metrics
        self.assertEqual(metrics["total_claims"], 4)
        self.assertEqual(metrics["supported"], 1)
        self.assertEqual(metrics["contradicted"], 1)
        self.assertEqual(metrics["needs_review"], 1)
        self.assertEqual(metrics["unsupported"], 1)
        self.assertEqual(metrics["claims_with_evidence"], 3)
        self.assertEqual(metrics["source_count"], 3)
        self.assertEqual(metrics["evidence_coverage"], 0.75)

    def test_empty_and_malformed_inputs_are_safe(self):
        empty = self.engine.verify(None, None)
        self.assertEqual(empty.results, ())
        self.assertEqual(empty.metrics["total_claims"], 0)
        self.assertEqual(empty.metrics["evidence_coverage"], 0.0)

        malformed = self.engine.verify(
            [None, {"claim": ""}, "Valid claim here."],
            [None, {"id": "bad"}, {"id": "ok", "text": "Something else."}],
        )
        self.assertEqual(malformed.metrics["malformed_claims"], 2)
        self.assertEqual(malformed.metrics["malformed_sources"], 2)
        self.assertEqual(malformed.results[0].status, VerificationStatus.UNSUPPORTED.value)

    def test_repair_proposals_cover_non_supported_results(self):
        report = self.engine.verify(
            ["A is true.", "B is true.", "C is true.", "D is true."],
            [
                {"id": "b", "text": "B is not true."},
                {"id": "c", "text": "C may be true."},
            ],
        )

        proposals = generate_repair_proposals(report)
        self.assertEqual(len(proposals), 4)
        self.assertEqual({proposal.status for proposal in proposals}, {
            VerificationStatus.UNSUPPORTED.value,
            VerificationStatus.CONTRADICTED.value,
            VerificationStatus.NEEDS_REVIEW.value,
        })
        self.assertTrue(all(proposal.action and proposal.rationale for proposal in proposals))

    def test_unrelated_negation_does_not_become_false_contradiction(self):
        report = self.engine.verify(["The server is online."], [Source("status", "The server is online, but not stable.")])
        self.assertEqual(report.results[0].status, VerificationStatus.NEEDS_REVIEW.value)

    def test_maybe_and_no_evidence_are_not_support(self):
        for source_text in ("Maybe the launch is successful.", "There is no evidence the launch is successful."):
            report = self.engine.verify(["The launch is successful."], [Source("brief", source_text)])
            self.assertNotEqual(report.results[0].status, VerificationStatus.SUPPORTED.value)

    def test_list_markers_do_not_become_claims(self):
        claims = extract_candidate_claims("1. Alice is a researcher.\n2. Bob works remotely.")
        self.assertEqual([claim.text for claim in claims], ["Alice is a researcher.", "Bob works remotely."])

    def test_invalid_candidate_offsets_are_malformed(self):
        report = self.engine.verify([CandidateClaim("The sky is blue.", -3, 4)], [Source("s", "The sky is blue.")])
        self.assertEqual(report.metrics["malformed_claims"], 1)
        self.assertEqual(report.results, ())


if __name__ == "__main__":
    unittest.main()
