"""Valuation register: SQLite by default, any SQLAlchemy URL via DCF_DATABASE_URL.

Every run keeps its complete validated inputs, the seed and engine version (so
it can be reproduced exactly), the headline numbers as real columns (so the
history can be charted and queried) and a compressed copy of the simulated
values for later exploration.
"""
from __future__ import annotations

import io
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text,
                        create_engine, event, select)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "company"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    yahoo_symbol: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    valuations: Mapped[list["Valuation"]] = relationship(back_populates="company", cascade="all, delete-orphan",
                                                         order_by="Valuation.created_at")


class Valuation(Base):
    __tablename__ = "valuation"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    label: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(40), default="app")   # app | legacy-import
    engine_version: Mapped[str] = mapped_column(String(20), default="")
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    n_paths: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    inputs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # headline results as columns (queryable / chartable)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    median: Mapped[float | None] = mapped_column(Float, nullable=True)
    sd: Mapped[float | None] = mapped_column(Float, nullable=True)
    p5: Mapped[float | None] = mapped_column(Float, nullable=True)
    p10: Mapped[float | None] = mapped_column(Float, nullable=True)
    p25: Mapped[float | None] = mapped_column(Float, nullable=True)
    p75: Mapped[float | None] = mapped_column(Float, nullable=True)
    p90: Mapped[float | None] = mapped_column(Float, nullable=True)
    p95: Mapped[float | None] = mapped_column(Float, nullable=True)
    prob_above_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    tv_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    company: Mapped[Company] = relationship(back_populates="valuations")
    result: Mapped["ValuationResult"] = relationship(back_populates="valuation", cascade="all, delete-orphan",
                                                     uselist=False)


class ValuationResult(Base):
    __tablename__ = "valuation_result"
    valuation_id: Mapped[str] = mapped_column(ForeignKey("valuation.id", ondelete="CASCADE"), primary_key=True)
    summary: Mapped[dict] = mapped_column(JSON)
    sample: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    valuation: Mapped[Valuation] = relationship(back_populates="result")


class PriceCache(Base):
    __tablename__ = "price_cache"
    symbol: Mapped[str] = mapped_column(String(40), primary_key=True)
    date: Mapped[str] = mapped_column(String(10), primary_key=True)
    close: Mapped[float] = mapped_column(Float)


class Setting(Base):
    __tablename__ = "setting"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


DEFAULT_SETTINGS = {
    # Juan's standing convention (Aug-Sep 2026); editable in Settings.
    "risk_free": {"USD": 0.0465, "EUR": 0.0315, "CHF": 0.0045},
    "erp_mature": 0.0482,
    "simulation_paths": 20000,
    "marginal_tax": {"USD": 0.25, "EUR": 0.25},
}


def default_db_url() -> str:
    url = os.environ.get("DCF_DATABASE_URL")
    if url:
        return url
    data_dir = Path(os.environ.get("DCF_DATA_DIR", Path.home() / ".dcfmc"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{data_dir / 'valuations.db'}"


class Store:
    def __init__(self, url: str | None = None):
        self.url = url or default_db_url()
        kw = {"connect_args": {"check_same_thread": False}} if self.url.startswith("sqlite") else {}
        self.engine = create_engine(self.url, future=True, **kw)
        if self.url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def _fk(dbapi_conn, _):  # pragma: no cover - trivial
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA journal_mode=WAL")
                cur.close()
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False, future=True)

    # ---------------------------------------------------------------- settings
    def get_settings(self) -> dict:
        with self.Session() as s:
            out = json.loads(json.dumps(DEFAULT_SETTINGS))
            for row in s.scalars(select(Setting)):
                out[row.key] = row.value
            return out

    def put_settings(self, values: dict) -> dict:
        with self.Session.begin() as s:
            for k, v in values.items():
                row = s.get(Setting, k)
                if row:
                    row.value = v
                else:
                    s.add(Setting(key=k, value=v))
        return self.get_settings()

    # ---------------------------------------------------------------- companies
    def upsert_company(self, s: Session, ticker: str, name: str = "", currency: str = "USD",
                       yahoo_symbol: str | None = None) -> Company:
        c = s.scalar(select(Company).where(Company.ticker == ticker.upper()))
        if c is None:
            c = Company(ticker=ticker.upper(), name=name or ticker.upper(), currency=currency,
                        yahoo_symbol=yahoo_symbol)
            s.add(c)
            s.flush()
        else:
            if name:
                c.name = name
            if currency:
                c.currency = currency
            if yahoo_symbol:
                c.yahoo_symbol = yahoo_symbol
        return c


def pack_sample(arrays: dict[str, np.ndarray]) -> bytes:
    buf = io.BytesIO()
    np.savez_compressed(buf, **{k: np.asarray(v, dtype=np.float32) for k, v in arrays.items()})
    return buf.getvalue()


def unpack_sample(blob: bytes | None) -> dict[str, np.ndarray]:
    if not blob:
        return {}
    with np.load(io.BytesIO(blob)) as z:
        return {k: z[k] for k in z.files}
