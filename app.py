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


# ==================== SISTEMA PRINCIPAL ====================
USER_ID = st.session_state["usuario_logado"]

if st.sidebar.button("🚪 Sair da Conta"):
    deslogar_usuario()

# --- 📅 FILTROS DE TEMPO & TAGS ---
st.sidebar.header("📅 Filtros do Painel")
hoje = datetime.date.today()
ano_selected = st.sidebar.selectbox("Ano de Análise:", [hoje.year, hoje.year - 1, hoje.year + 1], index=0)

lista_meses = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}
mes_selected_num = st.sidebar.selectbox(
    "Mês de Análise:", list(lista_meses.keys()), 
    format_func=lambda x: lista_meses[x],
    index=list(lista_meses.keys()).index(hoje.month)
)

janela_tempo = st.sidebar.radio("Intervalo do Painel:", ["Mês Completo", "Últimos 7 Dias", "Somente Hoje"])

st.sidebar.markdown("---")
st.sidebar.header("🏷️ Rastreamento Inteligente")
tag_busca = st.sidebar.text_input("Filtrar por Tag / Texto:", placeholder="Ex: #filho, #viagem").strip().lower()

# --- VARIÁVEIS DE CONTROLE ACUMULADO ---
renda_base_usuario = 0.0  
faturamento_extra_mes = 0.0
gastos_dinheiro_caixa = 0.0       
fatura_acumulada_mes = 0.0   

gastos_essencial = 0.0
gastos_estilo = 0.0
gastos_negocio = 0.0
gastos_dividas = 0.0

agenda_a_pagar_mes = 0.0
agenda_a_receber_mes = 0.0

dicionario_metas_alvo = {}
dicionario_aportes_acumulados = {}

lista_dividas_cadastradas = []
lista_cartoes_cadastrados = []
amortizacoes_totais_historicas = {}

df_todos_dados = pd.DataFrame()
df_filtrado = pd.DataFrame()

if supabase:
    try:
        resposta_completa = supabase.table("movimentacoes").select("id, data, descricao, grupo_orcamentario, subcategoria, valor, satisfacao, tipo, user_id").eq("user_id", USER_ID).execute()
        
        if resposta_completa and hasattr(resposta_completa, 'data') and resposta_completa.data:
            res_data = resposta_completa.data
            df_todos_dados = pd.DataFrame(res_data)

            # Garante as colunas esperadas mesmo em registros antigos.
            for coluna_obrigatoria in [
                "id",
                "data",
                "descricao",
                "grupo_orcamentario",
                "subcategoria",
                "valor",
                "satisfacao",
                "tipo",
                "user_id",
            ]:
                if coluna_obrigatoria not in df_todos_dados.columns:
                    df_todos_dados[coluna_obrigatoria] = None

            df_todos_dados["valor_original"] = df_todos_dados["valor"]
            df_todos_dados["valor"] = df_todos_dados["valor"].apply(
                lambda valor: normalizar_numero(valor, 0.0)
            )
            df_todos_dados["data_dt"] = df_todos_dados["data"].apply(
                normalizar_data
            )

            quantidade_datas_invalidas_global = int(
                df_todos_dados["data_dt"].isna().sum()
            )
            quantidade_valores_invalidos_global = int(
                df_todos_dados["valor_original"].apply(
                    lambda valor: normalizar_numero(valor, None) is None
                ).sum()
            )
            
            # Processamento de Configurações Globais e Metadados
            for item in res_data:
                desc = normalizar_texto(item.get("descricao"))
                subcat = normalizar_texto(item.get("subcategoria"))
                grupo = normalizar_texto(item.get("grupo_orcamentario"))
                tipo_mov = normalizar_texto(item.get("tipo"))
                val_mov = normalizar_numero(item.get("valor"), 0.0)
                dt_item = normalizar_data(item.get("data"))
                
                if "[CONFIG_CARTAO]" in desc:
                    detalhes_cartao = str(item.get("satisfacao") or "")
                    dia_fechamento = 10
                    dia_vencimento = 20
                    for parte in detalhes_cartao.split("|"):
                        if ":" not in parte:
                            continue
                        chave_detalhe, valor_detalhe = parte.split(":", 1)
                        chave_detalhe = chave_detalhe.strip().lower()
                        try:
                            valor_dia = int(float(valor_detalhe.strip()))
                        except ValueError:
                            continue
                        if "fechamento" in chave_detalhe:
                            dia_fechamento = max(1, min(valor_dia, 28))
                        elif "vencimento" in chave_detalhe:
                            dia_vencimento = max(1, min(valor_dia, 28))

                    lista_cartoes_cadastrados.append({
                        "id": item["id"],
                        "nome": subcat if subcat else "Cartão sem nome",
                        "limite": val_mov,
                        "fechamento": dia_fechamento,
                        "vencimento": dia_vencimento,
                    })
                    continue

                if "[CONFIG_PERFIL]" in desc and "Renda Base Nativa" in subcat:
                    renda_base_usuario = val_mov
                    continue
                
                if "[DIVIDA_ATIVA]" in desc:
                    lista_dividas_cadastradas.append({
                        "id": item["id"],
                        "nome": subcat,
                        "valor_original": val_mov,
                        "parcela": normalizar_numero(
                            normalizar_texto(item.get("satisfacao")).split(
                                " - ", 1
                            )[0]
                            if " - " in normalizar_texto(
                                item.get("satisfacao")
                            )
                            else 0,
                            0.0
                        )
                    })
                    continue
                
                if "AGENDA" in grupo.upper():
                    if (
                        dt_item is not None
                        and dt_item.year == int(ano_selected)
                        and dt_item.month == int(mes_selected_num)
                    ):
                        if "PAGAR" in grupo.upper():
                            agenda_a_pagar_mes += val_mov
                        elif "RECEBER" in grupo.upper():
                            agenda_a_receber_mes += val_mov
                    continue
                
                if "APORTE" in grupo.upper() or "🚀" in grupo:
                    if "ENTRADA" in tipo_mov.upper() or "FATURAMENTO" in tipo_mov.upper() or "RECEITA" in tipo_mov.upper():
                        dicionario_metas_alvo[subcat] = val_mov
                    elif "SAÍDA" in tipo_mov.upper() or "PIX" in tipo_mov.upper() or "DÉBITO" in tipo_mov.upper() or "📱" in tipo_mov or "💳" in tipo_mov:
                        dicionario_aportes_acumulados[subcat] = dicionario_aportes_acumulados.get(subcat, 0.0) + val_mov
                
                if "QUITAÇÃO" in grupo.upper() or "DIVIDAS" in grupo.upper() or "📋" in grupo:
                    if "SAÍDA" in tipo_mov.upper() or "📱" in tipo_mov or "💳" in tipo_mov:
                        amortizacoes_totais_historicas[subcat] = amortizacoes_totais_historicas.get(subcat, 0.0) + val_mov

            # --- CORREÇÃO DO FILTRO DE TEMPO REAL ---
            if not df_todos_dados.empty:
                df_filtrado = df_todos_dados.copy()
                df_filtrado = df_filtrado[~df_filtrado["grupo_orcamentario"].astype(str).str.upper().str.contains("CONFIGURAC|CONFIGURAÇÃO|CONFIG", na=False)]
                df_filtrado = df_filtrado[~df_filtrado["descricao"].astype(str).str.upper().str.contains("CONFIG_PERFIL|DIVIDA_ATIVA", na=False)]
                df_filtrado = df_filtrado[~df_filtrado["grupo_orcamentario"].astype(str).str.upper().str.contains("AGENDA", na=False)]
                
                if not df_filtrado.empty:
                    df_filtrado = df_filtrado[
                        df_filtrado["data_dt"].notna()
                    ].copy()
                    df_filtrado["ano"] = df_filtrado["data_dt"].apply(
                        lambda data: data.year
                    )
                    df_filtrado["mes"] = df_filtrado["data_dt"].apply(
                        lambda data: data.month
                    )

                    # Filtro estrito por mês do evento.
                    df_filtrado = df_filtrado[
                        (df_filtrado["ano"] == int(ano_selected))
                        & (df_filtrado["mes"] == int(mes_selected_num))
                    ].copy()

            df_acumulado_mes_cheio = df_filtrado.copy()

            if janela_tempo == "Últimos 7 Dias" and not df_filtrado.empty:
                df_filtrado = df_filtrado[
                    (df_filtrado["data_dt"] >= (
                        hoje - datetime.timedelta(days=7)
                    ))
                    & (df_filtrado["data_dt"] <= hoje)
                ].copy()
            elif janela_tempo == "Somente Hoje" and not df_filtrado.empty:
                df_filtrado = df_filtrado[
                    df_filtrado["data_dt"] == hoje
                ].copy()
            
            if tag_busca and not df_filtrado.empty:
                df_filtrado["descricao_lower"] = df_filtrado["descricao"].fillna("").astype(str).str.lower()
                df_filtrado = df_filtrado[df_filtrado["descricao_lower"].str.contains(tag_busca, na=False)]
                
            # --- CÁLCULO DA MATEMÁTICA LÍQUIDA SÓLIDA ---
            if not df_acumulado_mes_cheio.empty:
                for _, row in df_acumulado_mes_cheio.iterrows():
                    val = float(row["valor"])
                    grupo_item = str(row["grupo_orcamentario"] or "").upper()
                    tipo_mov = str(row.get("tipo") or "").upper()
                    
                    if "ENTRADA" in tipo_mov or "FATURAMENTO" in tipo_mov or "RECEITA" in tipo_mov:
                        if "APORTE" in grupo_item or "🚀" in grupo_item:
                            continue
                        faturamento_extra_mes += val
                    else:
                        if "APORTE" in grupo_item or "🚀" in grupo_item:
                            continue
                        
                        # Separação correta de fluxos de caixa imediato vs crédito
                        if "💳" in str(row.get("tipo") or "") or "CARTÃO" in tipo_mov:
                            fatura_acumulada_mes += val
                        else:
                            gastos_dinheiro_caixa += val
                        
                        # Agrupamento de limites orçamentários
                        if "ESSENCIAL" in grupo_item or "50%" in grupo_item:
                            gastos_essencial += val
                        elif "ESTILO" in grupo_item or "30%" in grupo_item:
                            gastos_estilo += val
                        elif "NEGÓCIO" in grupo_item or "💼" in grupo_item or "CUSTOS" in grupo_item:
                            gastos_negocio += val
                        elif "DÍVIDAS" in grupo_item or "QUITAÇÃO" in grupo_item or "📋" in grupo_item:
                            gastos_dividas += val
                        
    except Exception as e:
        if "JWT expired" in str(e) or "PGRST303" in str(e):
            limpar_sessao_local()
            st.warning(
                "🔒 Sua sessão expirou por segurança. "
                "Entre novamente para continuar."
            )
            st.rerun()
        else:
            st.error(f"Erro no processamento dos dados: {e}")

if not df_todos_dados.empty:
    if quantidade_datas_invalidas_global > 0:
        st.sidebar.warning(
            f"{quantidade_datas_invalidas_global} registro(s) com data "
            "inválida foram ignorados nos cálculos temporais."
        )
    if quantidade_valores_invalidos_global > 0:
        st.sidebar.warning(
            f"{quantidade_valores_invalidos_global} registro(s) com valor "
            "inválido foram considerados como R$ 0,00."
        )

# --- ORIGENS DE VERDADE MATEMÁTICA ---
saldo_real_exibido = renda_base_usuario + faturamento_extra_mes - gastos_dinheiro_caixa
total_consumido_orcamento = gastos_dinheiro_caixa + fatura_acumulada_mes
receita_total_reconhecida_mes = renda_base_usuario + faturamento_extra_mes
saldo_projetado_fim_mes = saldo_real_exibido + agenda_a_receber_mes - agenda_a_pagar_mes - fatura_acumulada_mes

porcentagem_cartao_renda = (fatura_acumulada_mes / renda_base_usuario) if renda_base_usuario > 0 else 0.0
porcentagem_consumo_total = (total_consumido_orcamento / receita_total_reconhecida_mes) if receita_total_reconhecida_mes > 0 else 0.0
porcentagem_gasto_caixa = (gastos_dinheiro_caixa / receita_total_reconhecida_mes) if receita_total_reconhecida_mes > 0 else 0.0
porcentagem_essencial = (gastos_essencial / (renda_base_usuario * 0.50)) if renda_base_usuario > 0 else 0.0
porcentagem_estilo = (gastos_estilo / (renda_base_usuario * 0.30)) if renda_base_usuario > 0 else 0.0


# --- PROJEÇÃO DE FLUXO DE CAIXA FUTURO ---
def ultimo_dia_do_mes(data_ref: datetime.date) -> datetime.date:
    if data_ref.month == 12:
        proximo_mes = datetime.date(data_ref.year + 1, 1, 1)
    else:
        proximo_mes = datetime.date(data_ref.year, data_ref.month + 1, 1)
    return proximo_mes - datetime.timedelta(days=1)


def eh_entrada(tipo_movimento: str) -> bool:
    tipo_normalizado = str(tipo_movimento or "").upper()
    return any(palavra in tipo_normalizado for palavra in ["ENTRADA", "FATURAMENTO", "RECEITA"])


def eh_cartao(tipo_movimento: str) -> bool:
    tipo_normalizado = str(tipo_movimento or "").upper()
    return "💳" in str(tipo_movimento or "") or "CARTÃO" in tipo_normalizado or "CARTAO" in tipo_normalizado


def eh_saida_caixa(tipo_movimento: str) -> bool:
    tipo_normalizado = str(tipo_movimento or "").upper()
    return any(palavra in tipo_normalizado for palavra in ["SAÍDA", "SAIDA", "PIX", "DÉBITO", "DEBITO"]) or "📱" in str(tipo_movimento or "")


saldo_base_fluxo_futuro = renda_base_usuario
entradas_realizadas_ate_hoje = 0.0
saidas_caixa_realizadas_ate_hoje = 0.0
fatura_estimada_mes_atual = 0.0
eventos_fluxo_futuro = []
limite_fluxo_futuro = hoje + datetime.timedelta(days=30)
fim_mes_atual = ultimo_dia_do_mes(hoje)

if not df_todos_dados.empty:
    df_fluxo_base = df_todos_dados.copy()

    for _, item_fluxo in df_fluxo_base.iterrows():
        data_item = item_fluxo.get("data_dt")
        valor_item = normalizar_numero(item_fluxo.get("valor"), 0.0)
        descricao_item = normalizar_texto(
            item_fluxo.get("descricao"),
            "Sem descrição"
        )
        grupo_item_original = normalizar_texto(
            item_fluxo.get("grupo_orcamentario")
        )
        grupo_item = grupo_item_original.upper()
        tipo_item = normalizar_texto(item_fluxo.get("tipo"))

        if data_item is None or valor_item <= 0:
            continue
        if "CONFIG" in grupo_item or "[CONFIG_PERFIL]" in descricao_item or "[DIVIDA_ATIVA]" in descricao_item:
            continue
        if "APORTE" in grupo_item or "🚀" in grupo_item:
            continue

        # Base de caixa de hoje: considera apenas movimentos já realizados no mês atual.
        if hoje.replace(day=1) <= data_item <= hoje and "AGENDA" not in grupo_item:
            if eh_entrada(tipo_item):
                entradas_realizadas_ate_hoje += valor_item
            elif eh_saida_caixa(tipo_item) and not eh_cartao(tipo_item):
                saidas_caixa_realizadas_ate_hoje += valor_item

        # Fatura estimada do mês atual: posicionada no fim do mês por não haver cadastro de vencimento de cartão.
        if hoje.replace(day=1) <= data_item <= fim_mes_atual and eh_cartao(tipo_item) and "AGENDA" not in grupo_item:
            fatura_estimada_mes_atual += valor_item

        # Agenda futura a pagar/receber.
        if hoje <= data_item <= limite_fluxo_futuro and "AGENDA" in grupo_item:
            descricao_limpa = descricao_item.replace("[AGENDA COMPROMISSO] ", "")
            if "PAGAR" in grupo_item:
                eventos_fluxo_futuro.append({
                    "Data": data_item,
                    "Descrição": descricao_limpa,
                    "Origem": "Agenda - A pagar",
                    "Entrada": 0.0,
                    "Saída": valor_item,
                })
            elif "RECEBER" in grupo_item:
                eventos_fluxo_futuro.append({
                    "Data": data_item,
                    "Descrição": descricao_limpa,
                    "Origem": "Agenda - A receber",
                    "Entrada": valor_item,
                    "Saída": 0.0,
                })
            continue

        # Movimentos futuros já registrados fora da agenda.
        if hoje < data_item <= limite_fluxo_futuro and "AGENDA" not in grupo_item:
            if eh_entrada(tipo_item):
                eventos_fluxo_futuro.append({
                    "Data": data_item,
                    "Descrição": descricao_item,
                    "Origem": "Entrada futura registrada",
                    "Entrada": valor_item,
                    "Saída": 0.0,
                })
            elif eh_saida_caixa(tipo_item) and not eh_cartao(tipo_item):
                eventos_fluxo_futuro.append({
                    "Data": data_item,
                    "Descrição": descricao_item,
                    "Origem": "Saída futura registrada",
                    "Entrada": 0.0,
                    "Saída": valor_item,
                })
            elif data_item > fim_mes_atual and eh_cartao(tipo_item):
                eventos_fluxo_futuro.append({
                    "Data": data_item,
                    "Descrição": descricao_item,
                    "Origem": "Cartão futuro registrado",
                    "Entrada": 0.0,
                    "Saída": valor_item,
                })

