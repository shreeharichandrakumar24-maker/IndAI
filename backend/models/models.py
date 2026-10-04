from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from backend.db.database import Base
import uuid

class Employee(Base):
    __tablename__ = "employees"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    role = Column(String(255), nullable=False)
    skills = Column(JSONB)
    certifications = Column(JSONB)
    shift = Column(String(100))
    status = Column(String(50), default="ACTIVE")
    availability = Column(String(50), default="AVAILABLE")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tasks = relationship("Task", back_populates="employee")
    incidents = relationship("Incident", back_populates="employee")

class Machine(Base):
    __tablename__ = "machines"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    machine_type = Column(String(100))
    location = Column(String(255))
    status = Column(String(50), default="OPERATIONAL")
    health_status = Column(String(50), default="GOOD")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tasks = relationship("Task", back_populates="machine")
    production_runs = relationship("ProductionRun", back_populates="machine")
    # ORM cascades mirror the DB's ON DELETE CASCADE on these NOT NULL FKs.
    # Without them, db.delete(machine) nullifies child FKs first and violates
    # the NOT NULL constraint on machine_telemetry.machine_id.
    telemetry = relationship("MachineTelemetry", back_populates="machine", cascade="all, delete-orphan")
    maintenance = relationship("Maintenance", back_populates="machine", cascade="all, delete-orphan")
    incidents = relationship("Incident", back_populates="machine")
    factory_memory = relationship("FactoryMemory", back_populates="machine")

class Order(Base):
    __tablename__ = "orders"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_number = Column(String(100), unique=True, nullable=False)
    customer_name = Column(String(255))
    product = Column(String(255))
    quantity = Column(Integer, default=0)
    priority = Column(String(50), default="NORMAL")
    status = Column(String(50), default="PENDING")
    deadline = Column(DateTime(timezone=True))
    progress = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tasks = relationship("Task", back_populates="order")
    production_runs = relationship("ProductionRun", back_populates="order")
    incidents = relationship("Incident", back_populates="order")
    factory_memory = relationship("FactoryMemory", back_populates="order")

class Task(Base):
    __tablename__ = "tasks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    required_skill = Column(String(255))
    priority = Column(String(50), default="NORMAL")
    status = Column(String(50), default="PENDING")
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"))
    machine_id = Column(UUID(as_uuid=True), ForeignKey("machines.id", ondelete="SET NULL"))
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"))
    start_time = Column(DateTime(timezone=True))
    deadline = Column(DateTime(timezone=True))
    progress = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    employee = relationship("Employee", back_populates="tasks")
    machine = relationship("Machine", back_populates="tasks")
    order = relationship("Order", back_populates="tasks")
    production_runs = relationship("ProductionRun", back_populates="task")
    incidents = relationship("Incident", back_populates="task")
    factory_memory = relationship("FactoryMemory", back_populates="task")

class ProductionRun(Base):
    __tablename__ = "production_runs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"))
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"))
    machine_id = Column(UUID(as_uuid=True), ForeignKey("machines.id", ondelete="SET NULL"))
    quantity_target = Column(Integer, default=0)
    quantity_completed = Column(Integer, default=0)
    status = Column(String(50), default="PLANNED")
    start_time = Column(DateTime(timezone=True))
    estimated_completion = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    order = relationship("Order", back_populates="production_runs")
    task = relationship("Task", back_populates="production_runs")
    machine = relationship("Machine", back_populates="production_runs")

class MachineTelemetry(Base):
    __tablename__ = "machine_telemetry"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    machine_id = Column(UUID(as_uuid=True), ForeignKey("machines.id", ondelete="CASCADE"), nullable=False)
    temperature = Column(Float)
    vibration = Column(Float)
    current = Column(Float)
    rpm = Column(Float)
    machine_status = Column(String(50))
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    machine = relationship("Machine", back_populates="telemetry")

class Maintenance(Base):
    __tablename__ = "maintenance"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    machine_id = Column(UUID(as_uuid=True), ForeignKey("machines.id", ondelete="CASCADE"), nullable=False)
    issue = Column(String(255), nullable=False)
    description = Column(Text)
    technician = Column(String(255))
    maintenance_date = Column(DateTime(timezone=True))
    resolution = Column(Text)
    status = Column(String(50), default="PENDING")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    machine = relationship("Machine", back_populates="maintenance")

class Incident(Base):
    __tablename__ = "incidents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    machine_id = Column(UUID(as_uuid=True), ForeignKey("machines.id", ondelete="SET NULL"))
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"))
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"))
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"))
    incident_type = Column(String(100), nullable=False)
    severity = Column(String(50), default="MEDIUM")
    description = Column(Text)
    status = Column(String(50), default="OPEN")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    machine = relationship("Machine", back_populates="incidents")
    task = relationship("Task", back_populates="incidents")
    employee = relationship("Employee", back_populates="incidents")
    order = relationship("Order", back_populates="incidents")

class FactoryMemory(Base):
    __tablename__ = "factory_memory"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    event_type = Column(String(100))
    description = Column(Text)
    machine_id = Column(UUID(as_uuid=True), ForeignKey("machines.id", ondelete="SET NULL"))
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"))
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"))
    resolution_action = Column(Text)
    metadata_ = Column("metadata", JSONB) # aliased because metadata is reserved in Base
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    machine = relationship("Machine", back_populates="factory_memory")
    order = relationship("Order", back_populates="factory_memory")
    task = relationship("Task", back_populates="factory_memory")

class FactoryProfile(Base):
    __tablename__ = "factory_profile"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    industry = Column(String(255))
    status = Column(String(50), default="DRAFT")
    answers = Column(JSONB)
    profile = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recommendation_type = Column(String(100), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    recommendation = Column(Text, nullable=False)
    reason = Column(Text)
    confidence = Column(Float)
    status = Column(String(50), default="PENDING")
    params = Column(JSONB, nullable=True)  # assistant action params (migration 005); may be absent in old DBs
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class AppUser(Base):
    __tablename__ = "app_users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supabase_uid = Column(Text, unique=True, nullable=False)
    email = Column(String(255))
    name = Column(String(255))
    role = Column(String(50), default="OPERATOR")
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"))
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"))
    title = Column(String(255), nullable=False)
    body = Column(Text)
    link = Column(String(255))
    kind = Column(String(100))
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class WorkPlan(Base):
    __tablename__ = "work_plans"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    payload = Column(JSONB)
    status = Column(String(50), default="DRAFT")
    created_by = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="SET NULL"))
    approved_by = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class PlanAssignment(Base):
    __tablename__ = "plan_assignments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("work_plans.id", ondelete="CASCADE"))
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"))
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"))
    machine_id = Column(UUID(as_uuid=True), ForeignKey("machines.id", ondelete="SET NULL"))
    status = Column(String(50), default="UNASSIGNED")
    notified_at = Column(DateTime(timezone=True))
    responded_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class FcmToken(Base):
    __tablename__ = "fcm_tokens"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"))
    token = Column(Text, unique=True, nullable=False)
    platform = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class WorkerCredential(Base):
    __tablename__ = "worker_credentials"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), unique=True, nullable=False)
    username = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    employee_code = Column(String(50), nullable=True)
    must_change_password = Column(Boolean, default=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
