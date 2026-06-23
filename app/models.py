import secrets
import string
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


def _utcnow():
    return datetime.utcnow()


class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False)      # e.g. 'bursar'
    name = db.Column(db.String(120), nullable=False)                  # e.g. 'University Bursar'
    description = db.Column(db.String(255))
    order_index = db.Column(db.Integer, default=0)

    admins = db.relationship("User", backref="department", foreign_keys="User.department_id")
    debt_records = db.relationship("DebtRecord", backref="department", cascade="all, delete-orphan")
    clearance_items = db.relationship("ClearanceItem", backref="department", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Department {self.code}>"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # role: 'student' | 'admin' | 'registrar'
    role = db.Column(db.String(20), nullable=False, default="student")

    # Student-only fields
    reg_number = db.Column(db.String(20), unique=True, nullable=True, index=True)
    course_type = db.Column(db.String(20), nullable=True)   # certificate/diploma/bachelors/llb
    course_name = db.Column(db.String(150), nullable=True)
    admission_year = db.Column(db.Integer, nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    profile_photo = db.Column(db.String(255), nullable=True)

    # Admin-only field
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)

    is_active_account = db.Column(db.Boolean, default=True)
    is_locked = db.Column(db.Boolean, default=False)  # locked after full clearance (no more edits)
    created_at = db.Column(db.DateTime, default=_utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    clearance_requests = db.relationship(
        "ClearanceRequest", backref="student", cascade="all, delete-orphan", foreign_keys="ClearanceRequest.student_id"
    )
    notifications = db.relationship(
        "Notification", backref="user", cascade="all, delete-orphan", foreign_keys="Notification.user_id"
    )

    # -- password helpers --
    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    # -- role helpers --
    @property
    def is_student(self):
        return self.role == "student"

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_registrar(self):
        return self.role == "registrar"

    @property
    def unread_notification_count(self):
        return Notification.query.filter_by(user_id=self.id, is_read=False).count()

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


class FinalistWhitelist(db.Model):
    """The master 'Active Finalists List' uploaded by the Registrar / Super Admin.

    Step 1 of the access gate: a student's registration number MUST appear
    here (and not be marked inactive) before any system access is granted.
    """

    __tablename__ = "finalist_whitelist"

    id = db.Column(db.Integer, primary_key=True)
    reg_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    student_name = db.Column(db.String(120), nullable=True)
    course_type = db.Column(db.String(20), nullable=True)
    admission_year = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    added_by = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    def __repr__(self):
        return f"<FinalistWhitelist {self.reg_number}>"


class DebtRecord(db.Model):
    """The Debt Exception Table. Presence of an un-settled row for a given
    (reg_number, department) forces a receipt-upload requirement instead of
    a simple checkbox during clearance submission.
    """

    __tablename__ = "debt_records"

    id = db.Column(db.Integer, primary_key=True)
    reg_number = db.Column(db.String(20), nullable=False, index=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0)
    reason = db.Column(db.String(255), nullable=True)
    is_settled = db.Column(db.Boolean, default=False)
    imported_by = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    def __repr__(self):
        return f"<DebtRecord {self.reg_number} dept={self.department_id} amt={self.amount}>"


def generate_tracking_code():
    digits = "".join(secrets.choice(string.digits) for _ in range(4))
    return f"CLR-{digits}"


class ClearanceRequest(db.Model):
    """One per student per clearance cycle. Aggregates the 5 ClearanceItems."""

    __tablename__ = "clearance_requests"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    tracking_code = db.Column(db.String(20), unique=True, default=generate_tracking_code)

    # overall: draft | submitted | fully_cleared
    status = db.Column(db.String(20), default="draft")

    submitted_at = db.Column(db.DateTime, nullable=True)
    fully_cleared_at = db.Column(db.DateTime, nullable=True)
    certificate_generated = db.Column(db.Boolean, default=False)
    certificate_filename = db.Column(db.String(255), nullable=True)
    verification_code = db.Column(db.String(64), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    items = db.relationship("ClearanceItem", backref="request", cascade="all, delete-orphan")

    @property
    def is_fully_approved(self):
        return self.items and all(item.status == "approved" for item in self.items)

    @property
    def progress_percent(self):
        if not self.items:
            return 0
        approved = sum(1 for i in self.items if i.status == "approved")
        return round((approved / len(self.items)) * 100)

    def __repr__(self):
        return f"<ClearanceRequest {self.tracking_code} student={self.student_id}>"


class ClearanceItem(db.Model):
    """Per-department line item within a ClearanceRequest."""

    __tablename__ = "clearance_items"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("clearance_requests.id"), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)

    has_debt = db.Column(db.Boolean, default=False)
    checkbox_confirmed = db.Column(db.Boolean, default=False)
    receipt_filename = db.Column(db.String(255), nullable=True)

    # status: not_submitted | pending | approved | rejected
    status = db.Column(db.String(20), default="not_submitted")
    rejection_reason = db.Column(db.String(255), nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    def __repr__(self):
        return f"<ClearanceItem req={self.request_id} dept={self.department_id} status={self.status}>"


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    link = db.Column(db.String(255), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    def __repr__(self):
        return f"<Notification to={self.user_id} read={self.is_read}>"
