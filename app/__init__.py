"""Application factory."""

from __future__ import annotations

import logging
import os
from logging.config import dictConfig
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for
from flask_login import current_user

from app.config import INSTANCE_DIR, get_config
from app.extensions import cache, csrf, db, limiter, login_manager, mail, migrate


def create_app(config_name: str | None = None) -> Flask:
    _configurar_logging()

    app = Flask(__name__, instance_path=str(INSTANCE_DIR))
    app.config.from_object(get_config(config_name))

    _garantir_diretorios(app)
    _init_extensions(app)
    _registrar_user_loader()
    _registrar_blueprints(app)
    _registrar_error_handlers(app)
    _registrar_context(app)
    _registrar_filtros(app)
    _registrar_hooks(app)
    _configurar_seguranca(app)

    app.logger.info(
        "Aplicação iniciada (env=%s)", config_name or os.getenv("FLASK_ENV", "development")
    )
    return app


# --------------------------------------------------------------------------- #
# Inicializadores
# --------------------------------------------------------------------------- #
def _garantir_diretorios(app: Flask) -> None:
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db, directory=str(Path(app.root_path).parent / "migrations"))
    login_manager.init_app(app)
    csrf.init_app(app)
    cache.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)

    # Registra os comandos de CLI (criar-org, criar-admin, seed, ...).
    from app import cli

    cli.register(app)


def _registrar_user_loader() -> None:
    from app.models.usuario import Usuario

    @login_manager.user_loader
    def carregar_usuario(user_id: str):
        return db.session.get(Usuario, int(user_id))


def _registrar_blueprints(app: Flask) -> None:
    from app.routes import register_blueprints

    register_blueprints(app)


def _registrar_error_handlers(app: Flask) -> None:
    @app.errorhandler(403)
    def proibido(e):
        return render_template(
            "errors/erro.html",
            codigo=403,
            titulo="Acesso negado",
            mensagem="Você não tem permissão para acessar este recurso.",
        ), 403

    @app.errorhandler(404)
    def nao_encontrado(e):
        return render_template(
            "errors/erro.html",
            codigo=404,
            titulo="Página não encontrada",
            mensagem="O recurso solicitado não existe.",
        ), 404

    @app.errorhandler(429)
    def muitas_requisicoes(e):
        return render_template(
            "errors/erro.html",
            codigo=429,
            titulo="Muitas tentativas",
            mensagem="Aguarde um momento antes de tentar novamente.",
        ), 429

    @app.errorhandler(500)
    def erro_interno(e):  # pragma: no cover
        app.logger.exception("Erro interno não tratado")
        return render_template(
            "errors/erro.html",
            codigo=500,
            titulo="Erro interno",
            mensagem="Algo deu errado. A equipe foi notificada.",
        ), 500


def _registrar_context(app: Flask) -> None:
    @app.context_processor
    def injetar_contexto():
        org = getattr(current_user, "organizacao", None) if current_user.is_authenticated else None
        return {
            "app_name": app.config["APP_NAME"],
            "organizacao_atual": org,
            "marca": {
                "nome": getattr(org, "nome", None) or app.config["APP_NAME"],
                "logo": getattr(org, "logo", None),
                "cor_primaria": getattr(org, "cor_primaria", "#0d6efd"),
                "cor_secundaria": getattr(org, "cor_secundaria", "#6c757d"),
            },
        }


def _registrar_filtros(app: Flask) -> None:
    from app.utils.formatacao import (
        formatar_data,
        formatar_datahora,
        formatar_moeda,
        formatar_numero,
    )

    app.jinja_env.filters["data"] = formatar_data
    app.jinja_env.filters["datahora"] = formatar_datahora
    app.jinja_env.filters["moeda"] = formatar_moeda
    app.jinja_env.filters["numero"] = formatar_numero

    def endpoint_existe(nome: str) -> bool:
        return nome in app.view_functions

    app.jinja_env.globals["endpoint_existe"] = endpoint_existe

    # Helpers para renderizar campos customizados nos templates.
    from app.services import campos_customizados as cc

    app.jinja_env.globals["cc_nome"] = cc.nome_campo
    app.jinja_env.globals["cc_valor_input"] = cc.valor_para_input
    app.jinja_env.globals["cc_formatar"] = cc.formatar_valor


def _registrar_hooks(app: Flask) -> None:
    @app.before_request
    def forcar_troca_senha():
        """Bloqueia o uso do sistema até o usuário trocar a senha inicial."""
        if not current_user.is_authenticated or not getattr(
            current_user, "deve_trocar_senha", False
        ):
            return None
        permitido = {"auth.trocar_senha", "auth.logout", "main.healthz", "static"}
        if request.endpoint not in permitido:
            return redirect(url_for("auth.trocar_senha"))
        return None


def _configurar_seguranca(app: Flask) -> None:
    """Headers de segurança (CSP, HSTS, etc.) via Talisman."""
    from flask_talisman import Talisman

    # CSP permissiva o suficiente para Bootstrap/HTMX/Alpine servidos localmente
    # e ícones via data:. Endurecer conforme os assets forem empacotados.
    csp = {
        "default-src": "'self'",
        "script-src": ["'self'", "'unsafe-inline'", "'unsafe-eval'"],
        "style-src": ["'self'", "'unsafe-inline'"],
        "img-src": ["'self'", "data:"],
        "font-src": ["'self'", "data:"],
    }
    Talisman(
        app,
        force_https=app.config.get("FORCE_HTTPS", False),
        strict_transport_security=app.config.get("FORCE_HTTPS", False),
        session_cookie_secure=app.config.get("FORCE_HTTPS", False),
        content_security_policy=csp,
        frame_options="DENY",
    )


def _configurar_logging() -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "padrao": {
                    "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "padrao",
                    "level": logging.INFO,
                }
            },
            "root": {"level": logging.INFO, "handlers": ["console"]},
        }
    )
