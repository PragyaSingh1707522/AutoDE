"""Create or update the demo organization and owner using environment credentials."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from backend.app.main import Membership, Organization, Role, SessionLocal, User, password_hasher


def main() -> None:
    email = os.getenv("SEED_OWNER_EMAIL", "").strip().lower()
    password = os.getenv("SEED_OWNER_PASSWORD", "")
    organization_name = os.getenv("SEED_ORG_NAME", "Demo Organization").strip()
    if not email or not password or len(password) < 10:
        raise SystemExit("Set SEED_OWNER_EMAIL and a SEED_OWNER_PASSWORD with at least 10 characters")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(id=str(uuid.uuid4()), email=email, password_hash=password_hasher.hash(password), is_active=True)
            db.add(user)
            db.flush()
        org = db.scalar(select(Organization).where(Organization.name == organization_name))
        if org is None:
            org = Organization(id=str(uuid.uuid4()), name=organization_name, created_at=datetime.now(timezone.utc))
            db.add(org)
            db.flush()
        membership = db.get(Membership, (user.id, org.id))
        if membership is None:
            db.add(Membership(user_id=user.id, organization_id=org.id, role=Role.owner.value))
        else:
            membership.role = Role.owner.value
        db.commit()
    print(f"Seeded owner {email} in {organization_name}")


if __name__ == "__main__":
    main()
