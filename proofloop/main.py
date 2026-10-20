from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import __version__
from .db import get_db, init_db
from .fixtures import DEMO_SCENARIOS
from .models import Case, Claim, HumanDecision, Revision
from .schemas import CaseCreate, ClaimUpdate, DecisionInput, RepairApply
from .services import add_event, create_case, dashboard_stats, extract_claims, latest_run, run_verification, serialize_case

BASE_DIR = Path(__file__).resolve().parent.parent
app = FastAPI(title="ProofLoop AI", version=__version__, description="Evidence-first verification for AI-generated decisions.")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.on_event("startup")
def startup() -> None:
    init_db()


def get_case(db: Session, case_id: str) -> Case:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "proofloop-ai", "version": __version__}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    cases = db.scalars(select(Case).order_by(Case.updated_at.desc())).all()
    return templates.TemplateResponse("dashboard.html", {"request": request, "cases": [serialize_case(db, case) for case in cases], "stats": dashboard_stats(db, cases), "scenarios": DEMO_SCENARIOS})


@app.get("/cases/{case_id}", response_class=HTMLResponse)
def case_page(request: Request, case_id: str, db: Session = Depends(get_db)):
    case = get_case(db, case_id)
    return templates.TemplateResponse("case.html", {"request": request, "case": serialize_case(db, case)})


@app.get("/api/cases")
def list_cases(db: Session = Depends(get_db)):
    cases = db.scalars(select(Case).order_by(Case.updated_at.desc())).all()
    return {"cases": [serialize_case(db, case) for case in cases], "stats": dashboard_stats(db, cases)}


@app.post("/api/cases", status_code=201)
def create_case_api(payload: CaseCreate, db: Session = Depends(get_db)):
    case = create_case(db, payload.title, payload.answer, [source.model_dump() for source in payload.sources])
    extract_claims(db, case)
    return serialize_case(db, case)


@app.get("/api/cases/{case_id}")
def get_case_api(case_id: str, db: Session = Depends(get_db)):
    return serialize_case(db, get_case(db, case_id))


@app.post("/api/cases/{case_id}/claims/extract")
def extract_claims_api(case_id: str, db: Session = Depends(get_db)):
    case = get_case(db, case_id)
    extract_claims(db, case)
    return serialize_case(db, case)


@app.patch("/api/claims/{claim_id}")
def update_claim(claim_id: str, payload: ClaimUpdate, db: Session = Depends(get_db)):
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    claim.text = payload.text.strip()
    claim.start_offset = 0
    claim.end_offset = len(claim.text)
    case = get_case(db, claim.case_id)
    add_event(db, case.id, "claim_edited", {"claim_id": claim.id})
    db.commit()
    return serialize_case(db, case)


@app.post("/api/cases/{case_id}/verify")
def verify_case(case_id: str, db: Session = Depends(get_db)):
    case = get_case(db, case_id)
    run_verification(db, case)
    return serialize_case(db, case)


@app.post("/api/cases/{case_id}/repairs/apply")
def apply_repairs(case_id: str, payload: list[RepairApply], db: Session = Depends(get_db)):
    case = get_case(db, case_id)
    current = case.current_answer
    selected = {item.claim_id: item for item in payload}
    for claim in case.claims:
        item = selected.get(claim.id)
        if not item or not claim.is_active:
            continue
        if item.action == "REMOVE":
            current = current.replace(claim.text, "").replace("  ", " ").strip()
        elif item.action in {"REWRITE", "QUALIFY"} and item.replacement_text:
            current = current.replace(claim.text, item.replacement_text)
    revision = Revision(case_id=case.id, answer_text=current, revision_reason="Evidence-grounded repair selection")
    db.add(revision)
    db.flush()
    case.current_answer = current
    add_event(db, case.id, "revision_created", {"revision_id": revision.id, "actions": [item.model_dump() for item in payload]})
    db.commit()
    extract_claims(db, case)
    return serialize_case(db, case)


@app.post("/api/cases/{case_id}/decision")
def record_decision(case_id: str, payload: DecisionInput, db: Session = Depends(get_db)):
    case = get_case(db, case_id)
    run = latest_run(db, case.id)
    if not run:
        raise HTTPException(status_code=409, detail="Run verification before recording a decision")
    decision = HumanDecision(case_id=case.id, verification_run_id=run.id, decision=payload.decision, comment=payload.comment)
    db.add(decision)
    case.decision_status = payload.decision.lower()
    case.status = "approved" if payload.decision == "APPROVED" else "rejected"
    add_event(db, case.id, "human_decision_recorded", {"decision": payload.decision, "comment": payload.comment, "run_id": run.id})
    db.commit()
    return serialize_case(db, case)


@app.get("/api/cases/{case_id}/audit")
def audit(case_id: str, db: Session = Depends(get_db)):
    return {"case_id": case_id, "events": serialize_case(db, get_case(db, case_id))["history"]}


@app.get("/api/cases/{case_id}/export")
def export_case(case_id: str, db: Session = Depends(get_db)):
    case = get_case(db, case_id)
    return JSONResponse(content=serialize_case(db, case), headers={"Content-Disposition": f'attachment; filename="proofloop-{case.id}.json"'})


@app.get("/api/demo/{scenario}")
def demo(scenario: str, db: Session = Depends(get_db)):
    if scenario not in DEMO_SCENARIOS:
        raise HTTPException(status_code=404, detail="Unknown demo scenario")
    data = DEMO_SCENARIOS[scenario]
    case = create_case(db, data["title"], data["answer"], data["sources"])
    extract_claims(db, case)
    run_verification(db, case)
    return {"case_id": case.id, "scenario": scenario}
