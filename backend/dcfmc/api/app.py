"""FastAPI application: JSON API under /api and the built web UI under /."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections import OrderedDict
from pathlib import Path
from threading import Lock

import numpy as np
from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, TypeAdapter, ValidationError

from .. import __version__
from ..core import advisor
from ..core.distributions import DIST_CATALOG, Distribution, describe
from ..core.engine import ENGINE_VERSION, base_case, simulate
from ..core.inputs import ValuationInputs, active_parameters
from ..core.parameters import PARAMETERS, registry
from ..core.stats import explore as explore_run
from ..core.stats import heatmap, summarize
from ..core.validation import validate
from ..io import report, sheets, template, yahoo
from ..store import repo
from ..store.db import Store

DIST_TA = TypeAdapter(Distribution)


class SuggestReq(BaseModel):
    key: str
    base: float | None = None
    low: float | None = None
    high: float | None = None
    history: list[float] | None = None
    context: dict | None = None


class SaveReq(BaseModel):
    run_token: str | None = None
    inputs: dict | None = None
    label: str = ""
    notes: str = ""


class PatchReq(BaseModel):
    label: str | None = None
    notes: str | None = None
    pinned: bool | None = None


class SheetReq(BaseModel):
    url: str
    tab: str | None = None


class RunCache:
    """Keeps the last few unsaved simulations in memory so they can be explored or saved."""
    def __init__(self, size: int = 8):
        self.size, self.items, self.lock = size, OrderedDict(), Lock()

    def put(self, out, summary) -> str:
        tok = secrets.token_urlsafe(12)
        with self.lock:
            self.items[tok] = (out, summary)
            while len(self.items) > self.size:
                self.items.popitem(last=False)
        return tok

    def get(self, tok):
        with self.lock:
            return self.items.get(tok)


def _err(e: ValidationError) -> HTTPException:
    return HTTPException(422, detail=[{"loc": list(x["loc"]), "msg": x["msg"]} for x in e.errors()])


def create_app(store: Store | None = None, static_dir: str | Path | None = None) -> FastAPI:
    app = FastAPI(title="DCF Monte Carlo", version=__version__, docs_url="/api/docs",
                  openapi_url="/api/openapi.json")
    app.add_middleware(GZipMiddleware, minimum_size=2000)
    app.state.store = store or Store()
    cache = RunCache()
    password = os.environ.get("DCF_APP_PASSWORD")
    secret = os.environ.get("DCF_SECRET", secrets.token_hex(16))

    def _token() -> str:
        return hmac.new(secret.encode(), (password or "").encode(), hashlib.sha256).hexdigest()

    @app.middleware("http")
    async def auth(request: Request, call_next):
        path = request.url.path
        if password and path.startswith("/api/") and path not in ("/api/health", "/api/auth/login", "/api/auth/status"):
            if not hmac.compare_digest(request.cookies.get("dcf_session", ""), _token()):
                return JSONResponse({"detail": "Not signed in"}, status_code=401)
        return await call_next(request)

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__, "engine": ENGINE_VERSION}

    @app.get("/api/auth/status")
    def auth_status(request: Request):
        ok = not password or hmac.compare_digest(request.cookies.get("dcf_session", ""), _token())
        return {"required": bool(password), "signed_in": ok}

    @app.post("/api/auth/login")
    def login(response: Response, payload: dict = Body(...)):
        if not password:
            return {"ok": True}
        if not hmac.compare_digest(str(payload.get("password", "")), password):
            time.sleep(0.5)
            raise HTTPException(401, "Wrong password")
        response.set_cookie("dcf_session", _token(), httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
        return {"ok": True}

    # ------------------------------------------------------------------ meta
    @app.get("/api/meta")
    def meta():
        return {**registry(), "distributions": DIST_CATALOG, "principles": advisor.PRINCIPLES,
                "sources": advisor.SOURCES, "engine_version": ENGINE_VERSION}

    @app.post("/api/distribution/preview")
    def dist_preview(spec: dict = Body(...)):
        try:
            d = DIST_TA.validate_python(spec)
        except ValidationError as e:
            raise _err(e)
        return describe(d)

    @app.post("/api/suggest")
    def suggest(req: SuggestReq):
        if req.key not in PARAMETERS:
            raise HTTPException(404, f"Unknown parameter {req.key}")
        return advisor.suggest(req.key, req.base, req.low, req.high, req.history, req.context)

    @app.get("/api/template")
    def new_template(ticker: str = "NEW", currency: str = "USD"):
        st = app.state.store.get_settings()
        rf = (st.get("risk_free") or {}).get(currency.upper())
        params = {
            "risk_free": {"value": rf, "source": "settings"} if rf is not None else {"value": None},
            "erp": {"value": st.get("erp_mature"), "source": "settings"},
            "beta": {"value": 1.0}, "default_spread": {"value": 0.01}, "debt_weight": {"value": 0.0},
            "tax_rate": {"value": (st.get("marginal_tax") or {}).get(currency.upper(), 0.25)},
        }
        for k in ("risk_free", "erp", "beta"):
            if params[k]["value"] is not None:
                params[k]["dist"] = advisor.recommended_dist(k, params[k]["value"])
        return {"company": {"ticker": ticker, "currency": currency.upper(), "name": ""},
                "params": params, "model": {"discount_mode": "build_up"},
                "simulation": {"n": int(st.get("simulation_paths", 20000))}}

    # ------------------------------------------------------------------ model
    def parse_inputs(payload: dict) -> ValuationInputs:
        try:
            return ValuationInputs.model_validate(payload)
        except ValidationError as e:
            raise _err(e)

    @app.post("/api/validate")
    def validate_ep(payload: dict = Body(...)):
        inp = parse_inputs(payload)
        issues = [i.to_dict() for i in validate(inp)]
        ok = not any(i["severity"] == "error" for i in issues)
        return {"issues": issues, "active": active_parameters(inp), "base": base_case(inp) if ok else None}

    @app.post("/api/simulate")
    def simulate_ep(payload: dict = Body(...)):
        inp = parse_inputs(payload)
        issues = [i.to_dict() for i in validate(inp)]
        if any(i["severity"] == "error" for i in issues):
            raise HTTPException(422, detail={"issues": issues})
        t0 = time.perf_counter()
        out = simulate(inp)
        summary = summarize(out)
        summary["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        tok = cache.put(out, summary)
        return {"run_token": tok, "issues": issues, "summary": summary, "active": active_parameters(inp)}

    @app.get("/api/explore")
    def explore_ep(x: str, y: str, run_token: str | None = None, valuation_id: str | None = None,
                   bins: int = Query(12, ge=4, le=30)):
        if run_token:
            hit = cache.get(run_token)
            if not hit:
                raise HTTPException(404, "This simulation is no longer in memory; run it again or open a saved one.")
            try:
                return explore_run(hit[0], x, y, bins=bins)
            except KeyError as e:
                raise HTTPException(400, f"Unknown driver {e}")
        if valuation_id:
            v = repo.get_valuation(app.state.store, valuation_id, with_sample=True)
            if not v:
                raise HTTPException(404, "Valuation not found")
            smp = v["_sample"]
            if x not in smp or y not in smp:
                raise HTTPException(400, "Driver not stored for this valuation")
            return {"x_key": x, "y_key": y, **heatmap(smp[x].astype(float), smp[y].astype(float),
                                                      smp["value"].astype(float), v["price"], bins=bins)}
        raise HTTPException(400, "run_token or valuation_id required")

    # ------------------------------------------------------------------ register
    @app.post("/api/valuations")
    def save(req: SaveReq):
        hit = cache.get(req.run_token) if req.run_token else None
        if hit is None:
            if not req.inputs:
                raise HTTPException(400, "The simulation expired; send the inputs to run it again.")
            inp = parse_inputs(req.inputs)
            if any(i.severity == "error" for i in validate(inp)):
                raise HTTPException(422, "Inputs have errors")
            out = simulate(inp)
            hit = (out, summarize(out))
        vid = repo.save_run(app.state.store, hit[0], hit[1], req.label, req.notes)
        return repo.get_valuation(app.state.store, vid)

    @app.get("/api/valuations")
    def list_vals(ticker: str | None = None):
        return repo.list_valuations(app.state.store, ticker)

    @app.get("/api/valuations/{vid}")
    def get_val(vid: str):
        v = repo.get_valuation(app.state.store, vid, with_sample=True)
        if not v:
            raise HTTPException(404, "Valuation not found")
        smp = v.pop("_sample", {})
        if smp and v.get("summary") is not None:
            n = smp["value"].size
            idx = np.sort(np.random.default_rng(0).choice(n, min(n, 2500), replace=False))
            v["summary"]["sample"] = {k: smp[k][idx].astype(float).tolist() for k in smp if not k.startswith("_")}
        return v

    @app.get("/api/valuations/{vid}/export.xlsx")
    def export_val(vid: str):
        v = repo.get_valuation(app.state.store, vid)
        if not v:
            raise HTTPException(404, "Valuation not found")
        name = f"{v['ticker']}_valuation_{v['created_at'][:10]}.xlsx"
        return Response(report.build_xlsx(v), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.patch("/api/valuations/{vid}")
    def patch_val(vid: str, req: PatchReq):
        v = repo.update_valuation(app.state.store, vid, **req.model_dump())
        if not v:
            raise HTTPException(404, "Valuation not found")
        return v

    @app.delete("/api/valuations/{vid}")
    def delete_val(vid: str):
        if not repo.delete_valuation(app.state.store, vid):
            raise HTTPException(404, "Valuation not found")
        return {"ok": True}

    @app.get("/api/companies")
    def list_companies():
        return repo.companies(app.state.store)

    @app.get("/api/companies/{ticker}")
    def get_company(ticker: str):
        c = repo.company(app.state.store, ticker)
        if not c:
            raise HTTPException(404, "Company not found")
        return c

    @app.get("/api/prices/{symbol}")
    def get_prices(symbol: str, start: str = "2020-01-01"):
        rows = repo.prices(app.state.store, symbol, start,
                           fetcher=lambda s, st: yahoo.price_history(s, start=st))
        return {"symbol": symbol, "dates": [d for d, _ in rows], "close": [c for _, c in rows]}

    @app.get("/api/settings")
    def get_settings():
        return app.state.store.get_settings()

    @app.put("/api/settings")
    def put_settings(values: dict = Body(...)):
        return app.state.store.put_settings(values)

    # ------------------------------------------------------------------ importers
    @app.post("/api/import/sheet/tabs")
    def sheet_tabs(req: SheetReq):
        try:
            return {"tabs": sheets.list_google_tabs(req.url)}
        except sheets.SheetError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/import/sheet")
    def import_sheet(req: SheetReq):
        try:
            res, tabs = sheets.load_google_tab(req.url, req.tab)
        except sheets.SheetError as e:
            raise HTTPException(400, str(e))
        return _import_response(res, req.tab, tabs)

    @app.post("/api/import/excel")
    async def import_excel(file: UploadFile = File(...), tab: str | None = Form(None)):
        data = await file.read()
        if len(data) > 40 * 1024 * 1024:
            raise HTTPException(413, "File too large (40 MB max)")
        try:
            wb = sheets.Workbook.from_bytes(data)
            tabs = wb.tabs()
            if not tab:
                return {"tabs": tabs, "needs_tab": True}
            res = wb.read_tab(tab, f"excel:{file.filename}")
        except sheets.SheetError as e:
            raise HTTPException(400, str(e))
        return _import_response(res, tab, tabs)

    def _import_response(res, tab, tabs):
        payload = template.to_inputs_payload(res, tab)
        check = None
        try:
            inp = ValuationInputs.model_validate(payload)
            iv = res.fields.get("intrinsic_value")
            if iv is not None:
                probe = inp.model_copy(deep=True)
                probe.params.pop("non_operating_assets", None)
                b = base_case(probe)["value_per_share"]
                check = {"sheet_value": iv.value, "model_value": b,
                         "match": b is not None and abs(b / iv.value - 1) < 0.005 if iv.value else False}
        except (ValidationError, Exception):  # noqa: BLE001
            pass
        return {"inputs": payload, "import": res.to_dict(), "tabs": tabs, "check": check}

    @app.get("/api/import/yahoo/{symbol}")
    def import_yahoo(symbol: str):
        y = yahoo.fetch(symbol)
        if "price" not in y.fields:
            raise HTTPException(404, {"messages": y.messages})
        return {"inputs": yahoo.to_inputs_payload(y), "import": y.to_result().to_dict(),
                "history": y.history, "currency": y.currency, "financial_currency": y.financial_currency}

    @app.get("/api/tickers/search")
    def ticker_search(q: str = Query(..., min_length=1)):
        return yahoo.search(q)

    # ------------------------------------------------------------------ static UI
    sd = Path(static_dir) if static_dir else Path(os.environ.get(
        "DCF_STATIC_DIR", Path(__file__).resolve().parents[3] / "frontend" / "dist"))
    if sd.exists():
        app.mount("/assets", StaticFiles(directory=sd / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            f = sd / path
            if path and f.is_file() and sd in f.resolve().parents:
                return FileResponse(f)
            return FileResponse(sd / "index.html")
    return app
