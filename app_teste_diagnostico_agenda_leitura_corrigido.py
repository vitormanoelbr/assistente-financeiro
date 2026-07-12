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

elif pagina_teste == "Agenda":
    st.title("📅 Agenda de Compromissos")
    st.caption(
        "Segunda página real migrada. Nesta etapa, a Agenda é "
        "somente para consulta."
    )

    hoje_agenda = datetime.date.today()

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

        with st.expander("Ver informações do teste da Agenda"):
            st.write(
                f"Registros retornados: {len(compromissos)}"
            )
            st.write(
                "Modo atual: somente leitura."
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
    "A Agenda ainda não permite cadastrar, editar ou excluir."
)
