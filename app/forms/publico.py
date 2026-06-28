"""Formulários de compras públicas (§7.10).

Os itens de ata e de contrato são linhas dinâmicas tratadas direto na rota
(``request.form.getlist``), no mesmo padrão de pedidos/NF da §7.9.
"""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.models.publico import (
    MODALIDADES,
    REGISTRO_DE_PRECOS,
    ROTULO_ADITIVO,
    ROTULO_MODALIDADE,
    ROTULO_PROCESSO,
    ROTULO_RECEBIMENTO,
    ROTULO_TIPO_EMPENHO,
    SEM_PROCEDIMENTO,
    STATUS_PROCESSO,
    TIPOS_ADITIVO,
    TIPOS_EMPENHO,
    TIPOS_RECEBIMENTO,
)

_DATA = {"type": "date"}


class DotacaoForm(FlaskForm):
    exercicio = IntegerField("Exercício", validators=[Optional(), NumberRange(min=2000, max=2100)])
    descricao = StringField("Descrição", validators=[Optional(), Length(max=160)])
    programa_trabalho = StringField("Programa de trabalho", validators=[Optional(), Length(max=60)])
    natureza_despesa = StringField("Natureza da despesa", validators=[Optional(), Length(max=40)])
    fonte_recurso = StringField("Fonte de recurso", validators=[Optional(), Length(max=40)])
    unidade_orcamentaria = StringField(
        "Unidade orçamentária", validators=[Optional(), Length(max=80)]
    )
    valor_dotado = StringField("Valor dotado (R$)", validators=[DataRequired()])
    submit = SubmitField("Salvar dotação")


class ProcessoForm(FlaskForm):
    numero_processo = StringField("Número do processo", validators=[DataRequired(), Length(max=40)])
    objeto = TextAreaField("Objeto", validators=[DataRequired()])
    modalidade = SelectField(
        "Modalidade",
        choices=[(m, ROTULO_MODALIDADE[m]) for m in MODALIDADES],
        validators=[DataRequired()],
    )
    procedimento_auxiliar = SelectField(
        "Procedimento auxiliar",
        choices=[(SEM_PROCEDIMENTO, "Nenhum"), (REGISTRO_DE_PRECOS, "Registro de preços")],
        validators=[DataRequired()],
    )
    valor_estimado = StringField("Valor estimado (R$)", validators=[Optional()])
    setor_id = SelectField("Setor demandante", coerce=int, validators=[Optional()])
    data_abertura = DateField("Data de abertura", validators=[Optional()], render_kw=_DATA)
    numero_pncp = StringField("Número PNCP", validators=[Optional(), Length(max=60)])
    observacoes = TextAreaField("Observações", validators=[Optional()])
    submit = SubmitField("Salvar processo")


class AtaForm(FlaskForm):
    numero = StringField("Número da ata", validators=[DataRequired(), Length(max=40)])
    fornecedor_id = SelectField("Fornecedor", coerce=int, validators=[DataRequired()])
    processo_id = SelectField("Processo de origem", coerce=int, validators=[Optional()])
    vigencia_inicio = DateField("Início da vigência", validators=[Optional()], render_kw=_DATA)
    vigencia_fim = DateField("Fim da vigência", validators=[Optional()], render_kw=_DATA)
    observacoes = TextAreaField("Observações", validators=[Optional()])
    submit = SubmitField("Salvar ata")


class ContratoForm(FlaskForm):
    numero = StringField("Número do contrato", validators=[DataRequired(), Length(max=40)])
    objeto = TextAreaField("Objeto", validators=[DataRequired()])
    fornecedor_id = SelectField("Fornecedor", coerce=int, validators=[DataRequired()])
    processo_id = SelectField("Processo de origem", coerce=int, validators=[Optional()])
    ata_id = SelectField("Ata de origem", coerce=int, validators=[Optional()])
    vigencia_inicio = DateField("Início da vigência", validators=[Optional()], render_kw=_DATA)
    vigencia_fim = DateField("Fim da vigência", validators=[Optional()], render_kw=_DATA)
    fiscal_id = SelectField("Fiscal", coerce=int, validators=[Optional()])
    gestor_id = SelectField("Gestor", coerce=int, validators=[Optional()])
    garantia = StringField("Garantia", validators=[Optional(), Length(max=120)])
    observacoes = TextAreaField("Observações", validators=[Optional()])
    submit = SubmitField("Salvar contrato")


