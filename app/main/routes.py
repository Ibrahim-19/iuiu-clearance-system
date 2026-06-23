from flask import render_template, redirect, url_for, jsonify
from flask_login import login_required, current_user

from app.main import main_bp
from app.extensions import db
from app.models import Notification


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return render_template("index.html")


@main_bp.route("/dashboard")
@login_required
def dashboard():
    if current_user.is_student:
        return redirect(url_for("student.dashboard"))
    if current_user.is_admin:
        return redirect(url_for("admin.dashboard"))
    if current_user.is_registrar:
        return redirect(url_for("registrar.dashboard"))
    return redirect(url_for("auth.login"))


@main_bp.route("/notifications")
@login_required
def notifications():
    items = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template("notifications.html", notifications=items)


@main_bp.route("/notifications/mark-read/<int:note_id>", methods=["POST"])
@login_required
def mark_notification_read(note_id):
    note = Notification.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    note.is_read = True
    db.session.commit()
    return jsonify({"ok": True})


@main_bp.route("/notifications/mark-all-read", methods=["POST"])
@login_required
def mark_all_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"ok": True})


@main_bp.route("/verify/<code>")
def verify_certificate(code):
    """Public verification page for the QR-code fraud-protection feature.
    No login required so an employer can scan and verify instantly."""
    from app.models import ClearanceRequest
    req = ClearanceRequest.query.filter_by(verification_code=code).first()
    valid = bool(req and req.status == "fully_cleared")
    return render_template("verify.html", request_obj=req, valid=valid)


@main_bp.route("/notifications/poll")
@login_required
def poll_notifications():
    """Lightweight JSON endpoint the navbar JS polls for the unread badge."""
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({"unread": count})
