"""Compras públicas (§7.10, Lei 14.133/2021) — só valem no modo PÚBLICO.

Cadeia da despesa pública: **dotação → empenho → liquidação → pagamento**, com a
entrada do material amarrada ao **recebimento definitivo**. Todos os saldos
(dotação, empenho, contrato, ata) são mantidos consistentes e nunca negativos
pela camada de serviço (``publico_service``).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.compras import NotaFiscal
    from app.models.fornecedor import Fornecedor
    from app.models.produto import Produto
    from app.models.setor import Setor
    from app.models.usuario import Usuario


# ===================================================== Dotação orçamentária === #
class DotacaoOrcamentaria(TenantMixin, TimestampMixin, db.Model):
    """Crédito orçamentário; o empenho reserva recurso decrementando o saldo."""

    __tablename__ = "dotacoes_orcamentarias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exercicio: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    programa_trabalho: Mapped[str | None] = mapped_column(String(60), nullable=True)
    natureza_despesa: Mapped[str | None] = mapped_column(String(40), nullable=True)
    fonte_recurso: Mapped[str | None] = mapped_column(String(40), nullable=True)
    unidade_orcamentaria: Mapped[str | None] = mapped_column(String(80), nullable=True)
    descricao: Mapped[str | None] = mapped_column(String(160), nullable=True)

    valor_dotado: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0, nullable=False)
    valor_empenhado: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0, nullable=False)

    @property
    def saldo_disponivel(self) -> Decimal:
        return Decimal(self.valor_dotado or 0) - Decimal(self.valor_empenhado or 0)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Dotacao {self.programa_trabalho or self.id} saldo={self.saldo_disponivel}>"


# ==================================================== Processo de contratação === #
PREGAO = "PREGAO"
CONCORRENCIA = "CONCORRENCIA"
CONCURSO = "CONCURSO"
LEILAO = "LEILAO"
DIALOGO_COMPETITIVO = "DIALOGO_COMPETITIVO"
DISPENSA = "DISPENSA"
INEXIGIBILIDADE = "INEXIGIBILIDADE"
MODALIDADES = (
    PREGAO, CONCORRENCIA, CONCURSO, LEILAO, DIALOGO_COMPETITIVO, DISPENSA, INEXIGIBILIDADE,
)
ROTULO_MODALIDADE = {
    PREGAO: "Pregão",
    CONCORRENCIA: "Concorrência",
    CONCURSO: "Concurso",
    LEILAO: "Leilão",
    DIALOGO_COMPETITIVO: "Diálogo competitivo",
    DISPENSA: "Dispensa de licitação",
    INEXIGIBILIDADE: "Inexigibilidade",
}

SEM_PROCEDIMENTO = "NENHUM"
REGISTRO_DE_PRECOS = "REGISTRO_DE_PRECOS"

# Status do processo.
PROC_PLANEJAMENTO = "PLANEJAMENTO"
PROC_PUBLICADO = "PUBLICADO"
PROC_EM_DISPUTA = "EM_DISPUTA"
PROC_HOMOLOGADO = "HOMOLOGADO"
PROC_DESERTO = "DESERTO"
PROC_FRACASSADO = "FRACASSADO"
PROC_REVOGADO = "REVOGADO"
PROC_ANULADO = "ANULADO"
PROC_CONCLUIDO = "CONCLUIDO"
STATUS_PROCESSO = (
    PROC_PLANEJAMENTO, PROC_PUBLICADO, PROC_EM_DISPUTA, PROC_HOMOLOGADO,
    PROC_DESERTO, PROC_FRACASSADO, PROC_REVOGADO, PROC_ANULADO, PROC_CONCLUIDO,
)
ROTULO_PROCESSO = {
    PROC_PLANEJAMENTO: "Planejamento",
    PROC_PUBLICADO: "Publicado",
    PROC_EM_DISPUTA: "Em disputa",
    PROC_HOMOLOGADO: "Homologado",
    PROC_DESERTO: "Deserto",
    PROC_FRACASSADO: "Fracassado",
    PROC_REVOGADO: "Revogado",
    PROC_ANULADO: "Anulado",
    PROC_CONCLUIDO: "Concluído",
}
COR_PROCESSO = {
    PROC_PLANEJAMENTO: "secondary",
    PROC_PUBLICADO: "info",
    PROC_EM_DISPUTA: "primary",
    PROC_HOMOLOGADO: "success",
    PROC_CONCLUIDO: "success",
    PROC_DESERTO: "warning",
    PROC_FRACASSADO: "warning",
    PROC_REVOGADO: "danger",
    PROC_ANULADO: "danger",
}


class ProcessoContratacao(TenantMixin, TimestampMixin, db.Model):
    """Processo licitatório ou contratação direta (dispensa/inexigibilidade)."""

    __tablename__ = "processos_contratacao"
    __table_args__ = (
        UniqueConstraint("organizacao_id", "numero_processo", name="uq_processo_org_numero"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero_processo: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    objeto: Mapped[str] = mapped_column(Text, nullable=False)
    modalidade: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    procedimento_auxiliar: Mapped[str] = mapped_column(
        String(20), default=SEM_PROCEDIMENTO, nullable=False
    )
    valor_estimado: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0, nullable=False)
    setor_id: Mapped[int | None] = mapped_column(
        ForeignKey("setores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    data_abertura: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_homologacao: Mapped[date | None] = mapped_column(Date, nullable=True)
    numero_pncp: Mapped[str | None] = mapped_column(String(60), nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), default=PROC_PLANEJAMENTO, nullable=False, index=True
    )
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    setor: Mapped[Setor | None] = relationship()

    @property
    def is_srp(self) -> bool:
        return self.procedimento_auxiliar == REGISTRO_DE_PRECOS

    @property
    def rotulo_modalidade(self) -> str:
        return ROTULO_MODALIDADE.get(self.modalidade, self.modalidade)

    @property
    def rotulo_status(self) -> str:
        return ROTULO_PROCESSO.get(self.status, self.status)

    @property
    def cor_status(self) -> str:
        return COR_PROCESSO.get(self.status, "secondary")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Processo {self.numero_processo} {self.status}>"


# ======================================================= Ata de registro de preços === #
ATA_VIGENTE = "VIGENTE"
ATA_ENCERRADA = "ENCERRADA"
ATA_CANCELADA = "CANCELADA"
STATUS_ATA = (ATA_VIGENTE, ATA_ENCERRADA, ATA_CANCELADA)


class AtaRegistroPrecos(TenantMixin, TimestampMixin, db.Model):
    """Ata de SRP — cada compra futura consome saldo dos itens registrados."""

    __tablename__ = "atas_registro_precos"
    __table_args__ = (UniqueConstraint("organizacao_id", "numero", name="uq_ata_org_numero"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    processo_id: Mapped[int | None] = mapped_column(
        ForeignKey("processos_contratacao.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fornecedor_id: Mapped[int] = mapped_column(
        ForeignKey("fornecedores.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    vigencia_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    vigencia_fim: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(12), default=ATA_VIGENTE, nullable=False, index=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    processo: Mapped[ProcessoContratacao | None] = relationship()
    fornecedor: Mapped[Fornecedor] = relationship()
    itens: Mapped[list[AtaItem]] = relationship(
        back_populates="ata", cascade="all, delete-orphan"
    )

    @property
    def vencida(self) -> bool:
        return self.vigencia_fim is not None and self.vigencia_fim < date.today()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Ata {self.numero} {self.status}>"


class AtaItem(TenantMixin, TimestampMixin, db.Model):
    """Item registrado em ata, com saldo de quantidade que vai sendo consumido."""

    __tablename__ = "ata_itens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ata_id: Mapped[int] = mapped_column(
        ForeignKey("atas_registro_precos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    produto_id: Mapped[int | None] = mapped_column(
        ForeignKey("produtos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    descricao: Mapped[str] = mapped_column(String(255), nullable=False)
    quantidade_registrada: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    preco_registrado: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    saldo_quantidade: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)

    ata: Mapped[AtaRegistroPrecos] = relationship(back_populates="itens")
    produto: Mapped[Produto | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AtaItem {self.descricao!r} saldo={self.saldo_quantidade}>"


# ============================================================== Contrato === #
CONTRATO_VIGENTE = "VIGENTE"
CONTRATO_SUSPENSO = "SUSPENSO"
CONTRATO_ENCERRADO = "ENCERRADO"
CONTRATO_RESCINDIDO = "RESCINDIDO"
STATUS_CONTRATO = (CONTRATO_VIGENTE, CONTRATO_SUSPENSO, CONTRATO_ENCERRADO, CONTRATO_RESCINDIDO)
ROTULO_CONTRATO = {
    CONTRATO_VIGENTE: "Vigente",
    CONTRATO_SUSPENSO: "Suspenso",
    CONTRATO_ENCERRADO: "Encerrado",
    CONTRATO_RESCINDIDO: "Rescindido",
}
COR_CONTRATO = {
    CONTRATO_VIGENTE: "success",
    CONTRATO_SUSPENSO: "warning",
    CONTRATO_ENCERRADO: "secondary",
    CONTRATO_RESCINDIDO: "danger",
}


class Contrato(TenantMixin, TimestampMixin, db.Model):
    """Contrato administrativo, com fiscal/gestor designados e saldos por item."""

    __tablename__ = "contratos"
    __table_args__ = (UniqueConstraint("organizacao_id", "numero", name="uq_contrato_org_numero"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    objeto: Mapped[str] = mapped_column(Text, nullable=False)
    processo_id: Mapped[int | None] = mapped_column(
        ForeignKey("processos_contratacao.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ata_id: Mapped[int | None] = mapped_column(
        ForeignKey("atas_registro_precos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fornecedor_id: Mapped[int] = mapped_column(
        ForeignKey("fornecedores.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    valor_global: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0, nullable=False)
    vigencia_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    vigencia_fim: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    fiscal_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    gestor_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    garantia: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(
        String(12), default=CONTRATO_VIGENTE, nullable=False, index=True
    )
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    processo: Mapped[ProcessoContratacao | None] = relationship()
    ata: Mapped[AtaRegistroPrecos | None] = relationship()
    fornecedor: Mapped[Fornecedor] = relationship()
    fiscal: Mapped[Usuario | None] = relationship(foreign_keys=[fiscal_id])
    gestor: Mapped[Usuario | None] = relationship(foreign_keys=[gestor_id])
    itens: Mapped[list[ContratoItem]] = relationship(
        back_populates="contrato", cascade="all, delete-orphan"
    )
    aditivos: Mapped[list[TermoAditivo]] = relationship(
        back_populates="contrato", cascade="all, delete-orphan"
    )

    @property
    def rotulo_status(self) -> str:
        return ROTULO_CONTRATO.get(self.status, self.status)

    @property
    def cor_status(self) -> str:
        return COR_CONTRATO.get(self.status, "secondary")

    @property
    def vencido(self) -> bool:
        return self.vigencia_fim is not None and self.vigencia_fim < date.today()

    @property
    def saldo_valor(self) -> Decimal:
        return sum((Decimal(i.saldo_valor or 0) for i in self.itens), Decimal(0))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Contrato {self.numero} {self.status}>"


class ContratoItem(TenantMixin, TimestampMixin, db.Model):
    """Item do contrato, com saldos de quantidade e valor consumidos por empenho."""

    __tablename__ = "contrato_itens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contrato_id: Mapped[int] = mapped_column(
        ForeignKey("contratos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    produto_id: Mapped[int | None] = mapped_column(
        ForeignKey("produtos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    descricao: Mapped[str] = mapped_column(String(255), nullable=False)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    preco_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    saldo_quantidade: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    saldo_valor: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0, nullable=False)

    contrato: Mapped[Contrato] = relationship(back_populates="itens")
    produto: Mapped[Produto | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ContratoItem {self.descricao!r} saldo={self.saldo_quantidade}>"


ADITIVO_PRAZO = "PRAZO"
ADITIVO_VALOR = "VALOR"
ADITIVO_QUANTIDADE = "QUANTIDADE"
ADITIVO_APOSTILAMENTO = "APOSTILAMENTO"
TIPOS_ADITIVO = (ADITIVO_PRAZO, ADITIVO_VALOR, ADITIVO_QUANTIDADE, ADITIVO_APOSTILAMENTO)
ROTULO_ADITIVO = {
    ADITIVO_PRAZO: "Prazo",
    ADITIVO_VALOR: "Valor",
    ADITIVO_QUANTIDADE: "Quantidade",
    ADITIVO_APOSTILAMENTO: "Apostilamento",
}


class TermoAditivo(TenantMixin, TimestampMixin, db.Model):
    """Aditivo/apostilamento a um contrato (prazo, valor, quantidade)."""

    __tablename__ = "termos_aditivos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contrato_id: Mapped[int] = mapped_column(
        ForeignKey("contratos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    numero: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tipo: Mapped[str] = mapped_column(String(16), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    nova_vigencia: Mapped[date | None] = mapped_column(Date, nullable=True)

    contrato: Mapped[Contrato] = relationship(back_populates="aditivos")

    @property
    def rotulo_tipo(self) -> str:
        return ROTULO_ADITIVO.get(self.tipo, self.tipo)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TermoAditivo {self.tipo} contrato={self.contrato_id}>"


# =============================================================== Empenho === #
EMP_ORDINARIO = "ORDINARIO"
EMP_ESTIMATIVO = "ESTIMATIVO"
EMP_GLOBAL = "GLOBAL"
TIPOS_EMPENHO = (EMP_ORDINARIO, EMP_ESTIMATIVO, EMP_GLOBAL)
ROTULO_TIPO_EMPENHO = {
    EMP_ORDINARIO: "Ordinário",
    EMP_ESTIMATIVO: "Estimativo",
    EMP_GLOBAL: "Global",
}

EMP_EMITIDO = "EMITIDO"
EMP_PARC_LIQUIDADO = "PARC_LIQUIDADO"
EMP_LIQUIDADO = "LIQUIDADO"
EMP_ANULADO = "ANULADO"
STATUS_EMPENHO = (EMP_EMITIDO, EMP_PARC_LIQUIDADO, EMP_LIQUIDADO, EMP_ANULADO)
ROTULO_EMPENHO = {
    EMP_EMITIDO: "Emitido",
    EMP_PARC_LIQUIDADO: "Parcialmente liquidado",
    EMP_LIQUIDADO: "Liquidado",
    EMP_ANULADO: "Anulado",
}
COR_EMPENHO = {
    EMP_EMITIDO: "primary",
    EMP_PARC_LIQUIDADO: "info",
    EMP_LIQUIDADO: "success",
    EMP_ANULADO: "danger",
}


class Empenho(TenantMixin, TimestampMixin, db.Model):
    """Nota de empenho — reserva o recurso na dotação (1ª fase da despesa)."""

    __tablename__ = "empenhos"
    __table_args__ = (UniqueConstraint("organizacao_id", "numero", name="uq_empenho_org_numero"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(12), default=EMP_ORDINARIO, nullable=False)
    data: Mapped[date | None] = mapped_column(Date, nullable=True)
    valor: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0, nullable=False)
    saldo_a_liquidar: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0, nullable=False)

    dotacao_id: Mapped[int] = mapped_column(
        ForeignKey("dotacoes_orcamentarias.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    contrato_id: Mapped[int | None] = mapped_column(
        ForeignKey("contratos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ata_id: Mapped[int | None] = mapped_column(
        ForeignKey("atas_registro_precos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    processo_id: Mapped[int | None] = mapped_column(
        ForeignKey("processos_contratacao.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fornecedor_id: Mapped[int | None] = mapped_column(
        ForeignKey("fornecedores.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(String(16), default=EMP_EMITIDO, nullable=False, index=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    dotacao: Mapped[DotacaoOrcamentaria] = relationship()
    contrato: Mapped[Contrato | None] = relationship()
    ata: Mapped[AtaRegistroPrecos | None] = relationship()
    processo: Mapped[ProcessoContratacao | None] = relationship()
    fornecedor: Mapped[Fornecedor | None] = relationship()

    @property
    def valor_liquidado(self) -> Decimal:
        return Decimal(self.valor or 0) - Decimal(self.saldo_a_liquidar or 0)

    @property
    def rotulo_tipo(self) -> str:
        return ROTULO_TIPO_EMPENHO.get(self.tipo, self.tipo)

    @property
    def rotulo_status(self) -> str:
        return ROTULO_EMPENHO.get(self.status, self.status)

    @property
    def cor_status(self) -> str:
        return COR_EMPENHO.get(self.status, "secondary")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Empenho {self.numero} {self.status} saldo={self.saldo_a_liquidar}>"


# ============================================================ Recebimento === #
RECEB_PROVISORIO = "PROVISORIO"
RECEB_DEFINITIVO = "DEFINITIVO"
TIPOS_RECEBIMENTO = (RECEB_PROVISORIO, RECEB_DEFINITIVO)
ROTULO_RECEBIMENTO = {RECEB_PROVISORIO: "Provisório", RECEB_DEFINITIVO: "Definitivo"}


class Recebimento(TenantMixin, TimestampMixin, db.Model):
    """Recebimento de material (art. 140); o DEFINITIVO dispara a entrada valorada."""

    __tablename__ = "recebimentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    nota_fiscal_id: Mapped[int | None] = mapped_column(
        ForeignKey("notas_fiscais.id", ondelete="SET NULL"), nullable=True, index=True
    )
    empenho_id: Mapped[int | None] = mapped_column(
        ForeignKey("empenhos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contrato_id: Mapped[int | None] = mapped_column(
        ForeignKey("contratos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    setor_id: Mapped[int | None] = mapped_column(
        ForeignKey("setores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    data: Mapped[date | None] = mapped_column(Date, nullable=True)
    conforme: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    recebido_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    nota_fiscal: Mapped[NotaFiscal | None] = relationship()
    empenho: Mapped[Empenho | None] = relationship()
    contrato: Mapped[Contrato | None] = relationship()
    setor: Mapped[Setor | None] = relationship()
    recebido_por: Mapped[Usuario | None] = relationship()

    @property
    def is_definitivo(self) -> bool:
        return self.tipo == RECEB_DEFINITIVO

    @property
    def rotulo_tipo(self) -> str:
        return ROTULO_RECEBIMENTO.get(self.tipo, self.tipo)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Recebimento {self.tipo} nf={self.nota_fiscal_id}>"


# ====================================================== Liquidação e pagamento === #
LIQ_REGISTRADA = "REGISTRADA"
LIQ_PAGA = "PAGA"
STATUS_LIQUIDACAO = (LIQ_REGISTRADA, LIQ_PAGA)


class Liquidacao(TenantMixin, TimestampMixin, db.Model):
    """2ª fase da despesa: reconhece o direito do credor; baixa o saldo do empenho."""

    __tablename__ = "liquidacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empenho_id: Mapped[int] = mapped_column(
        ForeignKey("empenhos.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    nota_fiscal_id: Mapped[int | None] = mapped_column(
        ForeignKey("notas_fiscais.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recebimento_id: Mapped[int | None] = mapped_column(
        ForeignKey("recebimentos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    valor: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0, nullable=False)
    data: Mapped[date | None] = mapped_column(Date, nullable=True)
    atestado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(12), default=LIQ_REGISTRADA, nullable=False, index=True
    )
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    empenho: Mapped[Empenho] = relationship()
    nota_fiscal: Mapped[NotaFiscal | None] = relationship()
    recebimento: Mapped[Recebimento | None] = relationship()
    atestado_por: Mapped[Usuario | None] = relationship()
    pagamentos: Mapped[list[Pagamento]] = relationship(
        back_populates="liquidacao", cascade="all, delete-orphan"
    )

    @property
    def valor_pago(self) -> Decimal:
        return sum((Decimal(p.valor or 0) for p in self.pagamentos), Decimal(0))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Liquidacao empenho={self.empenho_id} valor={self.valor}>"


class Pagamento(TenantMixin, TimestampMixin, db.Model):
    """3ª fase da despesa: pagamento ligado a uma liquidação."""

    __tablename__ = "pagamentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    liquidacao_id: Mapped[int] = mapped_column(
        ForeignKey("liquidacoes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    valor: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0, nullable=False)
    data: Mapped[date | None] = mapped_column(Date, nullable=True)
    ordem_bancaria: Mapped[str | None] = mapped_column(String(60), nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    liquidacao: Mapped[Liquidacao] = relationship(back_populates="pagamentos")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Pagamento liquidacao={self.liquidacao_id} valor={self.valor}>"
