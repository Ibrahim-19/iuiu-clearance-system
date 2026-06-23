from datetime import datetime

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app.auth import auth_bp
from app.extensions import db
from app.forms import RegistrationForm, LoginForm
from app.models import User
from app.utils import check_finalist_eligibility, notify_user


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = RegistrationForm()
    if form.validate_on_submit():
        reg_number = form.reg_number.data.strip()
        email = form.email.data.strip().lower()

        if User.query.filter_by(email=email).first():
            flash("An account with that Gmail address already exists.", "danger")
            return render_template("auth/register.html", form=form)

        if User.query.filter_by(reg_number=reg_number).first():
            flash("An account with that registration number already exists.", "danger")
            return render_template("auth/register.html", form=form)

        # Step 1 gate: must be on the Registrar's active Finalist list
        eligibility = check_finalist_eligibility(
            reg_number, admission_year=form.admission_year.data, course_type=form.course_type.data
        )
        if not eligibility["allowed"]:
            flash(eligibility["reason"], "danger")
            return render_template("auth/register.html", form=form)

        user = User(
            name=form.name.data.strip(),
            email=email,
            reg_number=reg_number,
            course_type=form.course_type.data,
            course_name=form.course_name.data.strip(),
            admission_year=form.admission_year.data,
            phone=form.phone.data,
            role="student",
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        flash("Account created successfully! You may now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(form.password.data):
            flash("Invalid email or password.", "danger")
            return render_template("auth/login.html", form=form)

        if not user.is_active_account:
            flash("Your account has been deactivated. Contact the Registrar's office.", "danger")
            return render_template("auth/login.html", form=form)

        # Re-check the finalist gate every login for students (Step 1)
        if user.role == "student":
            eligibility = check_finalist_eligibility(
                user.reg_number, admission_year=user.admission_year, course_type=user.course_type
            )
            if not eligibility["allowed"]:
                flash(eligibility["reason"], "danger")
                return render_template("auth/login.html", form=form)

        login_user(user, remember=form.remember.data)
        user.last_login = datetime.utcnow()
        db.session.commit()

        next_page = request.args.get("next")
        return redirect(next_page or url_for("main.dashboard"))

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
