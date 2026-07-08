import streamlit as st
import datetime
import pandas as pd
import plotly.express as px
from supabase import create_client, Client

st.set_page_config(page_title="Meu Planner Financeiro", layout="centered")

# --- 🔐 CONEXÃO COM BANCO ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    st.error("❌ Erro de Segurança: As credenciais não foram configuradas no painel do Streamlit.")
    st.stop()

@st.cache_resource
def conectar_banco():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase: Client = conectar_banco()
except Exception as e:
    st.error(f"Falha na conexão estrutural: {e}")
    st.stop()

def deslogar_usuario():
    try:
        supabase.auth.sign_out()
    except:
        pass
    st.session_state["usuario_logado"] = None
    st.session_state["user_token"] = None
    st.query_params.clear()
    st.rerun()

if "usuario_logado" not in st.session_state or st.session_state["usuario_logado"] is None:
    parametros_url = st.query_params
    if "uid" in parametros_url and "tok" in parametros_url:
        st.session_state["usuario_logado"] = parametros_url["uid"]
        st.session_state["user_token"] = parametros_url["tok"]
    else:
        st.session_state["usuario_logado"] = None
        st.session_state["user_token"] = None

# ==================== TELA DE AUTENTICAÇÃO ====================
if st.session_state["usuario_logado"] is None:
    st.title("📲 Bem-vindo ao Meu Planner Financeiro")
    st.caption("Acesse sua conta para gerenciar suas finanças com segurança.")
    
    aba_login, aba_cadastro = st.tabs(["🔐 Entrar na Conta", "🚀 Criar Nova Conta"])
    
    with aba_login:
        with st.form("form_login"):
            email_login = st.text_input("E-mail:", placeholder="seu@email.com")
            senha_login = st.text_input("Senha:", type="password", placeholder="******")
            botao_login = st.form_submit_button("Acessar Painel")
            
            if botao_login:
                if email_login and senha_login:
                    try:
                        resposta = supabase.auth.sign_in_with_password({"email": email_login, "password": senha_login})
                        st.session_state["usuario_logado"] = resposta.user.id
                        st.session_state["user_token"] = resposta.session.access_token
                        st.query_params["uid"] = resposta.user.id
                        st.query_params["tok"] = resposta.session.access_token
                        st.success("🎉 Acesso autorizado! Redirecionando...")
                        st.rerun()
                    except Exception:
                        st.error("❌ Erro ao entrar: E-mail ou senha incorretos.")
                else:
                    st.warning("Preencha todos os campos.")
                    
    with aba_cadastro:
        with st.form("form_cadastro"):
            email_cad = st.text_input("Escolha um E-mail:", placeholder="seu@email.com")
            senha_cad = st.text_input("Escolha uma Senha (mínimo 6 caracteres):", type="password", placeholder="******")
            botao_cad = st.form_submit_button("Cadastrar e Criar Plataforma")
            
            if botao_cad:
                if email_cad and len(senha_cad) >= 6:
                    try:
                        resposta = supabase.auth.sign_up({"email": email_cad, "password": senha_cad})
                        st.success("✅ Conta criada com sucesso! Mude para a aba de Login para acessar.")
                    except Exception as e:
                        st.error(f"Erro ao cadastrar: {e}")
                else:
                    st.warning("O e-mail precisa ser válido e a senha ter no mínimo 6 caracteres.")
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
amortizacoes_totais_historicas = {}

df_todos_dados = pd.DataFrame()
df_filtrado = pd.DataFrame()

