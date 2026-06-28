"""Instâncias únicas das extensões Flask.

Mantidas isoladas do app factory para evitar import circular: os módulos de
modelos e serviços importam daqui, e o factory chama ``.init_app(app)``.
"""

from __future__ import annotations

from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base declarativa do SQLAlchemy 2.x para todos os modelos."""


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
cache = Cache()
mail = Mail()
limiter = Limiter(key_func=get_remote_address, default_limits=[])

# Configuração do Flask-Login
login_manager.login_view = "auth.login"
login_manager.login_message = "Faça login para acessar esta página."
login_manager.login_message_category = "warning"
login_manager.session_protection = "strong"
