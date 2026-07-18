"""
Initialize the database: create tables and seed a default admin user.

Run with: python init_db.py
"""
import os
import secrets

from app.core.database import Base, engine, SessionLocal
from app.core.config import settings
from app.models.models import User
from app.core.security import get_password_hash

_WEAK_DEFAULT_PASSWORD = "admin123"


def init_db():
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created successfully!")


def seed_admin():
    """Create a default admin user if none exists.

    In production we refuse to seed the weak built-in password: ADMIN_PASSWORD
    must be set explicitly, otherwise a strong random password is generated and
    printed once so the operator can capture it. In development the convenience
    default is allowed.
    """
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == "admin").first()
        if existing:
            print("ℹ️  Admin user already exists — skipping seed.")
            return

        admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
        admin_password = os.getenv("ADMIN_PASSWORD")
        is_production = settings.ENVIRONMENT == "production"
        generated = False

        if not admin_password:
            if is_production:
                # Never seed a known password in production.
                admin_password = secrets.token_urlsafe(16)
                generated = True
            else:
                admin_password = _WEAK_DEFAULT_PASSWORD

        if is_production and admin_password == _WEAK_DEFAULT_PASSWORD:
            raise SystemExit(
                "Refusing to seed the weak default admin password in production. "
                "Set ADMIN_PASSWORD to a strong value and re-run."
            )

        admin = User(
            email=admin_email,
            username="admin",
            hashed_password=get_password_hash(admin_password),
            is_active=True,
            is_superuser=True,
        )
        db.add(admin)
        db.commit()

        print(f"✅ Default admin user created  →  email: {admin_email}")
        if generated:
            print(f"   🔑 Generated admin password (shown once): {admin_password}")
            print("   ⚠️  Store it now — it will not be shown again.")
        elif not is_production:
            print(f"   password: {admin_password}")
            print("   ⚠️  Development default — set ADMIN_PASSWORD before deploying.")
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    seed_admin()
