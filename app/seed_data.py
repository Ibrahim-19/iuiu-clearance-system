"""Idempotent initial-data seeding, safe to call on every app startup.

This exists as its own module (rather than living only in the root
seed.py CLI script) so that app/__init__.py can call it automatically
every time the app boots — which matters on Render's free tier, where
there's no shell access to run a one-off script after deploy.

Calling run_seed() repeatedly is always safe: every insert is guarded by
an existence check first.
"""
from app.extensions import db
from app.models import User, Department, FinalistWhitelist

REGISTRAR_EMAIL = "iuiu.registrar@gmail.com"
REGISTRAR_PASSWORD = "ChangeMe123!"

ADMIN_PASSWORD = "Admin123!"
ADMIN_EMAILS = {
    "faculty_dean": "iuiu.facultydean@gmail.com",
    "bursar": "iuiu.bursar@gmail.com",
    "library": "iuiu.library@gmail.com",
    "dean_of_students": "iuiu.deanofstudents@gmail.com",
    "ict": "iuiu.ict@gmail.com",
}

DEMO_FINALIST_REG = "220-067432-19874"


def run_seed(create_demo_finalist=True, verbose=True):
    """Create the Registrar + 5 department admin accounts if they don't
    already exist, plus (optionally) one demo finalist whitelist entry.

    Must be called inside an active app context.
    """
    lines = []

    if not User.query.filter_by(email=REGISTRAR_EMAIL).first():
        registrar = User(name="Academic Registrar", email=REGISTRAR_EMAIL, role="registrar")
        registrar.set_password(REGISTRAR_PASSWORD)
        db.session.add(registrar)
        db.session.commit()
        lines.append(f"Created Registrar account: {REGISTRAR_EMAIL} / {REGISTRAR_PASSWORD}")

    for dept in Department.query.order_by(Department.order_index).all():
        email = ADMIN_EMAILS.get(dept.code)
        if not email:
            continue
        if not User.query.filter_by(email=email).first():
            admin = User(
                name=f"{dept.name} Admin",
                email=email,
                role="admin",
                department_id=dept.id,
            )
            admin.set_password(ADMIN_PASSWORD)
            db.session.add(admin)
            db.session.commit()
            lines.append(f"Created department admin: {email} / {ADMIN_PASSWORD}  ({dept.name})")

    if create_demo_finalist and not FinalistWhitelist.query.filter_by(reg_number=DEMO_FINALIST_REG).first():
        db.session.add(FinalistWhitelist(
            reg_number=DEMO_FINALIST_REG,
            student_name="Demo Student",
            course_type="bachelors",
            admission_year=2023,
            added_by="seed script",
        ))
        db.session.commit()
        lines.append(f"Added demo finalist whitelist entry: {DEMO_FINALIST_REG}")

    if verbose:
        for line in lines:
            print(line)

    return lines