saldo_base_fluxo_futuro = renda_base_usuario + entradas_realizadas_ate_hoje - saidas_caixa_realizadas_ate_hoje

if fatura_estimada_mes_atual > 0:
    eventos_fluxo_futuro.append({
        "Data": min(fim_mes_atual, limite_fluxo_futuro),
        "Descrição": "Fatura estimada do cartão do mês atual",
        "Origem": "Cartão - estimativa mensal",
        "Entrada": 0.0,
        "Saída": fatura_estimada_mes_atual,
    })

df_fluxo_futuro = pd.DataFrame(eventos_fluxo_futuro)
if not df_fluxo_futuro.empty:
    df_fluxo_futuro = df_fluxo_futuro.sort_values(by=["Data", "Origem", "Descrição"]).reset_index(drop=True)
    saldo_corrente_projetado = saldo_base_fluxo_futuro
    saldos_projetados = []
    for _, evento in df_fluxo_futuro.iterrows():
        saldo_corrente_projetado += float(evento["Entrada"]) - float(evento["Saída"])
        saldos_projetados.append(saldo_corrente_projetado)
    df_fluxo_futuro["Saldo Projetado"] = saldos_projetados
else:
    df_fluxo_futuro = pd.DataFrame(columns=["Data", "Descrição", "Origem", "Entrada", "Saída", "Saldo Projetado"])


def calcular_saldo_horizonte(dias: int) -> float:
    data_limite = hoje + datetime.timedelta(days=dias)
    if df_fluxo_futuro.empty:
        return saldo_base_fluxo_futuro
    eventos_periodo = df_fluxo_futuro[df_fluxo_futuro["Data"] <= data_limite]
    entrada_periodo = float(eventos_periodo["Entrada"].sum()) if not eventos_periodo.empty else 0.0
    saida_periodo = float(eventos_periodo["Saída"].sum()) if not eventos_periodo.empty else 0.0
    return saldo_base_fluxo_futuro + entrada_periodo - saida_periodo

saldo_projetado_7_dias = calcular_saldo_horizonte(7)
saldo_projetado_15_dias = calcular_saldo_horizonte(15)
saldo_projetado_30_dias = calcular_saldo_horizonte(30)


# --- CONTROLE DE CARTÕES E FATURAS ---
def extrair_cartao_da_descricao(descricao: str) -> str:
    texto = str(descricao or "")
    marcador_inicio = "[CARTAO:"
    pos_inicio = texto.upper().find(marcador_inicio)
    if pos_inicio == -1:
        return "Cartão não identificado"
    pos_nome = pos_inicio + len(marcador_inicio)
    pos_fim = texto.find("]", pos_nome)
    if pos_fim == -1:
        return "Cartão não identificado"
    nome_cartao = texto[pos_nome:pos_fim].strip()
    return nome_cartao or "Cartão não identificado"


def limpar_marcador_cartao(descricao: str) -> str:
    texto = str(descricao or "")
    marcador_inicio = "[CARTAO:"
    pos_inicio = texto.upper().find(marcador_inicio)
    if pos_inicio == -1:
        return texto
    pos_fim = texto.find("]", pos_inicio)
    if pos_fim == -1:
        return texto
    return (texto[:pos_inicio] + texto[pos_fim + 1:]).strip()


def limpar_marcador_assinatura(descricao: str) -> str:
    texto = str(descricao or "").strip()
    marcador = "[ASSINATURA]"
    posicao = texto.upper().find(marcador)

    if posicao == -1:
        return texto

    return (
        texto[:posicao]
        + texto[posicao + len(marcador):]
    ).strip()


data_base_cartao = datetime.date(ano_selected, mes_selected_num, 1)
fim_mes_cartao = ultimo_dia_do_mes(data_base_cartao)
limite_analise_cartao = adicionar_meses(data_base_cartao, 6)

df_cartao_movimentos = pd.DataFrame()
df_cartao_mes = pd.DataFrame()
df_cartao_futuro = pd.DataFrame()
df_fatura_por_cartao = pd.DataFrame(columns=["Cartão", "Fatura Atual", "Limite", "% do Limite"])
df_compromisso_futuro_cartao = pd.DataFrame(columns=["Mês", "Cartão", "Valor Comprometido"])
df_assinaturas_cartao = pd.DataFrame()
lista_assinaturas_ativas = []
valor_mensal_assinaturas = 0.0
valor_fatura_cartao_mes = 0.0
valor_cartao_futuro_total = 0.0

if not df_todos_dados.empty:
    df_cartao_movimentos = df_todos_dados.copy()
    df_cartao_movimentos["tipo_str"] = df_cartao_movimentos["tipo"].fillna("").astype(str)
    df_cartao_movimentos["grupo_str"] = df_cartao_movimentos["grupo_orcamentario"].fillna("").astype(str)
    df_cartao_movimentos["descricao_str"] = df_cartao_movimentos["descricao"].fillna("").astype(str)
    df_cartao_movimentos["satisfacao_str"] = df_cartao_movimentos["satisfacao"].fillna("").astype(str)

    mascara_cartao = df_cartao_movimentos["tipo_str"].apply(eh_cartao)
    mascara_operacional = ~df_cartao_movimentos["grupo_str"].str.upper().str.contains("CONFIG|AGENDA", na=False)
    mascara_operacional &= ~df_cartao_movimentos["descricao_str"].str.upper().str.contains("CONFIG_PERFIL|CONFIG_CARTAO|DIVIDA_ATIVA", na=False)
    mascara_operacional &= ~df_cartao_movimentos["grupo_str"].str.upper().str.contains("APORTE", na=False)
    df_cartao_movimentos = df_cartao_movimentos[mascara_cartao & mascara_operacional].copy()

    if not df_cartao_movimentos.empty:
        df_cartao_movimentos["valor"] = df_cartao_movimentos["valor"].apply(
            lambda valor: normalizar_numero(valor, 0.0)
        )
        df_cartao_movimentos = df_cartao_movimentos[
            df_cartao_movimentos["data_dt"].notna()
            & (df_cartao_movimentos["valor"] > 0)
        ].copy()

    if not df_cartao_movimentos.empty:
        df_cartao_movimentos["Cartão"] = df_cartao_movimentos["descricao_str"].apply(extrair_cartao_da_descricao)
        df_cartao_movimentos["Descrição Limpa"] = (
            df_cartao_movimentos["descricao_str"]
            .apply(limpar_marcador_cartao)
            .apply(limpar_marcador_assinatura)
        )
        df_cartao_movimentos["Natureza"] = df_cartao_movimentos["satisfacao_str"].apply(
            lambda texto: "Assinatura" if "SUB:" in str(texto) else "Compra"
        )
        df_cartao_movimentos["Ano"] = df_cartao_movimentos["data_dt"].apply(
            lambda data: data.year
        )
        df_cartao_movimentos["Mes"] = df_cartao_movimentos["data_dt"].apply(
            lambda data: data.month
        )
        df_cartao_movimentos["Mês"] = df_cartao_movimentos["data_dt"].apply(
            lambda data: data.strftime("%Y-%m")
        )

        df_cartao_mes = df_cartao_movimentos[
            (df_cartao_movimentos["Ano"] == ano_selected) &
            (df_cartao_movimentos["Mes"] == mes_selected_num)
        ].copy()
        valor_fatura_cartao_mes = float(df_cartao_mes["valor"].sum()) if not df_cartao_mes.empty else 0.0

        df_cartao_futuro = df_cartao_movimentos[
            (df_cartao_movimentos["data_dt"] > fim_mes_cartao) &
            (df_cartao_movimentos["data_dt"] <= limite_analise_cartao)
        ].copy()
        valor_cartao_futuro_total = float(df_cartao_futuro["valor"].sum()) if not df_cartao_futuro.empty else 0.0

        if not df_cartao_mes.empty:
            df_fatura_por_cartao = df_cartao_mes.groupby("Cartão", as_index=False)["valor"].sum()
            df_fatura_por_cartao = df_fatura_por_cartao.rename(columns={"valor": "Fatura Atual"})
            limites_por_nome = {cartao["nome"]: float(cartao["limite"] or 0.0) for cartao in lista_cartoes_cadastrados}
            df_fatura_por_cartao["Limite"] = df_fatura_por_cartao["Cartão"].map(limites_por_nome).fillna(0.0)
            df_fatura_por_cartao["% do Limite"] = df_fatura_por_cartao.apply(
                lambda row: (float(row["Fatura Atual"]) / float(row["Limite"]) * 100) if float(row["Limite"] or 0.0) > 0 else 0.0,
                axis=1,
            )

        if not df_cartao_futuro.empty:
            df_compromisso_futuro_cartao = df_cartao_futuro.groupby(["Mês", "Cartão"], as_index=False)["valor"].sum()
            df_compromisso_futuro_cartao = df_compromisso_futuro_cartao.rename(columns={"valor": "Valor Comprometido"})

        mascara_assinaturas = df_cartao_movimentos["satisfacao_str"].str.contains(
            "SUB:",
            regex=False,
            na=False
        )

        df_assinaturas_cartao = df_cartao_movimentos[
            mascara_assinaturas
        ].copy()

        if not df_assinaturas_cartao.empty:
            df_assinaturas_cartao["Serie"] = df_assinaturas_cartao[
                "satisfacao_str"
            ].apply(
                lambda texto: extrair_metadado_agenda(texto, "SUB")
            )

            df_assinaturas_cartao = df_assinaturas_cartao[
                df_assinaturas_cartao["Serie"].notna()
            ].copy()

            for serie_id, grupo_serie in df_assinaturas_cartao.groupby("Serie"):
                grupo_serie = grupo_serie.sort_values("data_dt")
                futuras = grupo_serie[
                    grupo_serie["data_dt"] >= hoje
                ].copy()

                if futuras.empty:
                    continue

                proxima_linha = futuras.iloc[0]
                ultima_linha = grupo_serie.iloc[-1]

                resumo = {
                    "serie_id": str(serie_id),
                    "nome": str(proxima_linha["Descrição Limpa"]),
                    "cartao": str(proxima_linha["Cartão"]),
                    "valor": float(proxima_linha["valor"]),
                    "proxima_cobranca": proxima_linha["data_dt"],
                    "programada_ate": ultima_linha["data_dt"],
                    "cobrancas_futuras": int(len(futuras)),
                    "grupo": str(
                        proxima_linha.get("grupo_orcamentario") or ""
                    ),
                    "subcategoria": str(
                        proxima_linha.get("subcategoria") or ""
                    ),
                }

                lista_assinaturas_ativas.append(resumo)

            lista_assinaturas_ativas = sorted(
                lista_assinaturas_ativas,
                key=lambda item: (
                    item["proxima_cobranca"],
                    item["nome"].lower()
                )
            )

            valor_mensal_assinaturas = sum(
                float(item["valor"])
                for item in lista_assinaturas_ativas
            )

percentual_fatura_renda_v4 = (valor_fatura_cartao_mes / renda_base_usuario) if renda_base_usuario > 0 else 0.0
limite_total_cartoes = sum(float(cartao.get("limite") or 0.0) for cartao in lista_cartoes_cadastrados)
percentual_fatura_limite_total = (valor_fatura_cartao_mes / limite_total_cartoes) if limite_total_cartoes > 0 else 0.0

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Configurações do Usuário")

nova_renda_input = st.sidebar.number_input("Sua Renda Mensal Base (R$):", min_value=0.0, value=renda_base_usuario if renda_base_usuario > 0 else 2500.00, step=50.0, format="%.2f")
if st.sidebar.button("💾 Salvar/Atualizar Renda Base"):
    try:
        supabase.table("movimentacoes").delete().eq("subcategoria", "Renda Base Nativa").eq("user_id", USER_ID).execute()
        supabase.table("movimentacoes").insert({
            "data": str(hoje), "valor": float(nova_renda_input), "tipo": "Faturamento ou Receita (Entrada)",
            "descricao": "[CONFIG_PERFIL] Renda Base", "grupo_orcamentario": "⚙️ CONFIGURAÇÃO",
            "subcategoria": "Renda Base Nativa", "satisfacao": "3 - Indispensável", "user_id": USER_ID
        }).execute()
        st.sidebar.success("Renda salva!")
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Erro: {e}")

LIMITE_ESSENCIAL = renda_base_usuario * 0.50       
text_limite_essencial = f"R$ {LIMITE_ESSENCIAL:,.2f}" if LIMITE_ESSENCIAL > 0 else "Não Definido"
LIMITE_ESTILO_DE_VIDA = renda_base_usuario * 0.30  
text_limite_estilo = f"R$ {LIMITE_ESTILO_DE_VIDA:,.2f}" if LIMITE_ESTILO_DE_VIDA > 0 else "Não Definido"

lista_nomes_dividas = [d["nome"] for d in lista_dividas_cadastradas] if lista_dividas_cadastradas else ["Empréstimos Bancários", "Cartão de Crédito Atrasado"]
comprometimento_parcelas_mensais = sum([d["parcela"] for d in lista_dividas_cadastradas])
indice_comprometimento = (comprometimento_parcelas_mensais / renda_base_usuario * 100) if renda_base_usuario > 0 else 0.0
lista_porquinhos_existentes = list(dicionario_metas_alvo.keys())
if not lista_porquinhos_existentes:
    lista_porquinhos_existentes = ["🧱 Reserva de Emergência", "🏡 Comprar Casa"]

MAPA_CATEGORIAS = {
    "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)": [
        "Alimentação Básica & Mercado", 
        "Contas Fixas (Luz, Água, Internet)", 
        "Habitação (Aluguel / Financiamento)", 
        "Saúde & Medicamentos", 
        "Transporte & Combustível",
        "Impostos & Obrigações Pessoais",
        "Pensão / Obrigações Legais",
        "Filho e Dependentes"
    ],
    "🟡 30% Estilo de Vida (Lazer e Custos Voláteis)": [
        "Lazer, Bares & Restaurantes", 
        "Delivery / iFood / Conforto", 
        "Vestuário, Compras & Presentes",
        "Eletrônicos & Tecnologia",
        "Estética, Cuidados & Academia", 
        "Viagens & Hobbies", 
        "Assinaturas (Netflix, Spotify)"
    ],
    "🚀 20% Aporte para a Liberdade (Investimentos e Futuro)": lista_porquinhos_existentes + ["➕ [Criar Nova Meta / Porquinho]"],
    "📋 Quitação de Dívidas (Amortizações e Acordos)": lista_nomes_dividas,
    "💼 Custos de Negócio (Projetos e Clínica)": [
        "Ferramentas SaaS & Softwares", 
        "Marketing & Anúncios", 
        "Infraestrutura & Custos Operacionais",
        "Impostos, Taxas & Obrigações"
    ]
}

# Códigos compactos para guardar a categoria pretendida dentro da Agenda
# sem substituir o grupo "AGENDA", necessário para identificar compromissos.
CATEGORIAS_RECEITA = [
    "Salário / Renda Base",
    "Trabalho Extra / Freelancer",
    "Prestação de Serviços",
    "Venda de Bem",
    "Aluguel Recebido",
    "Reembolso",
    "Comissão / Bonificação",
    "Receitas de Negócio",
    "Outros Recebimentos",
]


CODIGOS_GRUPO_AGENDA = {
    "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)": "E",
    "🟡 30% Estilo de Vida (Lazer e Custos Voláteis)": "L",
    "🚀 20% Aporte para a Liberdade (Investimentos e Futuro)": "A",
    "📋 Quitação de Dívidas (Amortizações e Acordos)": "D",
    "💼 Custos de Negócio (Projetos e Clínica)": "N",
}

GRUPOS_AGENDA_POR_CODIGO = {
    codigo_grupo: nome_grupo
    for nome_grupo, codigo_grupo in CODIGOS_GRUPO_AGENDA.items()
}


def categorias_validas_agenda(nome_grupo: str):
    """Retorna categorias utilizáveis pela Agenda."""
    return [
        categoria
        for categoria in MAPA_CATEGORIAS.get(nome_grupo, [])
        if "CRIAR NOVA META" not in str(categoria).upper()
    ]


def definir_metadado_agenda(texto: str, chave: str, valor: str) -> str:
    """Adiciona ou troca um metadado, preservando série, ordem e modalidade."""
    partes = [
        parte.strip()
        for parte in str(texto or "").split("|")
        if parte.strip()
    ]

    prefixo = f"{chave}:"
    encontrou = False
    resultado = []

    for parte in partes:
        if parte.startswith(prefixo):
            resultado.append(f"{chave}:{valor}")
            encontrou = True
        else:
            resultado.append(parte)

    if not encontrou:
        resultado.append(f"{chave}:{valor}")

    return "|".join(resultado) if resultado else f"{chave}:{valor}"


