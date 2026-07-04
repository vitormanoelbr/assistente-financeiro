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
    st.caption("Crie sua conta ou faça login para proteger e gerenciar suas finanças com segurança de ponta.")
    
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
                        uid_autenticado = resposta.user.id
                        token_autenticado = resposta.session.access_token
                        
                        st.session_state["usuario_logado"] = uid_autenticado
                        st.session_state["user_token"] = token_autenticado
                        
                        st.query_params["uid"] = uid_autenticado
                        st.query_params["tok"] = token_autenticado
                        
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

def deslogar_usuario():
    try:
        supabase.auth.sign_out()
    except:
        pass
    st.session_state["usuario_logado"] = None
    st.session_state["user_token"] = None
    st.query_params.clear()
    st.rerun()

if st.sidebar.button("🚪 Sair da Conta"):
    deslogar_usuario()

# --- 📅 FILTROS DE TEMPO & TAGS (SIDEBAR) ---
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

# --- PROCESSAMENTO LÓGICO & EXTRAÇÃO DE DADOS ---
renda_base_usuario = 2500.00  
faturamento_extra_mes = 0.0
gastos_reais_mes = 0.0

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
        
        if res_data := resposta_completa.data:
            df_todos_dados = pd.DataFrame(res_data)
            df_todos_dados["valor"] = df_todos_dados["valor"].astype(float)
            df_todos_dados["data_dt"] = pd.to_datetime(df_todos_dados["data"]).dt.date
            
            # 1. Varredura Global de Parâmetros e Configurações
            for item in res_data:
                grupo = item.get("grupo_orcamentario") or ""
                subcat = item.get("subcategoria") or ""
                tipo_mov = item.get("tipo", "Gasto ou Investimento (Saída)")
                val_mov = float(item["valor"])
                desc = item.get("descricao") or ""
                
                if "[CONFIG_PERFIL]" in desc and "Renda Base Nativa" in subcat:
                    renda_base_usuario = val_mov
                    continue
                
                if "📅 AGENDA" in grupo:
                    continue
                
                if "🚀 20% Aporte" in grupo and "Entrada" in tipo_mov:
                    dicionario_metas_alvo[subcat] = val_mov
                    continue
                
                if "📋 Quitação de Dívidas" in grupo:
                    if "Entrada" in tipo_mov:
                        DIVIDA_TOTAL_INICIAL += val_mov
                    else:
                        total_pago_divida += val_mov
                
                if "🚀 20% Aporte" in grupo and "Saída" in tipo_mov:
                    dicionario_aportes_acumulados[subcat] = dicionario_aportes_acumulados.get(subcat, 0.0) + val_mov

            # 2. Filtragem Temporal Restrita
            df_filtrado = df_todos_dados.copy()
            df_filtrado["ano"] = pd.to_datetime(df_filtrado["data_dt"]).dt.year
            df_filtrado["mes"] = pd.to_datetime(df_filtrado["data_dt"]).dt.month
            
            df_filtrado = df_filtrado[(df_filtrado["ano"] == ano_selected) & (df_filtrado["mes"] == mes_selected_num)]
            
            if janela_tempo == "Últimos 7 Dias":
                inicio_intervalo = hoje - datetime.timedelta(days=7)
                df_filtrado = df_filtrado[(df_filtrado["data_dt"] >= inicio_intervalo) & (df_filtrado["data_dt"] <= hoje)]
            elif janela_tempo == "Somente Hoje":
                df_filtrado = df_filtrado[df_filtrado["data_dt"] == hoje]
            
            if tag_busca:
                df_filtrado["descricao_lower"] = df_filtrado["descricao"].fillna("").astype(str).str.lower()
                df_filtrado = df_filtrado[df_filtrado["descricao_lower"].str.contains(tag_busca, na=False)]
                
            # 3. Consolidação Mensal Real
            for _, row in df_filtrado.iterrows():
                val = float(row["valor"])
                grupo = str(row["grupo_orcamentario"] or "")
                tipo_mov = row.get("tipo", "Gasto ou Investimento (Saída)")
                desc = str(row["descricao"] or "")
                
                if "[CONFIG_PERFIL]" in desc:
                    continue
                
                if "📅 AGENDA: CONTAS A PAGAR" in grupo:
                    agenda_a_pagar_mes += val
                    continue
                elif "📅 AGENDA: CONTAS A RECEBER" in grupo:
                    agenda_a_receber_mes += val
                    continue
                
                if "🚀 20% Aporte" in grupo and "Entrada" in tipo_mov:
                    continue
                
                if "Faturamento" in tipo_mov:
                    faturamento_extra_mes += val
                else:
                    gastos_reais_mes += val
                    if "50% Essencial" in grupo:
                        gastos_essencial += val
                    elif "30% Estilo de Vida" in grupo:
                        gastos_estilo += val
                    elif "20% Aporte" in group := grupo:
                        gastos_aporte_mes += val
                    elif "💼 Custos de Negócio" in grupo:
                        gastos_negocio += val
                    
    except Exception as e:
        if "JWT expired" in str(e) or "PGRST303" in str(e):
            st.error("🔒 Sua sessão expirou por segurança. Faça login novamente.")
            deslogar_usuario()
        else:
            st.error(f"Erro na validação de segurança: {e}")

