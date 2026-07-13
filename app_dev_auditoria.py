import datetime
import time
from typing import Optional

import httpx
import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="Auditoria Financeira",
    layout="wide",
)


# ==================== CONFIGURAÇÃO ====================
try:
    SUPABASE_URL = str(
        st.secrets["SUPABASE_URL"]
    ).strip().rstrip("/")
    SUPABASE_KEY = str(
        st.secrets["SUPABASE_KEY"]
    ).strip()
except Exception:
    st.error(
        "As credenciais SUPABASE_URL e SUPABASE_KEY "
        "não estão configuradas nos Secrets."
    )
    st.stop()

if (
    not SUPABASE_URL.startswith("https://")
    or "/rest/v1" in SUPABASE_URL.lower()
    or not SUPABASE_KEY
):
    st.error(
        "Configuração inválida do Supabase. "
        "A URL deve ser somente a base do projeto."
    )
    st.stop()


# ==================== AUTENTICAÇÃO HTTP ====================
def requisicao_auth_http(
    caminho: str,
    *,
    metodo: str = "POST",
    token: Optional[str] = None,
    json_dados: Optional[dict] = None,
    params: Optional[dict] = None,
    timeout: float = 20.0,
):
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
        "Authorization": (
            f"Bearer {token}"
            if token
            else f"Bearer {SUPABASE_KEY}"
        ),
    }

    return httpx.request(
        metodo,
        f"{SUPABASE_URL}/auth/v1/{caminho.lstrip('/')}",
        headers=headers,
        json=json_dados,
        params=params,
        timeout=timeout,
        follow_redirects=True,
    )


def salvar_sessao(corpo: dict) -> None:
    usuario = corpo.get("user") or {}
    usuario_id = usuario.get("id")
    access_token = corpo.get("access_token")
    refresh_token = corpo.get("refresh_token")

    if not usuario_id or not access_token or not refresh_token:
        raise ValueError(
            "O Supabase não retornou uma sessão completa."
        )

    expires_at = corpo.get("expires_at")
    if not expires_at:
        expires_in = int(corpo.get("expires_in") or 3600)
        expires_at = int(time.time()) + expires_in

    st.session_state["usuario_logado"] = str(usuario_id)
    st.session_state["user_token"] = str(access_token)
    st.session_state["refresh_token"] = str(refresh_token)
    st.session_state["token_expires_at"] = int(expires_at)


def limpar_sessao() -> None:
    st.session_state["usuario_logado"] = None
    st.session_state["user_token"] = None
    st.session_state["refresh_token"] = None
    st.session_state["token_expires_at"] = 0


def renovar_token() -> bool:
    access_token = st.session_state.get("user_token")
    refresh_token = st.session_state.get("refresh_token")
    expires_at = int(
        st.session_state.get("token_expires_at") or 0
    )

    if not access_token or not refresh_token:
        return False

    if expires_at > int(time.time()) + 90:
        return True

    try:
        resposta = requisicao_auth_http(
            "token",
            params={"grant_type": "refresh_token"},
            json_dados={
                "refresh_token": refresh_token
            },
        )

        if resposta.status_code != 200:
            return False

        salvar_sessao(resposta.json())
        return True
    except Exception:
        return False


for chave, valor in {
    "usuario_logado": None,
    "user_token": None,
    "refresh_token": None,
    "token_expires_at": 0,
}.items():
    if chave not in st.session_state:
        st.session_state[chave] = valor


if st.session_state["usuario_logado"] is None:
    st.title("Auditoria do Supabase")
    st.caption(
        "Entre com a mesma conta usada no app financeiro."
    )

    with st.form("form_login_auditoria"):
        email = st.text_input("E-mail:")
        senha = st.text_input(
            "Senha:",
            type="password",
        )
        entrar = st.form_submit_button(
            "Entrar",
            width="stretch",
        )

    if entrar:
        if not email.strip() or not senha:
            st.warning("Preencha e-mail e senha.")
        else:
            try:
                resposta = requisicao_auth_http(
                    "token",
                    params={
                        "grant_type": "password"
                    },
                    json_dados={
                        "email": email.strip(),
                        "password": senha,
                    },
                )

                if resposta.status_code == 200:
                    salvar_sessao(resposta.json())
                    st.rerun()
                else:
                    st.error(
                        "Não foi possível entrar. "
                        "Confira e-mail e senha."
                    )
            except Exception as erro:
                st.error(
                    "Falha no login: "
                    f"{type(erro).__name__}: {erro}"
                )

    st.stop()


