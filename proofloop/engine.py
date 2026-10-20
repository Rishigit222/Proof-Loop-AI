"""Pure, deterministic claim verification for ProofLoop AI.

The engine intentionally uses only local string operations.  It does not try to
infer facts from the world: a claim is supported only when a source contains a
direct, non-hedged textual match.  Anything weaker is surfaced as
``needs_review`` or ``unsupported`` so callers can make the next decision
explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
import unicodedata
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple, Union


class VerificationStatus(str, Enum):
    """The only conclusions the deterministic verifier can return."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    NEEDS_REVIEW = "needs_review"


@dataclass(frozen=True)
class CandidateClaim:
    """A candidate claim and its half-open offsets in the input text."""

    text: str
    start: int
    end: int
    source_id: Optional[str] = None

    @property
    def normalized(self) -> str:
        return _normalized_text(self.text)

    @property
    def offset_start(self) -> int:
        return self.start

    @property
    def offset_end(self) -> int:
        return self.end

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "source_id": self.source_id,
        }

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]


@dataclass(frozen=True)
class Source:
    """A source document with a stable identifier for provenance."""

    id: str
    text: str
    title: Optional[str] = None

    @property
    def source_id(self) -> str:
        return self.id


@dataclass(frozen=True)
class Evidence:
    """A source passage that influenced a claim's status.

    ``start`` and ``end`` are offsets into ``source_text`` in the referenced
    source.  The full sentence is retained as the excerpt to make decisions
    auditable even when the matching phrase is only part of that sentence.
    """

    source_id: str
    text: str
    start: int
    end: int
    relation: str
    score: float
    reason: str
    source_text: str = field(repr=False, default="")

    @property
    def source_start(self) -> int:
        return self.start

    @property
    def source_end(self) -> int:
        return self.end

    @property
    def offset_start(self) -> int:
        return self.start

    @property
    def offset_end(self) -> int:
        return self.end

    @property
    def provenance(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "start": self.start,
            "end": self.end,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "relation": self.relation,
            "score": self.score,
            "reason": self.reason,
        }

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]


@dataclass(frozen=True)
class RepairProposal:
    """A deterministic next step for a result that cannot be accepted yet."""

    claim: str
    status: str
    action: str
    rationale: str
    source_ids: Tuple[str, ...] = ()

    @property
    def suggestion(self) -> str:
        return self.action

    @property
    def claim_text(self) -> str:
        return self.claim

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "status": self.status,
            "action": self.action,
            "rationale": self.rationale,
            "source_ids": list(self.source_ids),
        }

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]


@dataclass(frozen=True)
class ClaimResult:
    claim: CandidateClaim
    status: str
    evidence: Tuple[Evidence, ...] = ()
    confidence: float = 0.0
    rationale: str = ""
    repair_proposals: Tuple[RepairProposal, ...] = ()

    @property
    def provenance(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(item.provenance for item in self.evidence)

    @property
    def repairs(self) -> Tuple[RepairProposal, ...]:
        return self.repair_proposals

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim.as_dict(),
            "status": self.status,
            "evidence": [item.as_dict() for item in self.evidence],
            "confidence": self.confidence,
            "rationale": self.rationale,
            "repair_proposals": [
                item.as_dict()
                for item in self.repair_proposals
            ],
        }

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]


