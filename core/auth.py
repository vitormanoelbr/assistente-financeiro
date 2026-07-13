import time
from typing import Optional

import httpx
import streamlit as st


def inicializar_sessao() -> None:
    padroes = {
        "usuario_logado": None,
        "user_token": None,
        "refresh_token": None,
        "token_expires_at": 0,
    }

    for chave, valor in padroes.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor


def requisicao_auth(
    supabase_url: str,
    supabase_key: str,
    caminho: str,
    *,
    metodo: str = "POST",
    token: Optional[str] = None,
    json_dados: Optional[dict] = None,
    params: Optional[dict] = None,
    timeout: float = 20.0,
) -> httpx.Response:
    headers = {
        "apikey": supabase_key,
        "Content-Type": "application/json",
        "Authorization": (
            f"Bearer {token}"
            if token
            else f"Bearer {supabase_key}"
        ),
    }

    return httpx.request(
        metodo,
        f"{supabase_url}/auth/v1/{caminho.lstrip('/')}",
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


def renovar_token(
    supabase_url: str,
    supabase_key: str,
) -> bool:
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
        resposta = requisicao_auth(
            supabase_url,
            supabase_key,
            "token",
            params={"grant_type": "refresh_token"},
            json_dados={"refresh_token": refresh_token},
        )

        if resposta.status_code != 200:
            return False

        salvar_sessao(resposta.json())
        return True
    except Exception:
        return False


def renderizar_login(
    supabase_url: str,
    supabase_key: str,
) -> None:
    st.title("Meu Planner Financeiro")
    st.caption("Entre para acessar seus dados.")

    with st.form("form_login"):
        email = st.text_input("E-mail:")
        senha = st.text_input("Senha:", type="password")
        entrar = st.form_submit_button(
            "Entrar",
            width="stretch",
        )

    if entrar:
        if not email.strip() or not senha:
            st.warning("Preencha e-mail e senha.")
            return

        try:
            resposta = requisicao_auth(
                supabase_url,
                supabase_key,
                "token",
                params={"grant_type": "password"},
                json_dados={
                    "email": email.strip(),
                    "password": senha,
                },
            )

            if resposta.status_code == 200:
                salvar_sessao(resposta.json())
                st.rerun()

            st.error("E-mail ou senha incorretos.")
        except httpx.TimeoutException:
            st.error("O servidor demorou para responder.")
        except Exception as erro:
            st.error(
                "Falha no login: "
                f"{type(erro).__name__}: {erro}"
            )


def deslogar(
    supabase_url: str,
    supabase_key: str,
) -> None:
    token = st.session_state.get("user_token")

    if token:
        try:
            requisicao_auth(
                supabase_url,
                supabase_key,
                "logout",
                token=token,
            )
        except Exception:
            pass

    limpar_sessao()
    st.rerun()
