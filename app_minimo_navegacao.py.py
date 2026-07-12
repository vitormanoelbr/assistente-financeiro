import streamlit as st
import datetime
import calendar
import uuid
import time
from typing import Optional
import pandas as pd
import plotly.express as px
import httpx
from supabase import create_client, Client
from supabase.lib.client_options import SyncClientOptions

st.set_page_config(page_title="Meu Planner Financeiro", layout="centered")


def adicionar_meses(data_base: datetime.date, quantidade_meses: int) -> datetime.date:
    """Adiciona meses preservando o dia ou usando o último dia válido do mês."""
    indice_mes = data_base.month - 1 + quantidade_meses
    ano = data_base.year + indice_mes // 12
    mes = indice_mes % 12 + 1
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    dia = min(data_base.day, ultimo_dia)
    return datetime.date(ano, mes, dia)


def normalizar_data(valor):
    """Converte datas do Supabase em date; devolve None para conteúdo inválido."""
    if valor is None:
        return None

    try:
        timestamp = pd.to_datetime(valor, errors="coerce")
    except Exception:
        return None

    try:
        if pd.isna(timestamp):
            return None
    except (TypeError, ValueError):
        return None

    if isinstance(timestamp, pd.Timestamp):
        # Mantém o dia civil informado, sem deslocar pelo fuso horário.
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_localize(None)
        return timestamp.date()

    if isinstance(timestamp, datetime.datetime):
        return timestamp.date()

    if isinstance(timestamp, datetime.date):
        return timestamp

    return None


def normalizar_numero(valor, padrao=0.0):
    """Converte números do banco sem quebrar com None, texto ou pd.NA."""
    try:
        convertido = pd.to_numeric(valor, errors="coerce")
    except Exception:
        return padrao

    try:
        if pd.isna(convertido):
            return padrao
    except (TypeError, ValueError):
        return padrao

    try:
        return float(convertido)
    except (TypeError, ValueError, OverflowError):
        return padrao


def normalizar_texto(valor, padrao=""):
    """Converte valores em texto sem avaliar pd.NA como booleano."""
    if valor is None:
        return padrao

    try:
        if pd.isna(valor):
            return padrao
    except (TypeError, ValueError):
        pass

    texto = str(valor).strip()
    return texto if texto else padrao


def extrair_metadado_agenda(texto: str, chave: str) -> Optional[str]:
    """Lê metadados gravados no campo satisfação sem exigir nova tabela."""
    prefixo = f"{chave}:"

    for parte in str(texto or "").split("|"):
        parte_limpa = parte.strip()

        if parte_limpa.startswith(prefixo):
            return parte_limpa.split(":", 1)[1].strip()

    return None


def inserir_agendamentos_com_seguranca(
    cliente_supabase,
    registros,
    user_id: str,
    serie_id: Optional[str] = None
) -> int:
    """Insere cada compromisso separadamente e desfaz a série se algo falhar."""
    ids_inseridos = []

    try:
        for registro in registros:
            resposta = (
                cliente_supabase
                .table("movimentacoes")
                .insert(registro)
                .execute()
            )

            dados_resposta = getattr(resposta, "data", None) or []

            for item in dados_resposta:
                if isinstance(item, dict) and item.get("id") is not None:
                    ids_inseridos.append(item["id"])

        return len(registros)

    except Exception:
        # Primeiro tenta remover pelos IDs devolvidos pela API.
        for id_inserido in ids_inseridos:
            try:
                (
                    cliente_supabase
                    .table("movimentacoes")
                    .delete()
                    .eq("id", id_inserido)
                    .eq("user_id", user_id)
                    .execute()
                )
            except Exception:
                pass

        # Fallback para respostas sem representação dos registros inseridos.
        if serie_id:
            try:
                (
                    cliente_supabase
                    .table("movimentacoes")
                    .delete()
                    .eq("user_id", user_id)
                    .ilike("satisfacao", f"%S:{serie_id}%")
                    .execute()
                )
            except Exception:
                pass

        raise