if not renovar_token():
    limpar_sessao()
    st.warning(
        "Sua sessão expirou. Entre novamente."
    )
    st.rerun()


USER_ID = st.session_state["usuario_logado"]
TOKEN = st.session_state["user_token"]


# ==================== CONSULTA HTTP ====================
def buscar_todos_registros(
    limite_total: int = 5000,
    tamanho_pagina: int = 1000,
) -> list[dict]:
    url = f"{SUPABASE_URL}/rest/v1/movimentacoes"

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/json",
    }

    todos = []
    inicio = 0

    with httpx.Client(timeout=30.0) as cliente:
        while inicio < limite_total:
            fim = min(
                inicio + tamanho_pagina - 1,
                limite_total - 1,
            )

            resposta = cliente.get(
                url,
                headers={
                    **headers,
                    "Range": f"{inicio}-{fim}",
                },
                params=[
                    (
                        "select",
                        (
                            "id,data,descricao,"
                            "grupo_orcamentario,"
                            "subcategoria,valor,"
                            "satisfacao,tipo,user_id"
                        ),
                    ),
                    ("user_id", f"eq.{USER_ID}"),
                    ("order", "data.desc"),
                ],
            )

            if resposta.status_code not in (200, 206):
                raise RuntimeError(
                    f"Consulta retornou HTTP "
                    f"{resposta.status_code}: "
                    f"{resposta.text[:500]}"
                )

            pagina = resposta.json()

            if not isinstance(pagina, list):
                raise RuntimeError(
                    "O banco retornou um formato inesperado."
                )

            todos.extend(pagina)

            if len(pagina) < tamanho_pagina:
                break

            inicio += tamanho_pagina

    return todos


def moeda(valor) -> str:
    try:
        numero = float(valor)
    except Exception:
        numero = 0.0

    texto = f"{numero:,.2f}"
    texto = (
        texto.replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )
    return f"R$ {texto}"


# ==================== INTERFACE ====================
st.title("Auditoria dos dados financeiros")
st.caption(
    "Esta tela apenas lê o Supabase. "
    "Ela não cria, edita ou exclui registros."
)

if st.sidebar.button(
    "Sair",
    width="stretch",
):
    limpar_sessao()
    st.rerun()

limite_escolhido = st.sidebar.selectbox(
    "Limite máximo de registros:",
    [1000, 3000, 5000],
    index=2,
)

recarregar = st.sidebar.button(
    "Recarregar auditoria",
    width="stretch",
)

