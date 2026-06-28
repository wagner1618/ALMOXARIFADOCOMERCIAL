"""Formulário de empréstimo (§7.5). O item é consumível (produto+qtd) ou durável (ativo)."""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, Optional

TIPO_CONSUMIVEL = "CONSUMIVEL"
TIPO_DURAVEL = "DURAVEL"


class EmprestimoForm(FlaskForm):
    tipo = SelectField(
        "Tipo de item",
        choices=[
            (TIPO_CONSUMIVEL, "Consumível (por quantidade)"),
            (TIPO_DURAVEL, "Durável (ativo)"),
        ],
        validators=[DataRequired()],
    )
    produto_id = SelectField("Produto consumível", coerce=int, validators=[Optional()])
    quantidade = StringField("Quantidade", validators=[Optional()], default="1")
    ativo_id = SelectField("Ativo durável", coerce=int, validators=[Optional()])
    setor_id = SelectField("Setor de origem", coerce=int, validators=[Optional()])
    destinatario = StringField("Destinatário", validators=[Optional(), Length(max=160)])
    responsavel_id = SelectField("Responsável", coerce=int, validators=[Optional()])
    data_prevista = DateField(
        "Devolução prevista", validators=[Optional()], render_kw={"type": "date"}
    )
    observacoes = TextAreaField("Observações", validators=[Optional()])
    submit = SubmitField("Registrar empréstimo")
