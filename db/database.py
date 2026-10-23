"""Database engine setup, session management, and seed loader."""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from db.models_db import Base, DBResource, DBEvent, DBOwner, DBRiskVerdict, DBQuarantine

# Database URL from environment or local SQLite file
DB_PATH = Path(__file__).resolve().parent.parent / "archaeologist.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency to provide a transactional database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)


def load_seed_data(session: Session = None, force_reload: bool = False):
    """Load sample seed data from db/seed_data/ into SQLite."""
    close_after = False
    if session is None:
        session = SessionLocal()
        close_after = True

    try:
        init_db()

        # Check if already populated
        existing_count = session.query(DBResource).count()
        if existing_count > 0 and not force_reload:
            return

        if force_reload:
            session.query(DBQuarantine).delete()
            session.query(DBRiskVerdict).delete()
            session.query(DBOwner).delete()
            session.query(DBEvent).delete()
            session.query(DBResource).delete()
            session.commit()

        seed_dir = Path(__file__).resolve().parent / "seed_data"

        # 1. Load Resources (EC2, EBS, Security Groups)
        resource_files = ["ec2_instances.json", "ebs_volumes.json", "security_groups.json"]
        for fname in resource_files:
            fpath = seed_dir / fname
            if fpath.exists():
                with open(fpath, "r", encoding="utf-8") as f:
                    items = json.load(f)
                    for item in items:
                        created_dt = None
                        if item.get("created_at"):
                            created_dt = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))

                        r = DBResource(
                            id=item["id"],
                            name=item.get("name"),
                            resource_type=item["resource_type"],
                            region=item.get("region", "us-east-1"),
                            created_at=created_dt,
                            tags_json=json.dumps(item.get("tags", {})),
                            state=item.get("state", "running"),
                            cost_per_month=item.get("cost_per_month", 0.0),
                            details_json=json.dumps(item.get("details", {})),
                            attached_to_json=json.dumps(item.get("attached_to", [])),
                            dependencies_json=json.dumps(item.get("dependencies", []))
                        )
                        session.merge(r)

        session.commit()

        # 2. Load Events
        events_path = seed_dir / "cloudtrail_events.json"
        if events_path.exists():
            with open(events_path, "r", encoding="utf-8") as f:
                events = json.load(f)
                for ev in events:
                    ts = datetime.fromisoformat(ev["timestamp"].replace("Z", "+00:00"))
                    e = DBEvent(
                        id=ev["id"],
                        resource_id=ev["resource_id"],
                        timestamp=ts,
                        event_type=ev["event_type"],
                        actor=ev["actor"],
                        source=ev["source"],
                        description=ev["description"],
                        metadata_json=json.dumps(ev.get("metadata", {}))
                    )
                    session.merge(e)

        session.commit()
    finally:
        if close_after:
            session.close()


if __name__ == "__main__":
    init_db()
    load_seed_data(force_reload=True)
    print("Database initialized and seed data successfully loaded into archaeologist.db!")
