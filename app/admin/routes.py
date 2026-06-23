import os
from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, send_from_directory, abort, current_app
from flask_login import login_required, current_user
from sqlalchemy import or_

from app.admin import admin_bp
from app.extensions import db
from app.forms import RejectForm, DebtUploadForm, SingleDebtForm, SearchFilterForm
from app.models import ClearanceItem, ClearanceRequest, User, DebtRecord
from app.utils import (
    role_required, notify_user, check_request_fully_cleared, import_debt_csv,
    get_department_exception_config, is_remote_url
)


@admin_bp.before_request
@login_required
def _guard():
    if not current_user.is_admin:
        abort(403)


@admin_bp.route("/dashboard")
def dashboard():
    dept_id = current_user.department_id
    exc_config = get_department_exception_config(current_user.department.code)
    total = ClearanceItem.query.filter_by(department_id=dept_id).count()
    pending = ClearanceItem.query.filter_by(department_id=dept_id, status="pending").count()
    approved = ClearanceItem.query.filter_by(department_id=dept_id, status="approved").count()
    rejected = ClearanceItem.query.filter_by(department_id=dept_id, status="rejected").count()
    debts_open = DebtRecord.query.filter_by(department_id=dept_id, is_settled=False).count()
    return render_template(
        "admin/dashboard.html", total=total, pending=pending, approved=approved,
        rejected=rejected, debts_open=debts_open, exc_config=exc_config
    )


@admin_bp.route("/queue")
def queue():
    form = SearchFilterForm(formdata=request.args, meta={"csrf": False})
    dept_id = current_user.department_id

    query = (
        ClearanceItem.query.join(ClearanceRequest)
        .join(User, ClearanceRequest.student_id == User.id)
        .filter(ClearanceItem.department_id == dept_id)
    )

    status = request.args.get("status", "").strip()
    q = request.args.get("q", "").strip()

    if status:
        query = query.filter(ClearanceItem.status == status)
    if q:
        query = query.filter(
            or_(User.name.ilike(f"%{q}%"), User.reg_number.ilike(f"%{q}%"))
        )

    items = query.order_by(ClearanceItem.submitted_at.desc().nullslast()).all()
    return render_template("admin/queue.html", items=items, form=form, status=status, q=q)


@admin_bp.route("/clearance/<int:item_id>/view")
def view_item(item_id):
    item = ClearanceItem.query.get_or_404(item_id)
    if item.department_id != current_user.department_id:
        abort(403)
    reject_form = RejectForm()
    return render_template("admin/review_item.html", item=item, reject_form=reject_form)


@admin_bp.route("/clearance/<int:item_id>/receipt")
def view_receipt(item_id):
    item = ClearanceItem.query.get_or_404(item_id)
    if item.department_id != current_user.department_id:
        abort(403)
    if not item.receipt_filename:
        abort(404)
    if is_remote_url(item.receipt_filename):
        return redirect(item.receipt_filename)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], item.receipt_filename)


@admin_bp.route("/clearance/<int:item_id>/approve", methods=["POST"])
def approve_item(item_id):
    item = ClearanceItem.query.get_or_404(item_id)
    if item.department_id != current_user.department_id:
        abort(403)

    item.status = "approved"
    item.reviewed_by = current_user.id
    item.reviewed_at = datetime.utcnow()
    db.session.commit()

    req = ClearanceRequest.query.get(item.request_id)
    student = User.query.get(req.student_id)
    notify_user(
        student,
        f"{item.department.name} has approved your clearance request.",
        link=url_for("student.dashboard"),
        email_subject="IUIU Clearance: Department Approved",
    )

    check_request_fully_cleared(req)
    flash("Item approved.", "success")
    return redirect(url_for("admin.queue"))


@admin_bp.route("/clearance/<int:item_id>/reject", methods=["POST"])
def reject_item(item_id):
    item = ClearanceItem.query.get_or_404(item_id)
    if item.department_id != current_user.department_id:
        abort(403)

    form = RejectForm()
    if form.validate_on_submit():
        item.status = "rejected"
        item.rejection_reason = form.reason.data.strip()
        item.reviewed_by = current_user.id
        item.reviewed_at = datetime.utcnow()
        db.session.commit()

        req = ClearanceRequest.query.get(item.request_id)
        student = User.query.get(req.student_id)
        notify_user(
            student,
            f"ALERT: {item.department.name} rejected your submission. "
            f"Reason: {item.rejection_reason}. Log in to upload a fresh copy.",
            link=url_for("student.clearance_item", item_id=item.id),
            email_subject="IUIU Clearance: Submission Rejected",
        )
        flash("Item rejected and student notified.", "info")
    else:
        flash("Please provide a valid rejection reason.", "danger")

    return redirect(url_for("admin.view_item", item_id=item.id))


# --------------------------------------------------------------------------
# Department debt ledger management
# --------------------------------------------------------------------------
@admin_bp.route("/debts", methods=["GET", "POST"])
def debts():
    dept_id = current_user.department_id
    exc_config = get_department_exception_config(current_user.department.code)
    upload_form = DebtUploadForm()
    add_form = SingleDebtForm()

    if "csv_file" in request.files and upload_form.validate_on_submit():
        created, skipped = import_debt_csv(upload_form.csv_file.data, dept_id, current_user.name)
        flash(f"Imported {created} record(s), skipped {skipped} invalid row(s).", "success")
        return redirect(url_for("admin.debts"))

    if request.method == "POST" and "reason" in request.form and "csv_file" not in request.files:
        if add_form.validate_on_submit():
            if exc_config["is_monetary"] and (add_form.amount.data is None or add_form.amount.data <= 0):
                flash(f"Please enter a valid {exc_config['noun'].lower()} amount.", "danger")
            else:
                record = DebtRecord(
                    reg_number=add_form.reg_number.data.strip(),
                    department_id=dept_id,
                    amount=add_form.amount.data or 0,
                    reason=add_form.reason.data.strip(),
                    imported_by=current_user.name,
                )
                db.session.add(record)
                db.session.commit()
                flash("Record added.", "success")
            return redirect(url_for("admin.debts"))

    records = DebtRecord.query.filter_by(department_id=dept_id).order_by(DebtRecord.created_at.desc()).all()
    return render_template(
        "admin/debts.html", records=records, upload_form=upload_form, add_form=add_form, exc_config=exc_config
    )


@admin_bp.route("/debts/<int:debt_id>/settle", methods=["POST"])
def settle_debt(debt_id):
    record = DebtRecord.query.get_or_404(debt_id)
    if record.department_id != current_user.department_id:
        abort(403)
    record.is_settled = True
    db.session.commit()
    flash("Debt marked as settled.", "success")
    return redirect(url_for("admin.debts"))
