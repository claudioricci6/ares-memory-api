import os, json
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from functools import lru_cache

# === Config ===
DATA_PATH = os.getenv("ARES_DATA_PATH", "/opt/render/project/src/ARES_memory_unificata_ext.jsonl")

# === Models ===
class VideoMeta(BaseModel):
    resolution: Optional[str] = None
    fps: Optional[float] = None
    n_frames: Optional[float] = None
    duration_s: Optional[float] = None
    format: Optional[str] = None
    source_file: Optional[str] = None

class Metrics(BaseModel):
    bleeding_score: Optional[float] = None
    movement_economy: Optional[float] = None
    R: Optional[float] = None
    R_over_G: Optional[float] = None
    movement_index_delta: Optional[float] = None

class Record(BaseModel):
    dataset_version: Optional[str] = None
    schema_version: Optional[str] = None
    case_id: str
    step_id: int
    step_name: Optional[str] = None
    rules_text: Optional[str] = None
    rules_json: Optional[Dict[str, Any]] = None
    generated_at: Optional[str] = None
    fps: Optional[float] = None
    n_frames: Optional[float] = None
    duration_s: Optional[float] = None
    resolution: Optional[str] = None
    bleeding_score: Optional[float] = None
    movement_economy: Optional[float] = None
    R: Optional[float] = None
    R_over_G: Optional[float] = None
    video_meta: Optional[VideoMeta] = None
    metrics: Optional[Metrics] = None

# === Data loader ===
@lru_cache(maxsize=1)
def load_data() -> List[Dict[str, Any]]:
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Data file not found at {DATA_PATH}")
    rows = []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows

# === App ===
app = FastAPI(title="ARES Memory API", description="Read-only ARES memory (JSONL).", version="1.0.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

# Health/Status (entrambi per evitare 404 su vecchi path)
@app.get("/health")
@app.get("/status")
def health():
    return {"ok": True, "service": "ares-memory-api", "auth": "none"}

# --- Endpoints pubblici (nessuna auth) ---
@app.get("/stats")
def stats():
    data = load_data()
    total = len(data)
    cases = sorted({str(r.get("case_id")) for r in data if r.get("case_id") is not None})
    steps = sorted({int(r.get("step_id")) for r in data if r.get("step_id") is not None})
    return {"total_records": total, "n_cases": len(cases), "n_steps": len(steps), "cases_example": cases[:10]}

@app.get("/cases", response_model=List[str])
def list_cases(limit: int = 500, offset: int = 0):
    data = load_data()
    ids = sorted({str(r.get("case_id")) for r in data if r.get("case_id") is not None})
    return ids[offset: offset+limit]

@app.get("/case/{case_id}", response_model=List[Record])
def get_case(case_id: str):
    data = load_data()
    subset = [r for r in data if str(r.get("case_id")) == case_id]
    if not subset:
        raise HTTPException(status_code=404, detail="case_id not found")
    return subset

@app.get("/case/{case_id}/step/{step_id}", response_model=Record)
def get_step(case_id: str, step_id: int):
    data = load_data()
    for r in data:
        if str(r.get("case_id")) == case_id and int(r.get("step_id", -1)) == step_id:
            return r
    raise HTTPException(status_code=404, detail="record not found")

@app.get("/search", response_model=List[Record])
def search(
    q: Optional[str] = None,
    min_fps: Optional[float] = None,
    max_fps: Optional[float] = None,
    step_id: Optional[int] = None,
    min_bleeding: Optional[float] = None,
    max_bleeding: Optional[float] = None,
    limit: int = 100,
    offset: int = 0
):
    data = load_data()
    res = []
    for r in data:
        if q:
            blob = json.dumps(r, ensure_ascii=False).lower()
            if q.lower() not in blob:
                continue
        fps = r.get("fps", r.get("video_meta", {}).get("fps") if isinstance(r.get("video_meta"), dict) else None)
        bleed = r.get("bleeding_score", r.get("metrics", {}).get("bleeding_score") if isinstance(r.get("metrics"), dict) else None)
        if step_id is not None and int(r.get("step_id", -1)) != step_id:
            continue
        if min_fps is not None and (fps is None or float(fps) < min_fps):
            continue
        if max_fps is not None and (fps is None or float(fps) > max_fps):
            continue
        if min_bleeding is not None and (bleed is None or float(bleed) < min_bleeding):
            continue
        if max_bleeding is not None and (bleed is None or float(bleed) > max_bleeding):
            continue
        res.append(r)
    return res[offset: offset+limit]

@app.get("/")
def root():
    return {
        "endpoints": {
            "/status": "status",
            "/health": "status (alias)",
            "/stats": "dataset stats",
            "/cases": "list cases",
            "/case/{case_id}": "all steps",
            "/case/{case_id}/step/{step_id}": "one step",
            "/search": "filter"
        },
        "auth": "none"
    }
