"""Formulário de abertura de inventário (§8). A contagem é feita item a item na tela."""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Optional

from app.models.inventario import ROTULO_TIPO, TIPOS_INVENTARIO


class AbrirInventarioForm(FlaskForm):
    tipo = SelectField(
        "Tipo",
        choices=[(t, ROTULO_TIPO[t]) for t in TIPOS_INVENTARIO],
        validators=[DataRequired()],
    )
    setor_id = SelectField("Setor", coerce=int, validators=[DataRequired()])
    observacoes = TextAreaField("Observações", validators=[Optional()])
    submit = SubmitField("Abrir inventário")
