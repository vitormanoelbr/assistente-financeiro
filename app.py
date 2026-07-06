import streamlit as st
import datetime
import pandas as pd
import plotly.express as px
from supabase import create_client, Client

st.set_page_config(page_title="Meu Planner Financeiro", layout="centered")

# --- 🔐 CONEXÃO SECRETA ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    st.error("❌ Erro de Segurança: As credenciais (Secrets) não foram configuradas no painel do Streamlit.")
    st.stop()

@st.cache_resource
def conectar_banco():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase: Client = conectar_banco()
except Exception as e:
    st.error(f"Falha na conexão estrutural: {e}")

# --- FUNÇÃO AUXILIAR DE LOGOUT COMPLETO ---
def deslogar_usuario():
    try:
        supabase.auth.sign_out()
    except:
        pass
    st.session_state["usuario_logado"] = None
    st.session_state["user_token"] = None
    st.query_params.clear()
    st.rerun()

# --- 👤 GERENCIAMENTO NATIVO DE SESSÃO POR URL ---
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
    st.caption("Crie sua conta ou faça login para proteger e gerenciar suas finanças com segurança.")
    
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

# --- PROCESSAMENTO LÓGICO ---
renda_base_usuario = 2500.00  

global_entradas = 0.0
global_saidas_caixa = 0.0

faturamento_extra_mes = 0.0
gastos_reais_mes = 0.0       
saidas_imediatas_caixa = 0.0 
fatura_acumulada_mes = 0.0   

gastos_essencial = 0.0
gastos_estilo = 0.0
gastos_aporte_mes = 0.0
gastos_negocio = 0.0

DIVIDA_TOTAL_INICIAL = 0.0
total_pago_divida = 0.0

agenda_a_pagar_mes = 0.0
agenda_a_receber_mes = 0.0

dicionario_metas_alvo = {}
dicionario_aportes_acumulados = {}

df_todos_dados = pd.DataFrame()
df_filtrado = pd.DataFrame()

