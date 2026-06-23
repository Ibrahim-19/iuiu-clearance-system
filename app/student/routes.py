import os

from flask import (
    render_template, redirect, url_for, flash, request, send_from_directory, abort
)
from flask_login import login_required, current_user

from app.student import student_bp
from app.extensions import db
from app.forms import (
    ClearanceItemCheckboxForm, ClearanceItemReceiptForm, ProfileUpdateForm, ChangePasswordForm
)
from app.models import ClearanceItem, ClearanceRequest, Department
from app.utils import (
    role_required, get_or_create_active_request, save_receipt_file, save_profile_photo,
    save_certificate_pdf, notify_department_admins, notify_user, check_request_fully_cleared,
    compute_expected_graduation_year, get_department_exception_config, is_remote_url
)
from app.certificate import generate_certificate_pdf_bytes, make_verification_code
from datetime import datetime


@student_bp.before_request
@login_required
def _guard():
    if not current_user.is_student:
        abort(403)


@student_bp.route("/dashboard")
def dashboard():
    req = get_or_create_active_request(current_user)
    items = (
        ClearanceItem.query.filter_by(request_id=req.id)
        .join(Department)
        .order_by(Department.order_index)
        .all()
    )
    expected_grad_year = None
    if current_user.admission_year and current_user.course_type:
        expected_grad_year = compute_expected_graduation_year(
            current_user.admission_year, current_user.course_type
        )
    return render_template(
        "student/dashboard.html", request_obj=req, items=items, expected_grad_year=expected_grad_year
    )


@student_bp.route("/clearance/<int:item_id>", methods=["GET", "POST"])
def clearance_item(item_id):
    item = ClearanceItem.query.get_or_404(item_id)
    req = ClearanceRequest.query.get_or_404(item.request_id)

    if req.student_id != current_user.id:
        abort(403)
    if req.status == "fully_cleared" or current_user.is_locked:
        flash("This clearance record is locked and can no longer be edited.", "warning")
        return redirect(url_for("student.dashboard"))
    if item.status == "approved":
        flash("This department has already approved your clearance.", "info")
        return redirect(url_for("student.dashboard"))

    if item.has_debt:
        form = ClearanceItemReceiptForm()
        template = "student/clearance_item_receipt.html"
    else:
        form = ClearanceItemCheckboxForm()
        template = "student/clearance_item_checkbox.html"

    exc_config = get_department_exception_config(item.department.code)

    if form.validate_on_submit():
        if item.has_debt:
            filename = save_receipt_file(form.receipt.data, current_user.reg_number)
            item.receipt_filename = filename
        else:
            item.checkbox_confirmed = True

        item.status = "pending"
        item.submitted_at = datetime.utcnow()
        item.rejection_reason = None
        db.session.commit()

        if req.status == "draft":
            req.status = "submitted"
            req.submitted_at = datetime.utcnow()
            db.session.commit()
            notify_user(
                current_user,
                f"Your clearance file is active. Tracking reference code #{req.tracking_code}.",
                link=url_for("student.dashboard"),
                email_subject="IUIU Clearance: Submission Received",
            )

        notify_department_admins(
            item.department_id,
            f"New pending clearance folder waiting for audit from student {current_user.reg_number}.",
            link=url_for("admin.queue"),
        )
        flash(f"Submitted to {item.department.name} for review.", "success")
        return redirect(url_for("student.dashboard"))

    return render_template(template, form=form, item=item, exc_config=exc_config)


@student_bp.route("/profile", methods=["GET", "POST"])
def profile():
    form = ProfileUpdateForm(obj=current_user)
    if request.method == "GET":
        form.name.data = current_user.name
        form.phone.data = current_user.phone

    if form.validate_on_submit():
        current_user.name = form.name.data.strip()
        current_user.phone = form.phone.data
        if form.profile_photo.data:
            filename = save_profile_photo(form.profile_photo.data, current_user.reg_number)
            current_user.profile_photo = filename
        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("student.profile"))

    pwd_form = ChangePasswordForm()
    return render_template("student/profile.html", form=form, pwd_form=pwd_form)


@student_bp.route("/profile/password", methods=["POST"])
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("Current password is incorrect.", "danger")
        else:
            current_user.set_password(form.new_password.data)
            db.session.commit()
            flash("Password changed successfully.", "success")
    else:
        for errors in form.errors.values():
            for e in errors:
                flash(e, "danger")
    return redirect(url_for("student.profile"))


@student_bp.route("/certificate/<int:request_id>")
def certificate(request_id):
    req = ClearanceRequest.query.get_or_404(request_id)
    if req.student_id != current_user.id:
        abort(403)
    if not check_request_fully_cleared(req):
        flash("Your certificate will be available once all 5 departments approve your clearance.", "info")
        return redirect(url_for("student.dashboard"))

    if not req.certificate_generated or not req.certificate_filename:
        if not req.verification_code:
            req.verification_code = make_verification_code()
            db.session.commit()

        verify_url = url_for("main.verify_certificate", code=req.verification_code, _external=True)

        departments_status = [
            {"name": item.department.name, "status": item.status}
            for item in sorted(req.items, key=lambda i: i.department.order_index)
        ]
        pdf_bytes = generate_certificate_pdf_bytes(current_user, req, departments_status, verify_url)
        stored_ref = save_certificate_pdf(pdf_bytes, req.tracking_code)

        req.certificate_generated = True
        req.certificate_filename = stored_ref
        db.session.commit()

    return render_template("student/certificate.html", request_obj=req)


@student_bp.route("/certificate/<int:request_id>/download")
def download_certificate(request_id):
    req = ClearanceRequest.query.get_or_404(request_id)
    if req.student_id != current_user.id:
        abort(403)
    if not req.certificate_generated:
        abort(404)

    if is_remote_url(req.certificate_filename):
        return redirect(req.certificate_filename)

    from flask import current_app
    cert_dir = os.path.abspath(os.path.join(current_app.config["UPLOAD_FOLDER"], "..", "certificates"))
    return send_from_directory(cert_dir, req.certificate_filename, as_attachment=True)

