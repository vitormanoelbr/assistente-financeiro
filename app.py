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




# ==================== TESTE CONTROLADO: DIAGNÓSTICO ====================
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
    key="pagina_teste_diagnostico"
)

st.sidebar.markdown("---")
st.sidebar.caption(
    "Etapa atual: Diagnóstico e Agenda consultam dados. "
    "As demais páginas continuam vazias."
)

NOMES_MESES = {
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


def buscar_movimentacoes_mes_http(
    user_id: str,
    ano: int,
    mes: int,
) -> list[dict]:
    """Busca somente os registros do mês selecionado via REST HTTP."""
    primeiro_dia = datetime.date(ano, mes, 1)

    if mes == 12:
        proximo_mes = datetime.date(ano + 1, 1, 1)
    else:
        proximo_mes = datetime.date(ano, mes + 1, 1)

    url = f"{SUPABASE_URL}/rest/v1/movimentacoes"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {st.session_state['user_token']}",
        "Accept": "application/json",
    }
    parametros = {
        "select": (
            "id,data,descricao,grupo_orcamentario,"
            "subcategoria,valor,satisfacao,tipo,user_id"
        ),
        "user_id": f"eq.{user_id}",
        "data": (
            f"gte.{primeiro_dia.isoformat()},"
            f"lt.{proximo_mes.isoformat()}"
        ),
        "order": "data.asc",
        "limit": "1000",
    }

    # O PostgREST não aceita dois filtros da mesma coluna dentro
    # de um único parâmetro. Montamos a query explicitamente.
    query = (
        f"?select={parametros['select']}"
        f"&user_id=eq.{user_id}"
        f"&data=gte.{primeiro_dia.isoformat()}"
        f"&data=lt.{proximo_mes.isoformat()}"
        f"&order=data.asc"
        f"&limit=1000"
    )

    with httpx.Client(timeout=20.0) as cliente:
        resposta = cliente.get(
            url + query,
            headers=headers,
        )

    if resposta.status_code != 200:
        detalhe = resposta.text[:500]
        raise RuntimeError(
            f"Consulta retornou HTTP {resposta.status_code}: {detalhe}"
        )

    dados = resposta.json()
    if not isinstance(dados, list):
        raise RuntimeError("O banco retornou um formato inesperado.")

    return dados



# ==================== REGRAS E HTTP DO PAINEL DE LANÇAMENTOS ====================
def _texto_normalizado_busca(valor) -> str:
    """Normaliza texto para comparações case-insensitive e sem acentos."""
    texto = normalizar_texto(valor)
    if not texto:
        return ""

    import unicodedata

    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        caractere for caractere in texto
        if not unicodedata.combining(caractere)
    )
    return texto.upper()


def _valor_registro(registro, chave):
    if isinstance(registro, dict):
        return registro.get(chave)

    try:
        return registro[chave]
    except Exception:
        return None


def eh_registro_agenda(registro) -> bool:
    """Identifica compromissos administrativos da Agenda, não baixas reais."""
    grupo = _texto_normalizado_busca(_valor_registro(registro, "grupo_orcamentario"))
    descricao = _texto_normalizado_busca(_valor_registro(registro, "descricao"))

    return "AGENDA" in grupo or "[AGENDA COMPROMISSO]" in descricao


def eh_registro_administrativo(registro) -> bool:
    """Identifica registros reservados de configuração/administração."""
    grupo = _texto_normalizado_busca(_valor_registro(registro, "grupo_orcamentario"))
    descricao = _texto_normalizado_busca(_valor_registro(registro, "descricao"))

    marcadores_descricao = ("CONFIG_PERFIL", "CONFIG_CARTAO", "DIVIDA_ATIVA")
    return (
        any(marcador in descricao for marcador in marcadores_descricao)
        or "CONFIGURAC" in grupo
    )


def eh_lancamento_real(registro) -> bool:
    """Retorna True somente para lançamentos financeiros reais."""
    return (
        not eh_registro_agenda(registro)
        and not eh_registro_administrativo(registro)
    )


def filtrar_lancamentos_reais_df(df):
    """Remove Agenda e registros administrativos de um DataFrame."""
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()

    mascara = df.apply(eh_lancamento_real, axis=1)
    return df.loc[mascara].copy()


def calcular_resumo_lancamentos(df) -> dict:
    """Calcula totais financeiros a partir dos lançamentos informados."""
    resumo = {
        "entradas": 0.0,
        "saidas_dinheiro": 0.0,
        "cartao": 0.0,
        "despesas_totais": 0.0,
        "saldo": 0.0,
    }

    if df is None or df.empty:
        return resumo

    for _, registro in df.iterrows():
        valor = normalizar_numero(registro.get("valor"), 0.0)
        classe = classificar_movimento(registro.get("tipo"))

        if classe == "entrada":
            resumo["entradas"] += valor
        elif classe == "cartao":
            resumo["cartao"] += valor
        else:
            resumo["saidas_dinheiro"] += valor

    resumo["despesas_totais"] = resumo["saidas_dinheiro"] + resumo["cartao"]
    resumo["saldo"] = resumo["entradas"] - resumo["despesas_totais"]
    return resumo


def _headers_movimentacoes(prefer: bool = False, content_type: bool = False) -> dict:
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {st.session_state['user_token']}",
        "Accept": "application/json",
    }
    if content_type:
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = "return=representation"
    return headers


def _url_movimentacoes() -> str:
    return f"{SUPABASE_URL}/rest/v1/movimentacoes"


def _primeiro_dia_mes_seguinte(ano: int, mes: int) -> datetime.date:
    if mes == 12:
        return datetime.date(ano + 1, 1, 1)
    return datetime.date(ano, mes + 1, 1)


