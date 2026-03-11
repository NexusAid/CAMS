from flask import Blueprint

clubs = Blueprint("clubs", __name__, url_prefix="/clubs")

from . import routes
