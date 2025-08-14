Python 3.11.2 (v3.11.2:878ead1ac1, Feb  7 2023, 10:02:41) [Clang 13.0.0 (clang-1300.0.29.30)] on darwin
Type "help", "copyright", "credits" or "license()" for more information.
>>> import os, json
... from typing import List, Optional, Dict, Any
... from fastapi import FastAPI, HTTPException, Query, Depends
... from fastapi.middleware.cors import CORSMiddleware
... from pydantic import BaseModel
... from functools import lru_cache
... 
... DATA_PATH = os.getenv("ARES_DATA_PATH", "/opt/render/project/src/ARES_memory_unificata_ext.jsonl")
... PUBLIC_MODE = os.getenv("PUBLIC_MODE", "true").lower() == "true"
... API_KEY = os.getenv("API_KEY", "")
... 
... class VideoMeta(BaseModel):
...     resolution: Optional[str] = None
...     fps: Optional[float] = None
...     n_frames: Optional[float] = None
...     duration_s: Optional[float] = None
...     format: Optional[str] = None
...     source_file: Optional[str] = None
... 
... class Metrics(BaseModel):
...     bleeding_score: Optional[float] = None
...     movement_economy: Optional[float] = None
...     R: Optional[float] = None
...     R_over_G: Optional[float] = None
...     movement_index_delta: Optional[float] = None
... 
... class Record(BaseModel):
...     dataset_version: Optional[str] = None
...     schema_version: Optional[str] = None
...     case_id: str
...     step_id: int
...     step_name: Optional[str] = None
...     rules_text: Optional[str] = None
...     rules_json: Optional[Dict[str, Any]] = None
...     generated_at: Optional[str] = None
...     fps: Optional[float] = None
    n_frames: Optional[float] = None
    duration_s: Optional[float] = None
    resolution: Optional[str] = None
    bleeding_score: Optional[float] = None
    movement_economy: Optional[float] = None
    R: Optional[float] = None
    R_over_G: Optional[float] = None
    video_meta: Optional[VideoMeta] = None
    metrics: Optional[Metrics] = None

def check_auth(key: Optional[str] = Query(default=None, alias="key")):
    if PUBLIC_MODE:
        return True
    if not API_KEY:
        raise HTTPException(status_code=500, detail="Server misconfigured: API_KEY not set and PUBLIC_MODE is false.")
    if key == API_KEY:
        return True
    raise HTTPException(status_code=401, detail="Unauthorized")

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

app = FastAPI(title="ARES Memory API", description="Read-only ARES memory (JSONL).", version="1.0.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

@app.get("/health")
def health():
    return {"ok": True, "public_mode": PUBLIC_MODE}

@app.get("/stats", dependencies=[Depends(check_auth)])
def stats():
    data = load_data()
    total = len(data)
    cases = sorted({str(r.get("case_id")) for r in data if r.get("case_id") is not None})
    steps = sorted({int(r.get("step_id")) for r in data if r.get("step_id") is not None})
    return {"total_records": total, "n_cases": len(cases), "n_steps": len(steps), "cases_example": cases[:10]}

@app.get("/cases", response_model=List[str], dependencies=[Depends(check_auth)])
def list_cases(limit: int = 500, offset: int = 0):
    data = load_data()
    ids = sorted({str(r.get("case_id")) for r in data if r.get("case_id") is not None})
    return ids[offset: offset+limit]

@app.get("/case/{case_id}", response_model=List[Record], dependencies=[Depends(check_auth)])
def get_case(case_id: str):
    data = load_data()
    subset = [r for r in data if str(r.get("case_id")) == case_id]
    if not subset:
        raise HTTPException(status_code=404, detail="case_id not found")
    return subset

@app.get("/case/{case_id}/step/{step_id}", response_model=Record, dependencies=[Depends(check_auth)])
def get_step(case_id: str, step_id: int):
    data = load_data()
    for r in data:
        if str(r.get("case_id")) == case_id and int(r.get("step_id", -1)) == step_id:
            return r
    raise HTTPException(status_code=404, detail="record not found")

@app.get("/search", response_model=List[Record], dependencies=[Depends(check_auth)])
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
        "endpoints": {"/health": "status", "/stats": "dataset stats", "/cases": "list cases",
                      "/case/{case_id}": "all steps", "/case/{case_id}/step/{step_id}": "one step", "/search": "filter"},
        "auth": "Set PUBLIC_MODE=false and API_KEY=... to protect the API."
    }
