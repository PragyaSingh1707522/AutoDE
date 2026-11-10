"""AutoDE API with database-backed users, memberships, and rotating refresh tokens."""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import logging
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import DateTime, ForeignKey, String, Text, create_engine, select, update
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
import jwt

load_dotenv()
DATA_DIR = Path(os.getenv("AUTODE_DATA_DIR", str(Path(__file__).resolve().parents[2] / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'autode.db'}")
engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "15"))
REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
PLACEHOLDERS = ("change-me", "changeme", "secret", "your-secret", "replace-me", "placeholder", "example")
secret_value = JWT_SECRET.strip().lower()
if len(JWT_SECRET) < 32 or secret_value in PLACEHOLDERS or any(secret_value.startswith(f"{marker}-") for marker in PLACEHOLDERS):
    raise RuntimeError("JWT_SECRET must be configured with at least 32 non-placeholder characters")
if JWT_ALGORITHM not in {"HS256", "HS384", "HS512"}:
    raise RuntimeError("JWT_ALGORITHM must be one of HS256, HS384, or HS512")
if ACCESS_TOKEN_MINUTES < 1 or REFRESH_TOKEN_DAYS < 1:
    raise RuntimeError("Token lifetimes must be positive")

ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
log = logging.getLogger("autode")
password_hasher = PasswordHasher()
_dummy_password_hash = password_hasher.hash("dummy-password-to-equalize-login-work")
bearer = HTTPBearer(auto_error=False)


class Base(DeclarativeBase):
    pass


class Role(str, Enum):
    owner = "owner"
    analyst = "analyst"
    viewer = "viewer"


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Membership(Base):
    __tablename__ = "memberships"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, index=True)
    filename: Mapped[str] = mapped_column(String)
    content_hash: Mapped[str] = mapped_column(String)
    row_count: Mapped[int] = mapped_column(default=0)
    profile_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Approval(Base):
    __tablename__ = "approval_requests"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    action: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    organization_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    actor: Mapped[str] = mapped_column(String)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String, nullable=True)
    event: Mapped[str] = mapped_column(String)
    details: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def get_db():
    with SessionLocal() as session:
        yield session


def normalize_email(email: str) -> str:
    return email.strip().lower()


def audit(db: Session, *, event: str, actor: str, details: dict[str, Any], user_id: str | None = None, organization_id: str | None = None, ip_address: str | None = None) -> None:
    db.add(AuditEvent(id=str(uuid.uuid4()), organization_id=organization_id, actor=actor, user_id=user_id, ip_address=ip_address, event=event, details=json.dumps(details)))


def get_client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token(user: User, organization_id: str, role: str, token_type: str) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    lifetime = timedelta(minutes=ACCESS_TOKEN_MINUTES) if token_type == "access" else timedelta(days=REFRESH_TOKEN_DAYS)
    expires = now + lifetime
    claims = {"sub": user.id, "organization_id": organization_id, "role": role, "iat": now, "exp": expires, "jti": str(uuid.uuid4()), "type": token_type}
    return jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM), expires


def save_refresh(db: Session, user: User, organization_id: str, role: str) -> str:
    token, expires = issue_token(user, organization_id, role, "refresh")
    db.add(RefreshToken(id=str(uuid.uuid4()), token_hash=hash_refresh(token), user_id=user.id, organization_id=organization_id, expires_at=expires))
    return token


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie("autode_refresh", token, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=REFRESH_TOKEN_DAYS * 86400, path="/auth")


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie("autode_refresh", httponly=True, secure=COOKIE_SECURE, samesite="lax", path="/auth")