def inferir_grupo_por_subcategoria_agenda(subcategoria: str):
    """Tenta recuperar o grupo de registros antigos pela subcategoria."""
    subcategoria_limpa = str(subcategoria or "").strip()

    if not subcategoria_limpa:
        return None

    grupos_encontrados = [
        grupo
        for grupo in CODIGOS_GRUPO_AGENDA
        if subcategoria_limpa in categorias_validas_agenda(grupo)
    ]

    if len(grupos_encontrados) == 1:
        return grupos_encontrados[0]

    return None


def resolver_categoria_destino_agenda(
    texto_metadados: str,
    subcategoria: str
):
    """Resolve grupo e subcategoria que serão usados quando a conta for paga."""
    codigo_grupo = extrair_metadado_agenda(
        texto_metadados,
        "G"
    )

    grupo_destino = GRUPOS_AGENDA_POR_CODIGO.get(
        str(codigo_grupo or "").strip()
    )

    if grupo_destino is None:
        grupo_destino = inferir_grupo_por_subcategoria_agenda(
            subcategoria
        )

    categoria_destino = str(subcategoria or "").strip()

    if (
        grupo_destino is None
        or categoria_destino
        not in categorias_validas_agenda(grupo_destino)
    ):
        return None, None

    return grupo_destino, categoria_destino



def valor_ausente_seguro(valor) -> bool:
    """Detecta None, NaN, NaT e pd.NA sem provocar booleano ambíguo."""
    if valor is None:
        return True

    try:
        resultado = pd.isna(valor)

        if isinstance(resultado, bool):
            return resultado
    except (TypeError, ValueError):
        pass

    return False


def texto_seguro_registro(valor, padrao: str = "") -> str:
    """Converte uma célula em texto sem quebrar com valores ausentes."""
    if valor_ausente_seguro(valor):
        return padrao

    return str(valor).strip()


def numero_seguro_registro(valor, padrao=None):
    """Converte uma célula em número ou devolve o padrão."""
    convertido = pd.to_numeric(valor, errors="coerce")

    if pd.isna(convertido):
        return padrao

    return float(convertido)


def id_seguro_registro(valor):
    """Normaliza IDs numéricos ou textuais sem assumir que sempre são inteiros."""
    if valor_ausente_seguro(valor):
        raise ValueError("Compromisso sem identificador.")

    try:
        numero = float(valor)

        if numero.is_integer():
            return int(numero)
    except (TypeError, ValueError):
        pass

    texto = str(valor).strip()

    if not texto:
        raise ValueError("Compromisso sem identificador.")

    return texto


aba_diagnostico, aba_fluxo_futuro, aba_cartoes, aba_painel, aba_porquinhos, aba_agenda, aba_dividas = st.tabs([
    "🧭 Diagnóstico Financeiro",
    "📅 Fluxo de Caixa Futuro",
    "💳 Cartões & Faturas",
    "📊 Painel & Lançamentos", 
    "🐷 Meus Porquinhos & Rumo ao Milhão", 
    "📅 Agenda de Compromissos", 
    "📋 Gestão de Dívidas & Passivos"
])

# ==================== ABA 0 (DIAGNÓSTICO) ====================
with aba_diagnostico:
    st.title("🧭 Diagnóstico Financeiro")
    st.caption("Uma leitura prática do mês para transformar os lançamentos em decisão.")

    pontos_risco = 0
    alertas_diagnostico = []
    recomendacoes_diagnostico = []

    if renda_base_usuario <= 0:
        pontos_risco += 3
        alertas_diagnostico.append("A renda base ainda não foi definida. Sem isso, o diagnóstico perde precisão.")
        recomendacoes_diagnostico.append("Defina sua renda base na barra lateral antes de tomar decisões maiores.")

    if saldo_projetado_fim_mes < 0:
        pontos_risco += 3
        alertas_diagnostico.append("O saldo projetado para o fim do mês está negativo se agenda e fatura forem consideradas.")
        recomendacoes_diagnostico.append("Revise contas agendadas, gastos variáveis e compras no cartão antes de assumir novos compromissos.")
    elif saldo_projetado_fim_mes < (renda_base_usuario * 0.10) and renda_base_usuario > 0:
        pontos_risco += 1
        alertas_diagnostico.append("O saldo projetado está baixo em relação à renda base.")
        recomendacoes_diagnostico.append("Evite gastos não essenciais até criar uma folga maior de caixa.")

    if porcentagem_cartao_renda > 0.50:
        pontos_risco += 3
        alertas_diagnostico.append("A fatura do cartão já passa de 50% da renda base.")
        recomendacoes_diagnostico.append("Priorize reduzir cartão e evite parcelamentos novos neste ciclo.")
    elif porcentagem_cartao_renda > 0.30:
        pontos_risco += 2
        alertas_diagnostico.append("A fatura do cartão já passa de 30% da renda base.")
        recomendacoes_diagnostico.append("Acompanhe o cartão de perto; ele já começa a pressionar o mês seguinte.")
    elif porcentagem_cartao_renda > 0.15:
        pontos_risco += 1
        alertas_diagnostico.append("A fatura do cartão está controlada, mas merece acompanhamento.")

    if porcentagem_essencial > 1.0:
        pontos_risco += 2
        alertas_diagnostico.append("Os gastos essenciais ultrapassaram o limite planejado de 50% da renda.")
        recomendacoes_diagnostico.append("Revise contas fixas, mercado, transporte e compromissos obrigatórios.")

    if porcentagem_estilo > 1.0:
        pontos_risco += 1
        alertas_diagnostico.append("Os gastos de estilo de vida ultrapassaram o limite planejado de 30% da renda.")
        recomendacoes_diagnostico.append("Corte primeiro gastos de lazer, delivery, compras e assinaturas pouco usadas.")

    if indice_comprometimento > 30.0:
        pontos_risco += 3
        alertas_diagnostico.append("As parcelas de dívidas passam de 30% da renda base.")
        recomendacoes_diagnostico.append("Organize uma estratégia de quitação antes de acelerar metas ou compras parceladas.")
    elif indice_comprometimento > 15.0:
        pontos_risco += 2
        alertas_diagnostico.append("As parcelas de dívidas já têm peso relevante na renda.")
        recomendacoes_diagnostico.append("Evite assumir novas parcelas enquanto a dívida não cair.")

    if porcentagem_consumo_total > 1.0:
        pontos_risco += 3
        alertas_diagnostico.append("O consumo total do mês já ultrapassou a renda reconhecida no período.")
        recomendacoes_diagnostico.append("Reavalie o mês imediatamente: o padrão atual está acima da renda registrada.")
    elif porcentagem_consumo_total > 0.85:
        pontos_risco += 2
        alertas_diagnostico.append("O consumo total já passou de 85% da renda reconhecida no período.")
        recomendacoes_diagnostico.append("Reduza gastos variáveis para preservar caixa até o fechamento do mês.")

    if pontos_risco >= 8:
        status_mes = "Crítico"
        mensagem_status = "Seu mês precisa de intervenção. O app indica pressão alta sobre caixa, cartão ou dívidas."
        st.error(f"🚨 Status do mês: {status_mes}")
    elif pontos_risco >= 5:
        status_mes = "Risco"
        mensagem_status = "Seu mês ainda pode ser corrigido, mas já existem sinais claros de pressão financeira."
        st.warning(f"⚠️ Status do mês: {status_mes}")
    elif pontos_risco >= 2:
        status_mes = "Atenção"
        mensagem_status = "Seu mês está administrável, mas alguns indicadores merecem cuidado."
        st.info(f"🟡 Status do mês: {status_mes}")
    else:
        status_mes = "Saudável"
        mensagem_status = "Seu mês parece saudável com base nos dados registrados até agora."
        st.success(f"✅ Status do mês: {status_mes}")

    st.write(mensagem_status)

    col_diag1, col_diag2, col_diag3 = st.columns(3)
    col_diag1.metric("Saldo atual em conta", f"R$ {saldo_real_exibido:,.2f}")
    col_diag2.metric("Saldo projetado fim do mês", f"R$ {saldo_projetado_fim_mes:,.2f}")
    col_diag3.metric("Consumo total da renda", f"{porcentagem_consumo_total * 100:.1f}%")

    col_diag4, col_diag5, col_diag6 = st.columns(3)
    col_diag4.metric("Fatura / renda base", f"{porcentagem_cartao_renda * 100:.1f}%")
    col_diag5.metric("Dívidas / renda base", f"{indice_comprometimento:.1f}%")
    col_diag6.metric("Agenda líquida", f"R$ {(agenda_a_receber_mes - agenda_a_pagar_mes):,.2f}")

    st.markdown("---")
    st.subheader("📌 Leitura dos principais riscos")

    if alertas_diagnostico:
        for alerta in dict.fromkeys(alertas_diagnostico):
            st.write(f"- {alerta}")
    else:
        st.write("- Nenhum risco relevante identificado com os dados atuais.")

    st.markdown("---")
    st.subheader("🎯 Próximas ações recomendadas")

    if recomendacoes_diagnostico:
        for recomendacao in dict.fromkeys(recomendacoes_diagnostico):
            st.write(f"- {recomendacao}")
    else:
        st.write("- Continue registrando as movimentações e mantenha a fatura sob controle.")

    st.markdown("---")
    st.subheader("📊 Barras de controle")

    st.write(f"💳 Cartão de crédito: {porcentagem_cartao_renda * 100:.1f}% da renda base")
    st.progress(min(porcentagem_cartao_renda, 1.0))

    st.write(f"🔴 Essencial: {porcentagem_essencial * 100:.1f}% do limite de 50%")
    st.progress(min(porcentagem_essencial, 1.0))

    st.write(f"🟡 Estilo de vida: {porcentagem_estilo * 100:.1f}% do limite de 30%")
    st.progress(min(porcentagem_estilo, 1.0))

    st.write(f"📋 Dívidas: {indice_comprometimento:.1f}% da renda base")
    st.progress(min(indice_comprometimento / 100, 1.0))


# ==================== ABA 1 (FLUXO DE CAIXA FUTURO) ====================
with aba_fluxo_futuro:
    st.title("📅 Fluxo de Caixa Futuro")
    st.caption("Projeção dos próximos 7, 15 e 30 dias com base em agenda, fatura estimada e movimentações futuras já registradas.")

    if ano_selected != hoje.year or mes_selected_num != hoje.month:
        st.warning(
            "Você está com um mês diferente do mês atual selecionado nos filtros laterais. "
            "Esta aba usa a data de hoje como referência para projeção futura."
        )

    col_fluxo1, col_fluxo2, col_fluxo3, col_fluxo4 = st.columns(4)
    col_fluxo1.metric("Caixa base estimado hoje", f"R$ {saldo_base_fluxo_futuro:,.2f}")
    col_fluxo2.metric("Em 7 dias", f"R$ {saldo_projetado_7_dias:,.2f}")
    col_fluxo3.metric("Em 15 dias", f"R$ {saldo_projetado_15_dias:,.2f}")
    col_fluxo4.metric("Em 30 dias", f"R$ {saldo_projetado_30_dias:,.2f}")

    st.markdown("---")

    if saldo_projetado_30_dias < 0:
        st.error("🚨 Atenção: pela projeção atual, o caixa pode ficar negativo nos próximos 30 dias.")
    elif saldo_projetado_15_dias < 0:
        st.warning("⚠️ Atenção: o caixa pode ficar negativo antes de completar 15 dias.")
    elif saldo_projetado_7_dias < 0:
        st.warning("⚠️ Atenção: o caixa pode ficar negativo já nos próximos 7 dias.")
    elif saldo_projetado_30_dias < renda_base_usuario * 0.10 and renda_base_usuario > 0:
        st.info("🟡 O caixa continua positivo, mas com pouca folga para os próximos 30 dias.")
    else:
        st.success("✅ A projeção de caixa dos próximos 30 dias está positiva com os dados atuais.")

    st.markdown("### 🔎 Como essa projeção foi calculada")
    st.write(
        "O caixa base considera renda mensal cadastrada, entradas já realizadas no mês atual e saídas em dinheiro/Pix/débito já realizadas. "
        "Depois o sistema soma recebimentos futuros e subtrai contas agendadas, saídas futuras registradas e uma estimativa de fatura do cartão."
    )

    col_calc1, col_calc2, col_calc3 = st.columns(3)
    col_calc1.metric("Entradas realizadas no mês", f"R$ {entradas_realizadas_ate_hoje:,.2f}")
    col_calc2.metric("Saídas em caixa realizadas", f"R$ {saidas_caixa_realizadas_ate_hoje:,.2f}")
    col_calc3.metric("Fatura estimada atual", f"R$ {fatura_estimada_mes_atual:,.2f}")

    st.markdown("---")
    st.subheader("📍 Eventos que impactam o caixa")

    if df_fluxo_futuro.empty:
        st.info("Nenhum evento futuro encontrado nos próximos 30 dias. Cadastre contas na Agenda ou compras/parcelas futuras para enriquecer a projeção.")
    else:
        horizonte_escolhido = st.radio(
            "Horizonte de visualização:",
            [7, 15, 30],
            horizontal=True,
            format_func=lambda dias: f"Próximos {dias} dias",
        )
        data_limite_visual = hoje + datetime.timedelta(days=horizonte_escolhido)
        df_fluxo_visual = df_fluxo_futuro[df_fluxo_futuro["Data"] <= data_limite_visual].copy()

        if df_fluxo_visual.empty:
            st.info(f"Nenhum evento previsto para os próximos {horizonte_escolhido} dias.")
        else:
            df_fluxo_tabela = df_fluxo_visual.copy()
            df_fluxo_tabela["Data"] = df_fluxo_tabela["Data"].astype(str)
            df_fluxo_tabela["Entrada"] = df_fluxo_tabela["Entrada"].map(lambda v: f"R$ {v:,.2f}")
            df_fluxo_tabela["Saída"] = df_fluxo_tabela["Saída"].map(lambda v: f"R$ {v:,.2f}")
            df_fluxo_tabela["Saldo Projetado"] = df_fluxo_tabela["Saldo Projetado"].map(lambda v: f"R$ {v:,.2f}")
            st.dataframe(df_fluxo_tabela, use_container_width=True, hide_index=True)

            df_grafico_fluxo = df_fluxo_visual.groupby("Data", as_index=False).agg({"Entrada": "sum", "Saída": "sum"})
            saldo_grafico = saldo_base_fluxo_futuro
            saldos_por_dia = []
            for _, linha_dia in df_grafico_fluxo.iterrows():
                saldo_grafico += float(linha_dia["Entrada"]) - float(linha_dia["Saída"])
                saldos_por_dia.append(saldo_grafico)
            df_grafico_fluxo["Saldo Projetado"] = saldos_por_dia

            st.markdown("### 📈 Curva de saldo projetado")
            fig_fluxo = px.line(
                df_grafico_fluxo,
                x="Data",
                y="Saldo Projetado",
                markers=True,
                title="Saldo projetado ao longo do período",
            )
            fig_fluxo.update_layout(margin=dict(t=50, b=10, l=10, r=10))
            st.plotly_chart(fig_fluxo, use_container_width=True)

    st.markdown("---")
    st.subheader("🎯 Leitura prática")

    if saldo_projetado_30_dias < 0:
        st.write("- O foco agora deve ser preservar caixa. Evite compras parceladas, revise agenda de pagamentos e antecipe recebimentos se possível.")
    elif fatura_estimada_mes_atual > renda_base_usuario * 0.50 and renda_base_usuario > 0:
        st.write("- A fatura estimada está pesada. Mesmo com caixa positivo, o cartão pode pressionar o próximo ciclo.")
    elif not df_fluxo_futuro.empty and float(df_fluxo_futuro["Saída"].sum()) > float(df_fluxo_futuro["Entrada"].sum()):
        st.write("- Existem mais saídas futuras do que entradas previstas. O mês ainda está controlável, mas pede cautela.")
    else:
        st.write("- O fluxo futuro não mostra pressão relevante com os dados atuais. Continue registrando agenda e parcelas para manter a previsão confiável.")

    st.caption(
        "Observação: esta projeção não substitui o saldo real do banco. Ela depende da qualidade dos lançamentos feitos no app. "
        "Quanto mais completa estiver a agenda e o cartão, mais útil será o diagnóstico."
    )

