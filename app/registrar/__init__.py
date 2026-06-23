from flask import Blueprint

registrar_bp = Blueprint("registrar", __name__, template_folder="../templates/registrar")

from app.registrar import routes  # noqa: E402,F401
