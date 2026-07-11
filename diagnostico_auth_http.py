import json
import platform
import socket
import sys
from urllib.parse import urlparse

import httpx
import streamlit as st

st.set_page_config(
    page_title="Diagnóstico de autenticação",
    layout="centered"
)

st.title("Diagnóstico de autenticação")
st.caption(
    "Teste isolado sem guardar o cliente Supabase no session_state "
    "e sem usar o SDK no login."
)

st.success("Streamlit iniciou corretamente.")

supabase_url = str(st.secrets.get("SUPABASE_URL", "")).strip().rstrip("/")
supabase_key = str(st.secrets.get("SUPABASE_KEY", "")).strip()

st.subheader("1. Ambiente")
st.code(
    "\n".join([
        f"Python: {sys.version.split()[0]}",
        f"Plataforma: {platform.platform()}",
        f"URL: {supabase_url}",
    ]),
    language="text"
)

if not supabase_url or not supabase_key:
    st.error("SUPABASE_URL ou SUPABASE_KEY ausentes.")
    st.stop()

url_analisada = urlparse(supabase_url)

if (
    url_analisada.scheme != "https"
    or not url_analisada.hostname
    or url_analisada.path not in ("", "/")
):
    st.error(
        "SUPABASE_URL inválida. Use somente "
        "https://projeto.supabase.co"
    )
    st.stop()

st.subheader("2. DNS")

try:
    enderecos = socket.getaddrinfo(
        url_analisada.hostname,
        443,
        type=socket.SOCK_STREAM
    )
    ips = sorted({
        item[4][0]
        for item in enderecos
        if item and item[4]
    })
    st.success("DNS resolvido.")
    st.code("\n".join(ips), language="text")
except Exception as erro:
    st.error("Falha no DNS.")
    st.code(f"{type(erro).__name__}: {erro}", language="text")
    st.stop()

st.subheader("3. Login via HTTP direto")
st.info(
    "Este teste não usa supabase.auth.sign_in_with_password. "
    "Ele chama diretamente o endpoint oficial de autenticação."
)

with st.form("login_http"):
    email = st.text_input("E-mail")
    senha = st.text_input("Senha", type="password")
    enviar = st.form_submit_button("Testar login HTTP", width="stretch")

if enviar:
    if not email.strip() or not senha:
        st.warning("Informe e-mail e senha.")
    else:
        try:
            resposta = httpx.post(
                (
                    f"{supabase_url}/auth/v1/token"
                    "?grant_type=password"
                ),
                headers={
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "email": email.strip(),
                    "password": senha,
                },
                timeout=20.0,
            )

            st.write(f"Status HTTP: `{resposta.status_code}`")

            try:
                corpo = resposta.json()
            except Exception:
                corpo = {"resposta": resposta.text[:1000]}

            if resposta.status_code == 200:
                usuario = corpo.get("user") or {}
                sessao = corpo

                st.success("Login HTTP concluído com sucesso.")
                st.write(
                    "Usuário:",
                    usuario.get("id", "ID não informado")
                )
                st.write(
                    "Access token recebido:",
                    "sim" if sessao.get("access_token") else "não"
                )
                st.write(
                    "Refresh token recebido:",
                    "sim" if sessao.get("refresh_token") else "não"
                )

                st.warning(
                    "Os tokens não foram armazenados no session_state."
                )
            else:
                mensagem = (
                    corpo.get("msg")
                    or corpo.get("message")
                    or corpo.get("error_description")
                    or corpo.get("error")
                    or json.dumps(corpo, ensure_ascii=False)
                )
                st.error(f"Falha no login: {mensagem}")

        except Exception as erro:
            st.error("Falha na chamada HTTP.")
            st.code(
                f"{type(erro).__name__}: {erro}",
                language="text"
            )

st.markdown("---")
st.info(
    "Se este login funcionar sem derrubar o app, a falha está no uso "
    "do SDK Supabase ou no armazenamento do cliente no session_state."
)
