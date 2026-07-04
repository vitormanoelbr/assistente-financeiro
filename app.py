import streamlit as st
import datetime
import pandas as pd
from supabase import create_client, Client

st.set_page_config(page_title="Meu Planner Financeiro", layout="centered")

# --- 🔐 CONEXÃO SECRETA ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    st.error("❌ Erro de Segurança: Credenciais não configuradas no Streamlit.")
    st.stop()

@st.cache_resource
def conectar_banco():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase: Client = conectar_banco()
except Exception as e:
    st.error(f"Falha na conexão estrutural: {e}")

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
    st.caption("Crie sua conta ou faça login para proteger e gerenciar suas finanças.")
    
    aba_login, aba_cadastro = st.tabs(["🔐 Entrar na Conta", "🚀 Criar Nova Conta"])
    
    with aba_login:
        with st.form("form_login"):
            email_login = st.text_input("E-mail:", placeholder="seu@email.com")
            senha_login = st.text_input("Senha:", type="password", placeholder="******")
            botao_login = st.form_submit_button("Acessar Painel")
            
            if botao_login and email_login and senha_login:
                try:
                    resposta = supabase.auth.sign_in_with_password({"email": email_login, "password": senha_login})
                    st.session_state["usuario_logado"] = resposta.user.id
                    st.session_state["user_token"] = resposta.session.access_token
                    st.query_params["uid"] = resposta.user.id
                    st.query_params["tok"] = resposta.session.access_token
                    st.success("🎉 Acesso autorizado!")
                    st.rerun()
                except Exception:
                    st.error("❌ E-mail ou senha incorretos.")
                    
    with aba_cadastro:
        with st.form("form_cadastro"):
            email_cad = st.text_input("Escolha um E-mail:", placeholder="seu@email.com")
            senha_cad = st.text_input("Escolha uma Senha:", type="password", placeholder="******")
            botao_cad = st.form_submit_button("Criar Conta")
            
            if botao_cad and email_cad and len(senha_cad) >= 6:
                try:
                    supabase.auth.sign_up({"email": email_cad, "password": senha_cad})
                    st.success("✅ Conta criada! Mude para a aba de Login.")
                except Exception as e:
                    st.error(f"Erro ao cadastrar: {e}")
    st.stop()

# ==================== SISTEMA PRINCIPAL ====================
USER_ID = st.session_state["usuario_logado"]

if st.sidebar.button("🚪 Sair da Conta"):
    try:
        supabase.auth.sign_out()
    except:
        pass
    st.session_state["usuario_logado"] = None
    st.session_state["user_token"] = None
    st.query_params.clear()
    st.rerun()

# --- ⚙️ SIDEBAR FILTROS ---
st.sidebar.header("⚙️ Configurações do Perfil")
RENDA_BASE = st.sidebar.number_input("Sua Renda Mensal Base (R$):", min_value=0.0, value=2500.00, step=100.0)

st.sidebar.markdown("---")
st.sidebar.header("📅 Filtros de Tempo")
hoje = datetime.date.today()
ano_selected = st.sidebar.selectbox("Ano de Análise:", [hoje.year, hoje.year - 1, hoje.year + 1], index=0)

lista_meses = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}
mes_selected_num = st.sidebar.selectbox("Mês de Análise:", list(lista_meses.keys()), format_func=lambda x: lista_meses[x], index=list(lista_meses.keys()).index(hoje.month))
janela_tempo = st.sidebar.radio("Intervalo do Painel:", ["Mês Completo", "Últimos 7 Dias", "Somente Hoje"])

# --- PROCESSAMENTO MATEMÁTICO ---
LIMITE_ESSENCIAL = RENDA_BASE * 0.50       
LIMITE_ESTILO_DE_VIDA = RENDA_BASE * 0.30  
META_APORTE_MENSAL = RENDA_BASE * 0.20           

faturamento_extra_mes = 0.0
gastos_reais_mes = 0.0
gastos_essencial = 0.0
gastos_estilo = 0.0
gastos_aporte_mes = 0.0

DIVIDA_TOTAL_INICIAL = 0.0
total_pago_divida = 0.0
agenda_a_pagar_mes = 0.0
agenda_a_receber_mes = 0.0

dicionario_metas_alvo = {}
dicionario_aportes_acumulados = {}
df_filtrado = pd.DataFrame()