@dataclass(frozen=True)
class VerificationMetrics:
    """Counts and rates derived solely from a verification report."""

    total_claims: int = 0
    supported: int = 0
    unsupported: int = 0
    contradicted: int = 0
    needs_review: int = 0
    claims_with_evidence: int = 0
    evidence_items: int = 0
    source_count: int = 0
    malformed_claims: int = 0
    malformed_sources: int = 0

    @property
    def evidence_coverage(self) -> float:
        return _rate(self.claims_with_evidence, self.total_claims)

    @property
    def support_rate(self) -> float:
        return _rate(self.supported, self.total_claims)

    @property
    def contradiction_rate(self) -> float:
        return _rate(self.contradicted, self.total_claims)

    @property
    def review_rate(self) -> float:
        return _rate(self.needs_review, self.total_claims)

    @property
    def average_evidence_per_claim(self) -> float:
        return _rate(self.evidence_items, self.total_claims)

    def as_dict(self) -> dict[str, Union[int, float]]:
        return {
            "total_claims": self.total_claims,
            "supported": self.supported,
            "unsupported": self.unsupported,
            "contradicted": self.contradicted,
            "needs_review": self.needs_review,
            "claims_with_evidence": self.claims_with_evidence,
            "evidence_items": self.evidence_items,
            "source_count": self.source_count,
            "malformed_claims": self.malformed_claims,
            "malformed_sources": self.malformed_sources,
            "evidence_coverage": self.evidence_coverage,
            "support_rate": self.support_rate,
            "contradiction_rate": self.contradiction_rate,
            "review_rate": self.review_rate,
            "average_evidence_per_claim": self.average_evidence_per_claim,
        }

    def to_dict(self) -> dict[str, Union[int, float]]:
        return self.as_dict()

    def __getitem__(self, key: str) -> Union[int, float]:
        return self.as_dict()[key]


@dataclass(frozen=True)
class VerificationReport:
    results: Tuple[ClaimResult, ...]
    metrics: VerificationMetrics
    repair_proposals: Tuple[RepairProposal, ...] = ()

    @property
    def claims(self) -> Tuple[ClaimResult, ...]:
        return self.results

    @property
    def repairs(self) -> Tuple[RepairProposal, ...]:
        return self.repair_proposals

    def as_dict(self) -> dict[str, Any]:
        return {
            "results": [result.as_dict() for result in self.results],
            "metrics": self.metrics.as_dict(),
            "repair_proposals": [
                item.as_dict()
                for item in self.repair_proposals
            ],
        }

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]


_InputClaim = Union[str, CandidateClaim, Mapping[str, Any]]
_InputSource = Union[str, Source, Mapping[str, Any]]

_TOKEN_RE = re.compile(r"[\w]+(?:['’][\w]+)?", re.UNICODE)
_SEGMENT_RE = re.compile(r"[^.!?\r\n]+(?:[.!?]+|$)", re.UNICODE)
_NEGATION_WORDS = {
    "not",
    "no",
    "never",
    "neither",
    "nor",
    "cannot",
    "can't",
    "isn't",
    "aren't",
    "wasn't",
    "weren't",
    "doesn't",
    "don't",
    "didn't",
    "won't",
    "wouldn't",
    "shouldn't",
}
_PARTIAL_MATCH_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "but",
    "by",
    "do",
    "does",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "with",
}
_HEDGE_RE = re.compile(
    r"\b(?:may|might|could|maybe|perhaps|possibly|probably|likely|uncertain|unclear|"
    r"unconfirmed|alleged|appears?|seems?|suggests?|reportedly|believed|estimated|rumored)\b|"
    r"\b(?:no\s+evidence|not\s+(?:confirmed|verified|known|clear))\b",
    re.IGNORECASE,
)


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _normalized_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.replace("’", "'")
    return " ".join(_TOKEN_RE.findall(value))


def _tokens(value: str) -> list[str]:
    return _TOKEN_RE.findall(unicodedata.normalize("NFKC", value).casefold().replace("’", "'"))


def _without_negation(tokens: Sequence[str]) -> list[str]:
    return [token for token in tokens if token not in _NEGATION_WORDS]


def _has_negation(tokens: Sequence[str]) -> bool:
    return any(token in _NEGATION_WORDS for token in tokens)