# INTERFACE SIDEBAR: Renda Base Customizada
st.sidebar.markdown("---")
st.sidebar.header("⚙️ Configurações do Perfil")
nova_renda_input = st.sidebar.number_input("Sua Renda Mensal Base (R$):", min_value=0.0, value=renda_base_usuario, step=50.0, format="%.2f")

if st.sidebar.button("💾 Salvar Renda Base"):
    try:
        if not df_todos_dados.empty:
            supabase.table("movimentacoes").delete().eq("descricao", "[CONFIG_PERFIL] Renda Base").eq("user_id", USER_ID).execute()
        
        supabase.table("movimentacoes").insert({
            "data": str(hoje), "valor": float(nova_renda_input), "tipo": "Faturamento ou Receita (Entrada)",
            "descricao": "[CONFIG_PERFIL] Renda Base", "grupo_orcamentario": "⚙️ CONFIGURAÇÃO",
            "subcategoria": "Renda Base Nativa", "satisfacao": "3 - Indispensável", "user_id": USER_ID
        }).execute()
        st.sidebar.success("Renda updated com sucesso!")
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Erro ao salvar perfil: {e}")

# Atualização dos limites matemáticos dinâmicos
LIMITE_ESSENCIAL = renda_base_usuario * 0.50       
LIMITE_ESTILO_DE_VIDA = renda_base_usuario * 0.30  
META_APORTE_MENSAL = renda_base_usuario * 0.20           

receitas_totais_calculadas = renda_base_usuario + faturamento_extra_mes if not tag_busca else faturamento_extra_mes
saldo_disponivel_caixa = receitas_totais_calculadas - gastos_reais_mes
saldo_devedor_restante = max(DIVIDA_TOTAL_INICIAL - total_pago_divida, 0.0)

saldo_livre_puro = receitas_totais_calculadas - max(gastos_essencial, LIMITE_ESSENCIAL) - max(gastos_estilo, LIMITE_ESTILO_DE_VIDA) - max(gastos_aporte_mes, META_APORTE_MENSAL) - gastos_negocio

lista_porquinhos_existentes = list(dicionario_metas_alvo.keys())
if not lista_porquinhos_existentes:
    lista_porquinhos_existentes = ["🧱 Reserva de Emergência", "🏡 Comprar Casa"]

MAPA_CATEGORIAS = {
    "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)": [
        "Alimentação Básica & Mercado", "Contas Fixas (Luz, Água, Internet)", 
        "Habitação (Aluguel / Financiamento)", "Saúde & Medicamentos", 
        "Transporte & Combustível", "Pensão / Obrigações Legais"
    ],
    "🟡 30% Estilo de Vida (Lazer e Custos Voláteis)": [
        "Lazer, Bares & Restaurantes", "Delivery / iFood / Conforto", 
        "Vestuário, Compras & Presentes", "Estética, Cuidados & Academia", 
        "Viagens & Hobbies", "Assinaturas (Netflix, Spotify)"
    ],
    "🚀 20% Aporte para a Liberdade (Investimentos e Futuro)": lista_porquinhos_existentes + ["➕ [Criar Nova Meta / Porquinho]"],
    "📋 Quitação de Dívidas (Amortizações e Acordos)": [
        "Empréstimos Bancários", "Cartão de Crédito Atrasado", "Financiamentos de Bens", "Dívidas Pessoais / Terceiros"
    ],
    "💼 Custos de Negócio (Projetos e Clínica)": [
        "Ferramentas SaaS & Softwares", "Marketing & Anúncios", "Infraestrutura & Custos Operacionais"
    ]
}