def buscar_lancamentos_painel_http(user_id: str, ano: int, mes: int) -> list[dict]:
    """Busca lançamentos reais mensais do usuário via REST paginado."""
    if not normalizar_texto(user_id):
        raise ValueError("user_id é obrigatório.")

    primeiro_dia = datetime.date(ano, mes, 1)
    proximo_mes = _primeiro_dia_mes_seguinte(ano, mes)
    tamanho_pagina = 1000
    inicio = 0
    registros = []

    parametros = [
        ("select", "id,data,descricao,grupo_orcamentario,subcategoria,valor,satisfacao,tipo,user_id"),
        ("user_id", f"eq.{user_id}"),
        ("data", f"gte.{primeiro_dia.isoformat()}"),
        ("data", f"lt.{proximo_mes.isoformat()}"),
        ("order", "data.asc"),
    ]

    with httpx.Client(timeout=20.0) as cliente:
        while True:
            fim = inicio + tamanho_pagina - 1
            headers = _headers_movimentacoes()
            headers["Range"] = f"{inicio}-{fim}"
            resposta = cliente.get(_url_movimentacoes(), headers=headers, params=parametros)

            if resposta.status_code not in (200, 206):
                detalhe = resposta.text[:500]
                raise RuntimeError(f"Consulta retornou HTTP {resposta.status_code}: {detalhe}")

            dados = resposta.json()
            if not isinstance(dados, list):
                raise RuntimeError("O banco retornou um formato inesperado.")

            registros.extend(dados)
            if len(dados) < tamanho_pagina:
                break
            inicio += tamanho_pagina

    return [registro for registro in registros if eh_lancamento_real(registro)]




def formatar_moeda_br(valor) -> str:
    numero = normalizar_numero(valor, 0.0)
    texto = f"R$ {numero:,.2f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def preparar_dataframe_painel_lancamentos(registros: list[dict]):
    colunas_painel = [
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
    df = pd.DataFrame(registros).copy()

    for coluna in colunas_painel:
        if coluna not in df.columns:
            df[coluna] = None

    df = df[colunas_painel].copy()
    df["data_dt"] = pd.to_datetime(df["data"], errors="coerce")
    df["valor_num"] = df["valor"].apply(lambda valor: normalizar_numero(valor, 0.0))
    df["classe"] = df["tipo"].apply(classificar_movimento)
    return df


def rotulo_classe_movimento(classe: str) -> str:
    rotulos = {
        "entrada": "Entrada",
        "saida": "Saída",
        "cartao": "Cartão",
    }
    return rotulos.get(classe, classe)


def validar_dados_lancamento(descricao, grupo_orcamentario, subcategoria, tipo, valor) -> list[str]:
    erros = []
    if not normalizar_texto(descricao):
        erros.append("Descrição é obrigatória.")
    if not normalizar_texto(grupo_orcamentario):
        erros.append("Grupo orçamentário é obrigatório.")
    if not normalizar_texto(subcategoria):
        erros.append("Subcategoria é obrigatória.")
    if not normalizar_texto(tipo):
        erros.append("Tipo é obrigatório.")
    if normalizar_numero(valor, 0.0) <= 0:
        erros.append("Valor deve ser maior que zero.")

    if "AGENDA" in _texto_normalizado_busca(grupo_orcamentario) or "CONFIGURAC" in _texto_normalizado_busca(grupo_orcamentario):
        erros.append("Grupo reservado não pode ser usado em lançamentos reais.")

    descricao_norm = _texto_normalizado_busca(descricao)
    for marcador in ("[AGENDA COMPROMISSO]", "CONFIG_PERFIL", "CONFIG_CARTAO", "DIVIDA_ATIVA"):
        if marcador in descricao_norm:
            erros.append("Descrição contém marcador reservado.")
            break

    return erros


def _payload_lancamento(data_lancamento, descricao, tipo, grupo_orcamentario, subcategoria, valor, satisfacao="") -> dict:
    data = data_lancamento.isoformat() if hasattr(data_lancamento, "isoformat") else str(data_lancamento)
    return {
        "data": data,
        "descricao": normalizar_texto(descricao),
        "grupo_orcamentario": normalizar_texto(grupo_orcamentario),
        "subcategoria": normalizar_texto(subcategoria),
        "valor": float(valor),
        "satisfacao": normalizar_texto(satisfacao),
        "tipo": normalizar_texto(tipo),
    }


def _extrair_um_registro(resposta, acao: str) -> dict:
    dados = resposta.json()
    if not isinstance(dados, list) or len(dados) != 1 or not isinstance(dados[0], dict):
        raise RuntimeError(f"{acao} deve retornar exatamente um registro.")
    return dados[0]


def cadastrar_lancamento_http(user_id, data_lancamento, descricao, tipo, grupo_orcamentario, subcategoria, valor, satisfacao="") -> dict:
    payload = _payload_lancamento(data_lancamento, descricao, tipo, grupo_orcamentario, subcategoria, valor, satisfacao)
    payload["user_id"] = user_id
    with httpx.Client(timeout=20.0) as cliente:
        resposta = cliente.post(_url_movimentacoes(), headers=_headers_movimentacoes(prefer=True, content_type=True), json=payload)
    if resposta.status_code not in (200, 201):
        raise RuntimeError(f"Cadastro retornou HTTP {resposta.status_code}: {resposta.text[:500]}")
    registro = _extrair_um_registro(resposta, "Cadastro")
    if registro.get("id") is None:
        raise RuntimeError("Cadastro não retornou id do registro.")
    return registro


def atualizar_lancamento_http(lancamento_id, user_id, data_lancamento, descricao, tipo, grupo_orcamentario, subcategoria, valor, satisfacao="") -> dict:
    payload = _payload_lancamento(data_lancamento, descricao, tipo, grupo_orcamentario, subcategoria, valor, satisfacao)
    params = [("id", f"eq.{lancamento_id}"), ("user_id", f"eq.{user_id}")]
    with httpx.Client(timeout=20.0) as cliente:
        resposta = cliente.patch(_url_movimentacoes(), headers=_headers_movimentacoes(prefer=True, content_type=True), params=params, json=payload)
    if resposta.status_code not in (200, 204):
        raise RuntimeError(f"Edição retornou HTTP {resposta.status_code}: {resposta.text[:500]}")
    return _extrair_um_registro(resposta, "Edição")


def excluir_lancamento_http(lancamento_id, user_id) -> dict:
    params = [("id", f"eq.{lancamento_id}"), ("user_id", f"eq.{user_id}")]
    with httpx.Client(timeout=20.0) as cliente:
        resposta = cliente.delete(_url_movimentacoes(), headers=_headers_movimentacoes(prefer=True), params=params)
    if resposta.status_code not in (200, 204):
        raise RuntimeError(f"Exclusão retornou HTTP {resposta.status_code}: {resposta.text[:500]}")
    return _extrair_um_registro(resposta, "Exclusão")


def buscar_agenda_http(
    user_id: str,
    modo: str,
    ano: int,
    mes: int,
) -> list[dict]:
    """Busca somente compromissos da Agenda via REST HTTP."""
    hoje = datetime.date.today()

    if modo == "Próximos 90 dias":
        data_inicial = hoje
        data_final = hoje + datetime.timedelta(days=91)

    elif modo == "Mês selecionado":
        data_inicial = datetime.date(ano, mes, 1)

        if mes == 12:
            data_final = datetime.date(ano + 1, 1, 1)
        else:
            data_final = datetime.date(ano, mes + 1, 1)

    else:
        data_inicial = None
        data_final = None

    url = f"{SUPABASE_URL}/rest/v1/movimentacoes"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {st.session_state['user_token']}",
        "Accept": "application/json",
    }

    parametros = [
        (
            "select",
            (
                "id,data,descricao,grupo_orcamentario,"
                "subcategoria,valor,satisfacao,tipo,user_id"
            ),
        ),
        ("user_id", f"eq.{user_id}"),
        ("grupo_orcamentario", "ilike.*AGENDA*"),
        ("order", "data.asc"),
        ("limit", "500"),
    ]

    if data_inicial is not None:
        parametros.append(
            ("data", f"gte.{data_inicial.isoformat()}")
        )

    if data_final is not None:
        parametros.append(
            ("data", f"lt.{data_final.isoformat()}")
        )

    with httpx.Client(timeout=20.0) as cliente:
        resposta = cliente.get(
            url,
            headers=headers,
            params=parametros,
        )

    if resposta.status_code != 200:
        detalhe = resposta.text[:500]
        raise RuntimeError(
            f"Consulta da Agenda retornou HTTP "
            f"{resposta.status_code}: {detalhe}"
        )

    dados = resposta.json()

    if not isinstance(dados, list):
        raise RuntimeError(
            "A Agenda retornou um formato inesperado."
        )

    return dados



