from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from sqlalchemy import or_

from app.registrar import registrar_bp
from app.extensions import db
from app.forms import (
    FinalistUploadForm, SingleFinalistForm, CreateAdminForm, SearchFilterForm, RejectForm
)
from app.models import (
    User, Department, FinalistWhitelist, DebtRecord, ClearanceRequest, ClearanceItem
)
from app.utils import import_finalist_csv, notify_user, check_request_fully_cleared


@registrar_bp.before_request
@login_required
def _guard():
    if not current_user.is_registrar:
        abort(403)


@registrar_bp.route("/dashboard")
def dashboard():
    total_students = User.query.filter_by(role="student").count()
    fully_cleared = ClearanceRequest.query.filter_by(status="fully_cleared").count()
    in_progress = ClearanceRequest.query.filter_by(status="submitted").count()
    whitelist_count = FinalistWhitelist.query.filter_by(is_active=True).count()
    departments = Department.query.order_by(Department.order_index).all()

    dept_stats = []
    for dept in departments:
        dept_stats.append({
            "name": dept.name,
            "pending": ClearanceItem.query.filter_by(department_id=dept.id, status="pending").count(),
            "approved": ClearanceItem.query.filter_by(department_id=dept.id, status="approved").count(),
            "rejected": ClearanceItem.query.filter_by(department_id=dept.id, status="rejected").count(),
        })

    return render_template(
        "registrar/dashboard.html",
        total_students=total_students, fully_cleared=fully_cleared, in_progress=in_progress,
        whitelist_count=whitelist_count, dept_stats=dept_stats
    )


# --------------------------------------------------------------------------
# Finalist whitelist management
# --------------------------------------------------------------------------
@registrar_bp.route("/finalists", methods=["GET", "POST"])
def finalists():
    upload_form = FinalistUploadForm()
    add_form = SingleFinalistForm()

    if "csv_file" in request.files and upload_form.validate_on_submit():
        created, updated, skipped = import_finalist_csv(upload_form.csv_file.data, current_user.name)
        flash(f"Imported: {created} new, {updated} updated, {skipped} skipped.", "success")
        return redirect(url_for("registrar.finalists"))

    if request.method == "POST" and "reg_number" in request.form and "csv_file" not in request.files and add_form.validate_on_submit():
        existing = FinalistWhitelist.query.filter_by(reg_number=add_form.reg_number.data.strip()).first()
        if existing:
            flash("That registration number is already on the finalist list.", "warning")
        else:
            entry = FinalistWhitelist(
                reg_number=add_form.reg_number.data.strip(),
                student_name=add_form.student_name.data,
                course_type=add_form.course_type.data or None,
                admission_year=add_form.admission_year.data,
                added_by=current_user.name,
            )
            db.session.add(entry)
            db.session.commit()
            flash("Student added to finalist list.", "success")
        return redirect(url_for("registrar.finalists"))

    q = request.args.get("q", "").strip()
    query = FinalistWhitelist.query
    if q:
        query = query.filter(
            or_(FinalistWhitelist.reg_number.ilike(f"%{q}%"), FinalistWhitelist.student_name.ilike(f"%{q}%"))
        )
    entries = query.order_by(FinalistWhitelist.created_at.desc()).all()
    return render_template(
        "registrar/finalists.html", entries=entries, upload_form=upload_form, add_form=add_form, q=q
    )


@registrar_bp.route("/finalists/<int:entry_id>/toggle", methods=["POST"])
def toggle_finalist(entry_id):
    entry = FinalistWhitelist.query.get_or_404(entry_id)
    entry.is_active = not entry.is_active
    db.session.commit()
    flash(f"{entry.reg_number} is now {'active' if entry.is_active else 'inactive'}.", "info")
    return redirect(url_for("registrar.finalists"))