def _contains_contiguous(haystack: Sequence[str], needle: Sequence[str]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(list(haystack[index : index + width]) == list(needle) for index in range(len(haystack) - width + 1))


def _trim_candidate(text: str, start: int, end: int) -> tuple[str, int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    # List markers are formatting, not part of the candidate claim.  Keep
    # punctuation and all other characters so offsets remain exact.
    marker = re.match(r"(?:[-*•]|\d+[.)])\s+", text[start:end])
    if marker:
        start += marker.end()
        while start < end and text[start].isspace():
            start += 1
    return text[start:end], start, end


def extract_candidate_claims(text: Any, source_id: Optional[str] = None) -> Tuple[CandidateClaim, ...]:
    """Extract sentence-like candidates while preserving input offsets.

    Non-string, blank, or whitespace-only values produce an empty tuple.  The
    offsets are character offsets and use Python's conventional half-open
    interval ``[start, end)``.
    """

    if not isinstance(text, str) or not text.strip():
        return ()
    candidates: list[CandidateClaim] = []
    for match in _SEGMENT_RE.finditer(text):
        candidate_text, start, end = _trim_candidate(text, match.start(), match.end())
        if not candidate_text or not _tokens(candidate_text) or re.fullmatch(r"\d+[.)]", candidate_text.strip()):
            continue
        candidates.append(CandidateClaim(candidate_text, start, end, source_id))
    return tuple(candidates)


def _coerce_claim(value: Any) -> Optional[CandidateClaim]:
    if isinstance(value, CandidateClaim):
        if isinstance(value.text, str) and value.text.strip() and value.start >= 0 and value.end >= value.start:
            return value
        return None
    if isinstance(value, str) and value.strip():
        return CandidateClaim(value, 0, len(value))
    if isinstance(value, Mapping):
        text = value.get("text", value.get("claim"))
        if not isinstance(text, str) or not text.strip():
            return None
        try:
            start = int(value.get("start", value.get("offset_start", 0)))
            end = int(value.get("end", value.get("offset_end", start + len(text))))
        except (TypeError, ValueError):
            return None
        if start < 0 or end < start:
            return None
        source_id = value.get("source_id")
        return CandidateClaim(text, start, end, str(source_id) if source_id is not None else None)
    return None


def _coerce_source(value: Any, index: int) -> Optional[Source]:
    if isinstance(value, Source):
        return value if isinstance(value.text, str) and value.text.strip() else None
    if isinstance(value, str):
        if value.strip():
            return Source(f"source-{index}", value)
        return None
    if isinstance(value, Mapping):
        text = value.get("text", value.get("content"))
        if not isinstance(text, str) or not text.strip():
            return None
        source_id = value.get("id", value.get("source_id", f"source-{index}"))
        if source_id is None or str(source_id) == "":
            source_id = f"source-{index}"
        title = value.get("title")
        return Source(str(source_id), text, str(title) if title is not None else None)
    return None


def _source_segments(source: Source) -> Iterable[tuple[str, int, int]]:
    for match in _SEGMENT_RE.finditer(source.text):
        text, start, end = _trim_candidate(source.text, match.start(), match.end())
        if text and _tokens(text) and not re.fullmatch(r"\d+[.)]", text.strip()):
            yield text, start, end


def _partial_overlap(claim_tokens: Sequence[str], source_tokens: Sequence[str]) -> float:
    claim_set = {
        token for token in _without_negation(claim_tokens) if token not in _PARTIAL_MATCH_STOPWORDS
    }
    source_set = {
        token for token in _without_negation(source_tokens) if token not in _PARTIAL_MATCH_STOPWORDS
    }
    # A single shared content word (for example, the predicate in "A is
    # true" and "B is true") is too weak to count as ambiguous evidence.
    if len(claim_set) < 2:
        return 0.0
    return len(claim_set & source_set) / len(claim_set)


def _evidence_for_claim(claim: CandidateClaim, source: Source) -> list[Evidence]:
    claim_tokens = _tokens(claim.text)
    claim_base = _without_negation(claim_tokens)
    claim_negative = _has_negation(claim_tokens)
    found: list[Evidence] = []
    for segment_text, start, end in _source_segments(source):
        source_tokens = _tokens(segment_text)
        source_base = _without_negation(source_tokens)
        if not claim_base:
            continue
        direct = _contains_contiguous(source_tokens, claim_tokens)
        polarity_match = _contains_contiguous(source_base, claim_base)
        overlap = _partial_overlap(claim_tokens, source_tokens)
        if not direct and not polarity_match and not (overlap >= 0.6 and len(set(claim_base)) >= 2):
            continue

        source_negative = _has_negation(source_tokens)
        hedged = bool(_HEDGE_RE.search(segment_text))
        if hedged:
            relation = VerificationStatus.NEEDS_REVIEW.value
            reason = "The source contains a hedge or uncertainty marker."
            score = 0.5
        elif direct and source_negative != claim_negative:
            relation = VerificationStatus.NEEDS_REVIEW.value
            reason = "The source contains a direct match alongside a separate polarity marker; scope is ambiguous."
            score = 0.5
        elif polarity_match and source_negative != claim_negative:
            relation = VerificationStatus.CONTRADICTED.value
            reason = "The source explicitly negates the claim's polarity."
            score = 1.0
        elif direct or polarity_match:
            relation = VerificationStatus.SUPPORTED.value
            reason = "The source contains a direct textual match."
            score = 1.0
        else:
            relation = VerificationStatus.NEEDS_REVIEW.value
            reason = "The source overlaps substantially but does not state the claim directly."
            score = round(overlap, 4)
        found.append(Evidence(source.id, segment_text, start, end, relation, score, reason, source.text))
    return found


def _repair_for(result: ClaimResult) -> Optional[RepairProposal]:
    claim = result.claim.text
    evidence_sources = tuple(dict.fromkeys(item.source_id for item in result.evidence))
    if result.status == VerificationStatus.UNSUPPORTED.value:
        return RepairProposal(
            claim,
            result.status,
            f"Add a source that directly states or supports: {claim}",
            "No source contained a sufficiently direct match.",
            evidence_sources,
        )
    if result.status == VerificationStatus.CONTRADICTED.value:
        return RepairProposal(
            claim,
            result.status,
            f"Resolve the contradiction for: {claim}",
            "A source explicitly states the opposite polarity; verify the claim and source before accepting it.",
            evidence_sources,
        )
    if result.status == VerificationStatus.NEEDS_REVIEW.value:
        return RepairProposal(
            claim,
            result.status,
            f"Review the evidence and clarify: {claim}",
            "Evidence is hedged, only partially matched, or conflicts across sources.",
            evidence_sources,
        )
    return None


class VerificationEngine:
    """Offline deterministic verifier with no mutable or network state."""

    def extract_claims(self, text: Any, source_id: Optional[str] = None) -> Tuple[CandidateClaim, ...]:
        return extract_candidate_claims(text, source_id)

    def verify(
        self,
        claims: Any,
        sources: Any = None,
    ) -> VerificationReport:
        malformed_claims = 0
        if isinstance(claims, str):
            claim_values: Iterable[Any] = extract_candidate_claims(claims)
        elif claims is None:
            claim_values = ()
        elif isinstance(claims, (CandidateClaim, Mapping)):
            claim_values = (claims,)
        else:
            try:
                claim_values = iter(claims)
            except TypeError:
                claim_values = (claims,)
        normalized_claims: list[CandidateClaim] = []
        for value in claim_values:
            claim = _coerce_claim(value)
            if claim is None:
                malformed_claims += 1
            else:
                normalized_claims.append(claim)

        malformed_sources = 0
        if isinstance(sources, (str, Source, Mapping)):
            source_values: Iterable[Any] = (sources,)
        elif sources is None:
            source_values = ()
        else:
            try:
                source_values = iter(sources)
            except TypeError:
                source_values = (sources,)
        normalized_sources: list[Source] = []
        for index, value in enumerate(source_values, 1):
            source = _coerce_source(value, index)
            if source is None:
                malformed_sources += 1
            else:
                normalized_sources.append(source)

        results: list[ClaimResult] = []
        for claim in normalized_claims:
            evidence = tuple(
                item
                for source in normalized_sources
                for item in _evidence_for_claim(claim, source)
            )
            relations = {item.relation for item in evidence}
            if VerificationStatus.SUPPORTED.value in relations and VerificationStatus.CONTRADICTED.value in relations:
                status = VerificationStatus.NEEDS_REVIEW.value
                rationale = "Supporting and contradicting source passages conflict."
                confidence = 0.5
            elif VerificationStatus.NEEDS_REVIEW.value in relations:
                status = VerificationStatus.NEEDS_REVIEW.value
                rationale = "The available evidence is hedged or only partially direct."
                confidence = 0.5
            elif VerificationStatus.SUPPORTED.value in relations:
                status = VerificationStatus.SUPPORTED.value
                rationale = "At least one source directly supports the claim."
                confidence = 1.0
            elif VerificationStatus.CONTRADICTED.value in relations:
                status = VerificationStatus.CONTRADICTED.value
                rationale = "At least one source explicitly contradicts the claim."
                confidence = 1.0
            else:
                status = VerificationStatus.UNSUPPORTED.value
                rationale = "No source contained a direct or materially overlapping statement."
                confidence = 0.0
            provisional = ClaimResult(claim, status, evidence, confidence, rationale)
            proposal = _repair_for(provisional)
            results.append(
                ClaimResult(
                    claim,
                    status,
                    evidence,
                    confidence,
                    rationale,
                    (proposal,) if proposal else (),
                )
            )

        counts = {status.value: 0 for status in VerificationStatus}
        for result in results:
            counts[result.status] = counts.get(result.status, 0) + 1
        metrics = VerificationMetrics(
            total_claims=len(results),
            supported=counts[VerificationStatus.SUPPORTED.value],
            unsupported=counts[VerificationStatus.UNSUPPORTED.value],
            contradicted=counts[VerificationStatus.CONTRADICTED.value],
            needs_review=counts[VerificationStatus.NEEDS_REVIEW.value],
            claims_with_evidence=sum(bool(result.evidence) for result in results),
            evidence_items=sum(len(result.evidence) for result in results),
            source_count=len(normalized_sources),
            malformed_claims=malformed_claims,
            malformed_sources=malformed_sources,
        )
        repairs = tuple(proposal for result in results for proposal in result.repair_proposals)
        return VerificationReport(tuple(results), metrics, repairs)

    def verify_text(self, text: Any, sources: Any = None) -> VerificationReport:
        return self.verify(extract_candidate_claims(text), sources)

    def generate_repair_proposals(self, report: VerificationReport) -> Tuple[RepairProposal, ...]:
        return generate_repair_proposals(report)


ProofLoopEngine = VerificationEngine
Claim = CandidateClaim
VerificationResult = ClaimResult
SourceDocument = Source


def verify_claims(claims: Any, sources: Any = None) -> VerificationReport:
    """Convenience wrapper around :class:`VerificationEngine`."""

    return VerificationEngine().verify(claims, sources)


extract_claims = extract_candidate_claims
verify = verify_claims


def generate_repair_proposals(value: Any) -> Tuple[RepairProposal, ...]:
    """Return proposals for a report or an iterable of claim results."""

    if isinstance(value, VerificationReport):
        return value.repair_proposals
    if isinstance(value, ClaimResult):
        results = (value,)
    else:
        try:
            results = tuple(value)
        except TypeError:
            results = ()
    proposals: list[RepairProposal] = []
    for result in results:
        if not isinstance(result, ClaimResult):
            continue
        proposal = _repair_for(result)
        if proposal:
            proposals.append(proposal)
    return tuple(proposals)


__all__ = [
    "CandidateClaim",
    "Claim",
    "ClaimResult",
    "Evidence",
    "ProofLoopEngine",
    "RepairProposal",
    "Source",
    "SourceDocument",
    "VerificationEngine",
    "VerificationMetrics",
    "VerificationReport",
    "VerificationResult",
    "VerificationStatus",
    "extract_candidate_claims",
    "extract_claims",
    "generate_repair_proposals",
    "verify_claims",
    "verify",
]
