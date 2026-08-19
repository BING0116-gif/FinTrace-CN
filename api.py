"""Versioned HTTP API for the local FinTrace-CN research workbench.

Run: .venv/Scripts/uvicorn api:app --reload
"""

from __future__ import annotations

from typing import Any, Callable, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.cn import workbench_service as service
from src.cn.errors import UnsupportedSymbolError


API_SCHEMA_VERSION = "workbench-api-1.0.0"
app = FastAPI(title="FinTrace-CN Workbench API", version="1.0.0")


class ResearchRequest(BaseModel):
    symbol: str = Field(description="Canonical A-share symbol, for example 600519.SH.")


class SnapshotAcquisitionRequest(ResearchRequest):
    start_date: str = Field(pattern=r"^\d{8}$", description="Inclusive YYYYMMDD date.")
    end_date: str = Field(pattern=r"^\d{8}$", description="Inclusive YYYYMMDD date.")


class ApiError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ApiMeta(BaseModel):
    snapshot_id: str | None = None
    research_as_of: str | None = None
    provider: str | None = None
    currency: str | None = None
    unit: Any = None
    period_basis: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    validation_status: str | None = None
    data_coverage: Any = None
    freshness: Any = None


class ApiEnvelope(BaseModel):
    schema_version: str
    status: Literal["ok", "error"]
    data: Any = None
    meta: ApiMeta
    error: ApiError | None = None


@app.get("/health")
def health() -> dict[str, str]:
    """Unauthenticated liveness probe; never reads providers or credentials."""
    return {"status": "ok", "schema_version": API_SCHEMA_VERSION}


def _meta(**overrides: Any) -> dict[str, Any]:
    base = {
        "snapshot_id": None, "research_as_of": None, "provider": None, "currency": None,
        "unit": None, "period_basis": None, "evidence_ids": [],
        "validation_status": None, "data_coverage": None, "freshness": None,
    }
    base.update(overrides)
    return base


def _ok(data: Any, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"schema_version": API_SCHEMA_VERSION, "status": "ok", "data": data, "meta": meta or _meta(), "error": None}


def _error(code: str, message: str, *, retryable: bool = False, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "schema_version": API_SCHEMA_VERSION, "status": "error", "data": None, "meta": _meta(),
            "error": {"code": code, "message": message, "retryable": retryable},
        },
    )


@app.exception_handler(HTTPException)
async def http_error_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "HTTP_ERROR", "message": str(exc.detail)}
    return _error(detail.get("code", "HTTP_ERROR"), detail.get("message", "Request failed."), status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, _exc: RequestValidationError) -> JSONResponse:
    return _error("INVALID_REQUEST", "Request fields or parameters are invalid.", status_code=422)


def _research_meta(snapshot_id: str, data: dict[str, Any], *, unit: Any = None, period_basis: str | None = None) -> dict[str, Any]:
    payload = service.load_snapshot(snapshot_id)
    summary = service.research_summary(snapshot_id)
    validation = service.research_validation(snapshot_id)
    readiness = service.research_readiness(snapshot_id)
    evidence = data.get("evidence_ids", summary.get("evidence_ids", {}))
    if isinstance(evidence, dict):
        evidence = [value for value in evidence.values() if value]
    return _meta(
        snapshot_id=snapshot_id, research_as_of=payload["research_as_of"],
        provider=payload.get("provider", "snapshot"),
        currency=payload.get("data", {}).get("profile", {}).get("currency", "CNY"),
        unit=unit if unit is not None else data.get("unit"),
        period_basis=period_basis if period_basis is not None else data.get("period_basis"),
        evidence_ids=evidence, validation_status=validation["status"],
        data_coverage=readiness["checks"], freshness=readiness["checks"].get("snapshot_freshness"),
    )


def _research_result(fn: Callable[..., dict[str, Any]], snapshot_id: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        data = fn(snapshot_id, *args, **kwargs)
        return _ok(data, meta=_research_meta(snapshot_id, data))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "SNAPSHOT_NOT_FOUND", "message": "Research snapshot was not found."}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_REQUEST", "message": str(exc)}) from exc


