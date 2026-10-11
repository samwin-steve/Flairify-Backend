import hashlib
import secrets
import time
from dataclasses import dataclass
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .config import settings
from .store import store

bearer = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    uid: str
    admin: bool = False
    demo: bool = False

    @property
    def catalog_owner(self):
        return self.uid if self.demo else "retailer"


def create_demo_session():
    if settings().app_mode != "demo":
        raise HTTPException(404, "Demo mode is disabled")
    token = secrets.token_urlsafe(32)
    user = "demo-" + secrets.token_hex(12)
    store().put(
        "sessions",
        "system",
        hashlib.sha256(token.encode()).hexdigest(),
        {"uid": user, "expires": time.time() + 86400 * 7, "admin": False},
    )
    return {"token": token, "user_id": user, "expires_in": 604800}


def principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not credentials:
        raise HTTPException(401, "Sign in to continue")
    token = credentials.credentials
    if settings().app_mode == "demo":
        session = store().get("sessions", "system", hashlib.sha256(token.encode()).hexdigest())
        if session and session["expires"] >= time.time():
            return Principal(session["uid"], session.get("admin", False), True)
        if not settings().allow_firebase_in_demo:
            raise HTTPException(401, "Your demo session expired. Start a new demo.")
    try:
        import firebase_admin
        from firebase_admin import auth

        if not firebase_admin._apps:
            firebase_admin.initialize_app(options={"projectId": settings().google_cloud_project})
        decoded = auth.verify_id_token(token, check_revoked=True)
        return Principal(decoded["uid"], decoded.get("admin") is True)
    except Exception:
        raise HTTPException(401, "Invalid or expired sign-in")


def admin(p: Principal = Depends(principal)):
    if not p.admin:
        raise HTTPException(403, "Retailer administrator access required")
    return p


def require_record(kind, owner, key):
    value = store().get(kind, owner, key)
    if not value:
        raise HTTPException(404, "This item could not be found")
    return value


def quota(owner, kind, limit):
    key = f"{kind}:{time.strftime('%Y-%m-%d', time.gmtime())}"

    def increment(value):
        value = value or {"count": 0}
        if value["count"] >= limit:
            raise HTTPException(429, "Daily limit reached. Please try again tomorrow.")
        return {"count": value["count"] + 1}

    store().mutate("quotas", owner, key, increment)
