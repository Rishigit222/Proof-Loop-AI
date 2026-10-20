import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import __version__
from .engine import CandidateClaim, Source as EngineSource, VerificationEngine
from .models import AuditEvent, Case, Claim, HumanDecision, Revision, Source, VerificationRun


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_event(db: Session, case_id: str, event_type: str, data: dict) -> None:
    db.add(AuditEvent(case_id=case_id, event_type=event_type, event_data_json=json.dumps(data, sort_keys=True)))


def source_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def create_case(db: Session, title: str, answer: str, sources: list[dict]) -> Case:
    case = Case(title=title, original_answer=answer, current_answer=answer, status="draft")
    db.add(case)
    db.flush()
    for source in sources:
        db.add(Source(case_id=case.id, name=source["name"], content=source["content"], content_hash=source_hash(source["content"])))
    add_event(db, case.id, "case_created", {"title": title, "source_count": len(sources)})
    db.commit()
    db.refresh(case)
    return case


def extract_claims(db: Session, case: Case) -> list[Claim]:
    for old in case.claims:
        db.delete(old)
    db.flush()
    engine = VerificationEngine()
    candidates = engine.extract_claims(case.current_answer)
    claims = []
    for position, candidate in enumerate(candidates):
        claim = Claim(case_id=case.id, text=candidate.text, start_offset=candidate.start, end_offset=candidate.end, position=position)
        db.add(claim)
        claims.append(claim)
    case.status = "claims_ready"
    add_event(db, case.id, "claims_extracted", {"count": len(claims)})
    db.commit()
    db.refresh(case)
    return claims


def run_verification(db: Session, case: Case) -> VerificationRun:
    engine = VerificationEngine()
    if not case.claims:
        extract_claims(db, case)
        db.refresh(case)
    claims = [CandidateClaim(c.text, c.start_offset, c.end_offset, c.id) for c in case.claims if c.is_active]
    sources = [EngineSource(s.id, s.content, s.name) for s in case.sources]
    report = engine.verify(claims, sources)
    run = VerificationRun(
        case_id=case.id,
        engine_version=__version__,
        input_snapshot=json.dumps({"answer": case.current_answer, "claims": [c.as_dict() for c in claims], "sources": [{"id": s.id, "name": s.title, "text": s.text} for s in sources]}, sort_keys=True),
        results_json=json.dumps(report.as_dict(), sort_keys=True),
        metrics_json=json.dumps(report.metrics.as_dict(), sort_keys=True),
    )
    db.add(run)
    case.status = "verified"
    case.decision_status = "pending"
    add_event(db, case.id, "verification_run_completed", {"run_id": run.id, "metrics": report.metrics.as_dict()})
    db.commit()
    db.refresh(run)
    return run


def latest_run(db: Session, case_id: str) -> VerificationRun | None:
    return db.scalar(select(VerificationRun).where(VerificationRun.case_id == case_id).order_by(VerificationRun.created_at.desc()))


def serialize_case(db: Session, case: Case) -> dict:
    run = latest_run(db, case.id)
    return {
        "id": case.id,
        "title": case.title,
        "original_answer": case.original_answer,
        "current_answer": case.current_answer,
        "status": case.status,
        "decision_status": case.decision_status,
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
        "sources": [{"id": s.id, "name": s.name, "content": s.content, "content_hash": s.content_hash} for s in case.sources],
        "claims": [{"id": c.id, "text": c.text, "start_offset": c.start_offset, "end_offset": c.end_offset, "position": c.position, "is_active": c.is_active} for c in case.claims],
        "latest_run": {"id": run.id, "created_at": run.created_at.isoformat(), "metrics": json.loads(run.metrics_json), "results": json.loads(run.results_json)} if run else None,
        "history": [{"event_type": e.event_type, "data": json.loads(e.event_data_json), "created_at": e.created_at.isoformat()} for e in sorted(case.events, key=lambda item: item.created_at, reverse=True)],
    }