def cadastrar_compromisso_http(
    user_id: str,
    descricao: str,
    natureza: str,
    data_compromisso: datetime.date,
    valor: float,
    categoria: str,
) -> dict:
    """Cadastra um compromisso da Agenda via REST HTTP."""
    url = f"{SUPABASE_URL}/rest/v1/movimentacoes"

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {st.session_state['user_token']}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    if natureza.strip() == "A receber":
        grupo = "AGENDA - A RECEBER"
        tipo = "Entrada"
    else:
        grupo = "AGENDA - A PAGAR"
        tipo = "Saída"

    payload = {
        "data": data_compromisso.isoformat(),
        "descricao": f"[AGENDA COMPROMISSO] {descricao.strip()}",
        "grupo_orcamentario": grupo,
        "subcategoria": categoria.strip(),
        "valor": float(valor),
        "satisfacao": "3 - Indispensável",
        "tipo": tipo,
        "user_id": user_id,
    }

    with httpx.Client(timeout=20.0) as cliente:
        resposta = cliente.post(
            url,
            headers=headers,
            json=payload,
        )

    if resposta.status_code not in (200, 201):
        detalhe = resposta.text[:500]
        raise RuntimeError(
            f"Cadastro retornou HTTP {resposta.status_code}: {detalhe}"
        )

    dados = resposta.json()

    if isinstance(dados, list) and dados:
        return dados[0]

    if isinstance(dados, dict):
        return dados

    return payload


def atualizar_compromisso_http(
    compromisso_id,
    user_id: str,
    descricao: str,
    natureza: str,
    data_compromisso: datetime.date,
    valor: float,
    categoria: str,
) -> dict:
    """Atualiza um compromisso da Agenda via REST HTTP."""
    url = f"{SUPABASE_URL}/rest/v1/movimentacoes"

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {st.session_state['user_token']}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    if natureza.strip() == "A receber":
        grupo = "AGENDA - A RECEBER"
        tipo = "Entrada"
    else:
        grupo = "AGENDA - A PAGAR"
        tipo = "Saída"

    payload = {
        "data": data_compromisso.isoformat(),
        "descricao": f"[AGENDA COMPROMISSO] {descricao.strip()}",
        "grupo_orcamentario": grupo,
        "subcategoria": categoria.strip(),
        "valor": float(valor),
        "satisfacao": "3 - Indispensável",
        "tipo": tipo,
    }

    parametros = [
        ("id", f"eq.{compromisso_id}"),
        ("user_id", f"eq.{user_id}"),
    ]

    with httpx.Client(timeout=20.0) as cliente:
        resposta = cliente.patch(
            url,
            headers=headers,
            params=parametros,
            json=payload,
        )

    if resposta.status_code not in (200, 204):
        detalhe = resposta.text[:500]
        raise RuntimeError(
            f"Edição retornou HTTP {resposta.status_code}: {detalhe}"
        )

    if resposta.status_code == 204 or not resposta.text.strip():
        return payload

    dados = resposta.json()

    if isinstance(dados, list) and dados:
        return dados[0]

    if isinstance(dados, dict):
        return dados

    return payload


def excluir_registro_http(
    registro_id,
    user_id: str,
) -> None:
    """Exclui um registro específico do usuário via REST HTTP."""
    url = f"{SUPABASE_URL}/rest/v1/movimentacoes"

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {st.session_state['user_token']}",
        "Prefer": "return=representation",
    }

    parametros = [
        ("id", f"eq.{registro_id}"),
        ("user_id", f"eq.{user_id}"),
    ]

    with httpx.Client(timeout=20.0) as cliente:
        resposta = cliente.delete(
            url,
            headers=headers,
            params=parametros,
        )

    if resposta.status_code not in (200, 204):
        detalhe = resposta.text[:500]
        raise RuntimeError(
            f"Exclusão retornou HTTP {resposta.status_code}: {detalhe}"
        )


