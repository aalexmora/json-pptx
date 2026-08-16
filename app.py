"""FastAPI-приложение: REST API для превью и генерации `.pptx`.

Эндпоинты принимают JSON + язык + настройки плагинов и возвращают план слайдов
(для превью), готовый `.pptx` (на скачивание) и обслуживают профиль/админку.
"""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from roadmap_generator import approval, deck_meta, labels, linter, ordering, static_slides, strings, template_registry
from roadmap_generator.builder import build_presentation
from roadmap_generator.diffing import compute_diff, match_previous_project
from roadmap_generator.linter import lint_model
from roadmap_generator.plugins_engine import build_slide_plan, build_tree, list_releases
from roadmap_generator.schema import normalize_roadmap, validate_roadmap
from roadmap_generator.synthetic_template import ensure_synthetic_template

FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"


def _profile_path() -> Path:
    default = Path(__file__).resolve().parent / "data" / "profile.json"
    return Path(os.environ.get("ROADMAP_PROFILE_PATH", str(default)))


def _load_profile() -> None:
    path = _profile_path()
    if not path.exists():
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        ordering.import_state(data.get("ordering", {}))
        labels.import_state(data.get("labels", {}))
        linter.import_state(data.get("linter_rules", []))
        approval.import_state(data.get("under_approval_ids", []))
        deck_meta.import_state(data.get("deck_meta", {}))
        strings.import_state(data.get("service_strings", {}))
        static_slides.import_state(data.get("static_slides", []))
    except (json.JSONDecodeError, OSError):
        pass


def _save_profile() -> None:
    path = _profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "ordering": ordering.export_state(),
        "labels": labels.export_state(),
        "linter_rules": linter.export_state(),
        "under_approval_ids": approval.export_state(),
        "deck_meta": deck_meta.export_state(),
        "service_strings": strings.export_state(),
        "static_slides": static_slides.export_state(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_synthetic_template()
    _load_profile()
    yield


app = FastAPI(title="Roadmap PPTX Generator", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class PlanRequest(BaseModel):
    json_data: List[dict]
    language: Literal["ru", "en"] = "ru"
    plugin_settings: Dict[str, Any] = Field(default_factory=dict)


class DiffRequest(BaseModel):
    old_json: List[dict]
    new_json: List[dict]
    language: Literal["ru", "en"] = "ru"


def _build(req: PlanRequest):
    errors = validate_roadmap(req.json_data)
    if errors:
        return None, errors, [], [], None
    model = normalize_roadmap(req.json_data, language=req.language)
    plan = build_slide_plan(model, req.plugin_settings)
    lint_issues = lint_model(model)
    return plan, [], model.warnings, lint_issues, model


@app.post("/api/plan")
def api_plan(req: PlanRequest):
    plan, errors, warnings, lint_issues, model = _build(req)
    if plan is None:
        return {"errors": errors, "plan": None, "warnings": [], "lint_issues": [], "tree": None, "releases": []}
    return {
        "errors": [],
        "warnings": warnings,
        "lint_issues": lint_issues,
        "plan": asdict(plan),
        "tree": build_tree(model),
        "releases": list_releases(model),
    }


@app.post("/api/pptx")
def api_pptx(req: PlanRequest):
    plan, errors, _, _, _ = _build(req)
    if plan is None:
        raise HTTPException(status_code=422, detail={"errors": errors})
    prs = build_presentation(plan)
    buf = BytesIO()
    prs.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": "attachment; filename=roadmap.pptx"},
    )


@app.post("/api/diff")
def api_diff(req: DiffRequest):
    old_model = normalize_roadmap(req.old_json, language=req.language)
    new_model = normalize_roadmap(req.new_json, language=req.language)
    diff = compute_diff(old_model, new_model)
    match = match_previous_project(old_model, req.new_json)
    return {
        "diff": asdict(diff),
        "new_tier_paths": match.new_tier_paths,
        "removed_tier_paths": match.removed_tier_paths,
    }


@app.post("/api/templates/upload")
async def upload_template(file: UploadFile = File(...)):
    data = await file.read()
    filename = Path(file.filename or "template.pptx").name
    return template_registry.save_template(filename, data)


@app.get("/api/templates")
def list_templates():
    return template_registry.list_templates()


@app.post("/api/templates/active")
def set_active(payload: dict):
    filename = payload.get("filename")
    template_registry.set_active_template(filename or None)
    return {"status": "ok"}


@app.get("/api/templates/preview/{filename}")
def template_preview(filename: str):
    path = template_registry.preview_path(filename)
    if not path:
        raise HTTPException(status_code=404, detail="preview not found")
    return FileResponse(path, media_type="image/jpeg")


@app.post("/api/static-slides/pptx")
async def upload_static_slide_pptx(file: UploadFile = File(...)):
    data = await file.read()
    filename = Path(file.filename or "slide.pptx").name
    saved = static_slides.save_static_slide_pptx(filename, data)
    return {"filename": saved, "extracted_title": static_slides.extract_slide_title(saved)}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/profile")
def get_profile():
    return {
        "ordering": ordering.export_state(),
        "labels": labels.export_state(),
        "linter_rules": linter.export_state(),
        "under_approval_ids": approval.export_state(),
        "deck_meta": deck_meta.export_state(),
        "service_strings": strings.get_service_strings(),
        "static_slides": static_slides.export_state(),
    }


@app.post("/api/profile")
def save_profile(profile: dict):
    ordering.import_state(profile.get("ordering", {}))
    labels.import_state(profile.get("labels", {}))
    linter.import_state(profile.get("linter_rules", []))
    approval.import_state(profile.get("under_approval_ids", []))
    deck_meta.import_state(profile.get("deck_meta", {}))
    strings.save_service_strings(profile.get("service_strings", {}))
    static_slides.import_state(profile.get("static_slides", []))
    _save_profile()
    return {"status": "ok"}


# Статика фронтенда (после `cd frontend && npm run build`)
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
