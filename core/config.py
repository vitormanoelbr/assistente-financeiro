import streamlit as st


def carregar_configuracao() -> tuple[str, str]:
    try:
        url = str(st.secrets["SUPABASE_URL"]).strip().rstrip("/")
        chave = str(st.secrets["SUPABASE_KEY"]).strip()
    except Exception as erro:
        raise RuntimeError(
            "As credenciais SUPABASE_URL e SUPABASE_KEY "
            "não estão configuradas nos Secrets."
        ) from erro

    if (
        not url.startswith("https://")
        or "/rest/v1" in url.lower()
        or not chave
    ):
        raise RuntimeError(
            "Configuração inválida do Supabase. "
            "Use somente a URL base do projeto."
        )

    return url, chave
