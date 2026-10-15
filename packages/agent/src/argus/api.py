from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from argus_contracts.models import CreateRunRequest

from argus.config import settings
from argus.supervisor.loop import run_qa

app = FastAPI(title="Argus QA API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "argus-agent"}


@app.post("/runs")
async def create_run(request: CreateRunRequest) -> dict:
    host = request.url.host.lower()
    if request.url.scheme != "http" and request.url.scheme != "https":
        raise HTTPException(status_code=400, detail="Only HTTP(S) targets are supported")
    if settings.allowed_domains and not any(host == domain or host.endswith("." + domain)
                                            for domain in settings.allowed_domains):
        raise HTTPException(status_code=400, detail="Target host is not in ARGUS_ALLOWED_DOMAINS")
    try:
        return await run_qa(str(request.url), request.spec, spec_context=request.context)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