if supabase:
    try:
        supabase.postgrest.auth(st.session_state["user_token"])
        resposta = supabase.table("movimentacoes").select("*").execute()
        
        if res_data := resposta.data:
            df_total = pd.DataFrame(res_data)
            df_total["valor"] = df_total["valor"].astype(float)
            df_total["data_dt"] = pd.to_datetime(df_total["data"]).dt.date
            
            # Varredura Global Vitalícia
            for item in res_data:
                grupo = str(item.get("grupo_orcamentario") or "")
                subcat = str(item.get("subcategoria") or "")
                tipo_mov = str(item.get("tipo") or "")
                val = float(item["valor"])
                
                if "📅 AGENDA" in grupo: continue
                if "🚀 20% Aporte" in grupo and "Entrada" in tipo_mov:
                    dicionario_metas_alvo[subcat] = val
                    continue
                if "📋 Quitação de Dívidas" in grupo:
                    if "Entrada" in tipo_mov: DIVIDA_TOTAL_INICIAL += val
                    else: total_pago_divida += val
                if "🚀 20% Aporte" in grupo and "Saída" in tipo_mov:
                    dicionario_aportes_acumulados[subcat] = dicionario_aportes_acumulados.get(subcat, 0.0) + val

            # Filtragem Temporal Pró
            df_filtrado = df_total.copy()
            df_filtrado["ano"] = pd.to_datetime(df_filtrado["data_dt"]).dt.year
            df_filtrado["mes"] = pd.to_datetime(df_filtrado["data_dt"]).dt.month
            df_filtrado = df_filtrado[(df_filtrado["ano"] == ano_selected) & (df_filtrado["mes"] == mes_selected_num)]
            
            if janela_tempo == "Últimos 7 Dias":
                df_filtrado = df_filtrado[df_filtrado["data_dt"] >= (hoje - datetime.timedelta(days=7))]
            elif janela_tempo == "Somente Hoje":
                df_filtrado = df_filtrado[df_filtrado["data_dt"] == hoje]
                
            for _, row in df_filtrado.iterrows():
                val = float(row["valor"])
                grupo = str(row["grupo_orcamentario"] or "")
                tipo_mov = str(row["tipo"] or "")
                
                if "📅 AGENDA: CONTAS A PAGAR" in grupo: agenda_a_pagar_mes += val; continue
                if "📅 AGENDA: CONTAS A RECEBER" in grupo: agenda_a_receber_mes += val; continue
                if "🚀 20% Aporte" in grupo and "Entrada" in tipo_mov: continue
                
                if "Faturamento" in tipo_mov:
                    faturamento_extra_mes += val
                else:
                    gastos_reais_mes += val
                    if "50% Essencial" in grupo: gastos_essencial += val
                    elif "30% Estilo de Vida" in grupo: gastos_estilo += val
                    elif "20% Aporte" in grupo: gastos_aporte_mes += val
    except Exception as e:
        st.error(f"Erro ao processar dados: {e}")

receitas_totais_calculadas = RENDA_BASE + faturamento_extra_mes
saldo_disponivel_caixa = receitas_totais_calculadas - gastos_reais_mes
saldo_devedor_restante = max(DIVIDA_TOTAL_INICIAL - total_pago_divida, 0.0)

lista_porquinhos_existentes = list(dicionario_metas_alvo.keys()) or ["🧱 Reserva de Emergência", "🏡 Comprar Casa"]

MAPA_CATEGORIAS = {
    "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)": ["Alimentação Básica & Mercado", "Contas Fixas (Luz, Água, Internet)", "Habitação (Aluguel / Financiamento)", "Saúde & Medicamentos", "Transporte & Combustível"],
    "🟡 30% Estilo de Vida (Lazer e Custos Voláteis)": ["Lazer, Bares & Restaurantes", "Delivery / iFood / Conforto", "Vestuário, Compras & Presentes", "Estética, Cuidados & Academia", "Assinaturas (Netflix, Spotify)"],
    "🚀 20% Aporte para a Liberdade (Investimentos e Futuro)": lista_porquinhos_existentes + ["➕ [Criar Nova Meta / Porquinho]"],
    "📋 Quitação de Dívidas (Amortizações e Acordos)": ["Empréstimos Bancários", "Cartão de Crédito Atrasado", "Financiamentos de Bens"],
    "💼 Custos de Negócio (Projetos e Clínica)": ["Ferramentas SaaS & Softwares", "Marketing & Anúncios", "Infraestrutura & Custos Operacionais"]
}

aba_painel, aba_porquinhos, aba_agenda = st.tabs(["📊 Painel & Lançamentos", "🐷 Meus Porquinhos", "📅 Agenda de Compromissos"])