try:
    registros = buscar_todos_registros(
        limite_total=int(limite_escolhido)
    )

    df = pd.DataFrame(registros)

    if df.empty:
        st.warning(
            "Nenhum registro foi encontrado para este usuário."
        )
        st.stop()

    colunas = [
        "id",
        "data",
        "descricao",
        "grupo_orcamentario",
        "subcategoria",
        "valor",
        "satisfacao",
        "tipo",
        "user_id",
    ]

    for coluna in colunas:
        if coluna not in df.columns:
            df[coluna] = None

    df["data_dt"] = pd.to_datetime(
        df["data"],
        errors="coerce",
    )
    df["valor_num"] = pd.to_numeric(
        df["valor"],
        errors="coerce",
    ).fillna(0.0)

    df["grupo_limpo"] = (
        df["grupo_orcamentario"]
        .fillna("Sem grupo")
        .astype(str)
        .str.strip()
        .replace("", "Sem grupo")
    )
    df["tipo_limpo"] = (
        df["tipo"]
        .fillna("Sem tipo")
        .astype(str)
        .str.strip()
        .replace("", "Sem tipo")
    )

    data_minima = df["data_dt"].min()
    data_maxima = df["data_dt"].max()

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Registros encontrados",
        f"{len(df):,}".replace(",", "."),
    )
    col2.metric(
        "Valor total bruto",
        moeda(df["valor_num"].sum()),
    )
    col3.metric(
        "Primeira data",
        (
            data_minima.strftime("%d/%m/%Y")
            if pd.notna(data_minima)
            else "Sem data válida"
        ),
    )
    col4.metric(
        "Última data",
        (
            data_maxima.strftime("%d/%m/%Y")
            if pd.notna(data_maxima)
            else "Sem data válida"
        ),
    )

    st.markdown("---")

    st.subheader("Presença dos principais módulos")

    descricao_upper = (
        df["descricao"]
        .fillna("")
        .astype(str)
        .str.upper()
    )
    grupo_upper = (
        df["grupo_orcamentario"]
        .fillna("")
        .astype(str)
        .str.upper()
    )
    satisfacao_upper = (
        df["satisfacao"]
        .fillna("")
        .astype(str)
        .str.upper()
    )
    tipo_upper = (
        df["tipo"]
        .fillna("")
        .astype(str)
        .str.upper()
    )

    resumo_modulos = pd.DataFrame({
        "Módulo": [
            "Agenda",
            "Cartões",
            "Assinaturas",
            "Dívidas",
            "Configurações",
            "Saldo inicial",
            "Porquinhos / Aportes",
        ],
        "Registros": [
            int(
                grupo_upper.str.contains(
                    "AGENDA",
                    na=False,
                ).sum()
            ),
            int(
                (
                    tipo_upper.str.contains(
                        "CARTÃO|CARTAO",
                        regex=True,
                        na=False,
                    )
                    | descricao_upper.str.contains(
                        "[CARTAO:",
                        regex=False,
                        na=False,
                    )
                ).sum()
            ),
            int(
                satisfacao_upper.str.contains(
                    "SUB:",
                    regex=False,
                    na=False,
                ).sum()
            ),
            int(
                (
                    descricao_upper.str.contains(
                        "DIVIDA_ATIVA",
                        regex=False,
                        na=False,
                    )
                    | grupo_upper.str.contains(
                        "DÍVIDA|DIVIDA|QUITAÇÃO|QUITACAO",
                        regex=True,
                        na=False,
                    )
                ).sum()
            ),
            int(
                (
                    descricao_upper.str.contains(
                        "CONFIG_",
                        regex=False,
                        na=False,
                    )
                    | grupo_upper.str.contains(
                        "CONFIG",
                        regex=False,
                        na=False,
                    )
                ).sum()
            ),
            int(
                descricao_upper.str.contains(
                    "CONFIG_SALDO_INICIAL",
                    regex=False,
                    na=False,
                ).sum()
            ),
            int(
                grupo_upper.str.contains(
                    "APORTE|PORQUINHO",
                    regex=True,
                    na=False,
                ).sum()
            ),
        ],
    })

    st.dataframe(
        resumo_modulos,
        width="stretch",
        hide_index=True,
    )

    st.markdown("---")

    col_grupo, col_tipo = st.columns(2)

    with col_grupo:
        st.subheader("Registros por grupo")
        resumo_grupos = (
            df.groupby(
                "grupo_limpo",
                dropna=False,
            )
            .agg(
                Registros=("id", "count"),
                Valor=("valor_num", "sum"),
            )
            .reset_index()
            .rename(
                columns={
                    "grupo_limpo": "Grupo"
                }
            )
            .sort_values(
                "Registros",
                ascending=False,
            )
        )
        resumo_grupos["Valor"] = (
            resumo_grupos["Valor"].apply(moeda)
        )

        st.dataframe(
            resumo_grupos,
            width="stretch",
            hide_index=True,
        )

    with col_tipo:
        st.subheader("Registros por tipo")
        resumo_tipos = (
            df.groupby(
                "tipo_limpo",
                dropna=False,
            )
            .agg(
                Registros=("id", "count"),
                Valor=("valor_num", "sum"),
            )
            .reset_index()
            .rename(
                columns={
                    "tipo_limpo": "Tipo"
                }
            )
            .sort_values(
                "Registros",
                ascending=False,
            )
        )
        resumo_tipos["Valor"] = (
            resumo_tipos["Valor"].apply(moeda)
        )

        st.dataframe(
            resumo_tipos,
            width="stretch",
            hide_index=True,
        )

    st.markdown("---")
    st.subheader("Registros mais recentes")

    tabela = df[
        [
            "data_dt",
            "descricao",
            "grupo_orcamentario",
            "subcategoria",
            "tipo",
            "valor_num",
        ]
    ].copy()

    tabela = tabela.rename(
        columns={
            "data_dt": "Data",
            "descricao": "Descrição",
            "grupo_orcamentario": "Grupo",
            "subcategoria": "Categoria",
            "tipo": "Tipo",
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
    tabela["Valor"] = tabela["Valor"].apply(moeda)

    st.dataframe(
        tabela.head(100),
        width="stretch",
        hide_index=True,
    )

    st.success(
        "Auditoria concluída. Nenhum registro foi alterado."
    )

except httpx.TimeoutException:
    st.error(
        "A consulta ultrapassou 30 segundos."
    )
except httpx.RequestError as erro:
    st.error(
        f"Falha de conexão: {erro}"
    )
except Exception as erro:
    st.error(
        "Falha na auditoria: "
        f"{type(erro).__name__}: {erro}"
    )
