"""Formulário de definição de campo customizado."""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, Optional

from app.models.definicao_campo import ENTIDADES, ROTULO_ENTIDADE, ROTULO_TIPO_CAMPO, TIPOS_CAMPO


class DefinicaoCampoForm(FlaskForm):
    entidade = SelectField(
        "Entidade",
        choices=[(e, ROTULO_ENTIDADE[e]) for e in ENTIDADES],
        validators=[DataRequired()],
    )
    rotulo = StringField("Rótulo", validators=[DataRequired(), Length(max=120)])
    chave = StringField("Chave (identificador)", validators=[Optional(), Length(max=50)])
    tipo = SelectField(
        "Tipo",
        choices=[(t, ROTULO_TIPO_CAMPO[t]) for t in TIPOS_CAMPO],
        validators=[DataRequired()],
    )
    opcoes = TextAreaField("Opções (uma por linha)", validators=[Optional()])
    aplica_a_categoria_id = SelectField(
        "Aplica-se à categoria", coerce=int, validators=[Optional()]
    )
    obrigatorio = BooleanField("Obrigatório")
    ordem = IntegerField("Ordem", default=0)
    ajuda = StringField("Texto de ajuda", validators=[Optional(), Length(max=255)])
    ativo = BooleanField("Ativo", default=True)
    submit = SubmitField("Salvar")

    def categoria_real(self) -> int | None:
        return self.aplica_a_categoria_id.data or None

    def opcoes_lista(self) -> list[str]:
        if not self.opcoes.data:
            return []
        return [linha.strip() for linha in self.opcoes.data.splitlines() if linha.strip()]
