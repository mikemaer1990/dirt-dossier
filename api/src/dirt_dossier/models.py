from datetime import date, datetime
from decimal import Decimal

from geoalchemy2 import Geometry
from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from dirt_dossier.db import Base


class Trail(Base):
    __tablename__ = "trails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    osm_way_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str] = mapped_column(Text, nullable=False, server_default="nanaimo")
    difficulty: Mapped[str | None] = mapped_column(Text)
    direction: Mapped[str | None] = mapped_column(Text)
    length_m: Mapped[int | None] = mapped_column(Integer)
    descent_m: Mapped[int | None] = mapped_column(Integer)
    ascent_m: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="osm")
    raw_tags: Mapped[dict | None] = mapped_column(JSONB)
    geometry: Mapped[bytes] = mapped_column(Geometry("LINESTRING", srid=4326), nullable=False)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    activity_trails: Mapped[list["ActivityTrail"]] = relationship(back_populates="trail")


class Bike(Base):
    __tablename__ = "bikes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    strava_gear_id: Mapped[str | None] = mapped_column(Text, unique=True)
    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchase_cost_cad: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    notes: Mapped[str | None] = mapped_column(Text)

    components: Mapped[list["Component"]] = relationship(back_populates="bike")
    activities: Mapped[list["Activity"]] = relationship(back_populates="bike")
    maintenance_logs: Mapped[list["MaintenanceLog"]] = relationship(back_populates="bike")


class Component(Base):
    __tablename__ = "components"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bike_id: Mapped[int | None] = mapped_column(ForeignKey("bikes.id"))
    type: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    installed_at: Mapped[date] = mapped_column(Date, nullable=False)
    installed_cost_cad: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    replacement_threshold_km: Mapped[Decimal | None] = mapped_column(Numeric)
    replacement_threshold_hours: Mapped[Decimal | None] = mapped_column(Numeric)
    replacement_threshold_days: Mapped[int | None] = mapped_column(Integer)
    current_status: Mapped[str | None] = mapped_column(Text, server_default="active")
    notes: Mapped[str | None] = mapped_column(Text)

    bike: Mapped["Bike | None"] = relationship(back_populates="components")
    maintenance_logs: Mapped[list["MaintenanceLog"]] = relationship(back_populates="component")


class MaintenanceLog(Base):
    __tablename__ = "maintenance_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bike_id: Mapped[int | None] = mapped_column(ForeignKey("bikes.id"))
    component_id: Mapped[int | None] = mapped_column(ForeignKey("components.id"))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    action_date: Mapped[date] = mapped_column(Date, nullable=False)
    cost_cad: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    bike: Mapped["Bike | None"] = relationship(back_populates="maintenance_logs")
    component: Mapped["Component | None"] = relationship(back_populates="maintenance_logs")


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (Index("idx_activities_start_time", "start_time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strava_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    activity_type: Mapped[str] = mapped_column(Text, nullable=False)
    start_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    duration_s: Mapped[int] = mapped_column(Integer, nullable=False)
    moving_time_s: Mapped[int | None] = mapped_column(Integer)
    distance_m: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    elevation_gain_m: Mapped[Decimal | None] = mapped_column(Numeric)
    avg_speed_mps: Mapped[Decimal | None] = mapped_column(Numeric)
    max_speed_mps: Mapped[Decimal | None] = mapped_column(Numeric)
    avg_heartrate: Mapped[Decimal | None] = mapped_column(Numeric)
    max_heartrate: Mapped[Decimal | None] = mapped_column(Numeric)
    bike_id: Mapped[int | None] = mapped_column(ForeignKey("bikes.id"))
    strava_gear_id: Mapped[str | None] = mapped_column(Text)
    weather: Mapped[dict | None] = mapped_column(JSONB)
    geometry: Mapped[bytes | None] = mapped_column(Geometry("LINESTRING", srid=4326))
    raw_summary: Mapped[dict | None] = mapped_column(JSONB)
    ingested_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    bike: Mapped["Bike | None"] = relationship(back_populates="activities")
    activity_trails: Mapped[list["ActivityTrail"]] = relationship(back_populates="activity")


class ActivityTrail(Base):
    __tablename__ = "activity_trails"
    __table_args__ = (
        UniqueConstraint("activity_id", "trail_id"),
        Index("idx_activity_trails_activity", "activity_id"),
        Index("idx_activity_trails_trail", "trail_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), nullable=False
    )
    trail_id: Mapped[int] = mapped_column(ForeignKey("trails.id"), nullable=False)
    overlap_m: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    overlap_pct: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    elapsed_s: Mapped[int | None] = mapped_column(Integer)
    avg_speed_mps: Mapped[Decimal | None] = mapped_column(Numeric)
    direction: Mapped[str | None] = mapped_column(Text)
    matched_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    activity: Mapped["Activity"] = relationship(back_populates="activity_trails")
    trail: Mapped["Trail"] = relationship(back_populates="activity_trails")


class StravaAuth(Base):
    __tablename__ = "strava_auth"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, server_default="1")
    athlete_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
