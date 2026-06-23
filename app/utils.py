import os
import io
import csv
import secrets
from datetime import datetime
from functools import wraps

from flask import current_app, abort, url_for
from flask_login import current_user
from flask_mail import Message
from werkzeug.utils import secure_filename

from app.extensions import db, mail
from app.models import (
    User, Department, FinalistWhitelist, DebtRecord, ClearanceRequest,
    ClearanceItem, Notification
)


# --------------------------------------------------------------------------
# Access control decorators
# --------------------------------------------------------------------------
def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


# --------------------------------------------------------------------------
# Finalist Eligibility Engine
# --------------------------------------------------------------------------
def compute_expected_graduation_year(admission_year, course_type):
    durations = current_app.config["COURSE_DURATIONS"]
    duration = durations.get(course_type, 3)
    return (admission_year or 0) + duration


def get_department_exception_config(department_code):
    """Returns the per-department blocker config: whether it's monetary,
    what to call the issue, and what the receipt-upload label should say."""
    config = current_app.config["DEPARTMENT_EXCEPTION_CONFIG"].get(department_code)
    if config:
        return config
    return {
        "is_monetary": False,
        "noun": "Outstanding Issue",
        "example": "",
        "evidence_label": "Upload Proof of Resolution",
    }


def check_finalist_eligibility(reg_number, admission_year=None, course_type=None):
    """Step 1 of the access gate.

    Returns a dict: {allowed: bool, reason: str, expected_grad_year: int|None}
    A student must:
      1) appear (active) on the Registrar-uploaded Finalist Whitelist, AND
      2) have reached or passed their computed expected graduation year.
    """
    entry = FinalistWhitelist.query.filter_by(reg_number=reg_number, is_active=True).first()
    current_year = current_app.config["CURRENT_ACADEMIC_YEAR"]

    if not entry:
        return {
            "allowed": False,
            "reason": "Error: Profile not active on the graduation cohort list.",
            "expected_grad_year": None,
        }

    eff_admission_year = admission_year or entry.admission_year
    eff_course_type = course_type or entry.course_type

    if eff_admission_year and eff_course_type:
        expected_year = compute_expected_graduation_year(eff_admission_year, eff_course_type)
        if current_year < expected_year:
            return {
                "allowed": False,
                "reason": f"You are not a finalist until {expected_year}.",
                "expected_grad_year": expected_year,
            }
        return {"allowed": True, "reason": "Finalist Authenticated", "expected_grad_year": expected_year}

    # No course/admission info available to cross-check; whitelist presence is enough.
    return {"allowed": True, "reason": "Finalist Authenticated", "expected_grad_year": None}


# --------------------------------------------------------------------------
# Debt Exception Table lookups (Step 2 of the access gate)
# --------------------------------------------------------------------------
def get_open_debt(reg_number, department_id):
    return DebtRecord.query.filter_by(
        reg_number=reg_number, department_id=department_id, is_settled=False
    ).first()


def student_has_any_open_debt(reg_number):
    return DebtRecord.query.filter_by(reg_number=reg_number, is_settled=False).count() > 0


# --------------------------------------------------------------------------
# File upload helpers
# --------------------------------------------------------------------------
def cloudinary_enabled():
    return bool(current_app.config.get("CLOUDINARY_CLOUD_NAME"))


def allowed_file(filename, allowed_set=None):
    allowed_set = allowed_set or current_app.config["ALLOWED_EXTENSIONS"]
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_set


def is_remote_url(value):
    return bool(value) and value.startswith("http")


def save_receipt_file(file_storage, reg_number):
    """Returns either a Cloudinary secure URL (production) or a local
    filename relative to UPLOAD_FOLDER (local dev fallback)."""
    if cloudinary_enabled():
        import cloudinary.uploader
        token = secrets.token_hex(6)
        result = cloudinary.uploader.upload(
            file_storage,
            folder="iuiu_clearance/receipts",
            public_id=f"{reg_number}_{token}",
            resource_type="auto",
        )
        return result["secure_url"]

    folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    ext = secure_filename(file_storage.filename).rsplit(".", 1)[1].lower()
    token = secrets.token_hex(6)
    filename = f"{reg_number}_{token}.{ext}"
    file_storage.save(os.path.join(folder, filename))
    return filename


def save_profile_photo(file_storage, reg_number_or_id):
    """Returns either a Cloudinary secure URL (production) or a local
    filename (local dev fallback)."""
    if cloudinary_enabled():
        import cloudinary.uploader
        token = secrets.token_hex(6)
        result = cloudinary.uploader.upload(
            file_storage,
            folder="iuiu_clearance/profiles",
            public_id=f"profile_{reg_number_or_id}_{token}",
            resource_type="image",
        )
        return result["secure_url"]

    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "..", "profiles")
    folder = os.path.abspath(folder)
    os.makedirs(folder, exist_ok=True)
    ext = secure_filename(file_storage.filename).rsplit(".", 1)[1].lower()
    token = secrets.token_hex(6)
    filename = f"profile_{reg_number_or_id}_{token}.{ext}"
    file_storage.save(os.path.join(folder, filename))
    return filename


