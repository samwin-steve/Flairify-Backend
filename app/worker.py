from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from .config import settings
from .services.jobs import process

app = FastAPI(title="Flairify private worker")


class Task(BaseModel):
    owner: str = Field(max_length=128)
    job_id: str = Field(pattern=r"^[a-f0-9]{32}$")


@app.post("/tasks/process")
def run(task: Task, authorization: str = Header("")):
    cfg = settings()
    if not cfg.worker_url:
        raise HTTPException(503, "Worker authentication is not configured")
    try:
        claims = id_token.verify_oauth2_token(
            authorization.removeprefix("Bearer "), Request(), audience=cfg.worker_url
        )
        if claims.get("email") != cfg.task_service_account or not claims.get("email_verified"):
            raise ValueError("Unexpected service identity")
    except Exception:
        raise HTTPException(401, "Invalid task identity")
    process(task.owner, task.job_id)
    return {"processed": True}


@app.get("/health")
def health():
    return {"status": "ok", "service": "flairify-worker"}