# ==================== ABA 2 (CARTÕES & FATURAS) ====================
with aba_cartoes:
    st.title("💳 Cartões & Faturas")
    st.caption(
        "Controle separado para limite, fatura atual, compras parceladas, "
        "assinaturas mensais e meses futuros já comprometidos."
    )

    feedback_assinatura = st.session_state.pop(
        "feedback_assinatura",
        None
    )
    if feedback_assinatura:
        st.success(feedback_assinatura)

    col_card1, col_card2, col_card3, col_card4 = st.columns(4)
    col_card1.metric("Fatura do mês", f"R$ {valor_fatura_cartao_mes:,.2f}")
    col_card2.metric("Fatura / renda", f"{percentual_fatura_renda_v4 * 100:.1f}%")
    col_card3.metric("Limite total cadastrado", f"R$ {limite_total_cartoes:,.2f}")
    col_card4.metric("Próximos 6 meses", f"R$ {valor_cartao_futuro_total:,.2f}")

    if valor_fatura_cartao_mes <= 0:
        st.info("Nenhuma compra no cartão encontrada para o mês selecionado.")
    elif percentual_fatura_renda_v4 >= 0.70:
        st.error("🚨 Fatura muito pesada: ela já passa de 70% da renda base cadastrada.")
    elif percentual_fatura_renda_v4 >= 0.50:
        st.warning("⚠️ Fatura alta: ela já passa de 50% da renda base cadastrada.")
    elif percentual_fatura_renda_v4 >= 0.30:
        st.warning("🟡 Fatura em atenção: ela já passa de 30% da renda base cadastrada.")
    else:
        st.success("✅ Fatura aparentemente controlada em relação à renda base cadastrada.")

    if not lista_cartoes_cadastrados:
        st.info("Cadastre pelo menos um cartão para acompanhar limite, fechamento e vencimento. As compras sem cartão cadastrado continuam aparecendo como 'Cartão não identificado'.")

    st.markdown("---")
    st.subheader("➕ Cadastrar ou atualizar cartão")
    with st.form("form_config_cartao", clear_on_submit=True):
        col_cfg1, col_cfg2 = st.columns(2)
        nome_cartao_cfg = col_cfg1.text_input("Nome do cartão:", placeholder="Ex: Nubank, Itaú, Inter")
        limite_cartao_cfg = col_cfg2.number_input("Limite do cartão (R$):", min_value=0.0, step=100.0, format="%.2f")

        col_cfg3, col_cfg4 = st.columns(2)
        fechamento_cartao_cfg = col_cfg3.number_input("Dia de fechamento:", min_value=1, max_value=28, value=10, step=1)
        vencimento_cartao_cfg = col_cfg4.number_input("Dia de vencimento:", min_value=1, max_value=28, value=20, step=1)

        salvar_cartao_cfg = st.form_submit_button("Salvar cartão")

    if salvar_cartao_cfg and supabase:
        nome_cartao_limpo = nome_cartao_cfg.strip()
        if not nome_cartao_limpo:
            st.warning("Informe o nome do cartão.")
        elif limite_cartao_cfg <= 0:
            st.warning("Informe um limite maior que zero.")
        else:
            try:
                supabase.table("movimentacoes").delete().eq("descricao", "[CONFIG_CARTAO]").eq("subcategoria", nome_cartao_limpo).eq("user_id", USER_ID).execute()
                supabase.table("movimentacoes").insert({
                    "data": str(hoje),
                    "valor": float(limite_cartao_cfg),
                    "tipo": "Configuração",
                    "descricao": "[CONFIG_CARTAO]",
                    "grupo_orcamentario": "⚙️ CONFIGURAÇÃO CARTÃO",
                    "subcategoria": nome_cartao_limpo,
                    "satisfacao": f"fechamento:{int(fechamento_cartao_cfg)}|vencimento:{int(vencimento_cartao_cfg)}",
                    "user_id": USER_ID,
                }).execute()
                st.success("Cartão salvo com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar cartão: {e}")

    st.markdown("---")
    st.subheader("📌 Cartões cadastrados")
    if lista_cartoes_cadastrados:
        for cartao in lista_cartoes_cadastrados:
            col_cad1, col_cad2, col_cad3, col_cad4, col_cad5 = st.columns([3, 2, 2, 2, 2])
            col_cad1.write(f"**{cartao['nome']}**")
            col_cad2.write(f"Limite: R$ {float(cartao['limite']):,.2f}")
            col_cad3.write(f"Fecha dia {cartao['fechamento']}")
            col_cad4.write(f"Vence dia {cartao['vencimento']}")
            if col_cad5.button("Remover", key=f"del_card_{cartao['id']}"):
                try:
                    supabase.table("movimentacoes").delete().eq("id", cartao["id"]).eq("user_id", USER_ID).execute()
                    st.success("Cartão removido.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao remover cartão: {e}")
    else:
        st.write("Nenhum cartão cadastrado ainda.")

    st.markdown("---")
    st.subheader("🔁 Assinaturas recorrentes no cartão")
    st.caption(
        "Use esta área para ChatGPT, Gemini, Netflix, Spotify, internet "
        "e outras cobranças que se repetem mensalmente. Assinatura não é "
        "parcelamento: ela pode ser cancelada e o valor pode mudar."
    )

    col_ass_metric1, col_ass_metric2 = st.columns(2)
    col_ass_metric1.metric(
        "Assinaturas ativas",
        len(lista_assinaturas_ativas)
    )
    col_ass_metric2.metric(
        "Compromisso mensal estimado",
        f"R$ {valor_mensal_assinaturas:,.2f}"
    )

    if not lista_cartoes_cadastrados:
        st.warning(
            "Cadastre um cartão antes de criar uma assinatura recorrente."
        )
    else:
        grupos_permitidos_assinatura = [
            nome_grupo
            for nome_grupo in MAPA_CATEGORIAS.keys()
            if "APORTE" not in nome_grupo.upper()
            and "QUITAÇÃO" not in nome_grupo.upper()
        ]

        col_pre_ass1, col_pre_ass2, col_pre_ass3 = st.columns(3)

        cartao_assinatura = col_pre_ass1.selectbox(
            "Cartão da assinatura:",
            [cartao["nome"] for cartao in lista_cartoes_cadastrados],
            key="cartao_nova_assinatura"
        )

        grupo_assinatura = col_pre_ass2.selectbox(
            "Grupo orçamentário:",
            grupos_permitidos_assinatura,
            key="grupo_nova_assinatura"
        )

        categoria_assinatura = col_pre_ass3.selectbox(
            "Categoria:",
            MAPA_CATEGORIAS[grupo_assinatura],
            key="categoria_nova_assinatura"
        )

        with st.form(
            "form_nova_assinatura_cartao",
            clear_on_submit=True
        ):
            col_form_ass1, col_form_ass2 = st.columns(2)

            nome_assinatura = col_form_ass1.text_input(
                "Nome da assinatura:",
                placeholder="Ex.: ChatGPT, Gemini, Netflix"
            )

            valor_assinatura = col_form_ass2.number_input(
                "Valor mensal (R$):",
                min_value=0.0,
                step=0.01,
                format="%.2f"
            )

            col_form_ass3, col_form_ass4 = st.columns(2)

            primeira_cobranca_assinatura = col_form_ass3.date_input(
                "Data da primeira cobrança:",
                value=hoje
            )

            meses_assinatura = col_form_ass4.number_input(
                "Programar por quantos meses?",
                min_value=2,
                max_value=36,
                value=12,
                step=1,
                help=(
                    "A assinatura continua conceitualmente ativa, mas o app "
                    "programa um período controlado para evitar registros "
                    "infinitos. Depois você pode renovar."
                )
            )

            salvar_assinatura = st.form_submit_button(
                "Cadastrar assinatura mensal",
                use_container_width=True
            )

        if salvar_assinatura:
            nome_assinatura_limpo = str(
                nome_assinatura or ""
            ).strip()

            duplicada = any(
                item["nome"].strip().lower()
                == nome_assinatura_limpo.lower()
                and item["cartao"].strip().lower()
                == str(cartao_assinatura).strip().lower()
                for item in lista_assinaturas_ativas
            )

            if not nome_assinatura_limpo:
                st.warning("Informe o nome da assinatura.")
            elif float(valor_assinatura or 0) <= 0:
                st.warning("Informe um valor mensal maior que zero.")
            elif duplicada:
                st.warning(
                    "Já existe uma assinatura ativa com esse nome nesse "
                    "cartão. Edite a assinatura existente para evitar "
                    "cobrança duplicada."
                )
            else:
                serie_assinatura = uuid.uuid4().hex[:10]
                registros_assinatura = []

                for indice in range(int(meses_assinatura)):
                    data_cobranca = adicionar_meses(
                        primeira_cobranca_assinatura,
                        indice
                    )

                    registros_assinatura.append({
                        "data": str(data_cobranca),
                        "valor": float(valor_assinatura),
                        "tipo": "💳 Saída Cartão de Crédito",
                        "descricao": (
                            f"[CARTAO: {cartao_assinatura}] "
                            f"[ASSINATURA] {nome_assinatura_limpo}"
                        ),
                        "grupo_orcamentario": grupo_assinatura,
                        "subcategoria": categoria_assinatura,
                        "satisfacao": f"2|SUB:{serie_assinatura}",
                        "user_id": USER_ID
                    })

                salvou_assinatura = False

                try:
                    quantidade_criada = (
                        inserir_assinaturas_com_seguranca(
                            supabase,
                            registros_assinatura,
                            USER_ID,
                            serie_assinatura
                        )
                    )

                    st.session_state["feedback_assinatura"] = (
                        f"✅ Assinatura cadastrada e programada por "
                        f"{quantidade_criada} meses."
                    )
                    salvou_assinatura = True

                except Exception as e:
                    st.error(
                        "Não foi possível cadastrar a assinatura. "
                        "O sistema tentou remover qualquer cobrança criada "
                        "parcialmente."
                    )
                    st.exception(e)

                if salvou_assinatura:
                    st.rerun()

    if "assinatura_editando_id" not in st.session_state:
        st.session_state["assinatura_editando_id"] = None

    if "assinatura_cancelando_id" not in st.session_state:
        st.session_state["assinatura_cancelando_id"] = None

    if lista_assinaturas_ativas:
        st.markdown("#### Assinaturas ativas")

        for assinatura in lista_assinaturas_ativas:
            serie_id = assinatura["serie_id"]

            with st.container(border=True):
                col_ass1, col_ass2, col_ass3, col_ass4 = st.columns(
                    [3.2, 2.2, 1.8, 2.2]
                )

                col_ass1.markdown(f"**{assinatura['nome']}**")
                col_ass1.caption(assinatura["cartao"])

                col_ass2.markdown(
                    f"**R$ {assinatura['valor']:,.2f}/mês**"
                )
                col_ass2.caption(assinatura["subcategoria"])

                col_ass3.caption("Próxima")
                col_ass3.markdown(
                    f"**{assinatura['proxima_cobranca'].strftime('%d/%m/%Y')}**"
                )

                col_ass4.caption("Programada até")
                col_ass4.markdown(
                    f"**{assinatura['programada_ate'].strftime('%d/%m/%Y')}**"
                )

                st.caption(
                    f"{assinatura['cobrancas_futuras']} cobrança(s) "
                    "programada(s), incluindo a próxima."
                )

                col_acao_ass1, col_acao_ass2 = st.columns(2)

                if col_acao_ass1.button(
                    "✏️ Editar cobranças futuras",
                    key=f"editar_assinatura_{serie_id}",
                    use_container_width=True
                ):
                    st.session_state[
                        "assinatura_editando_id"
                    ] = serie_id
                    st.session_state[
                        "assinatura_cancelando_id"
                    ] = None

                if col_acao_ass2.button(
                    "⛔ Cancelar cobranças futuras",
                    key=f"cancelar_assinatura_{serie_id}",
                    use_container_width=True
                ):
                    st.session_state[
                        "assinatura_cancelando_id"
                    ] = serie_id
                    st.session_state[
                        "assinatura_editando_id"
                    ] = None

                if (
                    st.session_state["assinatura_editando_id"]
                    == serie_id
                ):
                    st.markdown("##### Editar próximas cobranças")

                    opcoes_cartao_edicao = [
                        cartao["nome"]
                        for cartao in lista_cartoes_cadastrados
                    ]

                    indice_cartao_atual = (
                        opcoes_cartao_edicao.index(
                            assinatura["cartao"]
                        )
                        if assinatura["cartao"]
                        in opcoes_cartao_edicao
                        else 0
                    )

                    with st.form(
                        f"form_editar_assinatura_{serie_id}"
                    ):
                        col_edit_ass1, col_edit_ass2 = st.columns(2)

                        novo_nome_assinatura = col_edit_ass1.text_input(
                            "Nome:",
                            value=assinatura["nome"]
                        )

                        novo_valor_assinatura = col_edit_ass2.number_input(
                            "Novo valor mensal (R$):",
                            min_value=0.01,
                            value=float(assinatura["valor"]),
                            step=0.01,
                            format="%.2f"
                        )

                        novo_cartao_assinatura = st.selectbox(
                            "Cartão:",
                            opcoes_cartao_edicao,
                            index=indice_cartao_atual,
                            key=f"novo_cartao_assinatura_{serie_id}"
                        )

                        col_salvar_ass, col_cancelar_edit_ass = st.columns(2)

                        salvar_edicao_assinatura = (
                            col_salvar_ass.form_submit_button(
                                "Salvar alterações",
                                use_container_width=True
                            )
                        )

                        cancelar_edicao_assinatura = (
                            col_cancelar_edit_ass.form_submit_button(
                                "Fechar edição",
                                use_container_width=True
                            )
                        )

                    if salvar_edicao_assinatura:
                        nome_editado = str(
                            novo_nome_assinatura or ""
                        ).strip()

                        if not nome_editado:
                            st.warning(
                                "Informe o nome da assinatura."
                            )
                        elif float(novo_valor_assinatura) <= 0:
                            st.warning(
                                "O valor precisa ser maior que zero."
                            )
                        else:
                            try:
                                (
                                    supabase
                                    .table("movimentacoes")
                                    .update({
                                        "valor": float(
                                            novo_valor_assinatura
                                        ),
                                        "descricao": (
                                            f"[CARTAO: "
                                            f"{novo_cartao_assinatura}] "
                                            f"[ASSINATURA] {nome_editado}"
                                        )
                                    })
                                    .eq("user_id", USER_ID)
                                    .ilike(
                                        "satisfacao",
                                        f"%SUB:{serie_id}%"
                                    )
                                    .gte("data", str(hoje))
                                    .execute()
                                )

                                st.session_state[
                                    "assinatura_editando_id"
                                ] = None
                                st.session_state[
                                    "feedback_assinatura"
                                ] = (
                                    "✅ Próximas cobranças da assinatura "
                                    "foram atualizadas."
                                )
                                st.rerun()

                            except Exception as e:
                                st.error(
                                    "Erro ao atualizar a assinatura: "
                                    f"{e}"
                                )

                    if cancelar_edicao_assinatura:
                        st.session_state[
                            "assinatura_editando_id"
                        ] = None
                        st.rerun()

                if (
                    st.session_state["assinatura_cancelando_id"]
                    == serie_id
                ):
                    st.warning(
                        "Isso excluirá somente as cobranças de hoje em "
                        "diante. As cobranças passadas continuarão no "
                        "histórico das faturas."
                    )

                    col_confirmar_cancel, col_fechar_cancel = st.columns(2)

                    if col_confirmar_cancel.button(
                        "Confirmar cancelamento",
                        key=f"confirmar_cancel_ass_{serie_id}",
                        type="primary",
                        use_container_width=True
                    ):
                        try:
                            (
                                supabase
                                .table("movimentacoes")
                                .delete()
                                .eq("user_id", USER_ID)
                                .ilike(
                                    "satisfacao",
                                    f"%SUB:{serie_id}%"
                                )
                                .gte("data", str(hoje))
                                .execute()
                            )

                            st.session_state[
                                "assinatura_cancelando_id"
                            ] = None
                            st.session_state[
                                "feedback_assinatura"
                            ] = (
                                "✅ Assinatura cancelada. O histórico "
                                "anterior foi preservado."
                            )
                            st.rerun()

                        except Exception as e:
                            st.error(
                                "Erro ao cancelar a assinatura: "
                                f"{e}"
                            )

                    if col_fechar_cancel.button(
                        "Não cancelar",
                        key=f"fechar_cancel_ass_{serie_id}",
                        use_container_width=True
                    ):
                        st.session_state[
                            "assinatura_cancelando_id"
                        ] = None
                        st.rerun()

    else:
        st.info(
            "Nenhuma assinatura mensal ativa foi cadastrada."
        )

    st.markdown("---")
    st.subheader(f"📊 Fatura por cartão - {lista_meses[mes_selected_num]}/{ano_selected}")

    if df_fatura_por_cartao.empty:
        st.info("Não há fatura de cartão para o período selecionado.")
    else:
        df_fatura_exibicao = df_fatura_por_cartao.copy()
        df_fatura_exibicao["Fatura Atual"] = df_fatura_exibicao["Fatura Atual"].map(lambda v: f"R$ {v:,.2f}")
        df_fatura_exibicao["Limite"] = df_fatura_exibicao["Limite"].map(lambda v: f"R$ {v:,.2f}" if v > 0 else "Não cadastrado")
        df_fatura_exibicao["% do Limite"] = df_fatura_exibicao["% do Limite"].map(lambda v: f"{v:.1f}%" if v > 0 else "-")
        st.dataframe(df_fatura_exibicao, use_container_width=True, hide_index=True)

        fig_fatura_cartao = px.bar(df_fatura_por_cartao, x="Cartão", y="Fatura Atual", title="Fatura atual por cartão")
        fig_fatura_cartao.update_layout(margin=dict(t=50, b=10, l=10, r=10))
        st.plotly_chart(fig_fatura_cartao, use_container_width=True)

    st.markdown("---")
    st.subheader("🧾 Compras no cartão do mês")
    if df_cartao_mes.empty:
        st.info("Nenhuma compra no cartão encontrada para este mês.")
    else:
        df_compras_mes = df_cartao_mes[
            [
                "data",
                "Descrição Limpa",
                "Natureza",
                "Cartão",
                "grupo_orcamentario",
                "subcategoria",
                "valor"
            ]
        ].copy()
        df_compras_mes.columns = [
            "Data",
            "Descrição",
            "Tipo",
            "Cartão",
            "Grupo",
            "Subcategoria",
            "Valor"
        ]
        df_compras_mes = df_compras_mes.sort_values(by="Data")
        df_compras_mes["Valor"] = df_compras_mes["Valor"].map(lambda v: f"R$ {v:,.2f}")
        st.dataframe(df_compras_mes, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("🔮 Parcelas e compras futuras")
    if df_compromisso_futuro_cartao.empty:
        st.info("Nenhuma parcela futura encontrada nos próximos 6 meses a partir do mês selecionado.")
    else:
        df_futuro_exibicao = df_compromisso_futuro_cartao.copy()
        df_futuro_exibicao["Valor Comprometido"] = df_futuro_exibicao["Valor Comprometido"].map(lambda v: f"R$ {v:,.2f}")
        st.dataframe(df_futuro_exibicao, use_container_width=True, hide_index=True)

        df_futuro_grafico = df_compromisso_futuro_cartao.groupby("Mês", as_index=False)["Valor Comprometido"].sum()
        fig_futuro_cartao = px.bar(df_futuro_grafico, x="Mês", y="Valor Comprometido", title="Cartão já comprometido nos próximos meses")
        fig_futuro_cartao.update_layout(margin=dict(t=50, b=10, l=10, r=10))
        st.plotly_chart(fig_futuro_cartao, use_container_width=True)

    st.markdown("---")
    st.subheader("🎯 Leitura prática")
    if percentual_fatura_renda_v4 >= 0.50:
        st.write("- O cartão está pressionando o orçamento. Antes de parcelar algo novo, veja se o fluxo de caixa futuro continua positivo.")
    elif valor_cartao_futuro_total > valor_fatura_cartao_mes and valor_cartao_futuro_total > 0:
        st.write("- O risco maior está nos próximos meses, não necessariamente na fatura atual. Revise compras parceladas.")
    elif valor_fatura_cartao_mes > 0:
        st.write("- A fatura atual existe, mas está relativamente controlada. Continue acompanhando para não transformar cartão em renda falsa.")
    else:
        st.write("- Ainda não há dados suficientes de cartão para uma leitura robusta.")


# ==================== ABA 1 ====================
with aba_painel:
    st.title("Meu Planner Financeiro")
    
    st.markdown(f"### 👑 Gestão de Teto Orçamentário ({lista_meses[mes_selected_num]})")
    c_caixa1, c_caixa2, c_caixa3 = st.columns(3)
    c_caixa1.metric(label="💰 Saldo Atual em Conta", value=f"R$ {saldo_real_exibido:,.2f}", help="Dinheiro físico disponível e líquido na sua conta corrente hoje.")
    c_caixa2.metric(label="📈 Faturamento Extra Capturado", value=f"R$ {faturamento_extra_mes:,.2f}", help="Total de receitas extras geradas neste ciclo mensal.")
    c_caixa3.metric(label="📉 Limite Total Consumido", value=f"R$ {total_consumido_orcamento:,.2f}", help="O impacto total real que seu padrão de vida gerou no seu orçamento (Dinheiro + Cartão).")

    st.markdown("---")
    col_cc_info1, col_cc_info2 = st.columns([2, 5])
    col_cc_info1.write(f"💳 **Fatura Acumulada:** R$ {fatura_acumulada_mes:,.2f}")
    
    porcentagem_cartao_renda = (fatura_acumulada_mes / renda_base_usuario) if renda_base_usuario > 0 else 0.0
    col_cc_info2.progress(min(porcentagem_cartao_renda, 1.0))
    if porcentagem_cartao_renda > 0.5:
        st.caption("⚠️ *Aviso de Risco:* Sua fatura atual já compromete mais de 50% da sua renda base fixa.")

    st.markdown("---")
    st.subheader("📊 Painel de Limites Orçamentários")
    
    st.write(f"🔴 **Gasto Essencial:** R$ {gastos_essencial:,.2f} de {text_limite_essencial}")
    st.progress(min(gastos_essencial / LIMITE_ESSENCIAL, 1.0) if LIMITE_ESSENCIAL > 0 else 0.0)
    st.write(f"🟡 **Estilo de Vida:** R$ {gastos_estilo:,.2f} de {text_limite_estilo}")
    st.progress(min(gastos_estilo / LIMITE_ESTILO_DE_VIDA, 1.0) if LIMITE_ESTILO_DE_VIDA > 0 else 0.0)
    st.write(f"📋 **Quitação de Dívidas Realizada:** R$ {gastos_dividas:,.2f}")
    
    try:
        if not df_filtrado.empty:
            df_saidas = df_filtrado[df_filtrado["tipo"].astype(str).str.contains("Saída|📱|💳", na=False)].copy()
            if not df_saidas.empty:
                st.markdown("---")
                st.subheader("🍩 Distribuição das Despesas Reais")
                df_pizza = df_saidas.groupby("grupo_orcamentario")["valor"].sum().reset_index()
                fig_donut = px.pie(df_pizza, values="valor", names="grupo_orcamentario", hole=0.4, color_discrete_sequence=px.colors.qualitative.Safe)
                fig_donut.update_layout(margin=dict(t=10, b=10, l=10, r=10))
                st.plotly_chart(fig_donut, use_container_width=True)
    except:
        pass

    st.markdown("---")
    st.subheader("📥 Registrar Movimentação Realizada")
    grupo_orcamentario = st.selectbox("Destinação Estratégica do Valor:", list(MAPA_CATEGORIAS.keys()), key="grupo_main")
    categoria = st.selectbox("Subcategoria Correspondente:", MAPA_CATEGORIAS[grupo_orcamentario], key="sub_main")

    criando_novo_porquinho = (categoria == "➕ [Criar Nova Meta / Porquinho]")
    nome_novo_fundo = ""
    val_alvo_novo_fundo = 0.0
    
    if criando_novo_porquinho:
        col_n1, col_n2 = st.columns(2)
        nome_novo_fundo = col_n1.text_input("Nome da Nova Meta:", placeholder="Ex: ✈️ Viagem")
        val_alvo_novo_fundo = col_n2.number_input("Valor Alvo da Meta (R$):", min_value=0.0, value=1000.00, step=50.0)

    tipo = st.radio("Fluxo Financeiro / Meio de Pagamento:", [
        "📱 Saída Dinheiro / Pix (Débito)", 
        "💳 Saída Cartão de Crédito", 
        "Faturamento ou Receita (Entrada)"
    ], horizontal=True, disabled=criando_novo_porquinho)

    is_parcelado = False
    num_parcelas = 1
    cartao_lancamento = "Cartão não identificado"
    if tipo == "💳 Saída Cartão de Crédito" and not criando_novo_porquinho:
        col_p1, col_p2 = st.columns(2)
        is_parcelado = col_p1.checkbox("Esta compra é parcelada?")
        if is_parcelado:
            num_parcelas = col_p2.number_input("Número de parcelas:", min_value=2, max_value=24, value=2, step=1)

        opcoes_cartao_lancamento = ["Cartão não identificado"] + [cartao["nome"] for cartao in lista_cartoes_cadastrados]
        cartao_lancamento = st.selectbox("Qual cartão foi usado?", opcoes_cartao_lancamento)
        st.caption(
            "Para ChatGPT, Gemini, Netflix e outras cobranças mensais, "
            "use 'Assinaturas recorrentes' na aba Cartões & Faturas. "
            "Não marque como compra parcelada."
        )

    with st.form("formulario_envio_blindado", clear_on_submit=True):
        valor = st.number_input("Qual o valor total da operação? (R$)", min_value=0.0, step=0.01, format="%.2f") if not is_parcelado else st.number_input("Qual o valor de CADA PARCELA? (R$)", min_value=0.0, step=0.01, format="%.2f")
        data_movimento = st.date_input("Data do evento:", datetime.date.today())
        descricao = st.text_input(
            "Descrição ou Estabelecimento:",
            placeholder=(
                "Ex.: Consulta pediátrica #filho | Babá sábado #filho"
            )
        )
        st.caption(
            "Use #filho na descrição para reunir todos os gastos do seu "
            "filho no filtro, mesmo quando a categoria for Saúde, "
            "Alimentação ou outra."
        )
        satisfacao = st.select_slider("🧠 Nível de necessidade?", options=["1 - Impulsivo / Evitável", "2 - Útil / Desejável", "3 - Indispensável"], value="2 - Útil / Desejável")
        botao_enviar = st.form_submit_button("Confirmar Lançamento")
        
    if botao_enviar and supabase:
        final_subcat = nome_novo_fundo.strip() if criando_novo_porquinho else categoria
        final_desc = f"Meta Criada: {final_subcat}" if criando_novo_porquinho else descricao.strip()
        final_tipo = "Faturamento ou Receita (Entrada)" if criando_novo_porquinho else tipo
        valor_para_salvar = float(val_alvo_novo_fundo) if criando_novo_porquinho else float(valor)

        if final_tipo == "💳 Saída Cartão de Crédito" and cartao_lancamento != "Cartão não identificado" and "[CARTAO:" not in final_desc.upper():
            final_desc = f"[CARTAO: {cartao_lancamento}] {final_desc}"

        if criando_novo_porquinho and not final_subcat:
            st.warning("Informe o nome da nova meta/porquinho.")
        elif valor_para_salvar <= 0:
            st.warning("Informe um valor maior que zero.")
        elif not final_desc:
            st.warning("Informe uma descrição para o lançamento.")
        else:
            try:
                if is_parcelado and final_tipo == "💳 Saída Cartão de Crédito":
                    base_date = data_movimento
                    for i in range(num_parcelas):
                        num_months = base_date.month - 1 + i
                        year_offset = num_months // 12
                        month_offset = (num_months % 12) + 1

                        try:
                            parcel_date = datetime.date(base_date.year + year_offset, month_offset, base_date.day)
                        except ValueError:
                            next_month_start = datetime.date(base_date.year + year_offset, month_offset + 1, 1) if month_offset < 12 else datetime.date(base_date.year + year_offset + 1, 1, 1)
                            parcel_date = next_month_start - datetime.timedelta(days=1)

                        desc_parcela = f"{final_desc} ({i+1}/{num_parcelas})"
                        supabase.table("movimentacoes").insert({
                            "data": str(parcel_date), "valor": valor_para_salvar, "tipo": final_tipo,
                            "descricao": desc_parcela, "grupo_orcamentario": grupo_orcamentario,
                            "subcategoria": final_subcat, "satisfacao": satisfacao, "user_id": USER_ID
                        }).execute()
                else:
                    supabase.table("movimentacoes").insert({
                        "data": str(data_movimento), "valor": valor_para_salvar, "tipo": final_tipo,
                        "descricao": final_desc, "grupo_orcamentario": grupo_orcamentario,
                        "subcategoria": final_subcat, "satisfacao": satisfacao, "user_id": USER_ID
                    }).execute()

                st.success("✅ Lançamento computado perfeitamente!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar movimentação: {e}")

    # --- 📋 SEÇÃO DE LANÇAMENTOS ---
    st.markdown("---")
    st.subheader("📋 Gerenciar Lançamentos do Período")
    st.caption(
        "Edite os campos diretamente na tabela. Para apagar um lançamento, "
        "marque a coluna 'Excluir?' e use o botão de exclusão."
    )

    feedback_lancamentos = st.session_state.pop(
        "feedback_lancamentos",
        None
    )
    if feedback_lancamentos:
        st.success(feedback_lancamentos)

    if "lancamentos_excluir_ids" not in st.session_state:
        st.session_state["lancamentos_excluir_ids"] = []

    if "editor_lancamentos_versao" not in st.session_state:
        st.session_state["editor_lancamentos_versao"] = 0

    def texto_seguro_editor(valor_celula):
        """Transforma valores do Pandas em texto sem avaliar pd.NA como booleano."""
        if valor_celula is None:
            return ""

        try:
            if pd.isna(valor_celula):
                return ""
        except (TypeError, ValueError):
            pass

        return str(valor_celula).strip()

    def booleano_seguro_editor(valor_celula):
        """Converte checkbox para bool sem quebrar com None ou pd.NA."""
        if valor_celula is None:
            return False

        try:
            if pd.isna(valor_celula):
                return False
        except (TypeError, ValueError):
            pass

        return bool(valor_celula)

    def id_seguro_editor(valor_id):
        """Preserva IDs inteiros e também aceita IDs textuais."""
        if valor_id is None:
            raise ValueError("Lançamento sem identificador.")

        try:
            if pd.isna(valor_id):
                raise ValueError("Lançamento sem identificador.")
        except (TypeError, ValueError):
            pass

        try:
            valor_float = float(valor_id)

            if valor_float.is_integer():
                return int(valor_float)
        except (TypeError, ValueError):
            pass

        return str(valor_id).strip()

    if supabase and not df_filtrado.empty:
        df_editor = df_filtrado[
            [
                "id",
                "data",
                "descricao",
                "grupo_orcamentario",
                "subcategoria",
                "valor",
                "tipo"
            ]
        ].copy()

        df_editor.columns = [
            "ID",
            "Data",
            "Descrição",
            "Grupo",
            "Subcategoria",
            "Valor (R$)",
            "Meio / Tipo"
        ]

        df_editor["Data"] = pd.to_datetime(
            df_editor["Data"],
            errors="coerce"
        ).dt.date

        for coluna_texto in [
            "Descrição",
            "Grupo",
            "Subcategoria",
            "Meio / Tipo"
        ]:
            df_editor[coluna_texto] = (
                df_editor[coluna_texto]
                .fillna("")
                .astype(str)
            )

        df_editor["Valor (R$)"] = pd.to_numeric(
            df_editor["Valor (R$)"],
            errors="coerce"
        ).fillna(0.0)

        df_editor["Excluir?"] = False
        df_editor = df_editor.reset_index(drop=True)

        grupos_editor = sorted(
            set(MAPA_CATEGORIAS.keys())
            | set(
                df_editor["Grupo"]
                .dropna()
                .astype(str)
                .tolist()
            )
        )

        subcategorias_editor = sorted(
            {
                str(subcategoria)
                for lista_subcategorias in MAPA_CATEGORIAS.values()
                for subcategoria in lista_subcategorias
                if "CRIAR NOVA META" not in str(subcategoria).upper()
            }
            | set(
                df_editor["Subcategoria"]
                .dropna()
                .astype(str)
                .tolist()
            )
        )

        meios_padrao = {
            "📱 Saída Dinheiro / Pix (Débito)",
            "💳 Saída Cartão de Crédito",
            "Faturamento ou Receita (Entrada)",
            "Gasto ou Investimento (Saída)"
        }

        meios_editor = sorted(
            meios_padrao
            | set(
                df_editor["Meio / Tipo"]
                .dropna()
                .astype(str)
                .tolist()
            )
        )

        chave_editor_lancamentos = (
            "editor_lancamentos_periodo_"
            f"{st.session_state['editor_lancamentos_versao']}"
        )

        dados_editados = st.data_editor(
            data=df_editor,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            disabled=["ID"],
            key=chave_editor_lancamentos,
            column_config={
                "ID": st.column_config.NumberColumn(
                    "ID",
                    help="Identificador interno do lançamento.",
                    format="%d"
                ),
                "Data": st.column_config.DateColumn(
                    "Data",
                    format="DD/MM/YYYY"
                ),
                "Descrição": st.column_config.TextColumn(
                    "Descrição",
                    help="Nome do estabelecimento, conta ou movimentação."
                ),
                "Grupo": st.column_config.SelectboxColumn(
                    "Grupo",
                    options=grupos_editor
                ),
                "Subcategoria": st.column_config.SelectboxColumn(
                    "Subcategoria",
                    options=subcategorias_editor
                ),
                "Valor (R$)": st.column_config.NumberColumn(
                    "Valor (R$)",
                    min_value=0.01,
                    step=0.01,
                    format="R$ %.2f"
                ),
                "Meio / Tipo": st.column_config.SelectboxColumn(
                    "Meio / Tipo",
                    options=meios_editor
                ),
                "Excluir?": st.column_config.CheckboxColumn(
                    "Excluir?",
                    help=(
                        "Marque somente os lançamentos que deseja apagar."
                    ),
                    default=False
                )
            }
        )

        estado_editor = st.session_state.get(
            chave_editor_lancamentos,
            {}
        )

        if isinstance(estado_editor, dict):
            linhas_editadas_estado = (
                estado_editor.get("edited_rows", {}) or {}
            )
        else:
            linhas_editadas_estado = {}

        col_salvar_tabela, col_excluir_tabela = st.columns(2)

        salvar_edicoes = col_salvar_tabela.button(
            "💾 Salvar edições",
            use_container_width=True,
            key="salvar_edicoes_lancamentos"
        )

        solicitar_exclusao = col_excluir_tabela.button(
            "🗑️ Excluir selecionados",
            use_container_width=True,
            key="solicitar_exclusao_lancamentos"
        )

        if salvar_edicoes:
            try:
                # O Streamlit registra apenas as células realmente alteradas.
                # A coluna de exclusão não é tratada como edição de conteúdo.
                linhas_com_edicao_real = {}

                for indice_linha, alteracoes_linha in (
                    linhas_editadas_estado.items()
                ):
                    if not isinstance(alteracoes_linha, dict):
                        continue

                    alteracoes_conteudo = {
                        coluna: valor
                        for coluna, valor in alteracoes_linha.items()
                        if coluna != "Excluir?"
                    }

                    if alteracoes_conteudo:
                        linhas_com_edicao_real[int(indice_linha)] = (
                            alteracoes_conteudo
                        )

                if not linhas_com_edicao_real:
                    st.success(
                        "✅ Tudo já está salvo. "
                        "Nenhuma alteração pendente foi identificada."
                    )
                else:
                    erros_validacao = []
                    atualizacoes = []

                    for indice_linha in sorted(
                        linhas_com_edicao_real.keys()
                    ):
                        if (
                            indice_linha < 0
                            or indice_linha >= len(dados_editados)
                            or indice_linha >= len(df_editor)
                        ):
                            erros_validacao.append(
                                "Uma linha editada não pôde ser localizada. "
                                "Atualize a página e tente novamente."
                            )
                            continue

                        row = dados_editados.iloc[indice_linha]
                        original = df_editor.iloc[indice_linha]

                        if booleano_seguro_editor(row.get("Excluir?")):
                            # Uma linha marcada para apagar não é atualizada.
                            continue

                        row_id = id_seguro_editor(row.get("ID"))
                        descricao_nova = texto_seguro_editor(
                            row.get("Descrição")
                        )
                        grupo_novo = texto_seguro_editor(
                            row.get("Grupo")
                        )
                        subcategoria_nova = texto_seguro_editor(
                            row.get("Subcategoria")
                        )
                        meio_novo = texto_seguro_editor(
                            row.get("Meio / Tipo")
                        )

                        valor_novo = pd.to_numeric(
                            row.get("Valor (R$)"),
                            errors="coerce"
                        )

                        data_nova_convertida = pd.to_datetime(
                            row.get("Data"),
                            errors="coerce"
                        )

                        if not descricao_nova:
                            erros_validacao.append(
                                f"ID {row_id}: a descrição não pode "
                                "ficar vazia."
                            )
                            continue

                        if (
                            pd.isna(valor_novo)
                            or float(valor_novo) <= 0
                        ):
                            erros_validacao.append(
                                f"ID {row_id}: o valor precisa ser "
                                "maior que zero."
                            )
                            continue

                        if pd.isna(data_nova_convertida):
                            erros_validacao.append(
                                f"ID {row_id}: informe uma data válida."
                            )
                            continue

                        if not grupo_novo:
                            erros_validacao.append(
                                f"ID {row_id}: selecione um grupo."
                            )
                            continue

                        if not subcategoria_nova:
                            erros_validacao.append(
                                f"ID {row_id}: selecione uma "
                                "subcategoria."
                            )
                            continue

                        if not meio_novo:
                            erros_validacao.append(
                                f"ID {row_id}: selecione o meio ou tipo."
                            )
                            continue

                        grupo_original = texto_seguro_editor(
                            original.get("Grupo")
                        )
                        subcategoria_original = texto_seguro_editor(
                            original.get("Subcategoria")
                        )

                        categoria_foi_alterada = (
                            grupo_novo != grupo_original
                            or subcategoria_nova
                            != subcategoria_original
                        )

                        if (
                            categoria_foi_alterada
                            and grupo_novo in MAPA_CATEGORIAS
                            and subcategoria_nova
                            not in MAPA_CATEGORIAS[grupo_novo]
                        ):
                            erros_validacao.append(
                                f"ID {row_id}: a subcategoria "
                                f"'{subcategoria_nova}' não pertence "
                                "ao grupo selecionado."
                            )
                            continue

                        data_nova = (
                            data_nova_convertida
                            .date()
                            .isoformat()
                        )

                        data_original_convertida = pd.to_datetime(
                            original.get("Data"),
                            errors="coerce"
                        )

                        data_original = (
                            data_original_convertida.date().isoformat()
                            if not pd.isna(data_original_convertida)
                            else ""
                        )

                        descricao_original = texto_seguro_editor(
                            original.get("Descrição")
                        )
                        meio_original = texto_seguro_editor(
                            original.get("Meio / Tipo")
                        )

                        valor_original = pd.to_numeric(
                            original.get("Valor (R$)"),
                            errors="coerce"
                        )

                        if pd.isna(valor_original):
                            valor_original = 0.0

                        houve_alteracao = any([
                            data_nova != data_original,
                            descricao_nova != descricao_original,
                            grupo_novo != grupo_original,
                            subcategoria_nova
                            != subcategoria_original,
                            abs(
                                float(valor_novo)
                                - float(valor_original)
                            ) > 0.000001,
                            meio_novo != meio_original
                        ])

                        if houve_alteracao:
                            atualizacoes.append(
                                (
                                    row_id,
                                    {
                                        "data": data_nova,
                                        "descricao": descricao_nova,
                                        "grupo_orcamentario": grupo_novo,
                                        "subcategoria": subcategoria_nova,
                                        "valor": float(valor_novo),
                                        "tipo": meio_novo
                                    }
                                )
                            )

                    if erros_validacao:
                        st.error(
                            "Existem campos que precisam ser corrigidos "
                            "antes de salvar:"
                        )

                        for erro in erros_validacao:
                            st.write(f"- {erro}")

                    elif not atualizacoes:
                        st.success(
                            "✅ Tudo já está salvo. "
                            "Nenhuma alteração pendente foi identificada."
                        )

                    else:
                        for row_id, payload in atualizacoes:
                            (
                                supabase
                                .table("movimentacoes")
                                .update(payload)
                                .eq("id", row_id)
                                .eq("user_id", USER_ID)
                                .execute()
                            )

                        st.session_state["feedback_lancamentos"] = (
                            f"✅ {len(atualizacoes)} lançamento(s) "
                            "atualizado(s)."
                        )

                        # Uma nova chave limpa o histórico de células
                        # editadas sem manipular diretamente o estado do widget.
                        st.session_state[
                            "editor_lancamentos_versao"
                        ] += 1
                        st.rerun()

            except Exception as e:
                # Todo o fluxo fica protegido para impedir a tela genérica
                # "Error running app".
                st.error(
                    "Não foi possível verificar ou salvar as edições. "
                    "Nenhum comando adicional será executado nesta tentativa."
                )
                st.code(
                    f"{type(e).__name__}: {e}",
                    language="text"
                )

        if solicitar_exclusao:
            try:
                mascara_exclusao = dados_editados[
                    "Excluir?"
                ].apply(booleano_seguro_editor)

                ids_selecionados = [
                    id_seguro_editor(valor_id)
                    for valor_id in (
                        dados_editados.loc[
                            mascara_exclusao,
                            "ID"
                        ].tolist()
                    )
                ]

                if not ids_selecionados:
                    st.warning(
                        "Marque pelo menos um lançamento na coluna "
                        "'Excluir?'."
                    )
                else:
                    st.session_state[
                        "lancamentos_excluir_ids"
                    ] = ids_selecionados
                    st.rerun()

            except Exception as e:
                st.error(
                    "Não foi possível preparar a exclusão."
                )
                st.code(
                    f"{type(e).__name__}: {e}",
                    language="text"
                )

        ids_pendentes_exclusao = st.session_state.get(
            "lancamentos_excluir_ids",
            []
        )

        if ids_pendentes_exclusao:
            linhas_pendentes = df_editor[
                df_editor["ID"].isin(ids_pendentes_exclusao)
            ]

            with st.container(border=True):
                st.warning(
                    "Confirme a exclusão definitiva dos lançamentos "
                    "selecionados."
                )

                for _, linha in linhas_pendentes.iterrows():
                    st.write(
                        f"- {linha['Data']} - "
                        f"{linha['Descrição']} - "
                        f"R$ {float(linha['Valor (R$)']):,.2f}"
                    )

                col_confirmar_exclusao, col_cancelar_exclusao = (
                    st.columns(2)
                )

                confirmar_exclusao = (
                    col_confirmar_exclusao.button(
                        "Sim, excluir definitivamente",
                        type="primary",
                        use_container_width=True,
                        key="confirmar_exclusao_lancamentos"
                    )
                )

                cancelar_exclusao = (
                    col_cancelar_exclusao.button(
                        "Cancelar",
                        use_container_width=True,
                        key="cancelar_exclusao_lancamentos"
                    )
                )

                if confirmar_exclusao:
                    try:
                        for row_id in ids_pendentes_exclusao:
                            (
                                supabase
                                .table("movimentacoes")
                                .delete()
                                .eq("id", row_id)
                                .eq("user_id", USER_ID)
                                .execute()
                            )

                        quantidade_excluida = len(
                            ids_pendentes_exclusao
                        )

                        st.session_state[
                            "lancamentos_excluir_ids"
                        ] = []

                        st.session_state[
                            "feedback_lancamentos"
                        ] = (
                            f"🗑️ {quantidade_excluida} "
                            "lançamento(s) excluído(s)."
                        )

                        st.session_state[
                            "editor_lancamentos_versao"
                        ] += 1
                        st.rerun()

                    except Exception as e:
                        st.error(
                            "Não foi possível excluir os lançamentos."
                        )
                        st.code(
                            f"{type(e).__name__}: {e}",
                            language="text"
                        )

                if cancelar_exclusao:
                    st.session_state[
                        "lancamentos_excluir_ids"
                    ] = []
                    st.rerun()

    else:
        st.info(
            "Nenhum lançamento efetuado ou encontrado para os filtros "
            "selecionados."
        )

# ==================== ABA 2 (PORQUINHOS) ====================
with aba_porquinhos:
    st.title("🐷 Meus Porquinhos & Metas Individuais")
    total_patrimonio_guardado = 0.0
    
    if dicionario_metas_alvo:
        for nome_meta, valor_alvo in dicionario_metas_alvo.items():
            guardado = dicionario_aportes_acumulados.get(nome_meta, 0.0)
            total_patrimonio_guardado += guardado
            st.subheader(f"{nome_meta}")
            c1, c2, c3 = st.columns(3)
            c1.metric(label="Valor Alvo Final", value=f"R$ {valor_alvo:,.2f}")
            c2.metric(label="Total Já Guardado", value=f"R$ {guardado:,.2f}")
            c3.metric(label="Quanto Falta", value=f"R$ {max(valor_alvo - guardado, 0.0):,.2f}")
            st.progress(min(guardado / valor_alvo, 1.0) if valor_alvo > 0 else 0.0)
            st.markdown("---")
    else:
        st.info("Nenhum porquinho ou meta de investimento criada ainda.")

# ==================== ABA 3 (AGENDA) ====================
with aba_agenda:
    st.title("📅 Agenda de Compromissos Financeiros")

    feedback_agenda = st.session_state.pop("feedback_agenda", None)
    if feedback_agenda:
        st.success(feedback_agenda)
    
    st.markdown("### 📊 Fluxo de Caixa Projetado da Agenda")
    col_ag1, col_ag2 = st.columns(2)
    col_ag1.metric(label="📉 Contas Agendadas a Pagar", value=f"R$ {agenda_a_pagar_mes:,.2f}")
    col_ag2.metric(label="🟢 Recebimentos Agendados", value=f"R$ {agenda_a_receber_mes:,.2f}")
    
    st.markdown("---")
    col_agenda1, col_agenda2 = st.columns(2)
    with col_agenda1:
        st.subheader("📌 Agendar Conta (A Pagar)")

        # Fica fora do formulário para o Streamlit atualizar os campos
        # imediatamente ao trocar a modalidade.
        modalidade_agendamento = st.selectbox(
            "Tipo de agendamento:",
            [
                "Lançamento único",
                "Conta parcelada",
                "Conta recorrente mensal"
            ],
            key="modalidade_agendamento_conta",
            help=(
                "Conta parcelada possui quantidade definida. Conta recorrente "
                "é usada para internet, aluguel, academia e outras mensalidades."
            )
        )

        st.markdown("##### Categoria do gasto")

        grupo_destino_agenda = st.selectbox(
            "Destinação Estratégica do Valor:",
            list(CODIGOS_GRUPO_AGENDA.keys()),
            key="grupo_destino_nova_conta_agenda",
            help=(
                "Quando a conta for marcada como paga, ela será lançada "
                "neste grupo orçamentário."
            )
        )

        opcoes_categoria_nova_agenda = categorias_validas_agenda(
            grupo_destino_agenda
        )

        categoria_destino_agenda = st.selectbox(
            "Subcategoria Correspondente:",
            opcoes_categoria_nova_agenda,
            key="categoria_destino_nova_conta_agenda"
        )

        with st.form("form_agenda_pagar_estavel", clear_on_submit=True):
            name_boleto = st.text_input(
                "Nome da Conta / Boleto:",
                placeholder="Ex.: Internet, aluguel, financiamento"
            )

            valor_boleto = st.number_input(
                "Valor de cada vencimento (R$):",
                min_value=0.0,
                step=0.01,
                format="%.2f"
            )

            vencimento_boleto = st.date_input(
                "Data do primeiro vencimento:",
                datetime.date.today()
            )

            quantidade_parcelas = 1
            meses_programados = 1

            if modalidade_agendamento == "Conta parcelada":
                quantidade_parcelas = st.number_input(
                    "Quantidade total de parcelas:",
                    min_value=2,
                    max_value=60,
                    value=2,
                    step=1
                )
                st.caption(
                    "Informe o valor de cada parcela, e não o valor total."
                )

            elif modalidade_agendamento == "Conta recorrente mensal":
                meses_programados = st.number_input(
                    "Por quantos meses deseja programar?",
                    min_value=2,
                    max_value=36,
                    value=12,
                    step=1
                )
                st.caption(
                    "Para contas sem data final, programe 12 meses e renove "
                    "depois. Isso evita registros infinitos no banco."
                )

            enviar_conta = st.form_submit_button(
                "Agendar Conta",
                use_container_width=True
            )

        if enviar_conta:
            nome_limpo = str(name_boleto or "").strip()

            if not nome_limpo:
                st.warning("Informe o nome da conta.")
            elif float(valor_boleto or 0) <= 0:
                st.warning("O valor precisa ser maior que zero.")
            else:
                registros_agenda = []
                serie_id = None

                if modalidade_agendamento == "Lançamento único":
                    registros_agenda.append({
                        "data": str(vencimento_boleto),
                        "valor": float(valor_boleto),
                        "tipo": "📱 Saída Dinheiro / Pix (Débito)",
                        "descricao": f"[AGENDA COMPROMISSO] {nome_limpo}",
                        "grupo_orcamentario": "📅 AGENDA: CONTAS A PAGAR",
                        "subcategoria": categoria_destino_agenda,
                        "satisfacao": (
                            "3|G:"
                            f"{CODIGOS_GRUPO_AGENDA[grupo_destino_agenda]}"
                        ),
                        "user_id": USER_ID
                    })

                else:
                    serie_id = uuid.uuid4().hex[:10]

                    if modalidade_agendamento == "Conta parcelada":
                        total_ocorrencias = int(quantidade_parcelas)
                        modalidade_curta = "P"
                        subcategoria_meta = categoria_destino_agenda
                    else:
                        total_ocorrencias = int(meses_programados)
                        modalidade_curta = "R"
                        subcategoria_meta = categoria_destino_agenda

                    for indice in range(total_ocorrencias):
                        data_ocorrencia = adicionar_meses(
                            vencimento_boleto,
                            indice
                        )

                        # Metadado compacto:
                        # S = série, M = modalidade, O = ordem.
                        metadados = (
                            f"3|S:{serie_id}|M:{modalidade_curta}"
                            f"|O:{indice + 1}/{total_ocorrencias}"
                            f"|G:{CODIGOS_GRUPO_AGENDA[grupo_destino_agenda]}"
                        )

                        registros_agenda.append({
                            "data": str(data_ocorrencia),
                            "valor": float(valor_boleto),
                            "tipo": "📱 Saída Dinheiro / Pix (Débito)",
                            "descricao": (
                                f"[AGENDA COMPROMISSO] {nome_limpo}"
                            ),
                            "grupo_orcamentario": (
                                "📅 AGENDA: CONTAS A PAGAR"
                            ),
                            "subcategoria": subcategoria_meta,
                            "satisfacao": metadados,
                            "user_id": USER_ID
                        })

                salvou_agenda = False

                try:
                    quantidade_salva = inserir_agendamentos_com_seguranca(
                        supabase,
                        registros_agenda,
                        USER_ID,
                        serie_id
                    )

                    if modalidade_agendamento == "Conta parcelada":
                        mensagem = (
                            f"✅ {quantidade_salva} parcelas foram agendadas."
                        )
                    elif modalidade_agendamento == "Conta recorrente mensal":
                        mensagem = (
                            f"✅ Conta recorrente programada por "
                            f"{quantidade_salva} meses."
                        )
                    else:
                        mensagem = "✅ Conta agendada."

                    st.session_state["feedback_agenda"] = mensagem
                    salvou_agenda = True

                except Exception as e:
                    st.error(
                        "Não foi possível salvar a conta. O sistema tentou "
                        "desfazer qualquer parcela criada parcialmente."
                    )
                    st.exception(e)

                # Fora do try: evita que o rerun seja tratado como erro.
                if salvou_agenda:
                    st.rerun()

    with col_agenda2:
        st.subheader("💰 Agendar Valor (A Receber)")

        modalidade_recebimento = st.selectbox(
            "Tipo de recebimento:",
            [
                "Recebimento único",
                "Recebimento parcelado",
                "Receita recorrente mensal"
            ],
            key="modalidade_agendamento_receita",
            help=(
                "Parcelado possui quantidade definida. Receita recorrente "
                "é usada para contratos mensais, aluguel e serviços contínuos."
            )
        )

        categoria_recebimento = st.selectbox(
            "Categoria da receita:",
            CATEGORIAS_RECEITA,
            index=CATEGORIAS_RECEITA.index(
                "Trabalho Extra / Freelancer"
            ),
            key="categoria_novo_recebimento"
        )

        with st.form(
            "form_agenda_receber_estavel",
            clear_on_submit=True
        ):
            nome_recebivel = st.text_input(
                "O que tem a receber?",
                placeholder="Ex.: Trabalho extra, venda do iPad, aluguel"
            )

            valor_recebivel = st.number_input(
                "Valor de cada recebimento (R$):",
                min_value=0.0,
                step=0.01,
                format="%.2f"
            )

            data_recebivel = st.date_input(
                "Data da primeira expectativa:",
                hoje
            )

            quantidade_parcelas_receber = 1
            meses_receita_recorrente = 1

            if modalidade_recebimento == "Recebimento parcelado":
                quantidade_parcelas_receber = st.number_input(
                    "Quantidade total de parcelas:",
                    min_value=2,
                    max_value=120,
                    value=2,
                    step=1
                )
                st.caption(
                    "Informe o valor de cada parcela, e não o valor total."
                )

            elif modalidade_recebimento == "Receita recorrente mensal":
                meses_receita_recorrente = st.number_input(
                    "Por quantos meses deseja programar?",
                    min_value=2,
                    max_value=60,
                    value=12,
                    step=1
                )
                st.caption(
                    "Use para contratos mensais, aluguel e serviços "
                    "recorrentes. A série pode ser renovada depois."
                )

            agendar_recebimento = st.form_submit_button(
                "Agendar Recebimento",
                use_container_width=True
            )

        if agendar_recebimento:
            nome_recebivel_limpo = str(
                nome_recebivel or ""
            ).strip()

            if not nome_recebivel_limpo:
                st.warning("Informe o que você tem a receber.")
            elif float(valor_recebivel or 0) <= 0:
                st.warning(
                    "O valor de cada recebimento precisa ser maior que zero."
                )
            else:
                registros_receber = []
                serie_receber = None

                if modalidade_recebimento == "Recebimento único":
                    registros_receber.append({
                        "data": str(data_recebivel),
                        "valor": float(valor_recebivel),
                        "tipo": "Faturamento ou Receita (Entrada)",
                        "descricao": (
                            "[AGENDA COMPROMISSO] "
                            f"{nome_recebivel_limpo}"
                        ),
                        "grupo_orcamentario": (
                            "📅 AGENDA: CONTAS A RECEBER"
                        ),
                        "subcategoria": categoria_recebimento,
                        "satisfacao": "3|MR:U",
                        "user_id": USER_ID
                    })

                else:
                    serie_receber = uuid.uuid4().hex[:10]

                    if (
                        modalidade_recebimento
                        == "Recebimento parcelado"
                    ):
                        total_recebimentos = int(
                            quantidade_parcelas_receber
                        )
                        modalidade_curta_receita = "P"
                    else:
                        total_recebimentos = int(
                            meses_receita_recorrente
                        )
                        modalidade_curta_receita = "R"

                    for indice in range(total_recebimentos):
                        data_ocorrencia_receita = adicionar_meses(
                            data_recebivel,
                            indice
                        )

                        metadados_receita = (
                            f"3|S:{serie_receber}"
                            f"|M:{modalidade_curta_receita}"
                            f"|O:{indice + 1}/{total_recebimentos}"
                            "|MR:REC"
                        )

                        registros_receber.append({
                            "data": str(data_ocorrencia_receita),
                            "valor": float(valor_recebivel),
                            "tipo": (
                                "Faturamento ou Receita (Entrada)"
                            ),
                            "descricao": (
                                "[AGENDA COMPROMISSO] "
                                f"{nome_recebivel_limpo}"
                            ),
                            "grupo_orcamentario": (
                                "📅 AGENDA: CONTAS A RECEBER"
                            ),
                            "subcategoria": categoria_recebimento,
                            "satisfacao": metadados_receita,
                            "user_id": USER_ID
                        })

                recebimentos_salvos = False

                try:
                    quantidade_recebimentos_salvos = (
                        inserir_agendamentos_com_seguranca(
                            supabase,
                            registros_receber,
                            USER_ID,
                            serie_receber
                        )
                    )

                    if (
                        modalidade_recebimento
                        == "Recebimento parcelado"
                    ):
                        mensagem_recebimento = (
                            f"✅ {quantidade_recebimentos_salvos} "
                            "parcelas a receber foram agendadas."
                        )
                    elif (
                        modalidade_recebimento
                        == "Receita recorrente mensal"
                    ):
                        mensagem_recebimento = (
                            "✅ Receita recorrente programada por "
                            f"{quantidade_recebimentos_salvos} meses."
                        )
                    else:
                        mensagem_recebimento = (
                            "✅ Recebimento agendado."
                        )

                    st.session_state["feedback_agenda"] = (
                        mensagem_recebimento
                    )
                    recebimentos_salvos = True

                except Exception as e:
                    st.error(
                        "Não foi possível agendar o recebimento. "
                        "O sistema tentou desfazer qualquer série incompleta."
                    )
                    st.code(
                        f"{type(e).__name__}: {e}",
                        language="text"
                    )

                if recebimentos_salvos:
                    st.rerun()

    st.markdown("---")
    st.subheader("📋 Seus Compromissos Mapeados")

    # Controla qual compromisso está sendo editado ou aguardando confirmação de exclusão.
    if "agenda_editando_id" not in st.session_state:
        st.session_state["agenda_editando_id"] = None

    if "agenda_excluir_id" not in st.session_state:
        st.session_state["agenda_excluir_id"] = None

    if supabase and not df_todos_dados.empty:
        df_agenda_pura = df_todos_dados[
            df_todos_dados["grupo_orcamentario"]
            .astype(str)
            .str.upper()
            .str.contains("AGENDA", na=False)
        ].copy()

        if not df_agenda_pura.empty:
            df_agenda_pura["data_agenda_ts"] = pd.to_datetime(
                df_agenda_pura["data_dt"],
                errors="coerce"
            )

            quantidade_datas_invalidas = int(
                df_agenda_pura["data_agenda_ts"].isna().sum()
            )

            modo_visualizacao_agenda = st.radio(
                "Exibir compromissos:",
                [
                    "Até os próximos 90 dias",
                    "Mês selecionado",
                    "Todos"
                ],
                horizontal=True,
                key="modo_visualizacao_agenda"
            )

            if modo_visualizacao_agenda == "Até os próximos 90 dias":
                inicio_agenda = pd.Timestamp(hoje)
                limite_agenda = pd.Timestamp(
                    hoje + datetime.timedelta(days=90)
                )

                mascara_periodo_agenda = (
                    df_agenda_pura["data_agenda_ts"].notna()
                    & (
                        df_agenda_pura["data_agenda_ts"]
                        >= inicio_agenda
                    )
                    & (
                        df_agenda_pura["data_agenda_ts"]
                        <= limite_agenda
                    )
                )

                df_agenda_pura = df_agenda_pura.loc[
                    mascara_periodo_agenda
                ].copy()

            elif modo_visualizacao_agenda == "Mês selecionado":
                mascara_mes_agenda = (
                    df_agenda_pura["data_agenda_ts"].notna()
                    & (
                        df_agenda_pura["data_agenda_ts"].dt.year
                        == int(ano_selected)
                    )
                    & (
                        df_agenda_pura["data_agenda_ts"].dt.month
                        == int(mes_selected_num)
                    )
                )

                df_agenda_pura = df_agenda_pura.loc[
                    mascara_mes_agenda
                ].copy()

            else:
                # Registros com data inválida não podem ser operados com
                # segurança e ficam fora da listagem, mas o usuário é avisado.
                df_agenda_pura = df_agenda_pura.loc[
                    df_agenda_pura["data_agenda_ts"].notna()
                ].copy()

            df_agenda_pura = df_agenda_pura.sort_values(
                by="data_agenda_ts"
            )

            if quantidade_datas_invalidas > 0:
                st.warning(
                    f"{quantidade_datas_invalidas} compromisso(s) com data "
                    "inválida foram ignorados para evitar falha no painel."
                )

            st.caption(
                f"{len(df_agenda_pura)} compromisso(s) exibido(s)."
            )

            if df_agenda_pura.empty:
                st.info(
                    "Nenhum compromisso encontrado para o período "
                    "selecionado."
                )

            for _, row in df_agenda_pura.iterrows():
                try:
                    id_item = id_seguro_registro(
                        row.get("id")
                    )

                    desc_pura = texto_seguro_registro(
                        row.get("descricao")
                    ).replace(
                        "[AGENDA COMPROMISSO] ",
                        ""
                    ).strip()

                    valor_item = numero_seguro_registro(
                        row.get("valor")
                    )

                    if valor_item is None:
                        raise ValueError(
                            f"Compromisso {id_item} com valor inválido."
                        )

                    grupo_item = texto_seguro_registro(
                        row.get("grupo_orcamentario")
                    )
                    eh_conta_pagar = "PAGAR" in grupo_item.upper()

                    texto_metadados = texto_seguro_registro(
                        row.get("satisfacao")
                    )
                    serie_id_item = (
                        extrair_metadado_agenda(texto_metadados, "SERIE")
                        or extrair_metadado_agenda(texto_metadados, "S")
                    )

                    modalidade_item = (
                        extrair_metadado_agenda(
                            texto_metadados,
                            "MODALIDADE"
                        )
                        or extrair_metadado_agenda(texto_metadados, "M")
                    )

                    ordem_item = (
                        extrair_metadado_agenda(texto_metadados, "ORDEM")
                        or extrair_metadado_agenda(texto_metadados, "O")
                    )

                    grupo_destino_item, categoria_destino_item = (
                        resolver_categoria_destino_agenda(
                            texto_metadados,
                            row.get("subcategoria")
                        )
                    )

                    if modalidade_item == "P":
                        modalidade_item = "PARCELADA"
                    elif modalidade_item == "R":
                        modalidade_item = "RECORRENTE"

                    identificador_repeticao = ""

                    if modalidade_item == "PARCELADA":
                        identificador_repeticao = (
                            f" · 📦 Parcela {ordem_item or ''}"
                        )
                    elif modalidade_item == "RECORRENTE":
                        identificador_repeticao = (
                            f" · 🔁 Mensal {ordem_item or ''}"
                        )

                    data_item_ts = row.get(
                        "data_agenda_ts"
                    )

                    if (
                        data_item_ts is None
                        or pd.isna(data_item_ts)
                    ):
                        raise ValueError(
                            f"Compromisso {id_item} com data inválida."
                        )

                    data_item = data_item_ts.date()

                    col_info, col_status, col_baixa, col_editar, col_excluir = st.columns(
                        [4.8, 1.5, 1.5, 1.3, 1.3]
                    )

                    col_info.write(
                        f"📅 **{data_item.strftime('%Y-%m-%d')}** - "
                        f"{desc_pura}{identificador_repeticao} "
                        f"| **R$ {valor_item:,.2f}**"
                    )

                    if eh_conta_pagar:
                        if grupo_destino_item and categoria_destino_item:
                            col_info.caption(
                                f"Categoria: {grupo_destino_item} > "
                                f"{categoria_destino_item}"
                            )
                        else:
                            col_info.caption(
                                "⚠️ Categoria não definida. Use Editar antes "
                                "de marcar como pago."
                            )
                    else:
                        categoria_receita_item = texto_seguro_registro(
                            row.get("subcategoria")
                        )

                        if categoria_receita_item in CATEGORIAS_RECEITA:
                            col_info.caption(
                                f"Categoria da receita: "
                                f"{categoria_receita_item}"
                            )
                        else:
                            col_info.caption(
                                "⚠️ Categoria da receita não definida. "
                                "Use Editar antes de receber."
                            )

                    if eh_conta_pagar:
                        col_status.caption("🔴 A Pagar")

                        if col_baixa.button(
                            "✅ Pagar",
                            key=f"pay_{id_item}",
                            use_container_width=True
                        ):
                            if not (
                                grupo_destino_item
                                and categoria_destino_item
                            ):
                                st.warning(
                                    "Defina o grupo e a subcategoria deste "
                                    "compromisso em Editar antes de pagar."
                                )
                            else:
                                try:
                                    resposta_baixa = (
                                        supabase
                                        .table("movimentacoes")
                                        .insert({
                                            "data": str(hoje),
                                            "valor": valor_item,
                                            "tipo": (
                                                "📱 Saída Dinheiro / Pix "
                                                "(Débito)"
                                            ),
                                            "descricao": (
                                                f"{desc_pura} (Pago)"
                                            ),
                                            "grupo_orcamentario": (
                                                grupo_destino_item
                                            ),
                                            "subcategoria": (
                                                categoria_destino_item
                                            ),
                                            "satisfacao": (
                                                "3 - Indispensável"
                                            ),
                                            "user_id": USER_ID
                                        })
                                        .execute()
                                    )

                                    dados_baixa = (
                                        getattr(
                                            resposta_baixa,
                                            "data",
                                            None
                                        )
                                        or []
                                    )

                                    try:
                                        (
                                            supabase
                                            .table("movimentacoes")
                                            .delete()
                                            .eq("id", id_item)
                                            .eq("user_id", USER_ID)
                                            .execute()
                                        )
                                    except Exception:
                                        for item_baixa in dados_baixa:
                                            if (
                                                isinstance(item_baixa, dict)
                                                and item_baixa.get("id")
                                                is not None
                                            ):
                                                (
                                                    supabase
                                                    .table("movimentacoes")
                                                    .delete()
                                                    .eq(
                                                        "id",
                                                        item_baixa["id"]
                                                    )
                                                    .eq(
                                                        "user_id",
                                                        USER_ID
                                                    )
                                                    .execute()
                                                )
                                        raise

                                    st.session_state["feedback_agenda"] = (
                                        "✅ Compromisso marcado como pago em "
                                        f"{categoria_destino_item}."
                                    )
                                    st.rerun()

                                except Exception as e:
                                    st.error(
                                        "Erro ao marcar como pago: "
                                        f"{e}"
                                    )

                    else:
                        col_status.caption("🟢 A Receber")

                        if col_baixa.button(
                            "💰 Receber",
                            key=f"rec_{id_item}",
                            use_container_width=True
                        ):
                            categoria_receita_item = (
                                texto_seguro_registro(
                                    row.get("subcategoria")
                                )
                            )

                            if (
                                categoria_receita_item
                                not in CATEGORIAS_RECEITA
                            ):
                                st.warning(
                                    "Defina a categoria da receita em "
                                    "Editar antes de marcar como recebido."
                                )
                            else:
                                try:
                                    resposta_recebimento = (
                                        supabase
                                        .table("movimentacoes")
                                        .insert({
                                            "data": str(hoje),
                                            "valor": valor_item,
                                            "tipo": (
                                                "Faturamento ou Receita "
                                                "(Entrada)"
                                            ),
                                            "descricao": (
                                                f"{desc_pura} (Recebido)"
                                            ),
                                            "grupo_orcamentario": (
                                                "💰 RECEITAS"
                                            ),
                                            "subcategoria": (
                                                categoria_receita_item
                                            ),
                                            "satisfacao": (
                                                "3 - Indispensável"
                                            ),
                                            "user_id": USER_ID
                                        })
                                        .execute()
                                    )

                                    dados_recebimento = (
                                        getattr(
                                            resposta_recebimento,
                                            "data",
                                            None
                                        )
                                        or []
                                    )

                                    try:
                                        (
                                            supabase
                                            .table("movimentacoes")
                                            .delete()
                                            .eq("id", id_item)
                                            .eq("user_id", USER_ID)
                                            .execute()
                                        )
                                    except Exception:
                                        for item_recebido in (
                                            dados_recebimento
                                        ):
                                            if (
                                                isinstance(
                                                    item_recebido,
                                                    dict
                                                )
                                                and item_recebido.get("id")
                                                is not None
                                            ):
                                                (
                                                    supabase
                                                    .table(
                                                        "movimentacoes"
                                                    )
                                                    .delete()
                                                    .eq(
                                                        "id",
                                                        item_recebido["id"]
                                                    )
                                                    .eq(
                                                        "user_id",
                                                        USER_ID
                                                    )
                                                    .execute()
                                                )
                                        raise

                                    st.session_state[
                                        "feedback_agenda"
                                    ] = (
                                        "✅ Recebimento lançado em "
                                        f"{categoria_receita_item}."
                                    )
                                    st.rerun()

                                except Exception as e:
                                    st.error(
                                        "Erro ao marcar como recebido."
                                    )
                                    st.code(
                                        f"{type(e).__name__}: {e}",
                                        language="text"
                                    )

                    if col_editar.button(
                        "✏️ Editar",
                        key=f"edit_agenda_{id_item}",
                        use_container_width=True
                    ):
                        st.session_state["agenda_editando_id"] = id_item
                        st.session_state["agenda_excluir_id"] = None

                    if col_excluir.button(
                        "🗑️ Excluir",
                        key=f"delete_agenda_{id_item}",
                        use_container_width=True
                    ):
                        st.session_state["agenda_excluir_id"] = id_item
                        st.session_state["agenda_editando_id"] = None

                    # Formulário de edição aberto apenas para o item escolhido.
                    if st.session_state["agenda_editando_id"] == id_item:
                        with st.container(border=True):
                            st.markdown(f"#### ✏️ Editando: {desc_pura}")

                            if serie_id_item:
                                st.caption(
                                    "Nome, valor e data alteram somente este "
                                    "vencimento. A categoria pode ser aplicada "
                                    "à série inteira."
                                )

                            grupo_padrao_edicao = (
                                grupo_destino_item
                                if grupo_destino_item
                                in CODIGOS_GRUPO_AGENDA
                                else list(CODIGOS_GRUPO_AGENDA.keys())[0]
                            )

                            indice_grupo_edicao = list(
                                CODIGOS_GRUPO_AGENDA.keys()
                            ).index(grupo_padrao_edicao)

                            grupo_edicao_agenda = st.selectbox(
                                "Destinação Estratégica do Valor:",
                                list(CODIGOS_GRUPO_AGENDA.keys()),
                                index=indice_grupo_edicao,
                                key=f"grupo_edicao_agenda_{id_item}"
                            )

                            categorias_edicao_agenda = (
                                categorias_validas_agenda(
                                    grupo_edicao_agenda
                                )
                            )

                            categoria_padrao_edicao = (
                                categoria_destino_item
                                if categoria_destino_item
                                in categorias_edicao_agenda
                                else categorias_edicao_agenda[0]
                            )

                            categoria_edicao_agenda = st.selectbox(
                                "Subcategoria Correspondente:",
                                categorias_edicao_agenda,
                                index=categorias_edicao_agenda.index(
                                    categoria_padrao_edicao
                                ),
                                key=f"categoria_edicao_agenda_{id_item}"
                            )

                            categoria_receita_edicao = (
                                texto_seguro_registro(
                                    row.get("subcategoria")
                                )
                            )

                            if (
                                categoria_receita_edicao
                                not in CATEGORIAS_RECEITA
                            ):
                                categoria_receita_edicao = (
                                    "Outros Recebimentos"
                                )

                            if not eh_conta_pagar:
                                categoria_receita_edicao = st.selectbox(
                                    "Categoria da receita:",
                                    CATEGORIAS_RECEITA,
                                    index=CATEGORIAS_RECEITA.index(
                                        categoria_receita_edicao
                                    ),
                                    key=(
                                        f"categoria_receita_edicao_"
                                        f"{id_item}"
                                    )
                                )

                            with st.form(f"form_editar_agenda_{id_item}"):
                                col_e1, col_e2 = st.columns([2, 1])

                                nova_descricao = col_e1.text_input(
                                    "Nome do compromisso:",
                                    value=desc_pura
                                )

                                novo_valor = col_e2.number_input(
                                    "Valor (R$):",
                                    min_value=0.01,
                                    value=valor_item,
                                    step=0.01,
                                    format="%.2f"
                                )

                                col_e3, col_e4 = st.columns(2)

                                nova_data = col_e3.date_input(
                                    "Data:",
                                    value=data_item
                                )

                                opcoes_status = ["A Pagar", "A Receber"]
                                status_atual = (
                                    "A Pagar"
                                    if eh_conta_pagar
                                    else "A Receber"
                                )

                                novo_status = col_e4.selectbox(
                                    "Tipo do compromisso:",
                                    opcoes_status,
                                    index=opcoes_status.index(
                                        status_atual
                                    )
                                )

                                aplicar_categoria_serie = False

                                if serie_id_item:
                                    aplicar_categoria_serie = st.checkbox(
                                        "Aplicar esta categoria a todas as "
                                        "parcelas/mensalidades da série",
                                        value=False
                                    )

                                col_salvar, col_cancelar = st.columns(2)

                                salvar_edicao = (
                                    col_salvar.form_submit_button(
                                        "💾 Salvar alterações",
                                        use_container_width=True
                                    )
                                )

                                cancelar_edicao = (
                                    col_cancelar.form_submit_button(
                                        "Cancelar",
                                        use_container_width=True
                                    )
                                )

                            if salvar_edicao:
                                descricao_limpa = str(
                                    nova_descricao or ""
                                ).strip()

                                if not descricao_limpa:
                                    st.warning(
                                        "Informe um nome para o compromisso."
                                    )
                                elif float(novo_valor or 0) <= 0:
                                    st.warning(
                                        "O valor precisa ser maior que zero."
                                    )
                                else:
                                    if novo_status == "A Pagar":
                                        novo_grupo_agenda = (
                                            "📅 AGENDA: CONTAS A PAGAR"
                                        )
                                        novo_tipo = (
                                            "📱 Saída Dinheiro / Pix "
                                            "(Débito)"
                                        )
                                        nova_subcategoria = (
                                            categoria_edicao_agenda
                                        )
                                        novos_metadados = (
                                            definir_metadado_agenda(
                                                texto_metadados,
                                                "G",
                                                CODIGOS_GRUPO_AGENDA[
                                                    grupo_edicao_agenda
                                                ]
                                            )
                                        )
                                    else:
                                        novo_grupo_agenda = (
                                            "📅 AGENDA: CONTAS A RECEBER"
                                        )
                                        novo_tipo = (
                                            "Faturamento ou Receita "
                                            "(Entrada)"
                                        )
                                        nova_subcategoria = (
                                            "Valores a Receber"
                                        )
                                        novos_metadados = texto_metadados

                                    try:
                                        (
                                            supabase
                                            .table("movimentacoes")
                                            .update({
                                                "data": str(nova_data),
                                                "valor": float(novo_valor),
                                                "tipo": novo_tipo,
                                                "descricao": (
                                                    "[AGENDA COMPROMISSO] "
                                                    f"{descricao_limpa}"
                                                ),
                                                "grupo_orcamentario": (
                                                    novo_grupo_agenda
                                                ),
                                                "subcategoria": (
                                                    nova_subcategoria
                                                ),
                                                "satisfacao": (
                                                    novos_metadados
                                                )
                                            })
                                            .eq("id", id_item)
                                            .eq("user_id", USER_ID)
                                            .execute()
                                        )

                                        if (
                                            serie_id_item
                                            and aplicar_categoria_serie
                                            and novo_status == "A Pagar"
                                        ):
                                            linhas_da_serie = (
                                                df_todos_dados[
                                                    df_todos_dados[
                                                        "satisfacao"
                                                    ]
                                                    .fillna("")
                                                    .astype(str)
                                                    .apply(
                                                        lambda texto: (
                                                            extrair_metadado_agenda(
                                                                texto,
                                                                "S"
                                                            )
                                                            or
                                                            extrair_metadado_agenda(
                                                                texto,
                                                                "SERIE"
                                                            )
                                                        )
                                                        == serie_id_item
                                                    )
                                                ]
                                            )

                                            for _, linha_serie in (
                                                linhas_da_serie.iterrows()
                                            ):
                                                meta_linha_serie = (
                                                    definir_metadado_agenda(
                                                        str(
                                                            linha_serie.get(
                                                                "satisfacao"
                                                            )
                                                            or ""
                                                        ),
                                                        "G",
                                                        CODIGOS_GRUPO_AGENDA[
                                                            grupo_edicao_agenda
                                                        ]
                                                    )
                                                )

                                                (
                                                    supabase
                                                    .table(
                                                        "movimentacoes"
                                                    )
                                                    .update({
                                                        "subcategoria": (
                                                            categoria_edicao_agenda
                                                        ),
                                                        "satisfacao": (
                                                            meta_linha_serie
                                                        )
                                                    })
                                                    .eq(
                                                        "id",
                                                        id_seguro_registro(
                                                            linha_serie.get(
                                                                "id"
                                                            )
                                                        )
                                                    )
                                                    .eq(
                                                        "user_id",
                                                        USER_ID
                                                    )
                                                    .execute()
                                                )

                                        st.session_state[
                                            "agenda_editando_id"
                                        ] = None
                                        st.session_state[
                                            "feedback_agenda"
                                        ] = (
                                            "✅ Compromisso atualizado com "
                                            "a categoria correta."
                                        )
                                        st.rerun()

                                    except Exception as e:
                                        st.error(
                                            "Erro ao atualizar o "
                                            f"compromisso: {e}"
                                        )

                            if cancelar_edicao:
                                st.session_state[
                                    "agenda_editando_id"
                                ] = None
                                st.rerun()

                    # Confirmação explícita antes da exclusão definitiva.
                    if st.session_state["agenda_excluir_id"] == id_item:
                        with st.container(border=True):
                            st.warning(
                                f"Excluir o compromisso “{desc_pura}”?"
                            )

                            escopo_exclusao = "Somente este vencimento"

                            if serie_id_item:
                                escopo_exclusao = st.radio(
                                    "O que deseja excluir?",
                                    [
                                        "Somente este vencimento",
                                        "Este e os próximos vencimentos",
                                        "Toda a série"
                                    ],
                                    key=f"escopo_delete_agenda_{id_item}"
                                )

                            col_confirma, col_cancela = st.columns(2)

                            if col_confirma.button(
                                "Confirmar exclusão",
                                key=f"confirm_delete_agenda_{id_item}",
                                type="primary",
                                use_container_width=True
                            ):
                                try:
                                    consulta_exclusao = supabase.table(
                                        "movimentacoes"
                                    ).delete().eq(
                                        "user_id",
                                        USER_ID
                                    )

                                    if (
                                        serie_id_item
                                        and escopo_exclusao == "Toda a série"
                                    ):
                                        consulta_exclusao = (
                                            consulta_exclusao.ilike(
                                                "satisfacao",
                                                (
                                                    f"%SERIE:{serie_id_item}%"
                                                    if "SERIE:" in texto_metadados
                                                    else f"%S:{serie_id_item}%"
                                                )
                                            )
                                        )

                                    elif (
                                        serie_id_item
                                        and escopo_exclusao
                                        == "Este e os próximos vencimentos"
                                    ):
                                        consulta_exclusao = (
                                            consulta_exclusao.ilike(
                                                "satisfacao",
                                                (
                                                    f"%SERIE:{serie_id_item}%"
                                                    if "SERIE:" in texto_metadados
                                                    else f"%S:{serie_id_item}%"
                                                )
                                            ).gte(
                                                "data",
                                                str(data_item)
                                            )
                                        )

                                    else:
                                        consulta_exclusao = (
                                            consulta_exclusao.eq(
                                                "id",
                                                id_item
                                            )
                                        )

                                    consulta_exclusao.execute()

                                    st.session_state[
                                        "agenda_excluir_id"
                                    ] = None
                                    st.success(
                                        "🗑️ Compromisso(s) excluído(s)."
                                    )
                                    st.rerun()

                                except Exception as e:
                                    st.error(
                                        "Erro ao excluir o compromisso: "
                                        f"{e}"
                                    )

                            if col_cancela.button(
                                "Não, cancelar",
                                key=f"cancel_delete_agenda_{id_item}",
                                use_container_width=True
                            ):
                                st.session_state["agenda_excluir_id"] = None
                                st.rerun()

                except Exception as erro_compromisso:
                    identificador_erro = texto_seguro_registro(
                        row.get("id"),
                        "desconhecido"
                    )

                    st.error(
                        "Um compromisso não pôde ser exibido, mas os "
                        "demais continuam disponíveis."
                    )
                    st.code(
                        f"Registro {identificador_erro} - "
                        f"{type(erro_compromisso).__name__}: "
                        f"{erro_compromisso}",
                        language="text"
                    )
                    st.markdown("---")
                st.markdown("---")
        else:
            st.info("Nenhum compromisso agendado.")
    else:
        st.info("Nenhum compromisso agendado.")


# ==================== ABA 4 (GESTÃO DE DÍVIDAS) ====================
with aba_dividas:
    st.title("📋 Controle Estrutural de Passivos e Dívidas")
    
    divida_bruta_total = sum([d["valor_original"] for d in lista_dividas_cadastradas])
    total_amortizado_historico = sum(amortizacoes_totais_historicas.values())
    divida_restante_real = max(divida_bruta_total - total_amortizado_historico, 0.0)
    
    c_div1, c_div2, c_div3 = st.columns(3)
    c_div1.metric(label="🚨 Saldo Devedor Restante", value=f"R$ {divida_restante_real:,.2f}")
    c_div2.metric(label="📉 Comprometimento de Renda", value=f"{indice_comprometimento:.1f}%")
    c_div3.metric(label="✅ Total Amortizado", value=f"R$ {total_amortizado_historico:,.2f}")
    
    if indice_comprometimento > 30.0:
        st.error(f"⚠️ Atenção Crítica: Suas parcelas de passivos consomem {indice_comprometimento:.1f}% da sua Renda.")
    elif indice_comprometimento > 0:
        st.warning(f"⚡ Atenção: {indice_comprometimento:.1f}% da sua renda está comprometida com dívidas.")

    st.markdown("---")
    st.subheader("🚀 Cadastrar Nova Dívida Estrutural")
    with st.form("form_cadastro_divida_passiva", clear_on_submit=True):
        col_d1, col_d2, col_d3 = st.columns(3)
        nome_credor = col_d1.text_input("Nome da Dívida / Credor:")
        saldo_devedor_inicial = col_d2.number_input("Valor Total Atual (R$):", min_value=0.0, step=100.0)
        valor_parcela_mensal = col_d3.number_input("Valor da Parcela Mensal (R$):", min_value=0.0, step=10.0)
        
        if st.form_submit_button("Registrar Passivo no Sistema") and nome_credor and saldo_devedor_inicial > 0:
            try:
                supabase.table("movimentacoes").insert({
                    "data": str(hoje), "valor": float(saldo_devedor_inicial), "tipo": "📱 Saída Dinheiro / Pix (Débito)",
                    "descricao": "[DIVIDA_ATIVA] Registro de Passivo Estrutural", "grupo_orcamentario": "📋 QUITAÇÃO DE DÍVIDAS (ATIVO)",
                    "subcategoria": nome_credor, "satisfacao": f"{valor_parcela_mensal} - Parcela Cadastrada", "user_id": USER_ID
                }).execute()
                st.success("✅ Dívida estrutural integrada!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao registrar passivo: {e}")

    if lista_dividas_cadastradas:
        st.markdown("---")
        st.subheader("📊 Evolução e Quitação dos Passivos")
        
        for divida in lista_dividas_cadastradas:
            nome = divida["nome"]
            original = divida["valor_original"]
            pago = amortizacoes_totais_historicas.get(nome, 0.0)
            restante = max(original - pago, 0.0)
            
            st.write(f"💳 **{nome}** (Parcela Mensal: R$ {divida['parcela']:,.2f})")
            col_l1, col_l2, col_l3 = st.columns(3)
            col_l1.caption(f"Dívida Original: R$ {original:,.2f}")
            col_l2.caption(f"Restante Atual: R$ {restante:,.2f}")
            col_l3.caption(f"Amortizado: R$ {pago:,.2f}")
            
            progresso = min(pago / original, 1.0) if original > 0 else 0.0
            st.progress(progresso)
            
            if st.button(f"🗑️ Remover Registro da Dívida: {nome}", key=f"del_div_{divida['id']}"):
                try:
                    supabase.table("movimentacoes").delete().eq("id", divida["id"]).eq("user_id", USER_ID).execute()
                    st.success("Registro removido do painel!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao deletar: {e}")
            st.markdown("<br>", unsafe_allow_html=True)
