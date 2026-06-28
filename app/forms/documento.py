"""Formulário de edição de ModeloDocumento (template HTML/Jinja por tipo, §7.7)."""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length


class ModeloDocumentoForm(FlaskForm):
    nome = StringField("Nome do modelo", validators=[DataRequired(), Length(max=120)])
    conteudo_html = TextAreaField(
        "Conteúdo (HTML + Jinja)",
        validators=[DataRequired()],
        render_kw={"rows": 20, "spellcheck": "false", "style": "font-family:monospace"},
    )
    ativo = BooleanField("Ativo", default=True)
    submit = SubmitField("Salvar modelo")