def _public_task(data: dict[str, Any]) -> dict[str, Any]:
    """Remove server-local implementation details from browser-facing task data."""
    return {key: value for key, value in data.items()
            if key not in {"report_path", "metadata_path", "snapshot_path", "probe_dir"}}


def _task_result(data: dict[str, Any]) -> dict[str, Any]:
    """Keep task responses in the same envelope without leaking server paths."""
    data = _public_task(data)
    snapshot_id = data.get("snapshot_id")
    if snapshot_id:
        return _ok(data, meta=_research_meta(snapshot_id, {}))
    return _ok(data)


@app.get("/api/research")
def list_research() -> ApiEnvelope:
    return _ok({"items": service.list_research()})


@app.get("/api/evaluations")
def list_evaluations() -> ApiEnvelope:
    return _ok({"items": service.list_evaluations()})


@app.get("/api/evaluations/{evaluation_id:path}")
def evaluation_detail(evaluation_id: str) -> ApiEnvelope:
    try:
        return _ok(service.evaluation_detail(evaluation_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "EVALUATION_NOT_FOUND", "message": "Evaluation artifact was not found."}) from exc


@app.post("/api/research", status_code=202)
def start_research(request: ResearchRequest) -> ApiEnvelope:
    try:
        return _task_result(service.start_research(request.symbol))
    except (ValueError, UnsupportedSymbolError) as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_SYMBOL", "message": str(exc)}) from exc


@app.get("/api/tasks")
def list_tasks() -> ApiEnvelope:
    return _ok({"items": [_public_task(task) for task in service.list_tasks()]})


@app.get("/api/tasks/{task_id}")
def task_detail(task_id: str) -> ApiEnvelope:
    try:
        return _task_result(service.get_task(task_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "Research task was not found."}) from exc


@app.get("/api/tasks/{task_id}/progress")
def task_progress(task_id: str) -> ApiEnvelope:
    try:
        progress = service.get_task_progress(task_id)
        task = service.get_task(task_id)
        return _task_result({**progress, "snapshot_id": task.get("snapshot_id")})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "Research task was not found."}) from exc


@app.post("/api/tasks/{task_id}/rerun", status_code=202)
def rerun_task(task_id: str) -> ApiEnvelope:
    try:
        return _task_result(service.rerun_task(task_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "Research task was not found."}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "TASK_RERUN_NOT_ALLOWED", "message": str(exc)}) from exc


@app.post("/api/tasks/{task_id}/cancel", status_code=202)
def cancel_task(task_id: str) -> ApiEnvelope:
    try:
        return _task_result(service.cancel_task(task_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "Research task was not found."}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "TASK_CANCEL_NOT_ALLOWED", "message": str(exc)}) from exc


@app.get("/api/tasks/{task_id}/diagnostics")
def task_diagnostics(task_id: str) -> ApiEnvelope:
    try:
        return _task_result(service.task_diagnostics(task_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "Research task was not found."}) from exc


@app.post("/api/snapshots/acquire", status_code=202)
def acquire_snapshot(request: SnapshotAcquisitionRequest) -> ApiEnvelope:
    try:
        return _ok(service.collect_snapshot(request.symbol, start_date=request.start_date, end_date=request.end_date))
    except (ValueError, UnsupportedSymbolError) as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_ACQUISITION_REQUEST", "message": str(exc)}) from exc


@app.get("/api/research/{snapshot_id}/summary")
def summary(snapshot_id: str) -> ApiEnvelope:
    return _research_result(service.research_summary, snapshot_id)


@app.get("/api/research/{snapshot_id}/market")
def market(snapshot_id: str, adjustment: str = Query("RAW", pattern="^(RAW|QFQ|HFQ)$")) -> ApiEnvelope:
    return _research_result(service.research_market, snapshot_id, adjustment)


@app.get("/api/research/{snapshot_id}/financials")
def financials(snapshot_id: str, period_basis: str | None = Query(None, pattern="^(FY|Q1|H1|9M|TTM)$")) -> ApiEnvelope:
    fn = service.research_financial_trends if period_basis else service.research_financials
    return _research_result(fn, snapshot_id, *([period_basis] if period_basis else []))