def inserir_assinaturas_com_seguranca(
    cliente_supabase,
    registros,
    user_id: str,
    serie_id: str
) -> int:
    """Grava cobranças mensais uma a uma e remove a série se houver falha."""
    ids_inseridos = []

    try:
        for registro in registros:
            resposta = (
                cliente_supabase
                .table("movimentacoes")
                .insert(registro)
                .execute()
            )

            dados_resposta = getattr(resposta, "data", None) or []

            for item in dados_resposta:
                if isinstance(item, dict) and item.get("id") is not None:
                    ids_inseridos.append(item["id"])

        return len(registros)

    except Exception:
        for id_inserido in ids_inseridos:
            try:
                (
                    cliente_supabase
                    .table("movimentacoes")
                    .delete()
                    .eq("id", id_inserido)
                    .eq("user_id", user_id)
                    .execute()
                )
            except Exception:
                pass

        try:
            (
                cliente_supabase
                .table("movimentacoes")
                .delete()
                .eq("user_id", user_id)
                .ilike("satisfacao", f"%SUB:{serie_id}%")
                .execute()
            )
        except Exception:
            pass

        raise

# --- 🔐 CONEXÃO COM BANCO E AUTENTICAÇÃO ESTÁVEL ---
try:
    SUPABASE_URL = str(st.secrets["SUPABASE_URL"]).strip().rstrip("/")
    SUPABASE_KEY = str(st.secrets["SUPABASE_KEY"]).strip()
except Exception:
    st.error(
        "❌ Erro de Segurança: as credenciais não foram configuradas "
        "no painel do Streamlit."
    )
    st.stop()

if (
    not SUPABASE_URL.startswith("https://")
    or "/rest/v1" in SUPABASE_URL.lower()
    or not SUPABASE_KEY
):
    st.error(
        "❌ Configuração inválida do Supabase. A URL deve conter apenas "
        "a base do projeto, por exemplo: https://projeto.supabase.co"
    )
    st.stop()


def requisicao_auth_http(
    caminho: str,
    *,
    metodo: str = "POST",
    token: Optional[str] = None,
    json_dados: Optional[dict] = None,
    params: Optional[dict] = None,
    timeout: float = 20.0,
):
    """Faz chamadas ao Supabase Auth sem usar o SDK de autenticação."""
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
    }

    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        headers["Authorization"] = f"Bearer {SUPABASE_KEY}"

    url = f"{SUPABASE_URL}/auth/v1/{caminho.lstrip('/')}"

    return httpx.request(
        metodo,
        url,
        headers=headers,
        json=json_dados,
        params=params,
        timeout=timeout,
        follow_redirects=True,
    )


def extrair_mensagem_auth(resposta: httpx.Response) -> str:
    """Extrai uma mensagem legível da resposta de autenticação."""
    try:
        corpo = resposta.json()
    except Exception:
        return resposta.text.strip() or f"Erro HTTP {resposta.status_code}"

    if isinstance(corpo, dict):
        return str(
            corpo.get("msg")
            or corpo.get("message")
            or corpo.get("error_description")
            or corpo.get("error")
            or f"Erro HTTP {resposta.status_code}"
        )

    return f"Erro HTTP {resposta.status_code}"


def salvar_sessao_http(corpo: dict):
    """Guarda somente valores simples e seguros no session_state."""
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


def limpar_sessao_local():
    """Remove somente dados simples da autenticação."""
    st.session_state["usuario_logado"] = None
    st.session_state["user_token"] = None
    st.session_state["refresh_token"] = None
    st.session_state["token_expires_at"] = 0


def renovar_token_se_necessario() -> bool:
    """Renova o token por HTTP apenas quando estiver perto de expirar."""
    access_token = st.session_state.get("user_token")
    refresh_token = st.session_state.get("refresh_token")
    expires_at = int(st.session_state.get("token_expires_at") or 0)

    if not access_token or not refresh_token:
        return False

    # Mantém 90 segundos de margem.
    if expires_at > int(time.time()) + 90:
        return True

    try:
        resposta = requisicao_auth_http(
            "token",
            params={"grant_type": "refresh_token"},
            json_dados={"refresh_token": refresh_token},
        )

        if resposta.status_code != 200:
            return False

        corpo = resposta.json()
        salvar_sessao_http(corpo)
        return True

    except Exception:
        return False