def baixar_compromisso_http(
    compromisso_id,
    user_id: str,
    descricao: str,
    natureza: str,
    data_baixa: datetime.date,
    valor: float,
    grupo_destino: str,
    categoria_destino: str,
) -> dict:
    """
    Cria o lançamento financeiro real e remove o item da Agenda.

    Se a remoção da Agenda falhar, o novo lançamento é excluído
    automaticamente para evitar duplicidade.
    """
    url = f"{SUPABASE_URL}/rest/v1/movimentacoes"

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {st.session_state['user_token']}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    eh_recebimento = natureza.strip() == "A receber"

    if eh_recebimento:
        tipo = "Faturamento ou Receita (Entrada)"
        grupo = "RECEITAS"
        descricao_final = f"{descricao.strip()} (Recebido)"
    else:
        tipo = "Saída Dinheiro / Pix (Débito)"
        grupo = grupo_destino.strip()
        descricao_final = f"{descricao.strip()} (Pago)"

    payload = {
        "data": data_baixa.isoformat(),
        "descricao": descricao_final,
        "grupo_orcamentario": grupo,
        "subcategoria": categoria_destino.strip(),
        "valor": float(valor),
        "satisfacao": "3 - Indispensável",
        "tipo": tipo,
        "user_id": user_id,
    }

    with httpx.Client(timeout=20.0) as cliente:
        resposta_criacao = cliente.post(
            url,
            headers=headers,
            json=payload,
        )

    if resposta_criacao.status_code not in (200, 201):
        detalhe = resposta_criacao.text[:500]
        raise RuntimeError(
            f"Baixa retornou HTTP "
            f"{resposta_criacao.status_code}: {detalhe}"
        )

    dados_criacao = resposta_criacao.json()

    if (
        not isinstance(dados_criacao, list)
        or not dados_criacao
        or dados_criacao[0].get("id") is None
    ):
        raise RuntimeError(
            "O lançamento foi criado, mas o banco não retornou "
            "um identificador seguro."
        )

    novo_registro = dados_criacao[0]
    novo_registro_id = novo_registro["id"]

    try:
        excluir_registro_http(compromisso_id, user_id)
    except Exception as erro_exclusao:
        try:
            excluir_registro_http(novo_registro_id, user_id)
        except Exception as erro_rollback:
            raise RuntimeError(
                "Falha crítica: o compromisso não foi removido e "
                "o novo lançamento também não pôde ser desfeito. "
                "Confira os registros antes de tentar novamente. "
                f"Erro ao remover Agenda: {erro_exclusao}. "
                f"Erro ao desfazer lançamento: {erro_rollback}"
            ) from erro_rollback

        raise RuntimeError(
            "A baixa foi desfeita porque o compromisso não pôde "
            f"ser removido da Agenda: {erro_exclusao}"
        ) from erro_exclusao

    return novo_registro

def limpar_descricao_agenda(texto) -> str:
    return str(texto or "").replace(
        "[AGENDA COMPROMISSO] ",
        "",
    ).strip()


def classificar_agenda(grupo) -> str:
    texto = normalizar_texto(grupo).upper()

    if "RECEBER" in texto:
        return "A receber"

    return "A pagar"

def classificar_movimento(tipo: str) -> str:
    texto = normalizar_texto(tipo).upper()

    termos_entrada = [
        "ENTRADA",
        "RECEITA",
        "FATURAMENTO",
        "RECEBIMENTO",
    ]
    termos_cartao = [
        "CARTÃO",
        "CARTAO",
        "CRÉDITO",
        "CREDITO",
    ]

    if any(termo in texto for termo in termos_entrada):
        return "entrada"

    if any(termo in texto for termo in termos_cartao):
        return "cartao"

    return "saida"


if pagina_teste == "Diagnóstico":
    st.title("🧭 Diagnóstico Financeiro")
    st.caption(
        "Primeira página real migrada. "
        "Somente os registros do mês selecionado são consultados."
    )

    hoje = datetime.date.today()

    col_filtro1, col_filtro2 = st.columns(2)

    with col_filtro1:
        ano_selecionado = st.selectbox(
            "Ano:",
            [hoje.year - 1, hoje.year, hoje.year + 1],
            index=1,
            key="diag_ano_http",
        )

    with col_filtro2:
        mes_selecionado = st.selectbox(
            "Mês:",
            list(NOMES_MESES.keys()),
            index=hoje.month - 1,
            format_func=lambda numero: NOMES_MESES[numero],
            key="diag_mes_http",
        )

    try:
        registros = buscar_movimentacoes_mes_http(
            USER_ID,
            int(ano_selecionado),
            int(mes_selecionado),
        )

        df_mes = pd.DataFrame(registros)

        if df_mes.empty:
            st.info(
                "Nenhum lançamento financeiro foi encontrado "
                "para o mês selecionado."
            )

            receitas = 0.0
            despesas_caixa = 0.0
            despesas_cartao = 0.0
            total_despesas = 0.0
            saldo = 0.0
            consumo_renda = 0.0

        else:
            for coluna in [
                "descricao",
                "grupo_orcamentario",
                "subcategoria",
                "tipo",
                "valor",
            ]:
                if coluna not in df_mes.columns:
                    df_mes[coluna] = None

            df_mes["valor_num"] = df_mes["valor"].apply(
                lambda valor: normalizar_numero(valor, 0.0)
            )
            df_mes["classe"] = df_mes["tipo"].apply(
                classificar_movimento
            )

            # Exclui configurações e registros administrativos.
            mascara_config = (
                df_mes["descricao"]
                .fillna("")
                .astype(str)
                .str.upper()
                .str.contains(
                    "CONFIG_PERFIL|CONFIG_CARTAO|DIVIDA_ATIVA",
                    regex=True,
                    na=False,
                )
            )

            mascara_grupo_config = (
                df_mes["grupo_orcamentario"]
                .fillna("")
                .astype(str)
                .str.upper()
                .str.contains(
                    "CONFIGURAC|CONFIGURAÇÃO|AGENDA",
                    regex=True,
                    na=False,
                )
            )

            df_financeiro = df_mes[
                ~mascara_config & ~mascara_grupo_config
            ].copy()

            receitas = float(
                df_financeiro.loc[
                    df_financeiro["classe"] == "entrada",
                    "valor_num",
                ].sum()
            )

            despesas_caixa = float(
                df_financeiro.loc[
                    df_financeiro["classe"] == "saida",
                    "valor_num",
                ].sum()
            )

            despesas_cartao = float(
                df_financeiro.loc[
                    df_financeiro["classe"] == "cartao",
                    "valor_num",
                ].sum()
            )

            total_despesas = despesas_caixa + despesas_cartao
            saldo = receitas - total_despesas

            consumo_renda = (
                total_despesas / receitas
                if receitas > 0
                else 0.0
            )

        if receitas <= 0 and total_despesas > 0:
            status = "Atenção"
            mensagem = (
                "Existem despesas registradas, mas nenhuma receita "
                "foi reconhecida no mês."
            )
            st.warning(f"⚠️ Status do mês: {status}")

        elif saldo < 0:
            status = "Crítico"
            mensagem = (
                "As despesas registradas já ultrapassaram "
                "as receitas reconhecidas."
            )
            st.error(f"🚨 Status do mês: {status}")

        elif consumo_renda >= 0.85:
            status = "Atenção"
            mensagem = (
                "Mais de 85% das receitas reconhecidas já foram "
                "consumidas."
            )
            st.warning(f"⚠️ Status do mês: {status}")

        else:
            status = "Saudável"
            mensagem = (
                "O mês parece saudável com base nos dados "
                "registrados até agora."
            )
            st.success(f"✅ Status do mês: {status}")

        st.write(mensagem)

        col1, col2, col3 = st.columns(3)
        col1.metric("Receitas", f"R$ {receitas:,.2f}")
        col2.metric("Despesas", f"R$ {total_despesas:,.2f}")
        col3.metric("Saldo", f"R$ {saldo:,.2f}")

        col4, col5, col6 = st.columns(3)
        col4.metric(
            "Saídas em caixa",
            f"R$ {despesas_caixa:,.2f}",
        )
        col5.metric(
            "Compras no cartão",
            f"R$ {despesas_cartao:,.2f}",
        )
        col6.metric(
            "Consumo da receita",
            f"{consumo_renda * 100:.1f}%",
        )

        st.markdown("---")
        st.subheader("Leitura prática")

        if saldo < 0:
            st.write(
                "- O mês está negativo. Revise gastos variáveis "
                "e confira se todas as receitas foram registradas."
            )
        elif receitas <= 0 and total_despesas > 0:
            st.write(
                "- Cadastre ou confira as entradas do mês para que "
                "o diagnóstico seja confiável."
            )
        elif consumo_renda >= 0.85:
            st.write(
                "- A margem restante está pequena. Evite assumir "
                "novas despesas até o fechamento do mês."
            )
        else:
            st.write(
                "- O saldo permanece positivo com os registros "
                "atuais. Continue lançando receitas e despesas."
            )

        with st.expander("Ver informações do teste"):
            st.write(
                f"Registros retornados pelo banco: {len(registros)}"
            )
            st.write(
                "Método da consulta: HTTP direto no REST do Supabase."
            )
            st.write(
                "Limite de segurança da consulta: 1.000 registros."
            )

    except httpx.TimeoutException:
        st.error(
            "A consulta demorou mais de 20 segundos e foi interrompida."
        )
    except httpx.RequestError as erro:
        st.error(f"Falha de conexão com o banco: {erro}")
    except Exception as erro:
        st.error(
            "Falha ao carregar o diagnóstico: "
            f"{type(erro).__name__}: {erro}"
        )

