import datetime

import pandas as pd
import streamlit as st

from core.formatacao import (
    classificar_tipo,
    moeda_br,
    numero_seguro,
)


MESES = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


def renderizar(api) -> None:
    st.title("Diagnóstico Financeiro")
    st.caption(
        "Leitura leve do mês selecionado. "
        "A página consulta apenas os registros desse período."
    )

    hoje = datetime.date.today()
    col1, col2 = st.columns(2)

    with col1:
        ano = st.selectbox(
            "Ano:",
            [hoje.year - 1, hoje.year, hoje.year + 1],
            index=1,
        )

    with col2:
        mes = st.selectbox(
            "Mês:",
            list(MESES),
            index=hoje.month - 1,
            format_func=lambda numero: MESES[numero],
        )

    try:
        registros = api.buscar_mes(
            int(ano),
            int(mes),
            limit=1000,
        )
    except Exception as erro:
        st.error(
            "Falha ao carregar o diagnóstico: "
            f"{type(erro).__name__}: {erro}"
        )
        return

    df = pd.DataFrame(registros)

    if df.empty:
        st.info("Nenhum lançamento encontrado para o mês.")
        return

    for coluna in (
        "descricao",
        "grupo_orcamentario",
        "valor",
        "tipo",
    ):
        if coluna not in df.columns:
            df[coluna] = None

    df["valor_num"] = df["valor"].apply(numero_seguro)
    df["classe"] = df["tipo"].apply(classificar_tipo)

    mascara_config = (
        df["grupo_orcamentario"]
        .fillna("")
        .astype(str)
        .str.upper()
        .str.contains("CONFIG|AGENDA", regex=True, na=False)
    )

    df = df[~mascara_config].copy()

    receitas = float(
        df.loc[df["classe"] == "entrada", "valor_num"].sum()
    )
    saidas = float(
        df.loc[df["classe"] == "saida", "valor_num"].sum()
    )
    cartao = float(
        df.loc[df["classe"] == "cartao", "valor_num"].sum()
    )
    saldo_caixa_mes = receitas - saidas

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Receitas", moeda_br(receitas))
    col_b.metric("Saídas pagas", moeda_br(saidas))
    col_c.metric("Compras no cartão", moeda_br(cartao))
    col_d.metric(
        "Resultado de caixa do mês",
        moeda_br(saldo_caixa_mes),
    )

    st.markdown("---")
    st.subheader("Leitura prática")

    if saldo_caixa_mes < 0:
        st.error(
            "As saídas pagas superam as receitas registradas "
            "neste mês."
        )
    elif receitas <= 0 and saidas > 0:
        st.warning(
            "Existem saídas, mas nenhuma receita foi reconhecida."
        )
    else:
        st.success(
            "O resultado de caixa do mês está positivo "
            "com os registros atuais."
        )

    with st.expander("Ver registros do mês"):
        tabela = df[
            [
                "data",
                "descricao",
                "grupo_orcamentario",
                "tipo",
                "valor_num",
            ]
        ].copy()

        tabela = tabela.rename(
            columns={
                "data": "Data",
                "descricao": "Descrição",
                "grupo_orcamentario": "Grupo",
                "tipo": "Tipo",
                "valor_num": "Valor",
            }
        )

        tabela["Valor"] = tabela["Valor"].apply(moeda_br)

        st.dataframe(
            tabela,
            width="stretch",
            hide_index=True,
        )
