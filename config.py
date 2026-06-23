import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Central configuration for the IUIU Arua Campus Online Clearance System."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "iuiu-clearance-dev-secret-change-in-production")

    # Render's managed Postgres gives a "postgres://" URL; SQLAlchemy 1.4+/2.x
    # requires "postgresql://". Falls back to local SQLite when unset (local dev).
    _database_url = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(basedir, "instance", "clearance.db")
    )
    if _database_url.startswith("postgres://"):
        _database_url = _database_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Cloudinary handles all persistent file storage (receipts, profile photos,
    # certificates) because Render's free-tier filesystem is ephemeral — any
    # locally saved file is wiped on every redeploy/restart. If these are left
    # unset, the app transparently falls back to local disk storage (handy for
    # local development without a Cloudinary account).
    CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET")

    # File uploads (receipts: bank slips / payment proof) — local-storage fallback only
    UPLOAD_FOLDER = os.path.join(basedir, "app", "static", "uploads", "receipts")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB
    ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}

    # CSV import for finalist whitelist / debt ledger
    ALLOWED_IMPORT_EXTENSIONS = {"csv"}

    # Whether to auto-create the demo finalist whitelist entry on every
    # startup. The Registrar + department admin accounts are always
    # auto-created (idempotently) since Render's free tier has no shell
    # access to run a one-off seed script. Set to "0" once you've loaded
    # your real cohort data, to stop re-checking for the demo entry.
    SEED_DEMO_DATA = os.environ.get("SEED_DEMO_DATA", "1") == "1"

    # Mail (Gmail SMTP works well here, App Password required if 2FA is on)
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@iuiuclearance.local")
    # Default to suppressed (logs to console) so the app runs out of the box
    # without real SMTP credentials. Set MAIL_SUPPRESS_SEND=0 in production.
    MAIL_SUPPRESS_SEND = os.environ.get("MAIL_SUPPRESS_SEND", "1") == "1"

    # Used by the Finalist Eligibility Engine (admission_year + course duration)
    CURRENT_ACADEMIC_YEAR = int(os.environ.get("CURRENT_ACADEMIC_YEAR", 2026))

    # The 5 campus clearance offices, in workflow order
    DEPARTMENTS = [
        ("faculty_dean", "Faculty Dean / HOD", "Checks academic marks and course completion"),
        ("bursar", "University Bursar", "Checks tuition and graduation fees"),
        ("library", "University Library", "Checks for unreturned books and fines"),
        ("dean_of_students", "Dean of Students", "Checks conduct and disciplinary records"),
        ("ict", "ICT / MIS Department", "Checks student ID cards and system records"),
    ]

    # Course duration matrix used for the Autonomous Finalist Status Calculation
    COURSE_DURATIONS = {
        "certificate": 2,
        "diploma": 2,
        "bachelors": 3,
        "llb": 4,
    }

    COURSE_LABELS = {
        "certificate": "Certificate",
        "diploma": "Diploma",
        "bachelors": "Bachelor's Degree",
        "llb": "Bachelor of Laws (LLB)",
    }

    # Each office has a different kind of "blocker" that forces a receipt
    # upload instead of a simple checkbox. Only Bursar and Library deal in
    # money; the others deal in academic, disciplinary, or equipment issues.
    DEPARTMENT_EXCEPTION_CONFIG = {
        "faculty_dean": {
            "is_monetary": False,
            "noun": "Academic / Clearance Issue",
            "example": "e.g. incomplete coursework, missing project submission, unresolved retake",
            "evidence_label": "Upload Proof of Resolution (e.g. signed clearance note, retake result)",
        },
        "bursar": {
            "is_monetary": True,
            "noun": "Outstanding Balance",
            "example": "e.g. tuition balance, graduation fee",
            "evidence_label": "Upload Payment Receipt (bank slip / proof of payment)",
        },
        "library": {
            "is_monetary": True,
            "noun": "Library Fine / Unreturned Book",
            "example": "e.g. overdue fine, lost or unreturned book",
            "evidence_label": "Upload Payment Receipt or Book Return Slip",
        },
        "dean_of_students": {
            "is_monetary": False,
            "noun": "Disciplinary / Conduct Issue",
            "example": "e.g. pending disciplinary case, hostel conduct report",
            "evidence_label": "Upload Proof of Resolution (e.g. signed conduct clearance letter)",
        },
        "ict": {
            "is_monetary": False,
            "noun": "Unreturned Equipment / ID Issue",
            "example": "e.g. unreturned device, lost student ID card",
            "evidence_label": "Upload Proof of Resolution (e.g. equipment return slip, ID replacement receipt)",
        },
    }

    SITE_NAME = "IUIU Arua Campus Online Clearance System for graduating students"