elif pagina_teste == "Painel e Lançamentos":
    st.title("💼 Painel e Lançamentos")
    st.caption(
        "Centro operacional dos lançamentos financeiros reais. "
        "Compromissos da Agenda e registros de configuração não aparecem aqui."
    )

    hoje_painel = datetime.date.today()
    col_periodo1, col_periodo2 = st.columns(2)

    with col_periodo1:
        ano_painel = st.selectbox(
            "Ano:",
            [hoje_painel.year - 1, hoje_painel.year, hoje_painel.year + 1],
            index=1,
            key="painel_ano_http",
        )

    with col_periodo2:
        mes_painel = st.selectbox(
            "Mês:",
            list(NOMES_MESES.keys()),
            index=hoje_painel.month - 1,
            format_func=lambda numero: NOMES_MESES[numero],
            key="painel_mes_http",
        )

    try:
        registros_painel = buscar_lancamentos_painel_http(
            USER_ID,
            int(ano_painel),
            int(mes_painel),
        )
    except httpx.TimeoutException:
        st.error(
            "A consulta do Painel e Lançamentos ultrapassou 20 segundos."
        )
        st.stop()
    except httpx.RequestError as erro:
        st.error(
            f"Falha de conexão ao consultar o Painel e Lançamentos: {erro}"
        )
        st.stop()
    except RuntimeError as erro:
        st.error(f"Falha ao carregar lançamentos reais: {erro}")
        st.stop()
    except Exception as erro:
        st.error(
            "Falha inesperada ao carregar o Painel e Lançamentos: "
            f"{type(erro).__name__}: {erro}"
        )
        st.stop()

    df_painel = preparar_dataframe_painel_lancamentos(registros_painel)
    resumo_painel = calcular_resumo_lancamentos(df_painel)

    col_metrica1, col_metrica2, col_metrica3, col_metrica4 = st.columns(4)
    col_metrica1.metric("Entradas", formatar_moeda_br(resumo_painel["entradas"]))
    col_metrica2.metric(
        "Saídas em dinheiro/Pix",
        formatar_moeda_br(resumo_painel["saidas_dinheiro"]),
    )
    col_metrica3.metric("Cartão", formatar_moeda_br(resumo_painel["cartao"]))
    col_metrica4.metric("Saldo", formatar_moeda_br(resumo_painel["saldo"]))

    if df_painel.empty:
        st.info(
            "Nenhum lançamento financeiro real foi encontrado para o mês selecionado."
        )
    else:
        st.markdown("---")
        st.subheader("Lançamentos reais")

        df_filtrado = df_painel.copy()
        col_filtro1, col_filtro2 = st.columns(2)

        with col_filtro1:
            busca_descricao = st.text_input(
                "Buscar na descrição:",
                key="painel_busca_descricao",
            )

        with col_filtro2:
            classes_disponiveis = [
                rotulo_classe_movimento(classe)
                for classe in sorted(df_painel["classe"].dropna().unique())
            ]
            classes_selecionadas = st.multiselect(
                "Classe:",
                ["Entrada", "Saída", "Cartão"],
                default=classes_disponiveis,
                key="painel_filtro_classe",
            )

        col_filtro3, col_filtro4 = st.columns(2)
        grupos_disponiveis = sorted(
            valor for valor in df_painel["grupo_orcamentario"].dropna().unique()
            if normalizar_texto(valor)
        )
        subcategorias_disponiveis = sorted(
            valor for valor in df_painel["subcategoria"].dropna().unique()
            if normalizar_texto(valor)
        )

        with col_filtro3:
            grupos_selecionados = st.multiselect(
                "Grupo orçamentário:",
                grupos_disponiveis,
                default=grupos_disponiveis,
                key="painel_filtro_grupo",
            )

        with col_filtro4:
            subcategorias_selecionadas = st.multiselect(
                "Subcategoria:",
                subcategorias_disponiveis,
                default=subcategorias_disponiveis,
                key="painel_filtro_subcategoria",
            )

        texto_busca = _texto_normalizado_busca(busca_descricao)
        if texto_busca:
            df_filtrado = df_filtrado[
                df_filtrado["descricao"].apply(
                    lambda valor: texto_busca in _texto_normalizado_busca(valor)
                )
            ]

        classes_por_rotulo = {
            "Entrada": "entrada",
            "Saída": "saida",
            "Cartão": "cartao",
        }
        classes_filtradas = [
            classes_por_rotulo[rotulo]
            for rotulo in classes_selecionadas
            if rotulo in classes_por_rotulo
        ]
        df_filtrado = df_filtrado[df_filtrado["classe"].isin(classes_filtradas)]

        if grupos_disponiveis:
            df_filtrado = df_filtrado[
                df_filtrado["grupo_orcamentario"].isin(grupos_selecionados)
            ]
        if subcategorias_disponiveis:
            df_filtrado = df_filtrado[
                df_filtrado["subcategoria"].isin(subcategorias_selecionadas)
            ]

        if df_filtrado.empty:
            st.info("Nenhum lançamento corresponde aos filtros selecionados.")
        else:
            df_tabela = df_filtrado.sort_values(
                ["data_dt", "id"],
                ascending=[False, False],
            ).copy()
            df_tabela["Data"] = df_tabela["data_dt"].dt.strftime("%d/%m/%Y")
            df_tabela["Descrição"] = df_tabela["descricao"]
            df_tabela["Tipo"] = df_tabela["tipo"]
            df_tabela["Grupo"] = df_tabela["grupo_orcamentario"]
            df_tabela["Subcategoria"] = df_tabela["subcategoria"]
            df_tabela["Valor"] = df_tabela["valor_num"].apply(formatar_moeda_br)
            df_tabela["Satisfação"] = df_tabela["satisfacao"]

            st.dataframe(
                df_tabela[
                    [
                        "Data",
                        "Descrição",
                        "Tipo",
                        "Grupo",
                        "Subcategoria",
                        "Valor",
                        "Satisfação",
                    ]
                ],
                width="stretch",
                hide_index=True,
            )