# ==================== ABA 1 ====================
with aba_painel:
    st.title("📲 Meu Planner Financeiro")
    
    st.markdown("### 🏦 Saúde Disponível do Caixa")
    c_caixa1, c_caixa2, c_caixa3 = st.columns(3)
    c_caixa1.metric(label="Salários / Receitas Totais", value=f"R$ {receitas_totais_calculadas:,.2f}")
    c_caixa2.metric(label="Contas Já Pagas", value=f"R$ {gastos_reais_mes:,.2f}", delta="-Saídas", delta_color="inverse")
    c_caixa3.metric(label="💰 Dinheiro Sobrando", value=f"R$ {saldo_disponivel_caixa:,.2f}")

    if agenda_a_pagar_mes > 0 or agenda_a_receber_mes > 0:
        st.markdown("#### 🔮 Previsões Mapeadas para o Restante do Mês")
        c_prev1, c_prev2, c_prev3 = st.columns(3)
        c_prev1.metric(label="A Receber Agendado", value=f"R$ {agenda_a_receber_mes:,.2f}")
        c_prev2.metric(label="Boletos Fixos Pendentes", value=f"R$ {agenda_a_pagar_mes:,.2f}")
        c_prev3.metric(label="Balanço Previsto", value=f"R$ {agenda_a_receber_mes - agenda_a_pagar_mes:,.2f}")

    st.markdown("---")
    st.subheader("📊 Painel de Limites Orçamentários")
    st.write(f"🔴 **Gasto Essencial:** R$ {gastos_essencial:,.2f} de R$ {LIMITE_ESSENCIAL:,.2f}")
    st.progress(min(gastos_essencial / LIMITE_ESSENCIAL, 1.0) if LIMITE_ESSENCIAL > 0 else 0.0)
    st.write(f"🟡 **Estilo de Vida:** R$ {gastos_estilo:,.2f} de R$ {LIMITE_ESTILO_DE_VIDA:,.2f}")
    st.progress(min(gastos_estilo / LIMITE_ESTILO_DE_VIDA, 1.0) if LIMITE_ESTILO_DE_VIDA > 0 else 0.0)
    st.write(f"🚀 **Aporte Mensal Realizado:** R$ {gastos_aporte_mes:,.2f} de R$ {META_APORTE_MENSAL:,.2f}")
    st.progress(min(gastos_aporte_mes / META_APORTE_MENSAL, 1.0) if META_APORTE_MENSAL > 0 else 0.0)

    st.markdown("---")
    st.subheader("📥 Registrar Movimentação Realizada")
    grupo_orcamentario = st.selectbox("Destinação Estratégica:", list(MAPA_CATEGORIAS.keys()))
    categoria = st.selectbox("Subcategoria Correspondente:", MAPA_CATEGORIAS[grupo_orcamentario])

    criando_novo_porquinho = (categoria == "➕ [Criar Nova Meta / Porquinho]")
    nome_novo_fundo = ""
    val_alvo_novo_fundo = 0.0
    if criando_novo_porquinho:
        col_n1, col_n2 = st.columns(2)
        nome_novo_fundo = col_n1.text_input("Nome da Nova Meta:")
        val_alvo_novo_fundo = col_n2.number_input("Valor Alvo (R$):", min_value=0.0, value=1000.00)

    with st.form("formulario_envio_blindado", clear_on_submit=True):
        valor = st.number_input("Valor (R$):", min_value=0.0, format="%.2f")
        tipo = st.radio("Direção:", ["Gasto ou Investimento (Saída)", "Faturamento ou Receita (Entrada)"] if not criando_novo_porquinho else ["Faturamento ou Receita (Entrada)"], horizontal=True)
        data_movimento = st.date_input("Data:", datetime.date.today())
        descricao = st.text_input("Descrição:")
        satisfacao = st.select_slider("🧠 Necessidade real?", options=["1 - Impulsivo / Evitável", "2 - Útil / Desejável", "3 - Indispensável"], value="2 - Útil / Desejável")
        botao_enviar = st.form_submit_button("Confirmar Lançamento Real")
        
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
                st.success("✅ Sincronizado!")
                st.rerun()
            except Exception as e: st.error(f"Erro ao salvar: {e}")

    # --- 📋 GERENCIADOR DE LANÇAMENTOS SEGURO ---
    st.markdown("---")
    st.subheader("📋 Gerenciar Lançamentos do Período")
    if supabase and not df_filtrado.empty:
        df_editor_limpo = df_filtrado.copy()
        df_editor_limpo["grupo_orcamentario"] = df_editor_limpo["grupo_orcamentario"].fillna("").astype(str)
        df_editor_limpo = df_editor_limpo[~df_editor_limpo["grupo_orcamentario"].str.contains("📅 AGENDA", na=False)]
        
        if not df_editor_limpo.empty:
            df_editor = df_editor_limpo[["id", "data", "descricao", "grupo_orcamentario", "subcategoria", "valor", "tipo"]].copy()
            df_editor.columns = ["ID", "Data", "Descrição", "Grupo", "Subcategoria", "Valor (R$)", "Tipo"]
            dados_editados = st.data_editor(df_editor, use_container_width=True, hide_index=True, disabled=["ID"], num_rows="dynamic")
            
            if st.button("💾 Salvar Alterações da Tabela"):
                try:
                    linhas_atuais_ids = set(dados_editados["ID"].tolist())
                    linhas_originais_ids = set(df_editor["ID"].tolist())
                    for id_del in (linhas_originais_ids - linhas_atuais_ids):
                        supabase.table("movimentacoes").delete().eq("id", int(id_del)).execute()
                    for _, row in dados_editados.iterrows():
                        supabase.table("movimentacoes").update({"descricao": row["Descrição"], "valor": float(row["Valor (R$)"]), "tipo": row["Tipo"]}).eq("id", int(row["ID"])).execute()
                    st.success("🔄 Alterações salvas!")
                    st.rerun()
                except Exception as e: st.error(f"Erro ao salvar: {e}")
        else: st.info("💡 Nenhum lançamento real realizado neste mês.")
    else: st.info("💡 Banco de dados vazio.")