if supabase:
    try:
        supabase.postgrest.auth(st.session_state["user_token"])
        resposta_completa = supabase.table("movimentacoes").select("id, data, descricao, grupo_orcamentario, subcategoria, valor, satisfacao, tipo, user_id").execute()
        
        if resposta_completa and hasattr(resposta_completa, 'data') and resposta_completa.data:
            res_data = resposta_completa.data
            df_todos_dados = pd.DataFrame(res_data)
            df_todos_dados["valor"] = df_todos_dados["valor"].astype(float)
            df_todos_dados["data_dt"] = pd.to_datetime(df_todos_dados["data"]).dt.date
            
            for item in res_data:
                grupo = item.get("grupo_orcamentario") or ""
                subcat = item.get("subcategoria") or ""
                tipo_mov = item.get("tipo") or ""
                val_mov = float(item["valor"] or 0.0)
                desc = item.get("descricao") or ""
                dt_item = pd.to_datetime(item["data"]).date()
                
                if "[CONFIG_PERFIL]" in desc and "Renda Base Nativa" in subcat:
                    renda_base_usuario = val_mov
                    continue
                
                if "📅 AGENDA" in group := grupo:
                    if dt_item.year == ano_selected and dt_item.month == mes_selected_num:
                        if "📅 AGENDA: CONTAS A PAGAR" in grupo:
                            agenda_a_pagar_mes += val_mov
                        elif "📅 AGENDA: CONTAS A RECEBER" in grupo:
                            agenda_a_receber_mes += val_mov
                    continue
                
                if "Faturamento" in tipo_mov or "Receita" in tipo_mov:
                    global_entradas += val_mov
                elif "📱" in tipo_mov or "Pix" in tipo_mov or "Débito" in tipo_mov or "[AJUSTE]" in desc:
                    global_saidas_caixa += val_mov

                if "🚀 20% Aporte" in grupo and "Entrada" in tipo_mov:
                    dicionario_metas_alvo[subcat] = val_mov
                elif "📋 Quitação de Dívidas" in grupo:
                    if "Entrada" in tipo_mov:
                        DIVIDA_TOTAL_INICIAL += val_mov
                    else:
                        total_pago_divida += val_mov
                elif "🚀 20% Aporte" in grupo and "Saída" in tipo_mov:
                    dicionario_aportes_acumulados[subcat] = dicionario_aportes_acumulados.get(subcat, 0.0) + val_mov

            df_filtrado = df_todos_dados.copy()
            if not df_filtrado.empty:
                df_filtrado = df_filtrado[~df_filtrado["grupo_orcamentario"].str.contains("CONFIGURAC", na=False)]
                df_filtrado = df_filtrado[~df_filtrado["descricao"].str.contains("CONFIG_PERFIL", na=False)]
                
                df_filtrado["ano"] = pd.to_datetime(df_filtrado["data_dt"]).dt.year
                df_filtrado["mes"] = pd.to_datetime(df_filtrado["data_dt"]).dt.month
                
                def calcular_mes_fatura(linha):
                    dt = linha["data_dt"]
                    tipo_pgto = str(linha.get("tipo") or "")
                    if "💳" in tipo_pgto or "Cartão" in tipo_pgto:
                        if dt.day > 20:
                            proximo_mes = dt.month + 1 if dt.month < 12 else 1
                            proximo_ano = dt.year if dt.month < 12 else dt.year + 1
                            return proximo_ano, proximo_mes
                    return dt.year, dt.month

                df_filtrado[["ano_fatura", "mes_fatura"]] = df_filtrado.apply(
                    lambda r: pd.Series(calcular_mes_fatura(r)), axis=1
                )
                
                df_filtrado = df_filtrado[
                    ((df_filtrado["tipo"].str.contains("💳|Cartão", na=False)) & (df_filtrado["ano_fatura"] == ano_selected) & (df_filtrado["mes_fatura"] == mes_selected_num)) |
                    ((~df_filtrado["tipo"].str.contains("💳|Cartão", na=False)) & (df_filtrado["ano"] == ano_selected) & (df_filtrado["mes"] == mes_selected_num))
                ]

            df_acumulado_mes_cheio = df_filtrado.copy()

            if janela_tempo == "Últimos 7 Dias":
                df_filtrado = df_filtrado[(df_filtrado["data_dt"] >= (hoje - datetime.timedelta(days=7))) & (df_filtrado["data_dt"] <= hoje)]
            elif janela_tempo == "Somente Hoje":
                df_filtrado = df_filtrado[df_filtrado["data_dt"] == hoje]
            
            if tag_busca:
                df_filtrado["descricao_lower"] = df_filtrado["descricao"].fillna("").astype(str).str.lower()
                df_filtrado = df_filtrado[df_filtrado["descricao_lower"].str.contains(tag_busca, na=False)]
                
            for _, row in df_acumulado_mes_cheio.iterrows():
                val = float(row["valor"])
                grupo_item = str(row["grupo_orcamentario"] or "")
                tipo_mov = str(row.get("tipo") or "")
                
                if "Faturamento" in tipo_mov or "Receita" in tipo_mov:
                    faturamento_extra_mes += val
                else:
                    gastos_reais_mes += val
                    if "💳" in tipo_mov or "Cartão" in tipo_mov:
                        fatura_acumulada_mes += val
                    else:
                        saidas_imediatas_caixa += val
                    
                    if "50% Essencial" in grupo_item:
                        gastos_essencial += val
                    elif "30% Estilo de Vida" in grupo_item:
                        gastos_estilo += val
                    elif "20% Aporte" in grupo_item:
                        gastos_aporte_mes += val
                    elif "💼 Custos de Negócio" in grupo_item:
                        gastos_negocio += val
                    
    except Exception as e:
        if "JWT expired" in str(e) or "PGRST303" in str(e):
            st.warning("🔒 Sua sessão expirou por segurança. Fazendo login de renovação...")
            deslogar_usuario()
        else:
            st.error(f"Erro na validação de dados: {e}")

# --- CONTROLE DE SALDO ---
saldo_real_exibido = global_entradas - global_saidas_caixa
saldo_devedor_restante = max(DIVIDA_TOTAL_INICIAL - total_pago_divida, 0.0)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Sincronização de Saldos")

novo_saldo_banco = st.sidebar.number_input("Saldo Real do seu Banco Hoje (R$):", min_value=-99999.0, value=saldo_real_exibido, step=10.0, format="%.2f")