class AditivoForm(FlaskForm):
    tipo = SelectField(
        "Tipo", choices=[(t, ROTULO_ADITIVO[t]) for t in TIPOS_ADITIVO], validators=[DataRequired()]
    )
    numero = StringField("Número", validators=[Optional(), Length(max=40)])
    valor = StringField("Valor do acréscimo (R$)", validators=[Optional()])
    nova_vigencia = DateField("Nova vigência", validators=[Optional()], render_kw=_DATA)
    descricao = TextAreaField("Descrição", validators=[Optional()])
    submit = SubmitField("Registrar aditivo")


class EmpenhoForm(FlaskForm):
    dotacao_id = SelectField("Dotação orçamentária", coerce=int, validators=[DataRequired()])
    numero = StringField(
        "Número (deixe vazio p/ automático)", validators=[Optional(), Length(max=40)]
    )
    tipo = SelectField(
        "Tipo",
        choices=[(t, ROTULO_TIPO_EMPENHO[t]) for t in TIPOS_EMPENHO],
        validators=[DataRequired()],
    )
    valor = StringField("Valor (R$)", validators=[DataRequired()])
    contrato_id = SelectField("Contrato", coerce=int, validators=[Optional()])
    ata_id = SelectField("Ata", coerce=int, validators=[Optional()])
    processo_id = SelectField("Processo", coerce=int, validators=[Optional()])
    fornecedor_id = SelectField("Fornecedor", coerce=int, validators=[Optional()])
    data = DateField("Data", validators=[Optional()], render_kw=_DATA)
    observacoes = TextAreaField("Observações", validators=[Optional()])
    submit = SubmitField("Emitir empenho")


class RecebimentoForm(FlaskForm):
    tipo = SelectField(
        "Tipo",
        choices=[(t, ROTULO_RECEBIMENTO[t]) for t in TIPOS_RECEBIMENTO],
        validators=[DataRequired()],
    )
    nota_fiscal_id = SelectField("Nota fiscal", coerce=int, validators=[Optional()])
    empenho_id = SelectField("Empenho", coerce=int, validators=[Optional()])
    contrato_id = SelectField("Contrato", coerce=int, validators=[Optional()])
    setor_id = SelectField("Setor", coerce=int, validators=[Optional()])
    data = DateField("Data", validators=[Optional()], render_kw=_DATA)
    conforme = BooleanField("Material conforme", default=True)
    observacoes = TextAreaField("Observações", validators=[Optional()])
    submit = SubmitField("Registrar recebimento")


class LiquidacaoForm(FlaskForm):
    valor = StringField("Valor a liquidar (R$)", validators=[DataRequired()])
    nota_fiscal_id = SelectField("Nota fiscal", coerce=int, validators=[Optional()])
    recebimento_id = SelectField("Recebimento definitivo", coerce=int, validators=[Optional()])
    observacoes = TextAreaField("Observações", validators=[Optional()])
    submit = SubmitField("Liquidar")


class PagamentoForm(FlaskForm):
    valor = StringField("Valor (R$)", validators=[DataRequired()])
    ordem_bancaria = StringField("Ordem bancária", validators=[Optional(), Length(max=60)])
    data = DateField("Data", validators=[Optional()], render_kw=_DATA)
    observacoes = TextAreaField("Observações", validators=[Optional()])
    submit = SubmitField("Registrar pagamento")


# Reexport para a rota montar filtros de status sem reimportar do modelo.
STATUS_PROCESSO_CHOICES = [(s, ROTULO_PROCESSO[s]) for s in STATUS_PROCESSO]
