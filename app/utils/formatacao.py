"""Formatação no padrão brasileiro (data dd/mm/aaaa, moeda R$, números)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def formatar_data(valor: date | datetime | None) -> str:
    if valor is None:
        return "—"
    return valor.strftime("%d/%m/%Y")


def formatar_datahora(valor: datetime | None) -> str:
    if valor is None:
        return "—"
    return valor.strftime("%d/%m/%Y %H:%M")


def _agrupar_milhar(inteiro: str) -> str:
    sinal = ""
    if inteiro.startswith("-"):
        sinal, inteiro = "-", inteiro[1:]
    partes = []
    while len(inteiro) > 3:
        partes.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    partes.insert(0, inteiro)
    return sinal + ".".join(partes)


def formatar_numero(valor: float | Decimal | int | None, casas: int = 2) -> str:
    if valor is None:
        return "—"
    try:
        dec = Decimal(str(valor)).quantize(Decimal(10) ** -casas)
    except (InvalidOperation, ValueError):
        return "—"
    inteiro, _, frac = f"{dec:.{casas}f}".partition(".")
    inteiro_fmt = _agrupar_milhar(inteiro)
    return f"{inteiro_fmt},{frac}" if casas else inteiro_fmt


def formatar_moeda(valor: float | Decimal | int | None) -> str:
    if valor is None:
        return "—"
    return f"R$ {formatar_numero(valor, 2)}"
