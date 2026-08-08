import sys
import types

# Permite validar as regras puras da página mesmo em um ambiente
# de teste que não tenha Streamlit instalado.
sys.modules.setdefault(
    "streamlit",
    types.SimpleNamespace(),
)

from pages_app.saldo import calcular_fluxo


def movimento(*, tipo="", valor=0.0, grupo="", descricao=""):
    return {
        "tipo": tipo,
        "valor": valor,
        "grupo_orcamentario": grupo,
        "descricao": descricao,
    }


def test_entrada_e_saida_afetam_fluxo():
    registros = [
        movimento(
            tipo="Faturamento ou Receita (Entrada)",
            valor=500.0,
        ),
        movimento(
            tipo="Saída Dinheiro / Pix (Débito)",
            valor=200.0,
        ),
    ]

    entradas, saidas, _ = calcular_fluxo(registros)

    assert entradas == 500.0
    assert saidas == 200.0


def test_compra_cartao_nao_reduz_caixa():
    entradas, saidas, _ = calcular_fluxo([
        movimento(
            tipo="Saída Cartão de Crédito",
            valor=500.0,
        )
    ])

    assert entradas == 0.0
    assert saidas == 0.0


def test_agenda_nao_reduz_caixa():
    entradas, saidas, _ = calcular_fluxo([
        movimento(
            tipo="Saída",
            grupo="AGENDA - A PAGAR",
            valor=400.0,
        )
    ])

    assert entradas == 0.0
    assert saidas == 0.0


def test_configuracao_nao_afeta_caixa():
    entradas, saidas, _ = calcular_fluxo([
        movimento(
            tipo="Faturamento ou Receita (Entrada)",
            grupo="CONFIGURAÇÃO",
            descricao="[CONFIG_PERFIL] Renda Base",
            valor=5000.0,
        )
    ])

    assert entradas == 0.0
    assert saidas == 0.0