aba_painel, aba_porquinhos, aba_agenda = st.tabs(["📊 Painel & Lançamentos", "🐷 Meus Porquinhos & Rumo ao Milhão", "📅 Agenda de Compromissos"])

# ==================== ABA 1 ====================
with aba_painel:
    if tag_busca:
        st.warning(f"🔍 **Modo de Rastreamento Ativo:** Mostrando apenas resultados para a tag `{tag_busca}`")
        
    st.title("📲 Meu Planner Financeiro")
    
    st.markdown(f"### 🏦 Saúde Disponível do Caixa ({janela_tempo})")
    c_caixa1, c_caixa2, c_caixa3 = st.columns(3)
    c_caixa1.metric(label="Receitas Mapeadas", value=f"R$ {receitas_totais_calculadas:,.2f}")
    c_caixa2.metric(label="Saldo Filtrado em Caixa", value=f"R$ {saldo_disponivel_caixa:,.2f}")
    c_caixa3.metric(label="Total Gasto no Filtro", value=f"R$ {gastos_reais_mes:,.2f}")

    if (agenda_a_pagar_mes > 0 or agenda_a_receber_mes > 0) and not tag_busca:
        st.markdown("#### 🔮 Previsões Mapeadas para o Restante do Mês")
        c_prev1, c_prev2, c_prev3 = st.columns(3)
        c_prev1.metric(label="A Receber Agendado", value=f"R$ {agenda_a_receber_mes:,.2f}")
        c_prev2.metric(label="Boletos Fixos Pendentes", value=f"R$ {agenda_a_pagar_mes:,.2f}")
        c_prev3.metric(label="Balanço Previsto", value=f"R$ {agenda_a_receber_mes - agenda_a_pagar_mes:,.2f}", delta="Cenário Futuro")

    st.markdown("---")
    st.subheader("📊 Painel de Limites Orçamentários")
    
    if not tag_busca:
        st.markdown("### 🧮 Situação de Dívidas Estruturadas")
        col1, col2, col3 = st.columns(3)
        col1.metric(label="Volume Devedor Inicial", value=f"R$ {DIVIDA_TOTAL_INICIAL:,.2f}")
        col2.metric(label="Total Amortizado (Pago)", value=f"R$ {total_pago_divida:,.2f}")
        
        if saldo_devedor_restante > 0:
            col3.metric(label="Falta Pagar (Saldo Real)", value=f"R$ {saldo_devedor_restante:,.2f}", delta="-Amortizando", delta_color="inverse")
        else:
            col3.metric(label="Saldo Devedor", value="R$ 0,00 🎉", delta="Quitado!")
            
        if DIVIDA_TOTAL_INICIAL > 0:
            st.progress(min(total_pago_divida / DIVIDA_TOTAL_INICIAL, 1.0))
        st.markdown("---")
    
    st.write(f"🔴 **Gasto Essencial:** R$ {gastos_essencial:,.2f} de R$ {LIMITE_ESSENCIAL:,.2f}")
    st.progress(min(gastos_essencial / LIMITE_ESSENCIAL, 1.0) if LIMITE_ESSENCIAL > 0 else 0.0)
    st.write(f"🟡 **Estilo de Vida:** R$ {gastos_estilo:,.2f} de R$ {LIMITE_ESTILO_DE_VIDA:,.2f}")
    st.progress(min(gastos_estilo / LIMITE_ESTILO_DE_VIDA, 1.0) if LIMITE_ESTILO_DE_VIDA > 0 else 0.0)
    st.write(f"🚀 **Aporte Mensal Realizado:** R$ {gastos_aporte_mes:,.2f} de R$ {META_APORTE_MENSAL:,.2f}")
    st.progress(min(gastos_aporte_mes / META_APORTE_MENSAL, 1.0) if META_APORTE_MENSAL > 0 else 0.0)

    # --- Gráfico Donut ---
    try:
        df_Seguro = df_filtrado.copy() if not df_filtrado.empty else pd.DataFrame(columns=["grupo_orcamentario", "descricao", "satisfacao", "valor", "tipo"])
        df_Seguro["grupo_orcamentario"] = df_Seguro["grupo_orcamentario"].fillna("").astype(str)
        df_Seguro["tipo"] = df_Seguro["tipo"].fillna("").astype(str)
        df_Seguro["descricao"] = df_Seguro["descricao"].fillna("").astype(str)
        
        df_saidas = df_Seguro[
            (~df_Seguro["grupo_orcamentario"].str.contains("📅 AGENDA", na=False)) & 
            (~df_Seguro["grupo_orcamentario"].str.contains("⚙️ CONFIGURAÇÃO", na=False)) & 
            (~df_Seguro["descricao"].str.contains("\[CONFIG_PERFIL\]", na=False)) &
            (df_Seguro["tipo"].str.contains("Saída", na=False))
        ].copy()
        
        if not df_saidas.empty:
            st.markdown("---")
            st.subheader("🍩 Distribuição do Filtro Atual")
            df_pizza = df_saidas.groupby("grupo_orcamentario")["valor"].sum().reset_index()
            fig_donut = px.pie(df_pizza, values="valor", names="grupo_orcamentario", hole=0.4, color_discrete_sequence=px.colors.qualitative.Safe)
            fig_donut.update_layout(margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig_donut, use_container_width=True)
    except Exception:
        pass

    st.markdown("---")
    st.subheader("📥 Registrar Movimentação Realizada")
    grupo_orcamentario = st.selectbox("Destinação Estratégica do Valor:", list(MAPA_CATEGORIAS.keys()), key="grupo_pai_main")
    opcoes_subcategoria = MAPA_CATEGORIAS[grupo_orcamentario]
    categoria = st.selectbox("Subcategoria Correspondente:", opcoes_subcategoria, key="sub_filho_main")

    criando_novo_porquinho = (categoria == "➕ [Criar Nova Meta / Porquinho]")
    nome_novo_fundo = ""
    val_alvo_novo_fundo = 0.0
    
    if criando_novo_porquinho:
        col_n1, col_n2 = st.columns(2)
        nome_novo_fundo = col_n1.text_input("Nome e Emoji da Nova Meta:", placeholder="Ex: ✈️ Férias")
        val_alvo_novo_fundo = col_n2.number_input("Valor Alvo da Meta (R$):", min_value=0.0, value=1000.00, step=50.0, format="%.2f")

    with st.form("formulario_envio_blindado", clear_on_submit=True):
        valor = st.number_input("Qual o valor da operação? (R$)", min_value=0.0, step=0.01, format="%.2f")
        if criando_novo_porquinho:
            tipo = st.radio("Direção configurada automaticamente:", ["Faturamento ou Receita (Entrada)"])
        else:
            tipo = st.radio("Direção do dinheiro:", ["Gasto ou Investimento (Saída)", "Faturamento ou Receita (Entrada)"], horizontal=True)
            
        data_movimento = st.date_input("Data do evento:", datetime.date.today())
        descricao = st.text_input("Descrição ou Estabelecimento:", placeholder="Use #filho para rastrear dependentes...")
        satisfacao = st.select_slider("🧠 Nível de necessidade real?", options=["1 - Impulsivo / Evitável", "2 - Útil / Desejável", "3 - Indispensável"], value="2 - Útil / Desejável")
        botao_enviar = st.form_submit_button("Confirmar Lançamento Real")
        
    if botao_enviar and supabase:
        final_subcat = nome_novo_fundo if criando_novo_porquinho else categoria
        final_valor = val_alvo_novo_fundo if criando_novo_porquinho else valor
        final_desc = f"Meta Criada: {nome_novo_fundo}" if criando_novo_porquinho else descricao
        
        if final_valor > 0 and final_desc:
            try:
                dados_gasto = {
                    "data": str(data_movimento), "valor": float(final_valor), "tipo": tipo,
                    "descricao": final_desc, "grupo_orcamentario": grupo_orcamentario,
                    "subcategoria": final_subcat, "satisfacao": satisfacao,
                    "user_id": USER_ID
                }
                supabase.table("movimentacoes").insert(dados_gasto).execute()
                st.success("✅ Sincronizado com sua conta!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

    # --- 📋 GERENCIADOR DE LANÇAMENTOS SEGURO ---
    st.markdown("---")
    st.subheader("📋 Gerenciar Lançamentos do Período")
    
    if supabase and not df_todos_dados.empty:
        df_editor_limpo = df_filtrado.copy() if not df_filtrado.empty else pd.DataFrame()
        if not df_editor_limpo.empty:
            df_editor_limpo["grupo_orcamentario"] = df_editor_limpo["grupo_orcamentario"].fillna("").astype(str)
            df_editor_limpo["descricao"] = df_editor_limpo["descricao"].fillna("").astype(str)
            df_editor_limpo = df_editor_limpo[
                (~df_editor_limpo["grupo_orcamentario"].str.contains("📅 AGENDA", na=False)) &
                (~df_editor_limpo["grupo_orcamentario"].str.contains("⚙️ CONFIGURAÇÃO", na=False)) &
                (~df_editor_limpo["descricao"].str.contains("\[CONFIG_PERFIL\]", na=False))
            ]
        
        if not df_editor_limpo.empty:
            df_editor = df_editor_limpo[["id", "data", "descricao", "grupo_orcamentario", "subcategoria", "valor", "tipo"]].copy()
            df_editor.columns = ["ID", "Data", "Descrição", "Grupo", "Subcategoria", "Valor (R$)", "Tipo"]
            
            dados_editados = st.data_editor(df_editor, use_container_width=True, hide_index=True, disabled=["ID"], num_rows="dynamic")
            
            if st.button("💾 Salvar Alterações da Tabela"):
                try:
                    linhas_atuais_ids = set(dados_editados["ID"].tolist())
                    linhas_originais_ids = set(df_editor["ID"].tolist())
                    ids_deletados = linhas_originais_ids - linhas_atuais_ids
                    for id_del in ids_deletados:
                        supabase.table("movimentacoes").delete().eq("id", int(id_del)).execute()
                    for _, row in dados_editados.iterrows():
                        row_id = int(row["ID"])
                        orig_row = df_editor[df_editor["ID"] == row_id].iloc[0]
                        if (row["Descrição"] != orig_row["Descrição"]) or (float(row["Valor (R$)"]) != float(orig_row["Valor (R$)"])) or (row["Tipo"] != orig_row["Tipo"]):
                            supabase.table("movimentacoes").update({"descricao": row["Descrição"], "valor": float(row["Valor (R$)"]), "tipo": row["Tipo"]}).eq("id", row_id).execute()
                    st.success("🔄 Alterações salvas com segurança!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar alterações: {e}")
        else:
            st.info("💡 Nenhum lançamento real encontrado com os filtros atuais.")

# ==================== ABA 2 (REESTRUTURADA) ====================
with aba_porquinhos:
    st.title("🐷 Meus Porquinhos & Metas Individuais")
    st.caption("Acompanhe o dinheiro real carimbado e guardado para cada objetivo da sua conta.")
    st.markdown("---")
    
    total_patrimonio_guardado = 0.0
    
    if dicionario_metas_alvo:
        for nome_meta, valor_alvo in dicionario_metas_alvo.items():
            guardado = dicionario_aportes_acumulados.get(nome_meta, 0.0)
            total_patrimonio_guardado += guardado
            falta_guardar = max(valor_alvo - guardado, 0.0)
            
            st.subheader(f"{nome_meta}")
            c1, c2, c3 = st.columns(3)
            c1.metric(label="Valor Alvo Final", value=f"R$ {valor_alvo:,.2f}")
            c2.metric(label="Total Já Guardado", value=f"R$ {guardado:,.2f}")
            c3.metric(label="Quanto Falta Alocar", value=f"R$ {falta_guardar:,.2f}")
            
            st.progress(min(guardado / valor_alvo, 1.0) if valor_alvo > 0 else 0.0)
            st.markdown(f"**Progresso do Objetivo:** {(guardado / valor_alvo) * 100:.1f}%" if valor_alvo > 0 else "0.0%")
            st.markdown("---")
    else:
        st.info("💡 Você ainda não criou nenhum porquinho.")

    # ==================== 🚀 O MOTOR DO PRIMEIRO MILHÃO ====================
    st.title("🚀 Estrada Estratégica Rumo ao 1 Milhão")
    st.caption("Abaixo está o seu plano de guerra comportamental. O sistema calcula o tempo exato para cravar cada degrau baseando-se no seu patrimônio acumulado e no seu aporte mensal teórico.")
    
    st.markdown(f"**💰 Seu Patrimônio Consolidado Atual:** R$ {total_patrimonio_guardado:,.2f}")
    st.markdown(f"**📈 Seu Aporte Mensal Planejado (20%):** R$ {META_APORTE_MENSAL:,.2f} /mês")
    
    # Parâmetro de inteligência: Taxa líquida conservadora de 0.8% ao mês (já descontando inflação/imposto médio estimado)
    TAXA_MENSAL_LIQUIDA = 0.008 
    
    # Definição dos degraus estratégicos do milhão
    degraus_objetivos = [
        {"alvo": 10000.0, "nome": "🧱 R$ 10k — Reserva de Segurança Base"},
        {"alvo": 50000.0, "nome": "🎯 R$ 50k — O Primeiro Impulso Real"},
        {"alvo": 100000.0, "nome": "💎 R$ 100k — O Lote de Elite Psicológico"},
        {"alvo": 250000.0, "nome": "🏰 R$ 250k — Um Quarto do Caminho Concluído"},
        {"alvo": 500000.0, "nome": "⚔️ R$ 500k — Meio Milhão (Reta de Aceleração)"},
        {"alvo": 1000000.0, "nome": "👑 R$ 1 Milhão — Liberdade Financeira Fundada"}
    ]
    
    st.markdown("### 🏁 Checklist de Conquista Intermediária")
    
    # Motor matemático iterativo de juros compostos mês a mês
    for degrau in degraus_objetivos:
        alvo_valor = degrau["alvo"]
        nome_degrau = degrau["nome"]
        
        if total_patrimonio_guardado >= alvo_valor:
            # Degrau já conquistado
            st.success(f"✅ **{nome_degrau}** — **CONQUISTADO!** Você já passou desse marco.")
        else:
            # Calcula quantos meses faltam usando projeção de juros compostos + aportes
            saldo_simulado = total_patrimonio_guardado
            meses_necessarios = 0
            
            # Limite de segurança para evitar loops infinitos caso o aporte seja zero
            if META_APORTE_MENSAL <= 0 and TAXA_MENSAL_LIQUIDA <= 0:
                meses_necessarios = 999
            else:
                while saldo_simulado < alvo_valor and meses_necessarios < 600:
                    saldo_simulado = (saldo_simulado * (1 + TAXA_MENSAL_LIQUIDA)) + META_APORTE_MENSAL
                    meses_necessarios += 1
            
            # Cálculo da data prevista de conquista
            if meses_necessarios < 600:
                data_conquista = hoje + datetime.timedelta(days=int(meses_necessarios * 30.41))
                mes_ano_texto = data_conquista.strftime("%B / %Y").capitalize()
                
                # Exibição do progresso em direção ao degrau atual
                porcentagem_degrau = min((total_patrimonio_guardado / alvo_valor) * 100, 100.0)
                
                st.markdown(f"🔒 **{nome_degrau}**")
                st.write(f"Faltam **{meses_necessarios} meses** — Previsão de conquista: **{mes_ano_texto}**")
                st.progress(porcentagem_degrau / 100.0)
                st.caption(f"Falta arrecadar R$ {alvo_valor - total_patrimonio_guardado:,.2f} ({porcentagem_degrau:.1f}% concluído)")
            else:
                st.markdown(f"🔒 **{nome_degrau}**")
                st.warning("⚠️ Ajuste ou configure um aporte mensal na barra lateral para calcular a linha do milhão.")
        st.markdown("---")

# ==================== ABA 3 ====================
with aba_agenda:
    st.title("📅 Agenda de Compromissos Financeiros")
    st.caption("Mapeie seus boletos fixos e contas a receber.")
    st.markdown("---")
    
    col_agenda1, col_agenda2 = st.columns(2)
    
    with col_agenda1:
        st.subheader("📌 Agendar Conta Fixa (A Pagar)")
        with st.form("form_agenda_pagar", clear_on_submit=True):
            name_boleto = st.text_input("Nome da Conta / Boleto:", placeholder="Ex: Conta de Luz...")
            valor_boleto = st.number_input("Valor Estimado (R$):", min_value=0.0, step=0.01, format="%.2f")
            vencimento_boleto = st.date_input("Data de Vencimento:", datetime.date.today())
            botao_agenda_pagar = st.form_submit_button("Agendar Conta Fixa")
            
            if botao_agenda_pagar and supabase and name_boleto and valor_boleto > 0:
                try:
                    supabase.table("movimentacoes").insert({
                        "data": str(vencimento_boleto), "valor": float(valor_boleto), "tipo": "Gasto ou Investimento (Saída)",
                        "descricao": f"[AGENDA COMPROMISSO] {name_boleto}", "grupo_orcamentario": "📅 AGENDA: CONTAS A PAGAR",
                        "subcategoria": "Conta Fixa", "satisfacao": "3 - Indispensável", "user_id": USER_ID
                    }).execute()
                    st.success("📝 Boleto agendado com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")
                    
    with col_agenda2:
        st.subheader("💰 Agendar Valor (A Receber)")
        with st.form("form_agenda_receber", clear_on_submit=True):
            nome_recebivel = st.text_input("O que tem a receber?:", placeholder="Ex: Freelance...")
            valor_recebivel = st.number_input("Valor a Receber (R$):", min_value=0.0, step=0.01, format="%.2f")
            data_recebivel = st.date_input("Data de Expectativa:", datetime.date.today())
            botao_agenda_receber = st.form_submit_button("Agendar Recebimento")
            
            if botao_agenda_receber and supabase and nome_recebivel and valor_recebivel > 0:
                try:
                    supabase.table("movimentacoes").insert({
                        "data": str(data_recebivel), "valor": float(valor_recebivel), "tipo": "Faturamento ou Receita (Entrada)",
                        "descricao": f"[AGENDA COMPROMISSO] {nome_recebivel}", "grupo_orcamentario": "📅 AGENDA: CONTAS A RECEBER",
                        "subcategoria": "Valores a Receber", "satisfacao": "3 - Indispensável", "user_id": USER_ID
                    }).execute()
                    st.success("📝 Recebimento agendado!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")

    st.markdown("---")
    st.subheader("📋 Seus Compromissos Mapeados no Período")
    
    if supabase and not df_todos_dados.empty:
        df_agenda_pura = df_todos_dados.copy()
        df_agenda_pura["grupo_orcamentario"] = df_agenda_pura["grupo_orcamentario"].fillna("").astype(str)
        df_agenda_pura["ano"] = pd.to_datetime(df_agenda_pura["data_dt"]).dt.year
        df_agenda_pura["mes"] = pd.to_datetime(df_agenda_pura["data_dt"]).dt.month
        
        df_agenda_pura = df_agenda_pura[(df_agenda_pura["ano"] == ano_selected) & (df_agenda_pura["mes"] == mes_selected_num)]
        df_agenda_pura = df_agenda_pura[df_agenda_pura["grupo_orcamentario"].str.contains("📅 AGENDA", na=False)]
        
        if not df_agenda_pura.empty:
            for idx, row in df_agenda_pura.iterrows():
                id_item = int(row["id"])
                desc_pura = str(row["descricao"]).replace("[AGENDA COMPROMISSO] ", "")
                valor_item = float(row["valor"])
                grupo_item = str(row["grupo_orcamentario"])
                tipo_item = str(row["tipo"])
                data_venc = row["data"]
                
                col_c1, col_c2, col_c3 = st.columns([3, 1, 1])
                col_c1.write(f"📅 **{data_venc}** - {desc_pura} | **R$ {valor_item:,.2f}**")
                
                if "CONTAS A PAGAR" in grupo_item:
                    col_c2.caption("🔴 A Pagar")
                    if col_c3.button("✅ Pagar", key=f"pay_{id_item}"):
                        supabase.table("movimentacoes").delete().eq("id", id_item).execute()
                        supabase.table("movimentacoes").insert({
                            "data": str(hoje), "valor": valor_item, "tipo": tipo_item,
                            "descricao": f"{desc_pura} (Pago via Agenda)", "grupo_orcamentario": "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)",
                            "subcategoria": "Contas Fixas (Luz, Água, Internet)", "satisfacao": "3 - Indispensável", "user_id": USER_ID
                        }).execute()
                        st.success(f"Baixa dada em: {desc_pura}!")
                        st.rerun()
                else:
                    col_c2.caption("🟢 A Receber")
                    if col_c3.button("💰 Receber", key=f"rec_{id_item}"):
                        supabase.table("movimentacoes").delete().eq("id", id_item).execute()
                        supabase.table("movimentacoes").insert({
                            "data": str(hoje), "valor": valor_item, "tipo": tipo_item,
                            "descricao": f"{desc_pura} (Recebido via Agenda)", "grupo_orcamentario": "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)",
                            "subcategoria": "Renda Base Nativa", "satisfacao": "3 - Indispensável", "user_id": USER_ID
                        }).execute()
                        st.success(f"Valor recebido: {desc_pura}!")
                        st.rerun()
        else:
            st.info("💡 Nenhum boleto ou valor a receber agendado para este mês.")