# ==================== ABA 2 ====================
with aba_porquinhos:
    st.title("🐷 Meus Porquinhos")
    if dicionario_metas_alvo:
        for nome_meta, valor_alvo in dicionario_metas_alvo.items():
            guardado = dicionario_aportes_acumulados.get(nome_meta, 0.0)
            falta_guardar = max(valor_alvo - guardado, 0.0)
            st.subheader(f"{nome_meta}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Valor Alvo Final", f"R$ {valor_alvo:,.2f}")
            c2.metric("Total Já Guardado", f"R$ {guardado:,.2f}")
            c3.metric("Quanto Falta Alocar", f"R$ {falta_guardar:,.2f}")
            st.progress(min(guardado / valor_alvo, 1.0) if valor_alvo > 0 else 0.0)
    else: st.info("💡 Nenhuma meta criada.")

# ==================== ABA 3 ====================
with aba_agenda:
    st.title("📅 Agenda de Compromissos")
    col_agenda1, col_agenda2 = st.columns(2)
    with col_agenda1:
        st.subheader("📌 Agendar Conta Fixa")
        with st.form("form_agenda_pagar", clear_on_submit=True):
            n_b = st.text_input("Boleto:")
            v_b = st.number_input("Valor (R$):", min_value=0.0)
            d_b = st.date_input("Vencimento:")
            if st.form_submit_button("Agendar") and n_b and v_b > 0:
                supabase.table("movimentacoes").insert({"data": str(d_b), "valor": float(v_b), "tipo": "Gasto ou Investimento (Saída)", "descricao": f"[AGENDA] {n_b}", "grupo_orcamentario": "📅 AGENDA: CONTAS A PAGAR", "subcategoria": "Conta Fixa", "satisfacao": "3 - Indispensável", "user_id": USER_ID}).execute()
                st.rerun()
    with col_agenda2:
        st.subheader("💰 Agendar Recebimento")
        with st.form("form_agenda_receber", clear_on_submit=True):
            n_r = st.text_input("A receber de:")
            v_r = st.number_input("Valor (R$):", min_value=0.0)
            d_r = st.date_input("Expectativa:")
            if st.form_submit_button("Agendar Rec.") and n_r and v_r > 0:
                supabase.table("movimentacoes").insert({"data": str(d_r), "valor": float(v_r), "tipo": "Faturamento ou Receita (Entrada)", "descricao": f"[AGENDA] {n_r}", "grupo_orcamentario": "📅 AGENDA: CONTAS A RECEBER", "subcategoria": "Valores a Receber", "satisfacao": "3 - Indispensável", "user_id": USER_ID}).execute()
                st.rerun()

    st.markdown("---")
    if not df_filtrado.empty:
        df_ag = df_filtrado.copy()
        df_ag["grupo_orcamentario"] = df_ag["grupo_orcamentario"].fillna("").astype(str)
        df_ag = df_ag[df_ag["grupo_orcamentario"].str.contains("📅 AGENDA", na=False)]
        if not df_ag.empty:
            st.dataframe(df_ag[["data", "descricao", "valor", "tipo"]], use_container_width=True, hide_index=True)