def criar_cliente_banco(access_token: str) -> Client:
    """Cria um cliente temporário para este rerun.

    O cliente não é armazenado no session_state e não persiste sessão.
    A autenticação do Data API é feita diretamente pelo header Bearer.
    """
    opcoes = SyncClientOptions(
        headers={
            "Authorization": f"Bearer {access_token}",
        },
        auto_refresh_token=False,
        persist_session=False,
    )

    return create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options=opcoes,
    )


for chave, valor_padrao in {
    "usuario_logado": None,
    "user_token": None,
    "refresh_token": None,
    "token_expires_at": 0,
}.items():
    if chave not in st.session_state:
        st.session_state[chave] = valor_padrao


def deslogar_usuario():
    token_atual = st.session_state.get("user_token")

    if token_atual:
        try:
            requisicao_auth_http(
                "logout",
                token=token_atual,
            )
        except Exception:
            pass

    limpar_sessao_local()
    st.query_params.clear()
    st.rerun()


# ==================== TELA DE AUTENTICAÇÃO ====================
if st.session_state["usuario_logado"] is None:
    st.title("📲 Bem-vindo ao Meu Planner Financeiro")
    st.caption(
        "Acesse sua conta para gerenciar suas finanças com segurança."
    )

    aba_login, aba_cadastro = st.tabs(
        ["🔐 Entrar na Conta", "🚀 Criar Nova Conta"]
    )

    with aba_login:
        with st.form("form_login"):
            email_login = st.text_input(
                "E-mail:",
                placeholder="seu@email.com"
            )
            senha_login = st.text_input(
                "Senha:",
                type="password",
                placeholder="******"
            )
            botao_login = st.form_submit_button("Acessar Painel")

        if botao_login:
            email_limpo = str(email_login or "").strip()

            if not email_limpo or not senha_login:
                st.warning("Preencha todos os campos.")
            else:
                try:
                    resposta = requisicao_auth_http(
                        "token",
                        params={"grant_type": "password"},
                        json_dados={
                            "email": email_limpo,
                            "password": senha_login,
                        },
                    )

                    if resposta.status_code == 200:
                        salvar_sessao_http(resposta.json())
                        st.query_params.clear()
                        st.success(
                            "🎉 Acesso autorizado! Redirecionando..."
                        )
                        st.rerun()
                    elif resposta.status_code in (400, 401):
                        st.error(
                            "❌ E-mail ou senha incorretos."
                        )
                    else:
                        st.error(
                            "❌ Não foi possível entrar: "
                            f"{extrair_mensagem_auth(resposta)}"
                        )

                except httpx.TimeoutException:
                    st.error(
                        "❌ O servidor demorou para responder. "
                        "Tente novamente em alguns segundos."
                    )
                except httpx.RequestError as erro:
                    st.error(
                        "❌ Falha de conexão com o Supabase: "
                        f"{erro}"
                    )
                except Exception as erro:
                    st.error(
                        "❌ Erro inesperado durante o login: "
                        f"{type(erro).__name__}: {erro}"
                    )

    with aba_cadastro:
        with st.form("form_cadastro"):
            email_cad = st.text_input(
                "Escolha um E-mail:",
                placeholder="seu@email.com"
            )
            senha_cad = st.text_input(
                "Escolha uma Senha (mínimo 6 caracteres):",
                type="password",
                placeholder="******"
            )
            botao_cad = st.form_submit_button(
                "Cadastrar e Criar Plataforma"
            )

        if botao_cad:
            email_cad_limpo = str(email_cad or "").strip()

            if not email_cad_limpo or len(senha_cad or "") < 6:
                st.warning(
                    "O e-mail precisa ser válido e a senha ter "
                    "no mínimo 6 caracteres."
                )
            else:
                try:
                    resposta = requisicao_auth_http(
                        "signup",
                        json_dados={
                            "email": email_cad_limpo,
                            "password": senha_cad,
                        },
                    )

                    if resposta.status_code in (200, 201):
                        corpo_cadastro = resposta.json()

                        if corpo_cadastro.get("access_token"):
                            salvar_sessao_http(corpo_cadastro)
                            st.success(
                                "✅ Conta criada e autenticada."
                            )
                            st.rerun()
                        else:
                            st.success(
                                "✅ Conta criada. Verifique seu e-mail "
                                "se a confirmação estiver habilitada e "
                                "depois entre pela aba de login."
                            )
                    else:
                        st.error(
                            "Erro ao cadastrar: "
                            f"{extrair_mensagem_auth(resposta)}"
                        )

                except httpx.TimeoutException:
                    st.error(
                        "O servidor demorou para responder. "
                        "Tente novamente."
                    )
                except httpx.RequestError as erro:
                    st.error(
                        "Falha de conexão ao cadastrar: "
                        f"{erro}"
                    )
                except Exception as erro:
                    st.error(
                        "Erro inesperado ao cadastrar: "
                        f"{type(erro).__name__}: {erro}"
                    )

    st.stop()


