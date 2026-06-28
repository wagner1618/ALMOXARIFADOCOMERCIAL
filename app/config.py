"""Configuração por ambiente, lida de variáveis de ambiente.

Em desenvolvimento, se ``DATABASE_URL`` não estiver definida, cai para um banco
SQLite local — permitindo rodar o sistema sem subir PostgreSQL/Docker.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "sim"}


class Config:
    """Configuração base, compartilhada por todos os ambientes."""

    APP_NAME = os.getenv("APP_NAME", "Almoxarifado")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-inseguro-troque-em-producao")

    # SQLAlchemy
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS: ClassVar[dict] = {"pool_pre_ping": True}

    # Sessão / cookies seguros
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12  # 12 horas

    # CSRF
    WTF_CSRF_TIME_LIMIT = None  # validade da sessão

    # Uploads
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB
    UPLOAD_DIR = str(BASE_DIR / "app" / "static" / "uploads")

    # Cache / rate limit
    CACHE_TYPE = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT = 300
    RATELIMIT_STORAGE_URI = "memory://"

    # Localização
    BABEL_DEFAULT_LOCALE = "pt_BR"
    BABEL_DEFAULT_TIMEZONE = "America/Sao_Paulo"

    # Segurança
    FORCE_HTTPS = _bool(os.getenv("FORCE_HTTPS"), default=False)
    SENTRY_DSN = os.getenv("SENTRY_DSN") or None

    # E-mail
    MAIL_SERVER = os.getenv("MAIL_SERVER") or None
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = _bool(os.getenv("MAIL_USE_TLS"), default=True)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME") or None
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD") or None
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "nao-responder@exemplo.com.br")

    @staticmethod
    def _redis_backed(app_config: type[Config]) -> None:
        """Liga Redis para cache/rate-limit se REDIS_URL estiver definida."""
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            app_config.CACHE_TYPE = "RedisCache"
            app_config.CACHE_REDIS_URL = redis_url  # type: ignore[attr-defined]
            app_config.RATELIMIT_STORAGE_URI = redis_url


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or (
        f"sqlite:///{INSTANCE_DIR / 'almoxarifado.sqlite3'}"
    )


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite://")  # em memória
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "")
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    FORCE_HTTPS = _bool(os.getenv("FORCE_HTTPS"), default=True)


_CONFIGS: dict[str, type[Config]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    """Resolve a classe de configuração pelo nome (ou FLASK_ENV)."""
    env = (name or os.getenv("FLASK_ENV") or "development").lower()
    config = _CONFIGS.get(env, DevelopmentConfig)
    config._redis_backed(config)
    return config
