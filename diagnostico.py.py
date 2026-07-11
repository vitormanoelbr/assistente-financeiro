import os
import platform
import socket
import sys
from urllib.parse import urlparse

import streamlit as st

st.set_page_config(
    page_title="Diagnóstico Streamlit e Supabase",
    layout="centered"
)

st.title("Diagnóstico técnico")
st.caption(
    "Este arquivo isola Streamlit, dependências, DNS, Supabase e autenticação."
)

st.success("Etapa 1 concluída: o Streamlit iniciou e renderizou a página.")

st.subheader("1. Ambiente")
st.code(
    "\n".join([
        f"Python: {sys.version}",
        f"Plataforma: {platform.platform()}",
        f"Processo: {os.getpid()}",
    ]),
    language="text"
)

st.subheader("2. Importação das dependências")

resultado_importacoes = []

try:
    import numpy as np
    resultado_importacoes.append(f"NumPy: {np.__version__}")
except Exception as erro:
    resultado_importacoes.append(
        f"NumPy: ERRO - {type(erro).__name__}: {erro}"
    )

try:
    import pandas as pd
    resultado_importacoes.append(f"Pandas: {pd.__version__}")
except Exception as erro:
    resultado_importacoes.append(
        f"Pandas: ERRO - {type(erro).__name__}: {erro}"
    )

try:
    import plotly
    resultado_importacoes.append(f"Plotly: {plotly.__version__}")
except Exception as erro:
    resultado_importacoes.append(
        f"Plotly: ERRO - {type(erro).__name__}: {erro}"
    )

try:
    import pyarrow
    resultado_importacoes.append(f"PyArrow: {pyarrow.__version__}")
except Exception as erro:
    resultado_importacoes.append(
        f"PyArrow: ERRO - {type(erro).__name__}: {erro}"
    )

try:
    import supabase as supabase_pacote
    versao_supabase = getattr(
        supabase_pacote,
        "__version__",
        "não informada"
    )
    resultado_importacoes.append(f"Supabase: {versao_supabase}")
except Exception as erro:
    resultado_importacoes.append(
        f"Supabase: ERRO - {type(erro).__name__}: {erro}"
    )

st.code("\n".join(resultado_importacoes), language="text")

st.subheader("3. Leitura dos Secrets")

supabase_url = str(st.secrets.get("SUPABASE_URL", "")).strip()
supabase_key = str(st.secrets.get("SUPABASE_KEY", "")).strip()

if not supabase_url:
    st.error("SUPABASE_URL não foi encontrada nos Secrets.")
    st.stop()

if not supabase_key:
    st.error("SUPABASE_KEY não foi encontrada nos Secrets.")
    st.stop()

url_analisada = urlparse(supabase_url)
host_supabase = url_analisada.hostname

st.write(f"URL configurada: `{supabase_url}`")
st.write(f"Host identificado: `{host_supabase}`")
st.write(
    "Chave encontrada: "
    f"`{supabase_key[:12]}...{supabase_key[-4:]}`"
)

if (
    url_analisada.scheme != "https"
    or not host_supabase
    or url_analisada.path not in ("", "/")
):
    st.error(
        "A URL deve conter somente a base do projeto, por exemplo: "
        "https://projeto.supabase.co"
    )
    st.stop()

st.subheader("4. Teste de DNS")

if st.button("Testar DNS", width="stretch"):
    try:
        enderecos = socket.getaddrinfo(
            host_supabase,
            443,
            type=socket.SOCK_STREAM
        )
        ips = sorted({
            item[4][0]
            for item in enderecos
            if item and item[4]
        })

        st.success("DNS resolvido corretamente.")
        st.code("\n".join(ips), language="text")

    except Exception as erro:
        st.error("Falha ao resolver o endereço do Supabase.")
        st.code(
            f"{type(erro).__name__}: {erro}",
            language="text"
        )

st.subheader("5. Teste HTTP do Supabase")

if st.button("Testar endpoint de autenticação", width="stretch"):
    try:
        import httpx

        resposta = httpx.get(
            f"{supabase_url.rstrip('/')}/auth/v1/health",
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
            },
            timeout=15.0,
            follow_redirects=True
        )

        st.write(f"Status HTTP: `{resposta.status_code}`")
        st.code(
            resposta.text[:1000] or "(resposta vazia)",
            language="text"
        )

        if resposta.status_code < 500:
            st.success(
                "O servidor Supabase respondeu. "
                "DNS, rede e URL estão funcionais."
            )
        else:
            st.error("O Supabase respondeu com erro de servidor.")

    except Exception as erro:
        st.error("Falha na comunicação HTTP com o Supabase.")
        st.code(
            f"{type(erro).__name__}: {erro}",
            language="text"
        )

st.subheader("6. Teste do cliente Supabase")

if st.button("Criar cliente Supabase", width="stretch"):
    try:
        from supabase import create_client

        cliente = create_client(
            supabase_url,
            supabase_key
        )

        st.session_state["cliente_diagnostico"] = cliente
        st.success("Cliente Supabase criado sem erro.")

    except Exception as erro:
        st.error("Falha ao criar o cliente Supabase.")
        st.code(
            f"{type(erro).__name__}: {erro}",
            language="text"
        )

st.subheader("7. Teste opcional de autenticação")
st.warning(
    "Use este teste somente depois de trocar a senha que apareceu no print."
)

with st.form("form_login_diagnostico"):
    email = st.text_input("E-mail")
    senha = st.text_input("Senha", type="password")
    testar_login = st.form_submit_button(
        "Testar login",
        width="stretch"
    )

if testar_login:
    if not email.strip() or not senha:
        st.warning("Informe e-mail e senha.")
    else:
        try:
            from supabase import create_client

            cliente_login = create_client(
                supabase_url,
                supabase_key
            )

            resposta_login = (
                cliente_login.auth.sign_in_with_password({
                    "email": email.strip(),
                    "password": senha,
                })
            )

            usuario = getattr(resposta_login, "user", None)

            if usuario is None:
                st.error(
                    "O Supabase não retornou um usuário autenticado."
                )
            else:
                st.success(
                    "Autenticação concluída. "
                    f"Usuário: {getattr(usuario, 'id', 'ID indisponível')}"
                )

        except Exception as erro:
            st.error("Falha no teste de autenticação.")
            st.code(
                f"{type(erro).__name__}: {erro}",
                language="text"
            )

st.markdown("---")
st.info(
    "Se este aplicativo permanecer estável, o problema está no app.py "
    "principal. Se ele também causar Segmentation fault, o problema está "
    "no ambiente ou em alguma dependência."
)