# --------------------------------------------------------------------------
# Department admin accounts
# --------------------------------------------------------------------------
@registrar_bp.route("/staff", methods=["GET", "POST"])
def staff():
    form = CreateAdminForm()
    form.department_id.choices = [(d.id, d.name) for d in Department.query.order_by(Department.order_index)]

    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data.strip().lower()).first():
            flash("A user with that email already exists.", "danger")
        else:
            admin = User(
                name=form.name.data.strip(),
                email=form.email.data.strip().lower(),
                role="admin",
                department_id=form.department_id.data,
            )
            admin.set_password(form.password.data)
            db.session.add(admin)
            db.session.commit()
            notify_user(
                admin,
                f"Your department admin account for {admin.department.name} has been created.",
                email_subject="IUIU Clearance: Admin Account Created",
            )
            flash("Department admin account created.", "success")
        return redirect(url_for("registrar.staff"))

    admins = User.query.filter_by(role="admin").order_by(User.created_at.desc()).all()
    return render_template("registrar/staff.html", form=form, admins=admins)


@registrar_bp.route("/staff/<int:user_id>/deactivate", methods=["POST"])
def deactivate_staff(user_id):
    user = User.query.get_or_404(user_id)
    if user.role not in ("admin", "student"):
        abort(403)
    user.is_active_account = not user.is_active_account
    db.session.commit()
    flash(f"Account {'activated' if user.is_active_account else 'deactivated'}.", "info")
    return redirect(request.referrer or url_for("registrar.staff"))


# --------------------------------------------------------------------------
# Master student / graduation list with search & filter
# --------------------------------------------------------------------------
@registrar_bp.route("/students")
def students():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()

    query = User.query.filter_by(role="student")
    if q:
        query = query.filter(or_(User.name.ilike(f"%{q}%"), User.reg_number.ilike(f"%{q}%")))

    all_students = query.order_by(User.created_at.desc()).all()

    rows = []
    for student in all_students:
        req = (
            ClearanceRequest.query.filter_by(student_id=student.id)
            .order_by(ClearanceRequest.created_at.desc())
            .first()
        )
        req_status = req.status if req else "not_started"
        if status and status != req_status:
            continue
        rows.append({"student": student, "request": req, "status": req_status})

    return render_template("registrar/students.html", rows=rows, q=q, status=status)


@registrar_bp.route("/students/<int:student_id>")
def student_detail(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    req = (
        ClearanceRequest.query.filter_by(student_id=student.id)
        .order_by(ClearanceRequest.created_at.desc())
        .first()
    )
    items = []
    if req:
        items = (
            ClearanceItem.query.filter_by(request_id=req.id)
            .join(Department)
            .order_by(Department.order_index)
            .all()
        )
    reject_form = RejectForm()
    return render_template("registrar/student_detail.html", student=student, request_obj=req, items=items, reject_form=reject_form)


@registrar_bp.route("/students/item/<int:item_id>/override-approve", methods=["POST"])
def override_approve(item_id):
    """Registrar can override and force-approve a stuck item (absolute control)."""
    item = ClearanceItem.query.get_or_404(item_id)
    item.status = "approved"
    item.reviewed_by = current_user.id
    item.reviewed_at = datetime.utcnow()
    item.rejection_reason = None
    db.session.commit()

    req = ClearanceRequest.query.get(item.request_id)
    student = User.query.get(req.student_id)
    notify_user(
        student,
        f"The Registrar has approved your {item.department.name} clearance on override.",
        link=url_for("student.dashboard"),
        email_subject="IUIU Clearance: Registrar Override Approval",
    )
    check_request_fully_cleared(req)
    flash("Item approved by Registrar override.", "success")
    return redirect(url_for("registrar.student_detail", student_id=student.id))


# --------------------------------------------------------------------------
# Cross-department debt ledger overview (read-only)
# --------------------------------------------------------------------------
@registrar_bp.route("/debts")
def debts_overview():
    q = request.args.get("q", "").strip()
    query = DebtRecord.query.join(Department)
    if q:
        query = query.filter(DebtRecord.reg_number.ilike(f"%{q}%"))
    records = query.order_by(DebtRecord.created_at.desc()).all()
    return render_template("registrar/debts_overview.html", records=records, q=q)


@registrar_bp.route("/departments")
def departments():
    depts = Department.query.order_by(Department.order_index).all()
    return render_template("registrar/departments.html", departments=depts)
