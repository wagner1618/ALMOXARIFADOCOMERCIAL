"""Testes das formatações no padrão brasileiro."""

from __future__ import annotations

from datetime import date, datetime

from app.utils.formatacao import (
    formatar_data,
    formatar_datahora,
    formatar_moeda,
    formatar_numero,
)


def test_formatar_data():
    assert formatar_data(date(2026, 6, 28)) == "28/06/2026"
    assert formatar_data(None) == "—"


def test_formatar_datahora():
    assert formatar_datahora(datetime(2026, 6, 28, 14, 5)) == "28/06/2026 14:05"
    assert formatar_datahora(None) == "—"


def test_formatar_numero_milhar():
    assert formatar_numero(1234567.5) == "1.234.567,50"
    assert formatar_numero(0) == "0,00"
    assert formatar_numero(None) == "—"
    assert formatar_numero(1000, casas=0) == "1.000"


def test_formatar_moeda():
    assert formatar_moeda(1234.5) == "R$ 1.234,50"
    assert formatar_moeda(None) == "—"
