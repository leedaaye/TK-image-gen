import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, JSON, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import DATABASE_URL


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = 'documents'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(24), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Task(Base):
    __tablename__ = 'tasks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    slide_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    type: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default='queued', index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Setting(Base):
    __tablename__ = 'settings'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


engine = create_engine(DATABASE_URL, pool_pre_ping=True, **({'connect_args': {'check_same_thread': False, 'timeout': 30}} if DATABASE_URL.startswith('sqlite') else {}))
Session = sessionmaker(engine, expire_on_commit=False)


def initialize():
    # Schema creation/upgrades are handled by Alembic before startup.
    with Session() as db:
        db.query(Setting).limit(1).all()


def task_json(task):
    return {k: (getattr(task, k).isoformat() if k.endswith('_at') else getattr(task, k)) for k in ('id', 'project_id', 'slide_id', 'type', 'status', 'error', 'created_at', 'updated_at')}
