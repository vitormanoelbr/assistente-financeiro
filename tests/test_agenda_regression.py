import datetime

import pytest

from core.api import SupabaseRestClient


class FakeAgendaApi(SupabaseRestClient):
    def __init__(self, falhar_ao_excluir=None):
        self.criados = []
        self.excluidos = []
        self.falhar_ao_excluir = falhar_ao_excluir
        self.proximo_id = 900

    def criar_movimentacao(self, payload):
        registro = {**payload, "id": self.proximo_id}
        self.proximo_id += 1
        self.criados.append(registro)
        return registro

    def excluir_movimentacao(self, registro_id):
        self.excluidos.append(registro_id)

        if registro_id == self.falhar_ao_excluir:
            raise RuntimeError("falha simulada")


def test_baixa_a_pagar_cria_saida_real():
    api = FakeAgendaApi()

    novo = api.baixar_compromisso(
        123,
        descricao="Aluguel",
        natureza="A pagar",
        data_baixa=datetime.date(2026, 8, 8),
        valor=900.0,
        grupo_destino="50% Essencial (Sobreviver)",
        categoria_destino="Moradia",
    )

    assert novo["tipo"] == "Saída Dinheiro / Pix (Débito)"
    assert novo["valor"] == 900.0
    assert novo["grupo_orcamentario"] == "50% Essencial (Sobreviver)"
    assert api.excluidos == [123]


def test_baixa_a_receber_cria_entrada_real():
    api = FakeAgendaApi()

    novo = api.baixar_compromisso(
        456,
        descricao="Cliente",
        natureza="A receber",
        data_baixa=datetime.date(2026, 8, 8),
        valor=1200.0,
        grupo_destino="ignorado",
        categoria_destino="Prestação de serviços",
    )

    assert novo["tipo"] == "Faturamento ou Receita (Entrada)"
    assert novo["grupo_orcamentario"] == "RECEITAS"
    assert novo["valor"] == 1200.0
    assert api.excluidos == [456]


def test_baixa_faz_rollback_se_compromisso_nao_for_removido():
    compromisso_id = 321
    api = FakeAgendaApi(falhar_ao_excluir=compromisso_id)

    with pytest.raises(RuntimeError, match="baixa foi desfeita"):
        api.baixar_compromisso(
            compromisso_id,
            descricao="Conta",
            natureza="A pagar",
            data_baixa=datetime.date(2026, 8, 8),
            valor=100.0,
            grupo_destino="50% Essencial (Sobreviver)",
            categoria_destino="Contas",
        )

    assert api.excluidos == [compromisso_id, 900]