def get_current_context(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> dict[str, str]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"require": ["sub", "organization_id", "role", "exp", "iat", "jti", "type"]})
        if claims.get("type") != "access" or claims.get("role") not in {role.value for role in Role}:
            raise jwt.InvalidTokenError("Invalid access token")
        user = db.get(User, claims["sub"])
        membership = db.get(Membership, (claims["sub"], claims["organization_id"]))
        if user is None or not user.is_active or membership is None or membership.role != claims["role"]:
            raise jwt.InvalidTokenError("Inactive or stale membership")
    except (jwt.PyJWTError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"}) from exc
    return {"user_id": user.id, "email": user.email, "organization_id": membership.organization_id, "role": membership.role}


def require_role(*roles: str) -> Callable[..., dict[str, str]]:
    def dependency(ctx: dict[str, str] = Depends(get_current_context)) -> dict[str, str]:
        if ctx["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return ctx
    return dependency


_rate_lock = threading.Lock()
_rate_windows: dict[str, deque[float]] = defaultdict(deque)


def reset_rate_limits() -> None:
    with _rate_lock:
        _rate_windows.clear()


def enforce_auth_rate_limit(request: Request, email: str) -> None:
    now = time.monotonic()
    keys = [f"{request.url.path}:ip:{get_client_ip(request) or 'unknown'}", f"{request.url.path}:email:{normalize_email(email)}"]
    with _rate_lock:
        queues = [_rate_windows[key] for key in keys]
        for bucket in queues:
            while bucket and now - bucket[0] >= 60:
                bucket.popleft()
        if any(len(bucket) >= 5 for bucket in queues):
            raise HTTPException(status_code=429, detail="Too many attempts. Please try again later.")
        for bucket in queues:
            bucket.append(now)


def infer_type(values: list[str]) -> str:
    present = [value.strip() for value in values if value and value.strip()]
    if not present:
        return "string"
    try:
        for value in present:
            int(value)
        return "integer"
    except ValueError:
        pass
    try:
        for value in present:
            float(value)
        return "number"
    except ValueError:
        return "string"


def parse_csv(filename: str, content: bytes) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if Path(filename).suffix.lower() not in {".csv", ".tsv"}:
        raise HTTPException(415, "This starter build accepts CSV and TSV files; PDF and Excel extraction are not configured yet")
    try:
        text = content.decode("utf-8-sig")
        if filename.lower().endswith(".tsv"):
            delimiter = "\t"
        else:
            try:
                delimiter = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
            except csv.Error:
                delimiter = ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError("missing header row")
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        raise HTTPException(400, detail=f"Could not parse delimited file: {exc}") from exc
    columns: dict[str, dict[str, Any]] = {}
    for field in reader.fieldnames:
        vals = [row.get(field, "") or "" for row in rows]
        columns[field] = {"inferred_type": infer_type(vals), "null_count": sum(not value.strip() for value in vals), "distinct_count": len({value for value in vals if value.strip()})}
    return rows, {"row_count": len(rows), "columns": columns}


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=10, max_length=1024)
    organization_name: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if normalized.count("@") != 1 or "." not in normalized.rsplit("@", 1)[1]:
            raise ValueError("Invalid email address")
        return normalized


class LoginRequest(BaseModel):
    email: str
    password: str
    organization_id: str | None = None

    @field_validator("email")
    @classmethod
    def normalized_email(cls, value: str) -> str:
        return normalize_email(value)


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class ApprovalDecision(BaseModel):
    approved: bool


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    language: str = "en"


class MemberRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Role
    password: str | None = Field(default=None, min_length=10, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalized_email(cls, value: str) -> str:
        return normalize_email(value)


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str


app = FastAPI(title="AutoDE", version="0.2.0", description="Autonomous Data Engineering for small organizations")
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "autode-api"}


@app.post("/auth/register", status_code=201)
def register(request: RegisterRequest, http_request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    enforce_auth_rate_limit(http_request, request.email)
    existing = db.scalar(select(User).where(User.email == request.email))
    if existing is not None:
        membership = db.scalar(select(Membership).where(Membership.user_id == existing.id).order_by(Membership.organization_id))
        audit(db, event="auth.register.failure", actor="unknown", user_id=existing.id, organization_id=membership.organization_id if membership else None, ip_address=get_client_ip(http_request), details={})
        db.commit()
        raise HTTPException(status_code=400, detail="Could not create account with these details")
    org = Organization(id=str(uuid.uuid4()), name=request.organization_name.strip())
    user = User(id=str(uuid.uuid4()), email=request.email, password_hash=password_hasher.hash(request.password), is_active=True)
    db.add_all([org, user])
    db.flush()
    membership = Membership(user_id=user.id, organization_id=org.id, role=Role.owner.value)
    db.add(membership)
    access, _ = issue_token(user, org.id, membership.role, "access")
    refresh = save_refresh(db, user, org.id, membership.role)
    audit(db, event="auth.register.success", actor=user.email, user_id=user.id, organization_id=org.id, ip_address=get_client_ip(http_request), details={})
    db.commit()
    set_refresh_cookie(response, refresh)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer", "user": {"id": user.id, "email": user.email}, "organization": {"id": org.id, "name": org.name}, "role": membership.role}


@app.post("/auth/login")
def login(request: LoginRequest, http_request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    enforce_auth_rate_limit(http_request, request.email)
    user = db.scalar(select(User).where(User.email == request.email))
    valid = False
    if user is not None:
        try:
            valid = password_hasher.verify(user.password_hash, request.password)
        except (VerifyMismatchError, InvalidHashError):
            valid = False
    else:
        try:
            password_hasher.verify(_dummy_password_hash, request.password)
        except VerifyMismatchError:
            pass
    if not valid or user is None or not user.is_active:
        known_membership = db.scalar(select(Membership).where(Membership.user_id == user.id).order_by(Membership.organization_id)) if user else None
        audit(db, event="auth.login.failure", actor="unknown", user_id=user.id if user else None, organization_id=known_membership.organization_id if known_membership else None, ip_address=get_client_ip(http_request), details={})
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")
    memberships = db.scalars(select(Membership).where(Membership.user_id == user.id).order_by(Membership.organization_id)).all()
    membership = next((item for item in memberships if item.organization_id == request.organization_id), None) if request.organization_id else (memberships[0] if memberships else None)
    if membership is None:
        audit(db, event="auth.login.failure", actor="unknown", user_id=user.id, ip_address=get_client_ip(http_request), details={})
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")
    org = db.get(Organization, membership.organization_id)
    if org is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    access, _ = issue_token(user, membership.organization_id, membership.role, "access")
    refresh = save_refresh(db, user, membership.organization_id, membership.role)
    audit(db, event="auth.login.success", actor=user.email, user_id=user.id, organization_id=membership.organization_id, ip_address=get_client_ip(http_request), details={})
    db.commit()
    set_refresh_cookie(response, refresh)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer", "user": {"id": user.id, "email": user.email}, "organization": {"id": org.id, "name": org.name}, "role": membership.role}


def decode_refresh(token: str) -> dict[str, Any]:
    claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"require": ["sub", "organization_id", "role", "exp", "iat", "jti", "type"]})
    if claims.get("type") != "refresh":
        raise jwt.InvalidTokenError("Not a refresh token")
    return claims


@app.post("/auth/refresh")
def refresh_auth(request: RefreshRequest, http_request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
    token = request.refresh_token or http_request.cookies.get("autode_refresh")
    if not token:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    try:
        claims = decode_refresh(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token") from exc
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh(token)))
    now = datetime.now(timezone.utc)
    token_digest = hash_refresh(token)
    if stored is None or not hmac.compare_digest(stored.token_hash, token_digest) or stored.revoked_at is not None or stored.expires_at.replace(tzinfo=timezone.utc) <= now or stored.user_id != claims["sub"] or stored.organization_id != claims["organization_id"]:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user = db.get(User, stored.user_id)
    membership = db.get(Membership, (stored.user_id, stored.organization_id))
    if user is None or not user.is_active or membership is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    revoked_id = db.execute(update(RefreshToken).where(RefreshToken.id == stored.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now).returning(RefreshToken.id)).scalar_one_or_none()
    if revoked_id is None:
        db.rollback()
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    stored.revoked_at = now
    access, _ = issue_token(user, stored.organization_id, membership.role, "access")
    replacement = save_refresh(db, user, stored.organization_id, membership.role)
    audit(db, event="auth.refresh", actor=user.email, user_id=user.id, organization_id=stored.organization_id, ip_address=get_client_ip(http_request), details={})
    db.commit()
    set_refresh_cookie(response, replacement)
    return {"access_token": access, "refresh_token": replacement, "token_type": "bearer"}


@app.post("/auth/logout")
def logout(request: RefreshRequest, http_request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
    token = request.refresh_token or http_request.cookies.get("autode_refresh")
    if token:
        stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh(token)))
        if stored is not None and stored.revoked_at is None:
            stored.revoked_at = datetime.now(timezone.utc)
            user = db.get(User, stored.user_id)
            audit(db, event="auth.logout", actor=user.email if user else "unknown", user_id=stored.user_id, organization_id=stored.organization_id, ip_address=get_client_ip(http_request), details={})
            db.commit()
    clear_refresh_cookie(response)
    return {"status": "ok"}