if supabase:
    try:
        supabase.postgrest.auth(st.session_state["user_token"])
        resposta_completa = supabase.table("movimentacoes").select("id, data, descricao, grupo_orcamentario, subcategoria, valor, satisfacao, tipo, user_id").eq("user_id", USER_ID).execute()
        
        if resposta_completa and hasattr(resposta_completa, 'data') and resposta_completa.data:
            res_data = resposta_completa.data
            df_todos_dados = pd.DataFrame(res_data)
            df_todos_dados["valor"] = df_todos_dados["valor"].astype(float)
            df_todos_dados["data_dt"] = pd.to_datetime(df_todos_dados["data"]).dt.date
            
            # Processamento de Configurações Globais e Metadados
            for item in res_data:
                desc = str(item.get("descricao") or "")
                subcat = str(item.get("subcategoria") or "")
                grupo = str(item.get("grupo_orcamentario") or "")
                tipo_mov = str(item.get("tipo") or "")
                val_mov = float(item["valor"] or 0.0)
                dt_item = pd.to_datetime(item["data"]).date()
                
                if "[CONFIG_PERFIL]" in desc and "Renda Base Nativa" in subcat:
                    renda_base_usuario = val_mov
                    continue
                
                if "[DIVIDA_ATIVA]" in desc:
                    lista_dividas_cadastradas.append({
                        "id": item["id"],
                        "nome": subcat,
                        "valor_original": val_mov,
                        "parcela": float(item.get("satisfacao").split(" - ")[0] if " - " in str(item.get("satisfacao")) else 0)
                    })
                    continue
                
                if "AGENDA" in grupo.upper():
                    if dt_item.year == ano_selected and dt_item.month == mes_selected_num:
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
                    df_filtrado["ano"] = pd.to_datetime(df_filtrado["data_dt"]).dt.year
                    df_filtrado["mes"] = pd.to_datetime(df_filtrado["data_dt"]).dt.month
                    
                    # Filtro estrito por mês do evento (Evita distorções de competência forçada)
                    df_filtrado = df_filtrado[(df_filtrado["ano"] == ano_selected) & (df_filtrado["mes"] == mes_selected_num)]

            df_acumulado_mes_cheio = df_filtrado.copy()

            if janela_tempo == "Últimos 7 Dias" and not df_filtrado.empty:
                df_filtrado = df_filtrado[(df_filtrado["data_dt"] >= (hoje - datetime.timedelta(days=7))) & (df_filtrado["data_dt"] <= hoje)]
            elif janela_tempo == "Somente Hoje" and not df_filtrado.empty:
                df_filtrado = df_filtrado[df_filtrado["data_dt"] == hoje]
            
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
                        if "💳" in row.get("tipo") or "CARTÃO" in tipo_mov:
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
            st.warning("🔒 Sua sessão expirou por segurança. Fazendo login de renovação...")
            deslogar_usuario()
        else:
            st.error(f"Erro no processamento dos dados: {e}")

# --- ORIGENS DE VERDADE MATEMÁTICA ---
saldo_real_exibido = renda_base_usuario + faturamento_extra_mes - gastos_dinheiro_caixa
total_consumido_orcamento = gastos_dinheiro_caixa + fatura_acumulada_mes

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
        "👶 Pensão / Filho"
    ],
    "🟡 30% Estilo de Vida (Lazer e Custos Voláteis)": [
        "Lazer, Bares & Restaurantes", 
        "Delivery / iFood / Conforto", 
        "Vestuário, Compras & Presentes", 
        "Estética, Cuidados & Academia", 
        "Viagens & Hobbies", 
        "Assinaturas (Netflix, Spotify)"
    ],
    "🚀 20% Aporte para a Liberdade (Investimentos e Futuro)": lista_porquinhos_existentes + ["➕ [Criar Nova Meta / Porquinho]"],
    "📋 Quitação de Dívidas (Amortizações e Acordos)": lista_nomes_dividas,
    "💼 Custos de Negócio (Projetos e Clínica)": [
        "Ferramentas SaaS & Softwares", 
        "Marketing & Anúncios", 
        "Infraestrutura & Custos Operacionais"
    ]
}

aba_painel, aba_porquinhos, aba_agenda, aba_dividas = st.tabs([
    "📊 Painel & Lançamentos", 
    "🐷 Meus Porquinhos & Rumo ao Milhão", 
    "📅 Agenda de Compromissos", 
    "📋 Gestão de Dívidas & Passivos"
])

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
        val_alvo_novo_f