elif pagina_teste == "Agenda":
    st.title("📅 Agenda de Compromissos")
    st.caption(
        "Segunda página real migrada. A Agenda agora permite "
        "consultar e cadastrar compromissos."
    )

    hoje_agenda = datetime.date.today()

    with st.expander("➕ Cadastrar novo compromisso", expanded=False):
        with st.form("form_cadastro_agenda", clear_on_submit=True):
            col_form1, col_form2 = st.columns(2)

            with col_form1:
                natureza_nova = st.selectbox(
                    "Natureza:",
                    ["A pagar", "A receber"],
                    key="agenda_nova_natureza",
                )

                descricao_nova = st.text_input(
                    "Compromisso:",
                    placeholder="Ex.: MEI, aluguel, consulta, cliente",
                    key="agenda_nova_descricao",
                )

                categoria_nova = st.text_input(
                    "Categoria:",
                    placeholder="Ex.: Impostos, Saúde, Cliente",
                    key="agenda_nova_categoria",
                )

            with col_form2:
                data_nova = st.date_input(
                    "Data do compromisso:",
                    value=hoje_agenda,
                    key="agenda_nova_data",
                )

                valor_novo = st.number_input(
                    "Valor (R$):",
                    min_value=0.0,
                    value=0.0,
                    step=10.0,
                    format="%.2f",
                    key="agenda_novo_valor",
                )

            salvar_compromisso = st.form_submit_button(
                "Salvar compromisso",
                width="stretch",
            )

        if salvar_compromisso:
            erros_formulario = []

            if not descricao_nova.strip():
                erros_formulario.append(
                    "Informe a descrição do compromisso."
                )

            if not categoria_nova.strip():
                erros_formulario.append(
                    "Informe uma categoria."
                )

            if float(valor_novo) <= 0:
                erros_formulario.append(
                    "Informe um valor maior que zero."
                )

            if erros_formulario:
                for mensagem_erro in erros_formulario:
                    st.error(mensagem_erro)
            else:
                try:
                    cadastrar_compromisso_http(
                        USER_ID,
                        descricao_nova,
                        natureza_nova,
                        data_nova,
                        float(valor_novo),
                        categoria_nova,
                    )
                    st.success("Compromisso cadastrado com sucesso.")
                    st.rerun()

                except httpx.TimeoutException:
                    st.error(
                        "O cadastro ultrapassou 20 segundos."
                    )
                except httpx.RequestError as erro:
                    st.error(
                        f"Falha de conexão ao cadastrar: {erro}"
                    )
                except Exception as erro:
                    st.error(
                        "Falha ao cadastrar o compromisso: "
                        f"{type(erro).__name__}: {erro}"
                    )

    col_ag1, col_ag2, col_ag3 = st.columns(3)

    with col_ag1:
        modo_agenda = st.selectbox(
            "Período:",
            [
                "Próximos 90 dias",
                "Mês selecionado",
                "Todos",
            ],
            key="agenda_modo_leitura",
        )

    with col_ag2:
        ano_agenda = st.selectbox(
            "Ano da Agenda:",
            [
                hoje_agenda.year - 1,
                hoje_agenda.year,
                hoje_agenda.year + 1,
            ],
            index=1,
            key="agenda_ano_leitura",
            disabled=(modo_agenda != "Mês selecionado"),
        )

    with col_ag3:
        mes_agenda = st.selectbox(
            "Mês da Agenda:",
            list(NOMES_MESES.keys()),
            index=hoje_agenda.month - 1,
            format_func=lambda numero: NOMES_MESES[numero],
            key="agenda_mes_leitura",
            disabled=(modo_agenda != "Mês selecionado"),
        )

    try:
        compromissos = buscar_agenda_http(
            USER_ID,
            modo_agenda,
            int(ano_agenda),
            int(mes_agenda),
        )

        df_agenda = pd.DataFrame(compromissos)

        if df_agenda.empty:
            st.info(
                "Nenhum compromisso encontrado para o período."
            )

        else:
            for coluna in [
                "data",
                "descricao",
                "grupo_orcamentario",
                "subcategoria",
                "valor",
                "tipo",
            ]:
                if coluna not in df_agenda.columns:
                    df_agenda[coluna] = None

            df_agenda["data_dt"] = pd.to_datetime(
                df_agenda["data"],
                errors="coerce",
            )
            df_agenda["valor_num"] = df_agenda["valor"].apply(
                lambda valor: normalizar_numero(valor, 0.0)
            )
            df_agenda["Natureza"] = (
                df_agenda["grupo_orcamentario"]
                .apply(classificar_agenda)
            )
            df_agenda["Compromisso"] = (
                df_agenda["descricao"]
                .apply(limpar_descricao_agenda)
            )

            datas_invalidas = int(
                df_agenda["data_dt"].isna().sum()
            )

            df_agenda_valida = df_agenda[
                df_agenda["data_dt"].notna()
            ].copy()

            total_pagar = float(
                df_agenda_valida.loc[
                    df_agenda_valida["Natureza"] == "A pagar",
                    "valor_num",
                ].sum()
            )
            total_receber = float(
                df_agenda_valida.loc[
                    df_agenda_valida["Natureza"] == "A receber",
                    "valor_num",
                ].sum()
            )
            saldo_agenda = total_receber - total_pagar

            met1, met2, met3 = st.columns(3)
            met1.metric(
                "Agendado a pagar",
                f"R$ {total_pagar:,.2f}",
            )
            met2.metric(
                "Agendado a receber",
                f"R$ {total_receber:,.2f}",
            )
            met3.metric(
                "Saldo projetado",
                f"R$ {saldo_agenda:,.2f}",
            )

            if datas_invalidas > 0:
                st.warning(
                    f"{datas_invalidas} compromisso(s) com data "
                    "inválida foram ignorados."
                )

            tabela_agenda = df_agenda_valida[
                [
                    "data_dt",
                    "Compromisso",
                    "Natureza",
                    "subcategoria",
                    "valor_num",
                ]
            ].copy()

            tabela_agenda = tabela_agenda.rename(
                columns={
                    "data_dt": "Data",
                    "subcategoria": "Categoria",
                    "valor_num": "Valor",
                }
            )

            tabela_agenda["Data"] = (
                tabela_agenda["Data"].dt.strftime("%d/%m/%Y")
            )

            st.subheader("Compromissos encontrados")
            st.caption(
                f"{len(tabela_agenda)} compromisso(s) exibido(s)."
            )

            st.dataframe(
                tabela_agenda,
                width="stretch",
                hide_index=True,
                column_config={
                    "Valor": st.column_config.NumberColumn(
                        "Valor",
                        format="R$ %.2f",
                    )
                },
            )

            st.markdown("---")
            st.subheader("Editar compromisso")

            opcoes_edicao = {}

            for _, linha in df_agenda_valida.iterrows():
                identificador = linha.get("id")
                data_texto = linha["data_dt"].strftime("%d/%m/%Y")
                descricao_texto = linha["Compromisso"]
                valor_texto = float(linha["valor_num"])

                rotulo = (
                    f"{data_texto} - {descricao_texto} - "
                    f"R$ {valor_texto:,.2f}"
                )

                # Evita colisão caso existam compromissos idênticos.
                if rotulo in opcoes_edicao:
                    rotulo = f"{rotulo} - ID {identificador}"

                opcoes_edicao[rotulo] = identificador

            rotulo_escolhido = st.selectbox(
                "Escolha o compromisso:",
                list(opcoes_edicao.keys()),
                key="agenda_editar_selecao",
            )

            id_escolhido = opcoes_edicao[rotulo_escolhido]

            registro_edicao = df_agenda_valida[
                df_agenda_valida["id"] == id_escolhido
            ].iloc[0]

            descricao_atual = str(
                registro_edicao["Compromisso"] or ""
            )
            natureza_atual = str(
                registro_edicao["Natureza"] or "A pagar"
            )
            categoria_atual = str(
                registro_edicao["subcategoria"] or ""
            )
            valor_atual = float(
                registro_edicao["valor_num"]
            )
            data_atual = registro_edicao["data_dt"].date()

            with st.form("form_editar_agenda"):
                col_edit1, col_edit2 = st.columns(2)

                with col_edit1:
                    natureza_editada = st.selectbox(
                        "Natureza:",
                        ["A pagar", "A receber"],
                        index=(
                            1 if natureza_atual == "A receber" else 0
                        ),
                        key="agenda_editar_natureza",
                    )

                    descricao_editada = st.text_input(
                        "Compromisso:",
                        value=descricao_atual,
                        key="agenda_editar_descricao",
                    )

                    categoria_editada = st.text_input(
                        "Categoria:",
                        value=categoria_atual,
                        key="agenda_editar_categoria",
                    )

                with col_edit2:
                    data_editada = st.date_input(
                        "Data do compromisso:",
                        value=data_atual,
                        key="agenda_editar_data",
                    )

                    valor_editado = st.number_input(
                        "Valor (R$):",
                        min_value=0.0,
                        value=valor_atual,
                        step=10.0,
                        format="%.2f",
                        key="agenda_editar_valor",
                    )

                salvar_edicao = st.form_submit_button(
                    "Salvar alterações",
                    width="stretch",
                )

            if salvar_edicao:
                erros_edicao = []

                if not descricao_editada.strip():
                    erros_edicao.append(
                        "Informe a descrição do compromisso."
                    )

                if not categoria_editada.strip():
                    erros_edicao.append(
                        "Informe uma categoria."
                    )

                if float(valor_editado) <= 0:
                    erros_edicao.append(
                        "Informe um valor maior que zero."
                    )

                if erros_edicao:
                    for mensagem_erro in erros_edicao:
                        st.error(mensagem_erro)
                else:
                    try:
                        atualizar_compromisso_http(
                            id_escolhido,
                            USER_ID,
                            descricao_editada,
                            natureza_editada,
                            data_editada,
                            float(valor_editado),
                            categoria_editada,
                        )
                        st.success(
                            "Compromisso atualizado com sucesso."
                        )
                        st.rerun()

                    except httpx.TimeoutException:
                        st.error(
                            "A edição ultrapassou 20 segundos."
                        )
                    except httpx.RequestError as erro:
                        st.error(
                            f"Falha de conexão ao editar: {erro}"
                        )
                    except Exception as erro:
                        st.error(
                            "Falha ao editar o compromisso: "
                            f"{type(erro).__name__}: {erro}"
                        )

            st.markdown("---")
            st.subheader("Dar baixa no compromisso")
            st.caption(
                "A baixa cria um lançamento financeiro real e remove "
                "o compromisso da Agenda."
            )

            opcoes_baixa = {}

            for _, linha in df_agenda_valida.iterrows():
                identificador = linha.get("id")
                data_texto = linha["data_dt"].strftime("%d/%m/%Y")
                descricao_texto = linha["Compromisso"]
                natureza_texto = linha["Natureza"]
                valor_texto = float(linha["valor_num"])

                rotulo = (
                    f"{data_texto} - {descricao_texto} - "
                    f"{natureza_texto} - R$ {valor_texto:,.2f}"
                )

                if rotulo in opcoes_baixa:
                    rotulo = f"{rotulo} - ID {identificador}"

                opcoes_baixa[rotulo] = identificador

            rotulo_baixa = st.selectbox(
                "Escolha o compromisso para dar baixa:",
                list(opcoes_baixa.keys()),
                key="agenda_baixa_selecao",
            )

            id_baixa = opcoes_baixa[rotulo_baixa]

            registro_baixa = df_agenda_valida[
                df_agenda_valida["id"] == id_baixa
            ].iloc[0]

            descricao_baixa = str(
                registro_baixa["Compromisso"] or ""
            )
            natureza_baixa = str(
                registro_baixa["Natureza"] or "A pagar"
            )
            categoria_baixa_atual = str(
                registro_baixa["subcategoria"] or ""
            )
            valor_baixa = float(
                registro_baixa["valor_num"]
            )

            grupos_saida = [
                "50% Essencial (Sobreviver)",
                "30% Estilo de Vida (Viver)",
                "20% Investimentos e Objetivos",
            ]

            with st.form("form_baixa_agenda"):
                st.write(
                    f"**{natureza_baixa}:** {descricao_baixa} - "
                    f"R$ {valor_baixa:,.2f}"
                )

                col_baixa1, col_baixa2 = st.columns(2)

                with col_baixa1:
                    data_baixa = st.date_input(
                        "Data da baixa:",
                        value=datetime.date.today(),
                        key="agenda_baixa_data",
                    )

                    if natureza_baixa == "A pagar":
                        grupo_baixa = st.selectbox(
                            "Grupo orçamentário:",
                            grupos_saida,
                            key="agenda_baixa_grupo",
                        )
                    else:
                        grupo_baixa = "RECEITAS"
                        st.text_input(
                            "Grupo orçamentário:",
                            value="RECEITAS",
                            disabled=True,
                            key="agenda_baixa_grupo_receita",
                        )

                with col_baixa2:
                    categoria_baixa = st.text_input(
                        "Categoria do lançamento:",
                        value=categoria_baixa_atual,
                        key="agenda_baixa_categoria",
                    )

                    confirmar_baixa = st.checkbox(
                        "Confirmo que os dados estão corretos.",
                        key="agenda_confirmar_baixa",
                    )

                texto_botao_baixa = (
                    "Marcar como recebido"
                    if natureza_baixa == "A receber"
                    else "Marcar como pago"
                )

                executar_baixa = st.form_submit_button(
                    texto_botao_baixa,
                    width="stretch",
                )

            if executar_baixa:
                erros_baixa = []

                if not categoria_baixa.strip():
                    erros_baixa.append(
                        "Informe a categoria do lançamento."
                    )

                if (
                    natureza_baixa == "A pagar"
                    and not grupo_baixa.strip()
                ):
                    erros_baixa.append(
                        "Informe o grupo orçamentário."
                    )

                if not confirmar_baixa:
                    erros_baixa.append(
                        "Marque a confirmação antes de dar baixa."
                    )

                if erros_baixa:
                    for mensagem_erro in erros_baixa:
                        st.error(mensagem_erro)
                else:
                    try:
                        baixar_compromisso_http(
                            id_baixa,
                            USER_ID,
                            descricao_baixa,
                            natureza_baixa,
                            data_baixa,
                            valor_baixa,
                            grupo_baixa,
                            categoria_baixa,
                        )

                        mensagem_baixa = (
                            "Compromisso marcado como recebido."
                            if natureza_baixa == "A receber"
                            else "Compromisso marcado como pago."
                        )

                        st.success(mensagem_baixa)
                        st.rerun()

                    except httpx.TimeoutException:
                        st.error(
                            "A baixa ultrapassou 20 segundos."
                        )
                    except httpx.RequestError as erro:
                        st.error(
                            f"Falha de conexão durante a baixa: {erro}"
                        )
                    except Exception as erro:
                        st.error(
                            "Falha ao dar baixa no compromisso: "
                            f"{type(erro).__name__}: {erro}"
                        )

        with st.expander("Ver informações do teste da Agenda"):
            st.write(
                f"Registros retornados: {len(compromissos)}"
            )
            st.write(
                "Modo atual: leitura, cadastro, edição e baixa."
            )
            st.write(
                "Limite de segurança: 500 compromissos."
            )
            st.write(
                "Consulta: HTTP direto no REST do Supabase."
            )

    except httpx.TimeoutException:
        st.error(
            "A consulta da Agenda ultrapassou 20 segundos."
        )
    except httpx.RequestError as erro:
        st.error(
            f"Falha de conexão ao consultar a Agenda: {erro}"
        )
    except Exception as erro:
        st.error(
            "Falha ao carregar a Agenda: "
            f"{type(erro).__name__}: {erro}"
        )

else:
    st.title(pagina_teste)
    st.success(f"Página {pagina_teste} carregada.")
    st.info(
        "Esta página ainda está vazia nesta etapa de teste."
    )

st.markdown("---")
st.caption(
    "Teste controlado: Diagnóstico e Agenda consultam o banco. "
    "A Agenda permite consultar, cadastrar, editar e dar baixa. A exclusão manual ainda não foi ativada."
)