@app.get("/auth/me")
def auth_me(ctx: dict[str, str] = Depends(get_current_context), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = db.get(User, ctx["user_id"])
    organization = db.get(Organization, ctx["organization_id"])
    if user is None or organization is None:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    return {"user": {"id": user.id, "email": user.email}, "organization": {"id": organization.id, "name": organization.name}, "role": ctx["role"]}


@app.post("/organizations/{org_id}/members", status_code=201)
def add_member(org_id: str, request: MemberRequest, http_request: Request, ctx: dict[str, str] = Depends(require_role(Role.owner.value)), db: Session = Depends(get_db)) -> dict[str, Any]:
    if org_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Organization not found")
    user = db.scalar(select(User).where(User.email == request.email))
    if user is None:
        if request.password is None:
            raise HTTPException(status_code=400, detail="A password is required when creating a new member")
        user = User(id=str(uuid.uuid4()), email=request.email, password_hash=password_hasher.hash(request.password), is_active=True)
        db.add(user)
        db.flush()
    membership = db.get(Membership, (user.id, org_id))
    event = "auth.role_changed" if membership else "auth.member_added"
    if membership is None:
        membership = Membership(user_id=user.id, organization_id=org_id, role=request.role.value)
        db.add(membership)
    else:
        membership.role = request.role.value
    audit(db, event=event, actor=ctx["email"], user_id=ctx["user_id"], organization_id=org_id, ip_address=get_client_ip(http_request), details={"member_user_id": user.id, "role": request.role.value})
    db.commit()
    return {"user": {"id": user.id, "email": user.email}, "organization_id": org_id, "role": membership.role}


@app.post("/api/sources", status_code=201)
async def upload_source(http_request: Request, file: UploadFile = File(...), ctx: dict[str, str] = Depends(require_role(Role.owner.value, Role.analyst.value)), db: Session = Depends(get_db)) -> dict[str, Any]:
    content = await file.read()
    if len(content) > 100_000_000:
    	raise HTTPException(status_code=413, detail="Maximum upload size is 100 MB")
    filename = Path(file.filename or "upload.csv").name
    rows, profile = parse_csv(filename, content)
    digest = hashlib.sha256(content).hexdigest()
    old = db.scalar(select(Source).where(Source.organization_id == ctx["organization_id"], Source.filename == filename).order_by(Source.created_at.desc()))
    source_id = str(uuid.uuid4())
    stored = DATA_DIR / "uploads" / ctx["organization_id"] / source_id
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(content)
    source = Source(id=source_id, organization_id=ctx["organization_id"], filename=filename, content_hash=digest, row_count=len(rows), profile_json=json.dumps(profile))
    db.add(source)
    approval_id = None
    if old and old.content_hash != digest:
        approval_id = str(uuid.uuid4())
        db.add(Approval(id=approval_id, organization_id=ctx["organization_id"], source_id=source_id, action="replace_source_schema", reason="Source content or inferred shape changed; review before applying a warehouse schema change."))
    audit(db, event="source.uploaded", actor=ctx["email"], user_id=ctx["user_id"], organization_id=ctx["organization_id"], ip_address=get_client_ip(http_request), details={"source_id": source_id, "filename": filename, "sha256": digest, "approval_required": bool(approval_id)})
    db.commit()
    log.info(json.dumps({"event": "source.uploaded", "organization_id": ctx["organization_id"], "source_id": source_id, "rows": len(rows)}))
    return {"source_id": source_id, "filename": filename, "row_count": len(rows), "profile": profile, "approval_id": approval_id, "status": "awaiting_approval" if approval_id else "profiled"}


@app.get("/api/sources")
def list_sources(ctx: dict[str, str] = Depends(get_current_context), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    sources = db.scalars(select(Source).where(Source.organization_id == ctx["organization_id"]).order_by(Source.created_at.desc())).all()
    return [{"id": source.id, "filename": source.filename, "row_count": source.row_count, "profile": json.loads(source.profile_json), "created_at": source.created_at} for source in sources]


@app.get("/api/approvals")
def list_approvals(ctx: dict[str, str] = Depends(get_current_context), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    approvals = db.scalars(select(Approval).where(Approval.organization_id == ctx["organization_id"]).order_by(Approval.created_at.desc())).all()
    return [{"id": item.id, "source_id": item.source_id, "action": item.action, "reason": item.reason, "status": item.status} for item in approvals]


@app.post("/api/approvals/{approval_id}")
def decide_approval(approval_id: str, decision: ApprovalDecision, http_request: Request, ctx: dict[str, str] = Depends(require_role(Role.owner.value)), db: Session = Depends(get_db)) -> dict[str, str]:
    approval = db.scalar(select(Approval).where(Approval.id == approval_id, Approval.organization_id == ctx["organization_id"]))
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail="Approval request already decided")
    approval.status = "approved" if decision.approved else "rejected"
    audit(db, event="approval.decided", actor=ctx["email"], user_id=ctx["user_id"], organization_id=ctx["organization_id"], ip_address=get_client_ip(http_request), details={"approval_id": approval.id, "decision": approval.status})
    db.commit()
    return {"id": approval.id, "status": approval.status}


@app.post("/api/ask")
def ask(request: AskRequest, ctx: dict[str, str] = Depends(require_role(Role.owner.value, Role.analyst.value)), db: Session = Depends(get_db)) -> dict[str, Any]:
    sources = db.scalars(select(Source).where(Source.organization_id == ctx["organization_id"])).all()
    if not sources:
        return {"answer": "Upload a CSV first so I can answer questions about your data.", "language": request.language, "sql": None}
    return {"answer": f"I found {len(sources)} uploaded source file(s) in this organization. Natural-language analysis is not configured yet.", "language": request.language, "sql": None}


@app.get("/api/audit")
def audit_log(ctx: dict[str, str] = Depends(get_current_context), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    events = db.scalars(select(AuditEvent).where(AuditEvent.organization_id == ctx["organization_id"]).order_by(AuditEvent.created_at.desc()).limit(200)).all()
    return [{"id": event.id, "organization_id": event.organization_id, "actor": event.actor, "user_id": event.user_id, "ip_address": event.ip_address, "event": event.event, "details": json.loads(event.details), "created_at": event.created_at} for event in events]
