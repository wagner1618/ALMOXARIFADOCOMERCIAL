"""Formulários de autenticação."""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length, Optional

SENHA_MIN = 8


class LoginForm(FlaskForm):
    identificador = StringField(
        "Usuário ou e-mail", validators=[DataRequired(message="Informe o usuário.")]
    )
    senha = PasswordField("Senha", validators=[DataRequired(message="Informe a senha.")])
    codigo_2fa = StringField("Código 2FA", validators=[Optional(), Length(min=6, max=8)])
    lembrar = BooleanField("Manter conectado")
    submit = SubmitField("Entrar")


class TrocarSenhaForm(FlaskForm):
    senha_atual = PasswordField("Senha atual", validators=[DataRequired()])
    nova_senha = PasswordField(
        "Nova senha",
        validators=[
            DataRequired(),
            Length(min=SENHA_MIN, message=f"A senha deve ter ao menos {SENHA_MIN} caracteres."),
        ],
    )
    confirmar = PasswordField(
        "Confirmar nova senha",
        validators=[DataRequired(), EqualTo("nova_senha", message="As senhas não conferem.")],
    )
    submit = SubmitField("Alterar senha")