@app.get("/api/research/{snapshot_id}/evidence")
def evidence(snapshot_id: str) -> ApiEnvelope:
    return _research_result(service.research_evidence, snapshot_id)


@app.get("/api/research/{snapshot_id}/valuation")
def valuation(snapshot_id: str) -> ApiEnvelope:
    return _research_result(service.research_valuation, snapshot_id)


@app.get("/api/research/{snapshot_id}/validation")
def validation(snapshot_id: str) -> ApiEnvelope:
    return _research_result(service.research_validation, snapshot_id)


@app.get("/api/research/{snapshot_id}/trace")
def trace(snapshot_id: str) -> ApiEnvelope:
    return _research_result(service.research_trace, snapshot_id)


@app.get("/api/research/{snapshot_id}/report")
def report(snapshot_id: str) -> ApiEnvelope:
    return _research_result(service.research_report, snapshot_id)


@app.get("/api/research/{snapshot_id}/artifacts")
def artifacts(snapshot_id: str) -> ApiEnvelope:
    return _research_result(service.research_artifacts, snapshot_id)


# ---------------------------------------------------------------------------
# Daily market review (新增；复用同一 ApiEnvelope 契约)
# ---------------------------------------------------------------------------
class DailyReviewRequest(BaseModel):
    review_date: str = Field(pattern=r"^\d{8}$", description="Inclusive YYYYMMDD date.")


def _daily_review_meta(snapshot_id: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    from src.cn.daily_review.provider import DailyReviewSnapshotProvider
    from src.cn.daily_review.gate import review_gate

    payload = service.load_market_review(snapshot_id)
    provider = DailyReviewSnapshotProvider.from_payload(payload)
    gate = review_gate(provider.snapshot)
    evidence = (data or {}).get("evidence_ids") or []
    return _meta(
        snapshot_id=snapshot_id, research_as_of=payload.get("research_as_of"),
        provider=payload.get("provider"), currency="CNY",
        evidence_ids=evidence, validation_status=gate.status,
        data_coverage={"synthetic_demo": provider.is_synthetic_demo()},
        freshness={"research_as_of": payload.get("research_as_of")},
    )


def _daily_review_result(fn: Callable[..., dict[str, Any]], snapshot_id: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        data = fn(snapshot_id, *args, **kwargs)
        return _ok(data, meta=_daily_review_meta(snapshot_id, data))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "MARKET_REVIEW_NOT_FOUND", "message": "Market review snapshot was not found."}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_REQUEST", "message": str(exc)}) from exc


@app.get("/api/daily-review")
def list_daily_reviews() -> ApiEnvelope:
    return _ok({"items": service.list_daily_reviews()})


@app.get("/api/daily-review/{snapshot_id}/summary")
def daily_review_summary(snapshot_id: str) -> ApiEnvelope:
    return _daily_review_result(service.daily_review_summary, snapshot_id)


@app.get("/api/daily-review/{snapshot_id}/panorama")
def daily_review_panorama(snapshot_id: str) -> ApiEnvelope:
    return _daily_review_result(service.daily_review_detail, snapshot_id, "panorama")


@app.get("/api/daily-review/{snapshot_id}/hotspots")
def daily_review_hotspots(snapshot_id: str) -> ApiEnvelope:
    return _daily_review_result(service.daily_review_detail, snapshot_id, "hotspots")


@app.get("/api/daily-review/{snapshot_id}/report", response_class=HTMLResponse)
def daily_review_report(snapshot_id: str) -> str:
    """Serve the standalone, CDN-free HTML market-review report for a snapshot.

    Renders whatever snapshot is selected (offline demo OR a freshly acquired
    live one) -- never fabricates.  Returns 404 if the snapshot is missing.
    """
    from src.cn.daily_review.report import render_report_html

    try:
        payload = service.load_market_review(snapshot_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "MARKET_REVIEW_NOT_FOUND", "message": "Market review snapshot was not found."},
        ) from exc
    return render_report_html(payload)


@app.post("/api/daily-review/acquire", status_code=202)
def acquire_daily_review(request: DailyReviewRequest) -> ApiEnvelope:
    try:
        return _ok(service.start_daily_review(request.review_date))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_REQUEST", "message": str(exc)}) from exc