def save_certificate_pdf(pdf_bytes, tracking_code):
    """Returns either a Cloudinary secure URL (production) or a local
    filename (local dev fallback). pdf_bytes is the raw PDF content."""
    filename = f"certificate_{tracking_code}.pdf"

    if cloudinary_enabled():
        import cloudinary.uploader
        result = cloudinary.uploader.upload(
            io.BytesIO(pdf_bytes),
            folder="iuiu_clearance/certificates",
            public_id=f"certificate_{tracking_code}",
            resource_type="raw",
            format="pdf",
            overwrite=True,
        )
        return result["secure_url"]

    cert_dir = os.path.abspath(os.path.join(current_app.config["UPLOAD_FOLDER"], "..", "certificates"))
    os.makedirs(cert_dir, exist_ok=True)
    filepath = os.path.join(cert_dir, filename)
    with open(filepath, "wb") as fh:
        fh.write(pdf_bytes)
    return filename


# --------------------------------------------------------------------------
# Notifications (in-app + email)
# --------------------------------------------------------------------------
def notify_user(user, message, link=None, email_subject=None):
    note = Notification(user_id=user.id, message=message, link=link)
    db.session.add(note)
    db.session.commit()
    if email_subject:
        send_email_async(user.email, email_subject, message)
    return note


def send_email_async(to, subject, body):
    try:
        msg = Message(subject=subject, recipients=[to], body=body,
                       sender=current_app.config.get("MAIL_DEFAULT_SENDER"))
        mail.send(msg)
    except Exception as exc:  # pragma: no cover - never break the request flow over email
        current_app.logger.warning("Email send failed to %s: %s", to, exc)


def notify_department_admins(department_id, message, link=None):
    admins = User.query.filter_by(role="admin", department_id=department_id).all()
    for admin in admins:
        notify_user(admin, message, link=link)


def notify_all_department_admins_for_request(message, link=None):
    admins = User.query.filter_by(role="admin").all()
    for admin in admins:
        notify_user(admin, message, link=link)


# --------------------------------------------------------------------------
# CSV import helpers
# --------------------------------------------------------------------------
def parse_csv_filestorage(file_storage):
    stream = io.StringIO(file_storage.stream.read().decode("utf-8-sig"), newline=None)
    return list(csv.DictReader(stream))


def import_finalist_csv(file_storage, added_by_label):
    """Expected columns: reg_number, student_name (optional), course_type (optional), admission_year (optional)"""
    rows = parse_csv_filestorage(file_storage)
    created, updated, skipped = 0, 0, 0
    for row in rows:
        reg = (row.get("reg_number") or row.get("Reg Number") or "").strip()
        if not reg:
            skipped += 1
            continue
        entry = FinalistWhitelist.query.filter_by(reg_number=reg).first()
        if entry is None:
            entry = FinalistWhitelist(reg_number=reg, added_by=added_by_label)
            db.session.add(entry)
            created += 1
        else:
            updated += 1
        entry.student_name = row.get("student_name") or row.get("Student Name") or entry.student_name
        entry.course_type = (row.get("course_type") or row.get("Course Type") or entry.course_type or "").strip() or None
        ay = row.get("admission_year") or row.get("Admission Year")
        if ay:
            try:
                entry.admission_year = int(ay)
            except ValueError:
                pass
        entry.is_active = True
    db.session.commit()
    return created, updated, skipped


def import_debt_csv(file_storage, department_id, imported_by_label):
    """Expected columns: reg_number, amount, reason (optional)"""
    rows = parse_csv_filestorage(file_storage)
    created, skipped = 0, 0
    for row in rows:
        reg = (row.get("reg_number") or row.get("Reg Number") or "").strip()
        amount_raw = row.get("amount") or row.get("Amount") or "0"
        if not reg:
            skipped += 1
            continue
        try:
            amount = float(str(amount_raw).replace(",", ""))
        except ValueError:
            amount = 0
        record = DebtRecord(
            reg_number=reg,
            department_id=department_id,
            amount=amount,
            reason=row.get("reason") or row.get("Reason") or "Outstanding issue",
            imported_by=imported_by_label,
        )
        db.session.add(record)
        created += 1
    db.session.commit()
    return created, skipped


# --------------------------------------------------------------------------
# Clearance request lifecycle
# --------------------------------------------------------------------------
def get_or_create_active_request(student):
    req = (
        ClearanceRequest.query.filter_by(student_id=student.id)
        .order_by(ClearanceRequest.created_at.desc())
        .first()
    )
    if req and req.status != "fully_cleared":
        return req

    if req and req.status == "fully_cleared":
        return req  # already finished; show read-only view

    req = ClearanceRequest(student_id=student.id, status="draft")
    db.session.add(req)
    db.session.flush()

    departments = Department.query.order_by(Department.order_index).all()
    for dept in departments:
        debt = get_open_debt(student.reg_number, dept.id)
        item = ClearanceItem(
            request_id=req.id,
            department_id=dept.id,
            has_debt=bool(debt),
            status="not_submitted",
        )
        db.session.add(item)
    db.session.commit()
    return req


def check_request_fully_cleared(request_obj):
    if request_obj.items and all(item.status == "approved" for item in request_obj.items):
        if request_obj.status != "fully_cleared":
            request_obj.status = "fully_cleared"
            request_obj.fully_cleared_at = datetime.utcnow()
            db.session.commit()
            student = request_obj.student
            notify_user(
                student,
                "Congratulations! You have been 100% cleared by all departments for graduation.",
                link=url_for("student.certificate", request_id=request_obj.id),
                email_subject="IUIU Clearance: You are 100% cleared!",
            )
        return True
    return False
