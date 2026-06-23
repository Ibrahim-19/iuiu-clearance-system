import os
from flask import Flask, render_template

from config import Config
from app.extensions import db, login_manager, mail, csrf


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    os.makedirs(os.path.join(app.root_path, "..", "instance"), exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)

    # Cloudinary handles persistent file storage (receipts, profile photos,
    # certificates) since Render's free-tier disk is wiped on every
    # redeploy/restart. If unset, save_*() helpers in app/utils.py
    # transparently fall back to local disk storage for local development.
    if app.config.get("CLOUDINARY_CLOUD_NAME"):
        import cloudinary
        cloudinary.config(
            cloud_name=app.config["CLOUDINARY_CLOUD_NAME"],
            api_key=app.config["CLOUDINARY_API_KEY"],
            api_secret=app.config["CLOUDINARY_API_SECRET"],
            secure=True,
        )

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Blueprints
    from app.auth.routes import auth_bp
    from app.main.routes import main_bp
    from app.student.routes import student_bp
    from app.admin.routes import admin_bp
    from app.registrar.routes import registrar_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(main_bp)
    app.register_blueprint(student_bp, url_prefix="/student")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(registrar_bp, url_prefix="/registrar")

    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        from datetime import datetime
        return {
            "site_name": app.config["SITE_NAME"],
            "current_user_obj": current_user,
            "current_year": datetime.utcnow().year,
        }

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500

    with app.app_context():
        db.create_all()
        _patch_missing_columns(app)
        _seed_departments(app)

        # Auto-seed Registrar + department admin accounts on every boot.
        # This is what makes the app usable on Render's free tier, where
        # there's no shell access to run `python seed.py` after deploy.
        from app.seed_data import run_seed
        run_seed(create_demo_finalist=app.config.get("SEED_DEMO_DATA", True))

    return app


def _seed_departments(app):
    from app.models import Department
    existing = {d.code for d in Department.query.all()}
    for idx, (code, name, desc) in enumerate(app.config["DEPARTMENTS"]):
        if code not in existing:
            db.session.add(Department(code=code, name=name, description=desc, order_index=idx))
    db.session.commit()


def _patch_missing_columns(app):
    """Safety net for future schema changes.

    Render's free tier has no shell access to run migrations, so if a
    future code update adds a new column to a model, this adds it to the
    live table automatically on next boot instead of crashing with
    "column does not exist". Works on both SQLite (local dev) and
    Postgres (Render). Only ever ADDS columns — never drops or alters
    existing ones, so it's safe to leave running permanently.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    try:
        existing_tables = set(inspector.get_table_names())
    except Exception as exc:  # pragma: no cover
        app.logger.warning("Could not inspect database tables: %s", exc)
        return

    for table in db.metadata.tables.values():
        if table.name not in existing_tables:
            continue  # brand-new table; db.create_all() already handled it
        existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing_cols:
                continue
            try:
                col_type = col.type.compile(db.engine.dialect)
                with db.engine.connect() as conn:
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col_type}'))
                    conn.commit()
                app.logger.info("Patched missing column: %s.%s", table.name, col.name)
            except Exception as exc:  # pragma: no cover
                app.logger.warning("Could not patch column %s.%s: %s", table.name, col.name, exc)
