"""Formulário de produto (campos fixos; os customizados são tratados à parte)."""

from __future__ import annotations

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    BooleanField,
    DecimalField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.models.produto import ROTULO_TIPO, TIPOS_CONTROLE, UNIDADES_PADRAO


class ProdutoForm(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired(), Length(max=160)])
    sku = StringField("SKU", validators=[Optional(), Length(max=40)])
    tipo_controle = SelectField(
        "Tipo de controle",
        choices=[(t, ROTULO_TIPO[t]) for t in TIPOS_CONTROLE],
        validators=[DataRequired()],
    )
    categoria_id = SelectField("Categoria", coerce=int, validators=[Optional()])
    unidade = SelectField(
        "Unidade", choices=[(u, u) for u in UNIDADES_PADRAO], validators=[DataRequired()]
    )
    estoque_minimo = DecimalField(
        "Estoque mínimo", validators=[Optional(), NumberRange(min=0)], places=3, default=0
    )
    estoque_maximo = DecimalField(
        "Estoque máximo", validators=[Optional(), NumberRange(min=0)], places=3
    )
    marca = StringField("Marca", validators=[Optional(), Length(max=80)])
    modelo = StringField("Modelo", validators=[Optional(), Length(max=80)])
    valor_unitario_referencia = DecimalField(
        "Valor unitário de referência (R$)", validators=[Optional(), NumberRange(min=0)], places=2
    )
    descricao = TextAreaField("Descrição", validators=[Optional(), Length(max=2000)])
    foto = FileField(
        "Foto",
        validators=[Optional(), FileAllowed(["png", "jpg", "jpeg", "webp"], "Apenas imagens.")],
    )
    ativo = BooleanField("Ativo", default=True)
    submit = SubmitField("Salvar")

    def categoria_real(self) -> int | None:
        return self.categoria_id.data or None
