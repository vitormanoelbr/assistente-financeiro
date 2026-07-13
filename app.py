import streamlit as st

from core.api import SupabaseRestClient
from core.auth import (
    deslogar,
    inicializar_sessao,
    limpar_sessao,
    renderizar_login,
    renovar_token,
)
from core.config import carregar_configuracao
from pages_app import agenda, diagnostico


st.set_page_config(
    page_title="Meu Planner Financeiro",
    layout="wide",
)

try:
    SUPABASE_URL, SUPABASE_KEY = carregar_configuracao()
except Exception as erro:
    st.error(str(erro))
    st.stop()

inicializar_sessao()

if st.session_state["usuario_logado"] is None:
    renderizar_login(
        SUPABASE_URL,
        SUPABASE_KEY,
    )
    st.stop()

if not renovar_token(
    SUPABASE_URL,
    SUPABASE_KEY,
):
    limpar_sessao()
    st.warning(
        "Sua sessão expirou. Entre novamente."
    )
    st.rerun()

USER_ID = st.session_state["usuario_logado"]
TOKEN = st.session_state["user_token"]

api = SupabaseRestClient(
    SUPABASE_URL,
    SUPABASE_KEY,
    TOKEN,
    USER_ID,
)

if st.sidebar.button(
    "Sair",
    width="stretch",
):
    deslogar(
        SUPABASE_URL,
        SUPABASE_KEY,
    )

st.sidebar.markdown("---")
st.sidebar.header("Navegação")

pagina = st.sidebar.radio(
    "Escolha uma área:",
    [
        "Diagnóstico",
        "Agenda",
    ],
)

st.sidebar.markdown("---")
st.sidebar.caption(
    "Base modular em desenvolvimento. "
    "Cada página consulta somente seus próprios dados."
)

if pagina == "Diagnóstico":
    diagnostico.renderizar(api)
elif pagina == "Agenda":
    agenda.renderizar(api)