if st.sidebar.button("🔄 Conciliar com o Banco"):
    discrepancia = novo_saldo_banco - saldo_real_exibido
    if discrepancia != 0:
        try:
            if discrepancia > 0:
                tipo_ajuste = "Faturamento ou Receita (Entrada)"
                grupo_ajuste = "⚙️ CONFIGURAÇÃO"
            else:
                tipo_ajuste = "📱 Saída Dinheiro / Pix (Débito)"
                grupo_ajuste = "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)"
            
            supabase.table("movimentacoes").insert({
                "data": str(hoje), "valor": float(abs(discrepancia)), "tipo": tipo_ajuste,
                "descricao": "[AJUSTE] Alinhamento de Saldo Real", "grupo_orcamentario": group_ajuste := grupo_ajuste,
                "subcategoria": "Ajuste de Saldo", "satisfacao": "3 - Indispensável", "user_id": USER_ID
            }).execute()
            st.sidebar.success("🎉 Ledger equilibrado com sucesso!")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erro ao ajustar saldo: {e}")

nova_renda_input = st.sidebar.number_input("Sua Renda Mensal Base (R$):", min_value=0.0, value=renda_base_usuario, step=50.0, format="%.2f")
if st.sidebar.button("💾 Salvar Renda Base"):
    try:
        if not df_todos_dados.empty:
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
LIMITE_ESTILO_DE_VIDA = renda_base_usuario * 0.30  
META_APORTE_MENSAL = renda_base_usuario * 0.20           

lista_porquinhos_existentes = list(dicionario_metas_alvo.keys())
if not lista_porquinhos_existentes:
    lista_porquinhos_existentes = ["🧱 Reserva de Emergência", "🏡 Comprar Casa"]

MAPA_CATEGORIAS = {
    "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)": ["Alimentação Básica & Mercado", "Contas Fixas (Luz, Água, Internet)", "Habitação (Aluguel / Financiamento)", "Saúde & Medicamentos", "Transporte & Combustível"],
    "🟡 30% Estilo de Vida (Lazer e Custos Voláteis)": ["Lazer, Bares & Restaurantes", "Delivery / iFood / Conforto", "Vestuário, Compras & Presentes", "Estética, Cuidados & Academia", "Viagens & Hobbies", "Assinaturas (Netflix, Spotify)"],
    "🚀 20% Aporte para a Liberdade (Investimentos e Futuro)": lista_porquinhos_existentes + ["➕ [Criar Nova Meta / Porquinho]"],
    "📋 Quitação de Dívidas (Amortizações e Acordos)": ["Empréstimos Bancários", "Cartão de Crédito Atrasado", "Financiamentos de Bens", "Dívidas Pessoais / Terceiros"],
    "💼 Custos de Negócio (Projetos e Clínica)": ["Ferramentas SaaS & Softwares", "Marketing & Anúncios", "Infraestrutura & Custos Operacionais"]
}

aba_painel, aba_porquinhos, aba_agenda = st.tabs(["📊 Painel & Lançamentos", "🐷 Meus Porquinhos & Rumo ao Milhão", "📅 Agenda de Compromissos"])

