from datetime import datetime, timezone
from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, JSON, ForeignKey, Text
from sqlalchemy.orm import relationship
from remmy.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class ShiftPlan(Base):
    __tablename__ = "shift_plans"
    id = Column(Integer, primary_key=True)
    site = Column(String, default="PHX6")
    shift_type = Column(String)  # "Day" / "Night"
    date = Column(String)
    planning_om = Column(String)
    big_gulp_volume = Column(Float)
    shift_volume_cret = Column(Float)
    shift_volume_whd = Column(Float)
    shift_duration = Column(Float)
    show_rate_day = Column(Float)
    show_rate_night = Column(Float)
    seed_hc_day = Column(Float)
    seed_hc_night = Column(Float)
    day_volume_pct = Column(Float)
    night_volume_pct = Column(Float)
    ns_pct = Column(Float)
    new_hire_pct = Column(Float, default=0)
    new_hire_count = Column(Integer, default=0)
    positioning = Column(String)  # "on_course" / "underprocess" / "overprocess"
    positioning_adj = Column(Float, default=0)
    backlog_current = Column(Float)
    backlog_target = Column(Float)
    prior_shift_hit = Column(String)  # "hit" / "miss" / "exceed"
    quarter = Column(Integer)
    status = Column(String, default="draft")  # "draft" / "locked"
    locked_by = Column(String)
    locked_at = Column(DateTime)
    closed_at = Column(DateTime)
    created_at = Column(DateTime, default=utcnow)
    # HC results stored as JSON: {role_code: hc_value}
    cret_direct_hc = Column(JSON)
    cret_support_hc = Column(JSON)
    whd_direct_hc = Column(JSON)
    whd_indirect_buffer = Column(Integer)
    total_cret_hc = Column(Integer)
    total_whd_hc = Column(Integer)
    building_total = Column(Integer)
    support_pct = Column(Float)
    flags = Column(JSON)  # list of active flag dicts
    assumed_inputs = Column(JSON)
    eos_quality = Column(JSON)
    overrides = relationship("Override", back_populates="plan", cascade="all, delete-orphan")
    actuals = relationship("ShiftActual", back_populates="plan", cascade="all, delete-orphan")


class Override(Base):
    __tablename__ = "overrides"
    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey("shift_plans.id"))
    timestamp = Column(DateTime, default=utcnow)
    role_code = Column(String)
    original_value = Column(Float)
    override_value = Column(Float)
    justification = Column(Text)
    override_type = Column(String)  # "soft" / "hard" / "lock"
    plan = relationship("ShiftPlan", back_populates="overrides")


class RollingAverage(Base):
    __tablename__ = "rolling_averages"
    id = Column(Integer, primary_key=True)
    site = Column(String, default="PHX6")
    model = Column(String)  # "CRET" / "WHD"
    role_code = Column(String)
    week_date = Column(String)  # ISO week identifier
    actual_uph = Column(Float)
    is_anomaly = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)


class LearningMetric(Base):
    __tablename__ = "learning_metrics"
    id = Column(Integer, primary_key=True)
    site = Column(String, default="PHX6")
    shift_date = Column(String)
    shift_type = Column(String)
    planning_accuracy = Column(Float)
    override_frequency = Column(Float)
    recommendation_acceptance = Column(Float)
    phase = Column(Integer, default=1)
    created_at = Column(DateTime, default=utcnow)


class ShiftActual(Base):
    __tablename__ = "shift_actuals"
    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey("shift_plans.id"))
    role_code = Column(String)
    actual_hc = Column(Integer)
    actual_uph = Column(Float)
    actual_volume = Column(Float)
    plan = relationship("ShiftPlan", back_populates="actuals")
    created_at = Column(DateTime, default=utcnow)


class NsRollingAverage(Base):
    __tablename__ = "ns_rolling_averages"
    id = Column(Integer, primary_key=True)
    site = Column(String, default="PHX6")
    week_date = Column(String)
    ns_pct = Column(Float)
    created_at = Column(DateTime, default=utcnow)
