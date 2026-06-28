"""Testes do motor de campos customizados (validação/coerção)."""

from __future__ import annotations

import pytest
from werkzeug.datastructures import MultiDict

from app.extensions import db
from app.models.definicao_campo import (
    ENTIDADE_PRODUTO,
    TIPO_DATA,
    TIPO_MULTISELECT,
    TIPO_NUMERO,
    TIPO_SELECT,
    TIPO_TEXTO,
    DefinicaoCampo,
)
from app.services import campos_customizados as cc
from app.services import setup


@pytest.fixture()
def org_campos(app):
    org = setup.criar_organizacao("Org Campos", slug="campos")

    def add(chave, tipo, **kw):
        d = DefinicaoCampo(
            organizacao_id=org.id,
            entidade=ENTIDADE_PRODUTO,
            chave=chave,
            rotulo=chave.title(),
            tipo=tipo,
            **kw,
        )
        db.session.add(d)
        return d

    add("processador", TIPO_TEXTO, obrigatorio=True)
    add("memoria_gb", TIPO_NUMERO)
    add("garantia_ate", TIPO_DATA)
    add("cor", TIPO_SELECT, opcoes=["Preto", "Branco"])
    add("portas", TIPO_MULTISELECT, opcoes=["USB", "HDMI", "VGA"])
    db.session.commit()
    return org


def _form(data):
    return MultiDict(data)


def test_definicoes_aplicaveis(org_campos):
    defs = cc.definicoes_aplicaveis(org_campos.id, ENTIDADE_PRODUTO)
    assert {d.chave for d in defs} == {"processador", "memoria_gb", "garantia_ate", "cor", "portas"}


def test_obrigatorio_falta(org_campos):
    defs = cc.definicoes_aplicaveis(org_campos.id, ENTIDADE_PRODUTO)
    valores, erros = cc.validar_e_coletar(defs, _form({}))
    assert "processador" in erros


def test_numero_e_data_validos(org_campos):
    defs = cc.definicoes_aplicaveis(org_campos.id, ENTIDADE_PRODUTO)
    form = _form(
        {
            "cc_processador": "Intel i7",
            "cc_memoria_gb": "16",
            "cc_garantia_ate": "31/12/2026",
        }
    )
    valores, erros = cc.validar_e_coletar(defs, form)
    assert erros == {}
    assert valores["memoria_gb"] == 16.0
    assert valores["garantia_ate"] == "2026-12-31"


def test_numero_invalido(org_campos):
    defs = cc.definicoes_aplicaveis(org_campos.id, ENTIDADE_PRODUTO)
    form = _form({"cc_processador": "x", "cc_memoria_gb": "abc"})
    _, erros = cc.validar_e_coletar(defs, form)
    assert "memoria_gb" in erros


def test_select_invalido(org_campos):
    defs = cc.definicoes_aplicaveis(org_campos.id, ENTIDADE_PRODUTO)
    form = _form({"cc_processador": "x", "cc_cor": "Verde"})
    _, erros = cc.validar_e_coletar(defs, form)
    assert "cor" in erros


def test_multiselect(org_campos):
    defs = cc.definicoes_aplicaveis(org_campos.id, ENTIDADE_PRODUTO)
    form = MultiDict([("cc_processador", "x"), ("cc_portas", "USB"), ("cc_portas", "HDMI")])
    valores, erros = cc.validar_e_coletar(defs, form)
    assert erros == {}
    assert valores["portas"] == ["USB", "HDMI"]


def test_formatar_valor(org_campos):
    defs = {d.chave: d for d in cc.definicoes_aplicaveis(org_campos.id, ENTIDADE_PRODUTO)}
    assert cc.formatar_valor(defs["garantia_ate"], "2026-12-31") == "31/12/2026"
    assert cc.formatar_valor(defs["portas"], ["USB", "HDMI"]) == "USB, HDMI"
    assert cc.formatar_valor(defs["memoria_gb"], None) == "—"