# ==================== ABA 1 ====================
with aba_painel:
    st.title("📲 Meu Planner Financeiro")
    
    st.markdown(f"### 👑 Movimentação de Caixa Real ({lista_meses[mes_selected_num]})")
    c_caixa1, c_caixa2, c_caixa3 = st.columns(3)
    c_caixa1.metric(label="💰 Saldo Atual em Conta", value=f"R$ {saldo_real_exibido:,.2f}", help="Histórico real consolidado de entradas e saídas de caixa da conta corrente.")
    c_caixa2.metric(label="💳 Cartão (A Vencer)", value=f"R$ {fatura_acumulada_mes:,.2f}", help="Total acumulado em compras no crédito com vencimento neste mês.")
    c_caixa3.metric(label="📉 Total Consumido no Mês", value=f"R$ {gastos_reais_mes:,.2f}", help="Soma de tudo o que foi conhecido no período (Débito + Crédito)")

    st.markdown("---")
    st.subheader("📊 Painel de Limites Orçamentários (Soma total de Pix + Crédito)")
    
    st.write(f"🔴 **Gasto Essencial:** R$ {gastos_essencial:,.2f} de R$ {LIMITE_ESSENCIAL:,.2f}")
    st.progress(min(gastos_essencial / LIMITE_ESSENCIAL, 1.0) if LIMITE_ESSENCIAL > 0 else 0.0)
    st.write(f"🟡 **Estilo de Vida:** R$ {gastos_estilo:,.2f} de R$ {LIMITE_ESTILO_DE_VIDA:,.2f}")
    st.progress(min(gastos_estilo / LIMITE_ESTILO_DE_VIDA, 1.0) if LIMITE_ESTILO_DE_VIDA > 0 else 0.0)
    st.write(f"🚀 **Aporte Mensal Realizado:** R$ {gastos_aporte_mes:,.2f} de R$ {META_APORTE_MENSAL:,.2f}")
    st.progress(min(gastos_aporte_mes / META_APORTE_MENSAL, 1.0) if META_APORTE_MENSAL > 0 else 0.0)

    try:
        df_saidas = df_filtrado[df_filtrado["tipo"].str.contains("Saída|📱|💳", na=False)].copy()
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

    with st.form("formulario_envio_blindado", clear_on_submit=True):
        valor = st.number_input("Qual o valor da operação? (R$)", min_value=0.0, step=0.01, format="%.2f")
        if criando_novo_porquinho:
            tipo = st.radio("Fluxo Financeiro:", ["Faturamento ou Receita (Entrada)"])
        else:
            tipo = st.radio("Fluxo Financeiro / Meio de Pagamento:", [
                "📱 Saída Dinheiro / Pix (Débito)", 
                "💳 Saída Cartão de Crédito", 
                "Faturamento ou Receita (Entrada)"
            ], horizontal=True)
            
        data_movimento = st.date_input("Data do evento:", datetime.date.today())
        descricao = st.text_input("Descrição ou Estabelecimento:")
        satisfacao = st.select_slider("🧠 Nível de necessidade?", options=["1 - Impulsivo / Evitável", "2 - Útil / Desejável", "3 - Indispensável"], value="2 - Útil / Desejável")
        botao_enviar = st.form_submit_button("Confirmar Lançamento")
        
    if botao_enviar and supabase:
        final_subcat = nome_novo_fundo if criando_novo_porquinho else categoria
        final_valor = val_alvo_novo_fundo if criando_novo_porquinho else valor
        final_desc = f"Meta Criada: {nome_novo_fundo}" if criando_novo_porquinho else descricao
        
        if final_valor > 0 and final_desc:
            try:
                supabase.table("movimentacoes").insert({
                    "data": str(data_movimento), "valor": float(final_valor), "tipo": tipo,
                    "descricao": final_desc, "grupo_orcamentario": grupo_orcamentario,
                    "subcategoria": final_subcat, "satisfacao": satisfacao, "user_id": USER_ID
                }).execute()
                st.success("✅ Sincronizado com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

    # ==================== MECANISMO DE RATEIO DE FATURA ====================
    st.markdown("---")
    st.subheader("💳 Rateio Rápido de Fatura Fechada (Ajustar Passado)")
    st.caption("Use esta ferramenta para desmembrar o valor total de uma fatura antiga de cartão de crédito diretamente nas categorias reais.")

    with st.form("formulario_rateio_fatura", clear_on_submit=True):
        col_f1, col_f2 = st.columns(2)
        val_total_fatura = col_f1.number_input("Valor Total Pago na Fatura (R$):", min_value=0.0, step=0.01, format="%.2f")
        data_fatura = col_f2.date_input("Data do Pagamento da Fatura:", datetime.date.today())
        descricao_fatura = st.text_input("Identificação da Fatura:", placeholder="Ex: Fatura Nubank - Junho/2026")
        
        st.markdown("**Distribuição Estratégica dos Gastos Dentro da Fatura:**")
        col_r1, col_r2 = st.columns(2)
        rateio_essencial = col_r1.number_input("🔴 Quanto foi Essencial (50%)? (R$)", min_value=0.0, step=0.01, format="%.2f")
        rateio_estilo = col_r2.number_input("🟡 Quanto foi Estilo de Vida (30%)? (R$)", min_value=0.0, step=0.01, format="%.2f")
        
        col_r3, col_r4 = st.columns(2)
        rateio_negocio = col_r3.number_input("💼 Quanto foi Custos de Negócio? (R$)", min_value=0.0, step=0.01, format="%.2f")
        rateio_dividas = col_r4.number_input("📋 Quanto foi Quitação de Dívidas? (R$)", min_value=0.0, step=0.01, format="%.2f")
        botao_enviar_rateio = st.form_submit_button("💥 Desmembrar e Sincronizar Fatura")

    if botao_enviar_rateio and supabase:
        soma_partes = rateio_essencial + rateio_estilo + rateio_negocio + rateio_dividas
        
        if not descricao_fatura:
            st.error("❌ Por favor, insira uma identificação para esta fatura.")
        elif val_total_fatura <= 0:
            st.error("❌ O valor total da fatura precisa ser maior que zero.")
        elif round(soma_partes, 2) != round(val_total_fatura, 2):
            st.error(f"❌ A soma das categorias (R$ {soma_partes:,.2f}) não bate com o valor total informado da fatura (R$ {val_total_fatura:,.2f}). Diferença: R$ {abs(val_total_fatura - soma_partes):,.2f}")
        else:
            try:
                inserts_pendentes = []
                mapeamento_rateio = [
                    {"valor": rateio_essencial, "grupo": "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)", "subcat": "Contas Fixas (Luz, Água, Internet)"},
                    {"valor": rateio_estilo, "grupo": "🟡 30% Estilo de Vida (Lazer e Custos Voláteis)", "subcat": "Lazer, Bares & Restaurantes"},
                    {"valor": rateio_negocio, "grupo": "💼 Custos de Negócio (Projetos e Clínica)", "subcat": "Infraestrutura & Custos Operacionais"},
                    {"valor": rateio_dividas, "grupo": "📋 Quitação de Dívidas (Amortizações e Acordos)", "subcat": "Cartão de Crédito Atrasado"}
                ]
                
                for item in mapeamento_rateio:
                    if item["valor"] > 0:
                        inserts_pendentes.append({
                            "data": str(data_fatura),
                            "valor": float(item["valor"]),
                            "tipo": "💳 Saída Cartão de Crédito",
                            "descricao": f"{descricao_fatura} [Rateio]",
                            "grupo_orcamentario": item["grupo"],
                            "subcategoria": item["subcat"],
                            "satisfacao": "3 - Indispensável",
                            "user_id": USER_ID
                        })
                
                if inserts_pendentes:
                    supabase.table("movimentacoes").insert(inserts_pendentes).execute()
                    st.success(f"🎉 Perfeito! A fatura foi fragmentada em {len(inserts_pendentes)} lançamentos estratégicos no Supabase.")
                    st.rerun()
            except Exception as e:
                st.error(f"Falha ao processar rateio no banco de dados: {e}")

    # Tabela Gerenciadora
    st.markdown("---")
    st.subheader("📋 Gerenciar Lançamentos do Período")
    if supabase and not df_filtrado.empty:
        df_editor = df_filtrado[["id", "data", "descricao", "grupo_orcamentario", "subcategoria", "valor", "tipo"]].copy()
        df_editor.columns = ["ID", "Data", "Descrição", "Grupo", "Subcategoria", "Valor (R$)", "Meio / Tipo"]
        dados_editados = st.data_editor(use_container_width=True, hide_index=True, disabled=["ID"], num_rows="dynamic", data=df_editor)
        
        if st.button("💾 Salvar Alterações da Tabela"):
            try:
                linhas_atuais_ids = set(dados_editados["ID"].tolist())
                linhas_originais_ids = set(df_editor["ID"].tolist())
                for id_del in (linhas_originais_ids - linhas_atuais_ids):
                    supabase.table("movimentacoes").delete().eq("id", int(id_del)).execute()
                for _, row in dados_editados.iterrows():
                    row_id = int(row["ID"])
                    supabase.table("movimentacoes").update({"descricao": row["Descrição"], "valor": float(row["Valor (R$)"]), "tipo": row["Meio / Tipo"]}).eq("id", row_id).eq("user_id", USER_ID).execute()
                st.success("🔄 Alterações sincronizadas!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

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
            
    st.title("🚀 Estrada Estratégica Rumo ao 1 Milhão")
    st.markdown(f"**💰 Seu Patrimônio Consolidado Atual:** R$ {total_patrimonio_guardado:,.2f}")
    st.markdown(f"**📈 Seu Aporte Mensal Planejado (20%):** R$ {META_APORTE_MENSAL:,.2f} /mês")
    
    TAXA_MENSAL_LIQUIDA = 0.008 
    degraus_objetivos = [
        {"alvo": 10000.0, "name": "🧱 R$ 10k — Reserva de Segurança Base"},
        {"alvo": 50000.0, "name": "🎯 R$ 50k — O Primeiro Impulso Real"},
        {"alvo": 100000.0, "name": "💎 R$ 100k — O Lote de Elite Psicológico"},
        {"alvo": 250000.0, "name": "🏰 R$ 250k — Um Quarto do Caminho"},
        {"alvo": 500000.0, "name": "⚔️ R$ 500k — Meio Milhão (Reta Final)"},
        {"alvo": 1000000.0, "name": "👑 R$ 1 Milhão — Liberdade Financeira Fundada"}
    ]
    
    for degrau in degraus_objetivos:
        alvo_valor = degrau["alvo"]
        if total_patrimonio_guardado >= alvo_valor:
            st.success(f"✅ **{degrau['name']}** — **CONQUISTADO!**")
        else:
            saldo_simulado = total_patrimonio_guardado
            meses = 0
            while saldo_simulado < alvo_valor and meses < 600:
                saldo_simulado = (saldo_simulado * (1 + TAXA_MENSAL_LIQUIDA)) + META_APORTE_MENSAL
                meses += 1
            data_conquista = hoje + datetime.timedelta(days=int(meses * 30.41))
            st.markdown(f"🔒 **{degrau['name']}**")
            st.write(f"Faltam **{meses} meses** — Previsão: **{data_conquista.strftime('%B / %Y').capitalize()}**")
            st.progress(min((total_patrimonio_guardado / alvo_valor), 1.0))
        st.markdown("---")

# ==================== ABA 3 (AGENDA) ====================
with aba_agenda:
    st.title("📅 Agenda de Compromissos Financeiros")
    
    st.markdown("### 📊 Fluxo de Caixa Projetado da Agenda")
    col_ag1, col_ag2, col_ag3 = st.columns(3)
    col_ag1.metric(label="📉 Contas Agendadas a Pagar", value=f"R$ {agenda_a_pagar_mes:,.2f}")
    col_ag2.metric(label="🟢 Recebimentos Agendados", value=f"R$ {agenda_a_receber_mes:,.2f}")
    
    balanco_agenda = agenda_a_receber_mes - agenda_a_pagar_mes
    if balanco_agenda >= 0:
        col_ag3.metric(label="⚖️ Saldo Isolado da Agenda", value=f"R$ {balanco_agenda:,.2f}", delta="Superávit de Compromissos")
    else:
        col_ag3.metric(label="⚖️ Saldo Isolado da Agenda", value=f"R$ {balanco_agenda:,.2f}", delta="Déficit de Compromissos", delta_color="inverse")
    
    st.markdown("---")
    col_agenda1, col_agenda2 = st.columns(2)
    with col_agenda1:
        st.subheader("📌 Agendar Conta Fixa (A Pagar)")
        with st.form("form_agenda_pagar", clear_on_submit=True):
            name_boleto = st.text_input("Nome da Conta / Boleto:")
            valor_boleto = st.number_input("Valor Estimado (R$):", min_value=0.0, step=0.01)
            vencimento_boleto = st.date_input("Data de Vencimento:", datetime.date.today())
            if st.form_submit_button("Agendar Conta Fixa") and name_boleto and valor_boleto > 0:
                supabase.table("movimentacoes").insert({"data": str(vencimento_boleto), "valor": float(valor_boleto), "tipo": "📱 Saída Dinheiro / Pix (Débito)", "descricao": f"[AGENDA COMPROMISSO] {name_boleto}", "grupo_orcamentario": "📅 AGENDA: CONTAS A PAGAR", "subcategoria": "Conta Fixa", "satisfacao": "3 - Indispensável", "user_id": USER_ID}).execute()
                st.rerun()
                
    with col_agenda2:
        st.subheader("💰 Agendar Valor (A Receber)")
        with st.form("form_agenda_receber", clear_on_submit=True):
            nome_recebivel = st.text_input("O que tem a receber?:")
            valor_recebivel = st.number_input("Valor (R$):", min_value=0.0, step=0.01)
            data_recebivel = st.date_input("Data de Expectativa:", datetime.date.today())
            if st.form_submit_button("Agendar Recebimento") and nome_recebivel and valor_recebivel > 0:
                supabase.table("movimentacoes").insert({"data": str(data_recebivel), "valor": float(valor_recebivel), "tipo": "Faturamento ou Receita (Entrada)", "descricao": f"[AGENDA COMPROMISSO] {nome_recebivel}", "grupo_orcamentario": "📅 AGENDA: CONTAS A RECEBER", "subcategoria": "Valores a Receber", "satisfacao": "3 - Indispensável", "user_id": USER_ID}).execute()
                st.rerun()

    st.markdown("---")
    st.subheader("📋 Seus Compromissos Mapeados")
    if supabase and not df_todos_dados.empty:
        df_agenda_pura = df_todos_dados[df_todos_dados["grupo_orcamentario"].str.contains("📅 AGENDA", na=False)].copy()
        if not df_agenda_pura.empty:
            df_agenda_pura = df_agenda_pura.sort_values(by="data")
            
            for idx, row in df_agenda_pura.iterrows():
                id_item = int(row["id"])
                desc_pura = str(row["descricao"]).replace("[AGENDA COMPROMISSO] ", "")
                valor_item = float(row["valor"])
                data_original = pd.to_datetime(row["data"]).date()
                
                col_c1, col_c2, col_c3 = st.columns([4, 2, 2])
                col_c1.write(f"📅 **{row['data']}** - {desc_pura} | **R$ {valor_item:,.2f}**")
                
                if "CONTAS A PAGAR" in str(row["grupo_orcamentario"]):
                    col_c2.caption("🔴 A Pagar")
                    
                    if col_c3.button("✅ Pagar", key=f"pay_{id_item}"):
                        supabase.table("movimentacoes").delete().eq("id", id_item).execute()
                        supabase.table("movimentacoes").insert({"data": str(hoje), "valor": valor_item, "tipo": "📱 Saída Dinheiro / Pix (Débito)", "descricao": f"{desc_pura} (Pago)", "grupo_orcamentario": "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)", "subcategoria": "Contas Fixas (Luz, Água, Internet)", "satisfacao": "3 - Indispensável", "user_id": USER_ID}).execute()
                        st.rerun()
                        
                    nova_data_futura = data_original + datetime.timedelta(days=30)
                    if col_c3.button("🔄 Repetir", key=f"rep_{id_item}", help="Clona esta mesma despesa para o mês seguinte (+30 dias)"):
                        try:
                            supabase.table("movimentacoes").insert({
                                "data": str(nova_data_futura),
                                "valor": valor_item,
                                "tipo": str(row["tipo"]),
                                "descricao": row["descricao"],
                                "grupo_orcamentario": str(row["grupo_orcamentario"]),
                                "subcategoria": str(row["subcategoria"]),
                                "satisfacao": str(row["satisfacao"]),
                                "user_id": USER_ID
                            }).execute()
                            st.success(f"🔄 Agendado para {nova_data_futura.strftime('%d/%m/%Y')}!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao clonar: {e}")
                else:
                    col_c2.caption("🟢 A Receber")
                    if col_c3.button("💰 Receber", key=f"rec_{id_item}"):
                        supabase.table("movimentacoes").delete().eq("id", id_item).execute()
                        supabase.table("movimentacoes").insert({"data": str(hoje), "valor": valor_item, "tipo": "Faturamento ou Receita (Entrada)", "descricao": f"{desc_pura} (Recebido)", "grupo_orcamentario": "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)", "subcategoria": "Renda Base Nativa", "satisfacao": "3 - Indispensável", "user_id": USER_ID}).execute()
                        st.rerun()
