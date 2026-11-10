"""Three mechanical checks over data the reply already has. Nothing is stored from a tool value."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.models import (
    CheckResult,
    ClaimedStatement,
    PublicSource,
    SourceEvidence,
    ToolEvidence,
)
from app.rag.retriever import MIN_SCORE

KEEP_RATIO = 0.94
_SUPPORT_TOOLS = {"get_merchant_account", "get_receivables", "diagnose_terminal"}


@dataclass(frozen=True)
class RetrievedPassage:
    title: str
    url: str
    score: float


@dataclass(frozen=True)
class StatedField:
    """In-memory comparison input. The value is never copied onto the review record."""

    tool: str
    field: str
    value: Any


@dataclass
class HallucinationReport:
    claimed_statements: list[ClaimedStatement] = field(default_factory=list)
    evidence: list[SourceEvidence | ToolEvidence] = field(default_factory=list)
    check_results: list[CheckResult] = field(default_factory=list)
    verdict: str = "unverified"
    verdict_confidence: float = 0.0


def evaluate(
    *,
    intent: str,
    outcome: str,
    claims: list[ClaimedStatement] | None = None,
    stated: list[StatedField] | None = None,
    payloads: dict[str, dict[str, Any]] | None = None,
    sources: list[PublicSource] | None = None,
    retrieved: list[RetrievedPassage] | None = None,
    retriever: str = "bm25",
    tools: list[str] | None = None,
) -> HallucinationReport:
    claim_list = list(claims or [])
    stated_fields = list(stated or [])
    tool_returns = payloads or {}
    source_urls = {source.url for source in (sources or [])}
    passages = list(retrieved or [])
    invoked = list(tools or [])
    by_url = {passage.url: passage for passage in passages}
    retriever_name = "chroma" if retriever == "chroma" else "bm25"

    evidence: list[SourceEvidence | ToolEvidence] = []
    for claim in claim_list:
        if claim.kind == "product":
            evidence.extend(_source_evidence(claim, by_url, retriever_name))
        else:
            evidence.extend(_tool_evidence(claim, stated_fields, tool_returns))

    anchor, anchor_missing, score_gap = _anchor(claim_list, passages, by_url)
    tool_status = _tool_payload(claim_list, invoked, stated_fields, tool_returns)
    structured = _structured(intent, outcome, claim_list, source_urls, invoked)
    results = [
        CheckResult(name="anchor", status=anchor),
        CheckResult(name="tool_payload", status=tool_status),
        CheckResult(name="structured_output", status=structured),
    ]
    verdict, confidence = _verdict(results, anchor_missing, score_gap, claim_list, by_url)
    return HallucinationReport(
        claimed_statements=claim_list,
        evidence=evidence,
        check_results=results,
        verdict=verdict,
        verdict_confidence=confidence,
    )


def _anchor(
    claims: list[ClaimedStatement],
    passages: list[RetrievedPassage],
    by_url: dict[str, RetrievedPassage],
) -> tuple[str, bool, float | None]:
    product = [claim for claim in claims if claim.kind == "product"]
    if not product:
        return "not_applicable", False, None
    top = max((passage.score for passage in passages), default=0.0)
    bar = max(MIN_SCORE, top * KEEP_RATIO)
    missing = False
    worst_gap: float | None = None
    failed = False
    for claim in product:
        urls = claim.citations or [""]
        for url in urls:
            passage = by_url.get(url)
            if passage is None:
                missing = True
                failed = True
                continue
            if passage.score < MIN_SCORE or passage.score + 1e-12 < top * KEEP_RATIO:
                failed = True
                gap = bar - passage.score
                worst_gap = gap if worst_gap is None else max(worst_gap, gap)
    if not failed:
        return "pass", False, None
    return "fail", missing, worst_gap


def _tool_payload(
    claims: list[ClaimedStatement],
    tools: list[str],
    stated: list[StatedField],
    payloads: dict[str, dict[str, Any]],
) -> str:
    support_claims = [claim for claim in claims if claim.kind == "support"]
    ran = any(name in _SUPPORT_TOOLS for name in tools)
    if not support_claims and not ran:
        return "not_applicable"
    lookup = {(item.tool, item.field): item.value for item in stated}
    for claim in support_claims:
        tool = claim.citations[0] if claim.citations else ""
        payload = payloads.get(tool)
        for name in claim.fields:
            if payload is None or name not in payload:
                return "fail"
            if (tool, name) not in lookup or lookup[(tool, name)] != payload[name]:
                return "fail"
    return "pass"


def _structured(
    intent: str,
    outcome: str,
    claims: list[ClaimedStatement],
    source_urls: set[str],
    tools: list[str],
) -> str:
    if intent in {"general_web", "refused"} or outcome == "refused":
        return "not_applicable"
    if outcome == "handoff" and not claims:
        return "not_applicable"
    expects_fact = (intent in {"product_knowledge", "account_support"} and outcome == "answered") or bool(claims)
    if not expects_fact:
        return "not_applicable"
    if not claims:
        return "fail"
    invoked = set(tools)
    for claim in claims:
        if claim.kind == "product":
            if not claim.citations or any(url not in source_urls for url in claim.citations):
                return "fail"
        elif claim.kind == "support":
            if not claim.citations or any(name not in invoked for name in claim.citations):
                return "fail"
        else:
            return "fail"
    return "pass"


def _source_evidence(
    claim: ClaimedStatement,
    by_url: dict[str, RetrievedPassage],
    retriever: str,
) -> list[SourceEvidence]:
    found: list[SourceEvidence] = []
    for url in claim.citations:
        passage = by_url.get(url)
        if passage is None:
            continue
        found.append(
            SourceEvidence(
                title=passage.title,
                url=passage.url,
                retriever=retriever,  # type: ignore[arg-type]
                score=passage.score,
            )
        )
    return found


def _tool_evidence(
    claim: ClaimedStatement,
    stated: list[StatedField],
    payloads: dict[str, dict[str, Any]],
) -> list[ToolEvidence]:
    tool = claim.citations[0] if claim.citations else ""
    payload = payloads.get(tool)
    lookup = {(item.tool, item.field): item.value for item in stated}
    rows: list[ToolEvidence] = []
    for name in claim.fields:
        matched = (
            payload is not None
            and name in payload
            and lookup.get((tool, name)) == payload[name]
        )
        rows.append(ToolEvidence(tool=tool or "unknown", fields=[name], matched=matched))
    return rows


def _verdict(
    results: list[CheckResult],
    anchor_missing: bool,
    score_gap: float | None,
    claims: list[ClaimedStatement],
    by_url: dict[str, RetrievedPassage],
) -> tuple[str, float]:
    applicable = [item for item in results if item.status != "not_applicable"]
    if not applicable:
        return "unverified", 0.0
    if any(item.status == "fail" for item in applicable):
        score_only = (
            not anchor_missing
            and score_gap is not None
            and all(item.status != "fail" or item.name == "anchor" for item in results)
        )
        if score_only:
            return "hallucinated", min(1.0, max(0.01, score_gap))
        return "hallucinated", 1.0
    cited = [
        by_url[url].score
        for claim in claims
        if claim.kind == "product"
        for url in claim.citations
        if url in by_url
    ]
    if cited:
        return "verified", min(cited)
    return "verified", 1.0
