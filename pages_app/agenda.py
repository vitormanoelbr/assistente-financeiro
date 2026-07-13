import datetime

import httpx
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

GRUPOS_SAIDA = [
    "50% Essencial (Sobreviver)",
    "30% Estilo de Vida (Viver)",
    "20% Investimentos e Objetivos",
    "Custos de Negócio",
    "Quitação de Dívidas",
]


def limpar_descricao_agenda(texto) -> str:
    return str(texto or "").replace(
        "[AGENDA COMPROMISSO] ",
        "",
        1,
    ).strip()


def preparar_dataframe(registros: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(registros)

    if df.empty:
        return df

    for coluna in (
        "id",
        "data",
        "descricao",
        "grupo_orcamentario",
        "subcategoria",
        "valor",
        "tipo",
    ):
        if coluna not in df.columns:
            df[coluna] = None

    df["data_dt"] = pd.to_datetime(
        df["data"],
        errors="coerce",
    )
    df["valor_num"] = df["valor"].apply(numero_seguro)
    df["Compromisso"] = df["descricao"].apply(
        limpar_descricao_agenda
    )
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

    return df[
        df["id"].notna()
        & df["data_dt"].notna()
        & (df["valor_num"] > 0)
    ].copy()


def criar_rotulos(df: pd.DataFrame) -> dict[str, object]:
    opcoes = {}

    for _, linha in df.iterrows():
        identificador = linha["id"]
        data_texto = linha["data_dt"].strftime("%d/%m/%Y")
        descricao = str(linha["Compromisso"])
        natureza = str(linha["Natureza"])
        valor = float(linha["valor_num"])

        rotulo = (
            f"{data_texto} - {descricao} - "
            f"{natureza} - {moeda_br(valor)}"
        )

        if rotulo in opcoes:
            rotulo = f"{rotulo} - ID {identificador}"

        opcoes[rotulo] = identificador

    return opcoes


def localizar_registro(
    df: pd.DataFrame,
    registro_id,
) -> pd.Series:
    resultado = df[df["id"] == registro_id]

    if resultado.empty:
        raise ValueError(
            "O compromisso selecionado não foi encontrado."
        )

    return resultado.iloc[0]


def renderizar_cadastro(api) -> None:
    st.subheader("Novo compromisso")

    with st.form("form_cadastrar_agenda", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            natureza = st.selectbox(
                "Natureza:",
                ["A pagar", "A receber"],
                key="agenda_cadastro_natureza",
            )
            descricao = st.text_input(
                "Descrição:",
                placeholder="Ex.: aluguel, cliente, mensalidade",
                key="agenda_cadastro_descricao",
            )
            categoria = st.text_input(
                "Categoria:",
                placeholder="Ex.: Moradia, Cliente, Energia",
                key="agenda_cadastro_categoria",
            )

        with col2:
            data_compromisso = st.date_input(
                "Data do compromisso:",
                value=datetime.date.today(),
                format="DD/MM/YYYY",
                key="agenda_cadastro_data",
            )
            valor = st.number_input(
                "Valor (R$):",
                min_value=0.0,
                step=10.0,
                format="%.2f",
                key="agenda_cadastro_valor",
            )

        salvar = st.form_submit_button(
            "Cadastrar compromisso",
            width="stretch",
        )

    if not salvar:
        return

    erros = []

    if not descricao.strip():
        erros.append("Informe a descrição.")
    if not categoria.strip():
        erros.append("Informe a categoria.")
    if float(valor) <= 0:
        erros.append("Informe um valor maior que zero.")

    if erros:
        for erro in erros:
            st.error(erro)
        return

    try:
        api.cadastrar_compromisso(
            descricao=descricao,
            natureza=natureza,
            data_compromisso=data_compromisso,
            valor=float(valor),
            categoria=categoria,
        )
        st.success("Compromisso cadastrado.")
        st.rerun()
    except httpx.TimeoutException:
        st.error("O cadastro ultrapassou 25 segundos.")
    except httpx.RequestError as erro:
        st.error(f"Falha de conexão: {erro}")
    except Exception as erro:
        st.error(
            "Falha ao cadastrar: "
            f"{type(erro).__name__}: {erro}"
        )


def renderizar_edicao(api, df: pd.DataFrame) -> None:
    st.subheader("Editar compromisso")

    opcoes = criar_rotulos(df)
    rotulo = st.selectbox(
        "Escolha o compromisso:",
        list(opcoes),
        key="agenda_edicao_selecao",
    )

    registro_id = opcoes[rotulo]
    registro = localizar_registro(df, registro_id)

    natureza_atual = str(registro["Natureza"])
    descricao_atual = str(registro["Compromisso"])
    categoria_atual = str(registro["subcategoria"] or "")
    data_atual = registro["data_dt"].date()
    valor_atual = float(registro["valor_num"])

    with st.form(f"form_editar_agenda_{registro_id}"):
        col1, col2 = st.columns(2)

        with col1:
            natureza = st.selectbox(
                "Natureza:",
                ["A pagar", "A receber"],
                index=(
                    1
                    if natureza_atual == "A receber"
                    else 0
                ),
                key=f"agenda_editar_natureza_{registro_id}",
            )
            descricao = st.text_input(
                "Descrição:",
                value=descricao_atual,
                key=f"agenda_editar_descricao_{registro_id}",
            )
            categoria = st.text_input(
                "Categoria:",
                value=categoria_atual,
                key=f"agenda_editar_categoria_{registro_id}",
            )

        with col2:
            data_compromisso = st.date_input(
                "Data:",
                value=data_atual,
                format="DD/MM/YYYY",
                key=f"agenda_editar_data_{registro_id}",
            )
            valor = st.number_input(
                "Valor (R$):",
                min_value=0.0,
                value=valor_atual,
                step=10.0,
                format="%.2f",
                key=f"agenda_editar_valor_{registro_id}",
            )

        salvar = st.form_submit_button(
            "Salvar alterações",
            width="stretch",
        )

    if not salvar:
        return

    erros = []

    if not descricao.strip():
        erros.append("Informe a descrição.")
    if not categoria.strip():
        erros.append("Informe a categoria.")
    if float(valor) <= 0:
        erros.append("Informe um valor maior que zero.")

    if erros:
        for erro in erros:
            st.error(erro)
        return

    try:
        api.atualizar_compromisso(
            registro_id,
            descricao=descricao,
            natureza=natureza,
            data_compromisso=data_compromisso,
            valor=float(valor),
            categoria=categoria,
        )
        st.success("Compromisso atualizado.")
        st.rerun()
    except Exception as erro:
        st.error(
            "Falha ao editar: "
            f"{type(erro).__name__}: {erro}"
        )


def renderizar_baixa(api, df: pd.DataFrame) -> None:
    st.subheader("Dar baixa")
    st.caption(
        "A baixa cria um lançamento financeiro real e "
        "remove o item da Agenda."
    )

    opcoes = criar_rotulos(df)
    rotulo = st.selectbox(
        "Escolha o compromisso:",
        list(opcoes),
        key="agenda_baixa_selecao",
    )

    registro_id = opcoes[rotulo]
    registro = localizar_registro(df, registro_id)

    descricao = str(registro["Compromisso"])
    natureza = str(registro["Natureza"])
    categoria_atual = str(registro["subcategoria"] or "")
    valor = float(registro["valor_num"])

    with st.form(f"form_baixa_agenda_{registro_id}"):
        st.write(
            f"**{natureza}:** {descricao} - {moeda_br(valor)}"
        )

        col1, col2 = st.columns(2)

        with col1:
            data_baixa = st.date_input(
                "Data da baixa:",
                value=datetime.date.today(),
                format="DD/MM/YYYY",
                key=f"agenda_baixa_data_{registro_id}",
            )

            if natureza == "A pagar":
                grupo_destino = st.selectbox(
                    "Grupo orçamentário:",
                    GRUPOS_SAIDA,
                    key=f"agenda_baixa_grupo_{registro_id}",
                )
            else:
                grupo_destino = "RECEITAS"
                st.text_input(
                    "Grupo orçamentário:",
                    value="RECEITAS",
                    disabled=True,
                    key=f"agenda_baixa_grupo_receita_{registro_id}",
                )

        with col2:
            categoria_destino = st.text_input(
                "Categoria do lançamento:",
                value=categoria_atual,
                key=f"agenda_baixa_categoria_{registro_id}",
            )
            confirmar = st.checkbox(
                "Confirmo que os dados estão corretos.",
                key=f"agenda_baixa_confirmar_{registro_id}",
            )

        executar = st.form_submit_button(
            (
                "Marcar como recebido"
                if natureza == "A receber"
                else "Marcar como pago"
            ),
            width="stretch",
        )

    if not executar:
        return

    if not categoria_destino.strip():
        st.error("Informe a categoria.")
        return

    if not confirmar:
        st.error("Marque a confirmação.")
        return

    try:
        api.baixar_compromisso(
            registro_id,
            descricao=descricao,
            natureza=natureza,
            data_baixa=data_baixa,
            valor=valor,
            grupo_destino=grupo_destino,
            categoria_destino=categoria_destino,
        )
        st.success(
            "Compromisso recebido."
            if natureza == "A receber"
            else "Compromisso pago."
        )
        st.rerun()
    except Exception as erro:
        st.error(
            "Falha ao dar baixa: "
            f"{type(erro).__name__}: {erro}"
        )


def renderizar_exclusao(api, df: pd.DataFrame) -> None:
    st.subheader("Excluir compromisso")
    st.warning(
        "A exclusão remove o compromisso sem criar "
        "um lançamento financeiro."
    )

    opcoes = criar_rotulos(df)
    rotulo = st.selectbox(
        "Escolha o compromisso:",
        list(opcoes),
        key="agenda_exclusao_selecao",
    )

    registro_id = opcoes[rotulo]
    registro = localizar_registro(df, registro_id)
    descricao = str(registro["Compromisso"])

    with st.form(f"form_excluir_agenda_{registro_id}"):
        st.write(f"Compromisso: **{descricao}**")
        confirmar = st.checkbox(
            "Entendo que esta ação não pode ser desfeita.",
            key=f"agenda_excluir_confirmar_{registro_id}",
        )
        excluir = st.form_submit_button(
            "Excluir definitivamente",
            width="stretch",
        )

    if not excluir:
        return

    if not confirmar:
        st.error("Marque a confirmação antes de excluir.")
        return

    try:
        api.excluir_movimentacao(registro_id)
        st.success("Compromisso excluído.")
        st.rerun()
    except Exception as erro:
        st.error(
            "Falha ao excluir: "
            f"{type(erro).__name__}: {erro}"
        )


def renderizar(api) -> None:
    st.title("Agenda de Compromissos")
    st.caption(
        "Cadastro, edição, baixa e exclusão por HTTP direto."
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
        ("grupo_orcamentario", "ilike.*AGENDA*")
    ]

    if modo == "Próximos 90 dias":
        fim = hoje + datetime.timedelta(days=91)
        filtros.extend([
            ("data", f"gte.{hoje.isoformat()}"),
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
        df = preparar_dataframe(registros)
    except Exception as erro:
        st.error(
            "Falha ao carregar a Agenda: "
            f"{type(erro).__name__}: {erro}"
        )
        return

    aba_lista, aba_novo, aba_editar, aba_baixa, aba_excluir = st.tabs([
        "Compromissos",
        "Novo",
        "Editar",
        "Dar baixa",
        "Excluir",
    ])

    with aba_lista:
        if df.empty:
            st.info(
                "Nenhum compromisso encontrado para o período."
            )
        else:
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
                lambda data: data.strftime("%d/%m/%Y")
            )
            tabela["Valor"] = tabela["Valor"].apply(moeda_br)

            st.dataframe(
                tabela,
                width="stretch",
                hide_index=True,
            )

    with aba_novo:
        renderizar_cadastro(api)

    with aba_editar:
        if df.empty:
            st.info("Não há compromisso para editar.")
        else:
            renderizar_edicao(api, df)

    with aba_baixa:
        if df.empty:
            st.info("Não há compromisso para dar baixa.")
        else:
            renderizar_baixa(api, df)

    with aba_excluir:
        if df.empty:
            st.info("Não há compromisso para excluir.")
        else:
            renderizar_exclusao(api, df)
