import datetime

import pandas as pd
import streamlit as st

from core.formatacao import moeda_br, numero_seguro


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
    st.title("Agenda de Compromissos")
    st.caption(
        "Nesta etapa, a Agenda está em modo de leitura."
    )

    hoje = datetime.date.today()

    col1, col2, col3 = st.columns(3)

    with col1:
        modo = st.selectbox(
            "Período:",
            [
                "Próximos 90 dias",
                "Mês selecionado",
                "Todos",
            ],
        )

    with col2:
        ano = st.selectbox(
            "Ano:",
            [hoje.year - 1, hoje.year, hoje.year + 1],
            index=1,
            disabled=(modo != "Mês selecionado"),
        )

    with col3:
        mes = st.selectbox(
            "Mês:",
            list(MESES),
            index=hoje.month - 1,
            format_func=lambda numero: MESES[numero],
            disabled=(modo != "Mês selecionado"),
        )

    filtros = [
        (
            "grupo_orcamentario",
            "ilike.*AGENDA*",
        )
    ]

    if modo == "Próximos 90 dias":
        inicio = hoje
        fim = hoje + datetime.timedelta(days=91)
        filtros.extend([
            ("data", f"gte.{inicio.isoformat()}"),
            ("data", f"lt.{fim.isoformat()}"),
        ])

    elif modo == "Mês selecionado":
        inicio = datetime.date(int(ano), int(mes), 1)

        if int(mes) == 12:
            fim = datetime.date(int(ano) + 1, 1, 1)
        else:
            fim = datetime.date(int(ano), int(mes) + 1, 1)

        filtros.extend([
            ("data", f"gte.{inicio.isoformat()}"),
            ("data", f"lt.{fim.isoformat()}"),
        ])

    try:
        registros = api.buscar_movimentacoes(
            filtros=filtros,
            order="data.asc",
            limit=500,
        )
    except Exception as erro:
        st.error(
            "Falha ao carregar a Agenda: "
            f"{type(erro).__name__}: {erro}"
        )
        return

    df = pd.DataFrame(registros)

    if df.empty:
        st.info(
            "Nenhum compromisso encontrado para o período."
        )
        return

    for coluna in (
        "data",
        "descricao",
        "grupo_orcamentario",
        "subcategoria",
        "valor",
    ):
        if coluna not in df.columns:
            df[coluna] = None

    df["data_dt"] = pd.to_datetime(
        df["data"],
        errors="coerce",
    )
    df["valor_num"] = df["valor"].apply(numero_seguro)

    df["Natureza"] = (
        df["grupo_orcamentario"]
        .fillna("")
        .astype(str)
        .str.upper()
        .apply(
            lambda texto: (
                "A receber"
                if "RECEBER" in texto
                else "A pagar"
            )
        )
    )

    df["Compromisso"] = (
        df["descricao"]
        .fillna("")
        .astype(str)
        .str.replace(
            "[AGENDA COMPROMISSO] ",
            "",
            regex=False,
        )
    )

    total_pagar = float(
        df.loc[
            df["Natureza"] == "A pagar",
            "valor_num",
        ].sum()
    )
    total_receber = float(
        df.loc[
            df["Natureza"] == "A receber",
            "valor_num",
        ].sum()
    )

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("A pagar", moeda_br(total_pagar))
    col_b.metric("A receber", moeda_br(total_receber))
    col_c.metric(
        "Saldo projetado",
        moeda_br(total_receber - total_pagar),
    )

    tabela = df[
        [
            "data_dt",
            "Compromisso",
            "Natureza",
            "subcategoria",
            "valor_num",
        ]
    ].copy()

    tabela = tabela.rename(
        columns={
            "data_dt": "Data",
            "subcategoria": "Categoria",
            "valor_num": "Valor",
        }
    )

    tabela["Data"] = tabela["Data"].apply(
        lambda data: (
            data.strftime("%d/%m/%Y")
            if pd.notna(data)
            else ""
        )
    )
    tabela["Valor"] = tabela["Valor"].apply(moeda_br)

    st.dataframe(
        tabela,
        width="stretch",
        hide_index=True,
    )