# Renova somente quando necessário e cria um cliente novo neste rerun.
if not renovar_token_se_necessario():
    limpar_sessao_local()
    st.warning(
        "🔒 Sua sessão expirou. Entre novamente para continuar."
    )
    st.rerun()

try:
    supabase: Client = criar_cliente_banco(
        st.session_state["user_token"]
    )
except Exception as erro:
    st.error(
        "Falha ao preparar a conexão com o banco: "
        f"{type(erro).__name__}: {erro}"
    )
    st.stop()



# ==================== APP MÍNIMO DE NAVEGAÇÃO ====================
USER_ID = st.session_state["usuario_logado"]

if st.sidebar.button("🚪 Sair da Conta", width="stretch"):
    deslogar_usuario()

st.sidebar.markdown("---")
st.sidebar.header("Navegação")

PAGINAS_TESTE = [
    "Diagnóstico",
    "Fluxo de Caixa",
    "Cartões",
    "Painel e Lançamentos",
    "Porquinhos",
    "Agenda",
    "Dívidas",
]

pagina_teste = st.sidebar.radio(
    "Escolha uma página:",
    PAGINAS_TESTE,
    key="pagina_teste_minimo"
)

st.sidebar.markdown("---")
st.sidebar.caption(
    "Este é um app mínimo. Nenhum cálculo financeiro pesado é executado."
)

st.title("Teste de estabilidade")
st.caption(
    "Troque entre as páginas várias vezes. "
    "Se este app permanecer aberto, a navegação e a autenticação estão estáveis."
)

if pagina_teste == "Diagnóstico":
    st.header("Diagnóstico")
    st.success("Página Diagnóstico carregada.")

elif pagina_teste == "Fluxo de Caixa":
    st.header("Fluxo de Caixa")
    st.success("Página Fluxo de Caixa carregada.")

elif pagina_teste == "Cartões":
    st.header("Cartões")
    st.success("Página Cartões carregada.")

elif pagina_teste == "Painel e Lançamentos":
    st.header("Painel e Lançamentos")
    st.success("Página Painel e Lançamentos carregada.")

elif pagina_teste == "Porquinhos":
    st.header("Porquinhos")
    st.success("Página Porquinhos carregada.")

elif pagina_teste == "Agenda":
    st.header("Agenda")
    st.success("Página Agenda carregada.")

elif pagina_teste == "Dívidas":
    st.header("Dívidas")
    st.success("Página Dívidas carregada.")

st.markdown("---")

col1, col2 = st.columns(2)

col1.metric(
    "Usuário autenticado",
    "Sim"
)

col2.metric(
    "Página atual",
    pagina_teste
)

st.info(
    "Teste sugerido: troque de página 20 vezes, espere 10 segundos "
    "em cada uma e depois saia e entre novamente."
)
