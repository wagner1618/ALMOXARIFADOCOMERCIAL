"""Formulários de compras: fornecedor, pedido e nota fiscal (§7.9).

Os itens (de pedido e de NF) são linhas dinâmicas tratadas direto na rota
(``request.form.getlist``), no mesmo padrão do lançamento em lote de estoque.
"""

from __future__ import annotations

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    DateField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, Optional

from app.models.fornecedor import ROTULO_PESSOA, TIPOS_PESSOA


class FornecedorForm(FlaskForm):
    nome = StringField("Nome/razão social", validators=[DataRequired(), Length(max=160)])
    tipo_pessoa = SelectField(
        "Tipo", choices=[(t, ROTULO_PESSOA[t]) for t in TIPOS_PESSOA], validators=[DataRequired()]
    )
    documento = StringField("CNPJ/CPF", validators=[Optional(), Length(max=20)])
    inscricao_estadual = StringField("Inscrição estadual", validators=[Optional(), Length(max=30)])
    contato = StringField("Pessoa de contato", validators=[Optional(), Length(max=120)])
    email = StringField("E-mail", validators=[Optional(), Length(max=160)])
    telefone = StringField("Telefone", validators=[Optional(), Length(max=40)])
    endereco = StringField("Endereço", validators=[Optional(), Length(max=255)])
    observacoes = TextAreaField("Observações", validators=[Optional()])
    submit = SubmitField("Salvar")


class PedidoForm(FlaskForm):
    setor_id = SelectField("Setor (com poder de compra)", coerce=int, validators=[DataRequired()])
    fornecedor_id = SelectField("Fornecedor", coerce=int, validators=[Optional()])
    justificativa = TextAreaField("Justificativa", validators=[Optional()])
    observacoes = TextAreaField("Observações", validators=[Optional()])
    submit = SubmitField("Salvar pedido")


class NotaFiscalForm(FlaskForm):
    fornecedor_id = SelectField("Fornecedor", coerce=int, validators=[DataRequired()])
    setor_id = SelectField("Setor de entrada", coerce=int, validators=[DataRequired()])
    pedido_id = SelectField("Pedido vinculado", coerce=int, validators=[Optional()])
    numero = StringField("Número da NF", validators=[DataRequired(), Length(max=40)])
    serie = StringField("Série", validators=[Optional(), Length(max=10)])
    chave_nfe = StringField("Chave de acesso (NF-e)", validators=[Optional(), Length(max=44)])
    data_emissao = DateField("Data de emissão", validators=[Optional()], render_kw={"type": "date"})
    data_entrada = DateField("Data de entrada", validators=[Optional()], render_kw={"type": "date"})
    arquivo_pdf = FileField("Anexo PDF", validators=[Optional(), FileAllowed(["pdf"])])
    arquivo_xml = FileField("XML da NF-e", validators=[Optional(), FileAllowed(["xml"])])
    observacoes = TextAreaField("Observações", validators=[Optional()])
    submit = SubmitField("Registrar nota")
