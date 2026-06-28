"""Rotas de autenticação: login, logout, troca de senha obrigatória."""

from __future__ import annotations

from datetime import UTC, datetime

import pyotp
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_, select

from app.extensions import db, limiter
from app.forms.auth import LoginForm, TrocarSenhaForm
from app.models.usuario import Usuario
from app.security.auditoria import registrar

bp = Blueprint("auth", __name__)


def _autenticar(identificador: str) -> Usuario | None:
    """Busca usuário ativo por username ou e-mail (case-insensitive)."""
    ident = identificador.strip().lower()
    stmt = select(Usuario).where(
        or_(
            db.func.lower(Usuario.username) == ident,
            db.func.lower(Usuario.email) == ident,
        )
    )
    return db.session.scalars(stmt).first()


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        usuario = _autenticar(form.identificador.data)
        if usuario is None or not usuario.verificar_senha(form.senha.data):
            registrar(
                "login.falha", entidade="usuario", dados_depois={"id": form.identificador.data}
            )
            db.session.commit()
            flash("Usuário ou senha inválidos.", "danger")
            return render_template("auth/login.html", form=form), 401

        if not usuario.ativo:
            flash("Usuário inativo. Procure o administrador.", "danger")
            return render_template("auth/login.html", form=form), 403

        # Segundo fator (TOTP), se configurado.
        if usuario.tem_2fa:
            codigo = (form.codigo_2fa.data or "").strip()
            if not codigo:
                flash("Informe o código de autenticação (2FA).", "warning")
                return render_template("auth/login.html", form=form, exige_2fa=True)
            if not pyotp.TOTP(usuario.totp_secret).verify(codigo, valid_window=1):
                registrar("login.2fa_invalido", entidade="usuario", entidade_id=usuario.id)
                db.session.commit()
                flash("Código 2FA inválido.", "danger")
                return render_template("auth/login.html", form=form, exige_2fa=True), 401

        login_user(usuario, remember=form.lembrar.data)
        usuario.ultimo_acesso = datetime.now(UTC)
        registrar("login.sucesso", entidade="usuario", entidade_id=usuario.id)
        db.session.commit()

        if usuario.deve_trocar_senha:
            flash("Por segurança, defina uma nova senha.", "info")
            return redirect(url_for("auth.trocar_senha"))

        destino = request.args.get("next") or url_for("main.dashboard")
        return redirect(destino)

    return render_template("auth/login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    registrar("logout", entidade="usuario", entidade_id=current_user.id)
    db.session.commit()
    logout_user()
    flash("Sessão encerrada.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/trocar-senha", methods=["GET", "POST"])
@login_required
def trocar_senha():
    form = TrocarSenhaForm()
    if form.validate_on_submit():
        if not current_user.verificar_senha(form.senha_atual.data):
            flash("Senha atual incorreta.", "danger")
            return render_template("auth/trocar_senha.html", form=form), 400
        current_user.definir_senha(form.nova_senha.data)
        current_user.deve_trocar_senha = False
        registrar("senha.alterada", entidade="usuario", entidade_id=current_user.id)
        db.session.commit()
        flash("Senha alterada com sucesso.", "success")
        return redirect(url_for("main.dashboard"))
    return render_template("auth/trocar_senha.html", form=form)
