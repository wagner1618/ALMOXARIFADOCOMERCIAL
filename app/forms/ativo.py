"""Formulários de ativos (patrimônio)."""

from __future__ import annotations

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    DateField,
    DecimalField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.models.ativo import ESTADOS_CONSERVACAO, ROTULO_ESTADO


class AtivoForm(FlaskForm):
    nome = StringField("Nome/descrição", validators=[DataRequired(), Length(max=160)])
    produto_id = SelectField("Produto (modelo de catálogo)", coerce=int, validators=[Optional()])
    tombamento = StringField("Tombamento", validators=[Optional(), Length(max=60)])
    numero_serie = StringField("Número de série", validators=[Optional(), Length(max=80)])
    marca = StringField("Marca", validators=[Optional(), Length(max=80)])
    modelo = StringField("Modelo", validators=[Optional(), Length(max=80)])
    fornecedor = StringField("Fornecedor", validators=[Optional(), Length(max=160)])

    data_aquisicao = DateField(
        "Data de aquisição", validators=[Optional()], render_kw={"type": "date"}
    )
    valor_aquisicao = DecimalField(
        "Valor de aquisição (R$)", validators=[Optional(), NumberRange(min=0)], places=2
    )
    garantia_ate = DateField("Garantia até", validators=[Optional()], render_kw={"type": "date"})
    vida_util_meses = IntegerField("Vida útil (meses)", validators=[Optional(), NumberRange(min=0)])
    valor_residual = DecimalField(
        "Valor residual (R$)", validators=[Optional(), NumberRange(min=0)], places=2
    )

    estado_conservacao = SelectField(
        "Estado de conservação",
        choices=[(e, ROTULO_ESTADO[e]) for e in ESTADOS_CONSERVACAO],
        validators=[DataRequired()],
    )
    setor_atual_id = SelectField("Setor atual", coerce=int, validators=[DataRequired()])
    observacoes = TextAreaField("Observações", validators=[Optional()])
    foto = FileField("Foto", validators=[Optional(), FileAllowed(["png", "jpg", "jpeg", "webp"])])
    submit = SubmitField("Salvar")

    def produto_real(self) -> int | None:
        return self.produto_id.data or None


class DestinarForm(FlaskForm):
    setor_id = SelectField("Setor de destino", coerce=int, validators=[DataRequired()])
    responsavel_id = SelectField("Responsável", coerce=int, validators=[Optional()])
    submit = SubmitField("Destinar (gerar termo)")


class RecertificarForm(FlaskForm):
    estado_conservacao = SelectField(
        "Estado de conservação",
        choices=[(e, ROTULO_ESTADO[e]) for e in ESTADOS_CONSERVACAO],
        validators=[DataRequired()],
    )
    meses_proxima = IntegerField(
        "Próxima revisão em (meses)",
        default=12,
        validators=[Optional(), NumberRange(min=1, max=120)],
    )
    submit = SubmitField("Registrar recertificação")
