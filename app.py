import streamlit as st
import datetime
import pandas as pd
import plotly.express as px
from supabase import create_client, Client

# Configuração de Layout
st.set_page_config(page_title="Essentia Finance", layout="centered")

# --- CONEXÃO ---
SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- SESSÃO ---
if "user_id" not in st.session_state:
    st.session_state.user_id = None

# --- UI SIMPLES DE TESTE ---
st.title("Essentia Finance - Sistema Limpo")

if st.session_state.user_id is None:
    st.write("Sistema rodando. Aguardando autenticação.")
    # Login básico para teste
    if st.button("Simular Login"):
        st.session_state.user_id = "teste_usuario"
        st.rerun()
else:
    st.success("Usuário logado!")
    if st.button("Sair"):
        st.session_state.user_id = None
        st.rerun()

# --- TESTE DE QUERY ---
try:
    data = supabase.table("movimentacoes").select("*").limit(5).execute()
    st.write("Conexão com Banco OK!")
    st.dataframe(data.data)
except Exception as e:
    st.error(f"Erro ao ler banco: {e}")
