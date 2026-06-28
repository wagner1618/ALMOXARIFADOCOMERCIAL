"""Formulários dos cadastros base: setor, categoria, localização, visibilidade."""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DecimalField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class SetorForm(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired(), Length(max=120)])
    codigo = StringField("Código", validators=[Optional(), Length(max=40)])
    setor_pai_id = SelectField("Setor pai", coerce=int, validators=[Optional()])
    poder_compra = BooleanField("Pode realizar compras")
    centro_custo = StringField("Centro de custo", validators=[Optional(), Length(max=40)])
    orcamento_anual = DecimalField(
        "Orçamento anual (R$)", validators=[Optional(), NumberRange(min=0)], places=2
    )
    permite_visualizacao_externa = BooleanField("Permite visualização externa do estoque")
    ativo = BooleanField("Ativo", default=True)
    submit = SubmitField("Salvar")

    # 0 representa "sem pai" (setor raiz).
    def setor_pai_real(self) -> int | None:
        return self.setor_pai_id.data or None


class CategoriaForm(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired(), Length(max=80)])
    descricao = TextAreaField("Descrição", validators=[Optional(), Length(max=255)])
    ativo = BooleanField("Ativo", default=True)
    submit = SubmitField("Salvar")


class LocalizacaoForm(FlaskForm):
    setor_id = SelectField("Setor", coerce=int, validators=[DataRequired()])
    nome = StringField("Nome", validators=[DataRequired(), Length(max=80)])
    descricao = TextAreaField("Descrição", validators=[Optional(), Length(max=255)])
    ativo = BooleanField("Ativo", default=True)
    submit = SubmitField("Salvar")


class RegraVisibilidadeForm(FlaskForm):
    setor_observador_id = SelectField(
        "Setor que visualiza", coerce=int, validators=[DataRequired()]
    )
    setor_alvo_id = SelectField("Estoque visível", coerce=int, validators=[DataRequired()])
    inclui_subarvore = BooleanField("Incluir a subárvore do setor alvo", default=True)
    submit = SubmitField("Adicionar regra")
