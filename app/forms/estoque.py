"""Formulários de movimentação de estoque (entrada/saída)."""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import (
    DecimalField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, NumberRange, Optional


class _MovBase(FlaskForm):
    produto_id = SelectField("Produto", coerce=int, validators=[DataRequired()])
    setor_id = SelectField("Setor", coerce=int, validators=[DataRequired()])
    quantidade = DecimalField(
        "Quantidade",
        validators=[DataRequired(), NumberRange(min=0.001, message="Informe uma quantidade.")],
        places=3,
    )
    observacoes = TextAreaField("Observações", validators=[Optional()])


class EntradaForm(_MovBase):
    valor_unitario = DecimalField(
        "Valor unitário (R$)", validators=[Optional(), NumberRange(min=0)], places=4
    )
    submit = SubmitField("Registrar entrada")


class SaidaForm(_MovBase):
    destinatario = StringField("Destinatário", validators=[Optional()])
    submit = SubmitField("Registrar saída")


class AjusteForm(FlaskForm):
    nova_quantidade = DecimalField(
        "Quantidade contada", validators=[DataRequired(), NumberRange(min=0)], places=3
    )
    justificativa = TextAreaField("Justificativa", validators=[DataRequired()])
    submit = SubmitField("Ajustar saldo")
