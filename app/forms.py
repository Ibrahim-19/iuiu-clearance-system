import re

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, PasswordField, SelectField, IntegerField, BooleanField,
    TextAreaField, SubmitField, FloatField
)
from wtforms.validators import (
    DataRequired, Email, EqualTo, Length, ValidationError, Optional, NumberRange
)

REG_NUMBER_PATTERN = re.compile(r"^\d{3}-\d{6}-\d{5}$")


def reg_number_validator(form, field):
    value = (field.data or "").strip()
    if not REG_NUMBER_PATTERN.match(value):
        raise ValidationError(
            "Registration number must be in the format xxx-xxxxxx-xxxxx (e.g. 220-067432-19874)."
        )


def gmail_only_validator(form, field):
    value = (field.data or "").strip().lower()
    if not value.endswith("@gmail.com"):
        raise ValidationError("Please use a valid Gmail address (must end with @gmail.com).")


class RegistrationForm(FlaskForm):
    name = StringField("Full Name*", validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField(
        "Gmail Address*", validators=[DataRequired(), Email(), gmail_only_validator, Length(max=120)]
    )
    reg_number = StringField(
        "Registration Number*", validators=[DataRequired(), reg_number_validator],
        render_kw={"placeholder": "e.g. 220-067432-19874"}
    )
    course_type = SelectField(
        "Programme Type*",
        choices=[
            ("certificate", "Certificate"),
            ("diploma", "Diploma"),
            ("bachelors", "Bachelor's Degree"),
            ("llb", "Bachelor of Laws (LLB)"),
        ],
        validators=[DataRequired()],
    )
    course_name = StringField("Course / Programme Name*", validators=[DataRequired(), Length(max=150)])
    admission_year = IntegerField(
        "Year of Admission*", validators=[DataRequired(), NumberRange(min=2000, max=2100)]
    )
    phone = StringField("Phone Number*", validators=[Optional(), Length(max=20)])
    password = PasswordField("Password*", validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField(
        "Confirm Password*", validators=[DataRequired(), EqualTo("password", message="Passwords must match.")]
    )
    submit = SubmitField("Create Account")


class LoginForm(FlaskForm):
    email = StringField("Email*", validators=[DataRequired(), Email()])
    password = PasswordField("Password*", validators=[DataRequired()])
    remember = BooleanField("Remember me")
    submit = SubmitField("Log In")


class ProfileUpdateForm(FlaskForm):
    name = StringField("Full Name", validators=[DataRequired(), Length(min=2, max=120)])
    phone = StringField("Phone Number", validators=[Optional(), Length(max=20)])
    profile_photo = FileField(
        "Profile Photo", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png"], "Images only!")]
    )
    submit = SubmitField("Save Changes")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current Password", validators=[DataRequired()])
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(min=6)])
    confirm_new_password = PasswordField(
        "Confirm New Password", validators=[DataRequired(), EqualTo("new_password", message="Passwords must match.")]
    )
    submit = SubmitField("Update Password")


class ClearanceItemCheckboxForm(FlaskForm):
    """Used when a student has NO debt for a department: simple confirmation."""
    confirm = BooleanField("I confirm I have no outstanding obligations with this office", validators=[DataRequired()])
    submit = SubmitField("Confirm")


class ClearanceItemReceiptForm(FlaskForm):
    """Used when a student HAS a debt: must upload proof of payment."""
    receipt = FileField(
        "Upload Payment Receipt (PDF, JPG or PNG)",
        validators=[DataRequired(), FileAllowed(["pdf", "png", "jpg", "jpeg"], "PDF or image files only!")]
    )
    submit = SubmitField("Upload & Submit")


class RejectForm(FlaskForm):
    reason = TextAreaField("Reason for Rejection", validators=[DataRequired(), Length(min=5, max=255)])
    submit = SubmitField("Reject")


class FinalistUploadForm(FlaskForm):
    csv_file = FileField("Finalists Enrollment List (CSV)", validators=[DataRequired(), FileAllowed(["csv"], "CSV files only!")])
    submit = SubmitField("Import Finalist List")


class SingleFinalistForm(FlaskForm):
    reg_number = StringField("Registration Number", validators=[DataRequired(), reg_number_validator])
    student_name = StringField("Student Name", validators=[Optional(), Length(max=120)])
    course_type = SelectField(
        "Programme Type",
        choices=[("certificate", "Certificate"), ("diploma", "Diploma"),
                  ("bachelors", "Bachelor's Degree"), ("llb", "Bachelor of Laws (LLB)")],
        validators=[Optional()],
    )
    admission_year = IntegerField("Year of Admission", validators=[Optional(), NumberRange(min=2000, max=2100)])
    submit = SubmitField("Add to Finalist List")


class DebtUploadForm(FlaskForm):
    csv_file = FileField("Debt Ledger (CSV)", validators=[DataRequired(), FileAllowed(["csv"], "CSV files only!")])
    submit = SubmitField("Import Debt Ledger")


class SingleDebtForm(FlaskForm):
    reg_number = StringField("Registration Number", validators=[DataRequired(), reg_number_validator])
    amount = FloatField("Amount Owed (UGX)", validators=[Optional(), NumberRange(min=0)])
    reason = StringField("Reason / Description", validators=[DataRequired(), Length(max=255)])
    submit = SubmitField("Add Record")


class CreateAdminForm(FlaskForm):
    name = StringField("Full Name", validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField(
        "Gmail Address", validators=[DataRequired(), Email(), gmail_only_validator, Length(max=120)]
    )
    department_id = SelectField("Department", coerce=int, validators=[DataRequired()])
    password = PasswordField("Temporary Password", validators=[DataRequired(), Length(min=6)])
    submit = SubmitField("Create Department Admin")


class SearchFilterForm(FlaskForm):
    """Simple GET-based search/filter bar shared by admin & registrar dashboards."""
    q = StringField("Search", validators=[Optional(), Length(max=120)])
    status = SelectField(
        "Status",
        choices=[("", "All Statuses"), ("not_submitted", "Not Submitted"), ("pending", "Pending"),
                  ("approved", "Approved"), ("rejected", "Rejected")],
        validators=[Optional()],
    )
    submit = SubmitField("Filter")
