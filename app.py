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
global_entradas = 0.0  
gastos_reais_mes = 0.0       
saidas_imediatas_caixa = 0.0 
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
            
            # Varredura segura para extração de parâmetros estruturais
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
                
                # Agrupamento da Agenda independente de Caixa Alta/Baixa
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

            # --- CONSTRUÇÃO DO REPOSITÓRIO FILTRADO ---
            if not df_todos_dados.empty:
                df_filtrado = df_todos_dados.copy()
                
                # Filtro robusto e normalizado (Ignora Case Sensitivity e previne somiço da tabela)
                df_filtrado = df_filtrado[~df_filtrado["grupo_orcamentario"].astype(str).str.upper().str.contains("CONFIGURAC|CONFIGURAÇÃO|CONFIG", na=False)]
                df_filtrado = df_filtrado[~df_filtrado["descricao"].astype(str).str.upper().str.contains("CONFIG_PERFIL|DIVIDA_ATIVA", na=False)]
                df_filtrado = df_filtrado[~df_filtrado["grupo_orcamentario"].astype(str).str.upper().str.contains("AGENDA", na=False)]
                
                if not df_filtrado.empty:
                    df_filtrado["ano"] = pd.to_datetime(df_filtrado["data_dt"]).dt.year
                    df_filtrado["mes"] = pd.to_datetime(df_filtrado["data_dt"]).dt.month
                    
                    def calcular_mes_fatura(linha):
                        dt = linha["data_dt"]
                        tipo_pgto = str(linha.get("tipo") or "")
                        if "💳" in tipo_pgto or "CARTÃO" in tipo_pgto.upper():
                            if dt.day > 20:
                                proximo_mes = dt.month + 1 if dt.month < 12 else 1
                                proximo_ano = dt.year if dt.month < 12 else dt.year + 1
                                return proximo_ano, proximo_mes
                        return dt.year, dt.month

                    df_filtrado[["ano_fatura", "mes_fatura"]] = df_filtrado.apply(
                        lambda r: pd.Series(calcular_mes_fatura(r)), axis=1
                    )
                    
                    # Aplicação das regras de competência temporal
                    df_filtrado = df_filtrado[
                        ((df_filtrado["tipo"].astype(str).str.contains("💳|Cartão", na=False)) & (df_filtrado["ano_fatura"] == ano_selected) & (df_filtrado["mes_fatura"] == mes_selected_num)) |
                        ((~df_filtrado["tipo"].astype(str).str.contains("💳|Cartão", na=False)) & (df_filtrado["ano"] == ano_selected) & (df_filtrado["mes"] == mes_selected_num))
                    ]

            df_acumulado_mes_cheio = df_filtrado.copy()

            # Janelas temporárias dinâmicas
            if janela_tempo == "Últimos 7 Dias" and not df_filtrado.empty:
                df_filtrado = df_filtrado[(df_filtrado["data_dt"] >= (hoje - datetime.timedelta(days=7))) & (df_filtrado["data_dt"] <= hoje)]
            elif janela_tempo == "Somente Hoje" and not df_filtrado.empty:
                df_filtrado = df_filtrado[df_filtrado["data_dt"] == hoje]
            
            if tag_busca and not df_filtrado.empty:
                df_filtrado["descricao_lower"] = df_filtrado["descricao"].fillna("").astype(str).str.lower()
                df_filtrado = df_filtrado[df_filtrado["descricao_lower"].str.contains(tag_busca, na=False)]
                
            # Liquidação matemática do período corrente
            if not df_acumulado_mes_cheio.empty:
                for _, row in df_acumulado_mes_cheio.iterrows():
                    val = float(row["valor"])
                    grupo_item = str(row["grupo_orcamentario"] or "").upper()
                    tipo_mov = str(row.get("tipo") or "").upper()
                    
                    if "ENTRADA" in tipo_mov or "FATURAMENTO" in tipo_mov or "RECEITA" in tipo_mov:
                        if "APORTE" in grupo_item or "🚀" in grupo_item:
                            continue
                        faturamento_extra_mes += val
                        global_entradas += val
                    else:
                        if "APORTE" in grupo_item or "🚀" in grupo_item:
                            continue
                        
                        gastos_reais_mes += val
                        if "💳" in row.get("tipo") or "CARTÃO" in tipo_mov:
                            fatura_acumulada_mes += val
                        else:
                            saidas_imediatas_caixa += val
                        
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

# --- 🎯 O SALDO VERDADEIRO POR DEDUÇÃO ---
saldo_real_exibido = renda_base_usuario + faturamento_extra_mes - gastos_reais_mes

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
    c_caixa1.metric(label="💰 Saldo Disponível (Orçamento)", value=f"R$ {saldo_real_exibido:,.2f}")
    c_caixa2.metric(label="📈 Faturamento Extra Capturado", value=f"R$ {faturamento_extra_mes:,.2f}")
    c_caixa3.metric(label="📉 Total Consumido no Mês", value=f"R$ {gastos_reais_mes:,.2f}")

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

    # === 📋 SEÇÃO RESTAURADA E BLINDADA DE LANÇAMENTOS ===
    st.markdown("---")
    st.subheader("📋 Gerenciar Lançamentos do Período")
    
    if supabase and not df_filtrado.empty:
        df_editor = df_filtrado[["id", "data", "descricao", "grupo_orcamentario", "subcategoria", "valor", "tipo"]].copy()
        df_editor.columns = ["ID", "Data", "Descrição", "Grupo", "Subcategoria", "Valor (R$)", "Meio / Tipo"]
        
        dados_editados = st.data_editor(
            data=df_editor,
            use_container_width=True,
            hide_index=True,
            disabled=["ID", "Grupo", "Subcategoria"],
            num_rows="dynamic"
        )
        
        if st.button("💾 Salvar Alterações da Tabela"):
            try:
                linhas_atuais_ids = set(dados_editados["ID"].dropna().astype(int).tolist())
                linhas_originais_ids = set(df_editor["ID"].astype(int).tolist())
                
                # Exclusão segura das linhas removidas pelo usuário
                for id_del in (linhas_originais_ids - linhas_atuais_ids):
                    supabase.table("movimentacoes").delete().eq("id", id_del).execute()
                    
                # Atualização explícita baseada em chaves primárias imutáveis (IDs)
                for _, row in dados_editados.iterrows():
                    if pd.notna(row["ID"]):
                        row_id = int(row["ID"])
                        supabase.table("movimentacoes").update({
                            "descricao": str(row["Descrição"]),
                            "valor": float(row["Valor (R$)"]),
                            "tipo": str(row["Meio / Tipo"]),
                            "data": str(row["Data"])
                        }).eq("id", row_id).eq("user_id", USER_ID).execute()
                        
                st.success("🔄 Alterações guardadas com total estabilidade!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao processar lote de atualizações: {e}")
    else:
        st.info("Nenhum lançamento efetuado ou encontrado para os filtros selecionados.")

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
    
    st.markdown("### 📊 Fluxo de Caixa Projetado da Agenda")
    col_ag1, col_ag2 = st.columns(2)
    col_ag1.metric(label="📉 Contas Agendadas a Pagar", value=f"R$ {agenda_a_pagar_mes:,.2f}")
    col_ag2.metric(label="🟢 Recebimentos Agendados", value=f"R$ {agenda_a_receber_mes:,.2f}")
    
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
        df_agenda_pura = df_todos_dados[df_todos_dados["grupo_orcamentario"].astype(str).str.upper().str.contains("AGENDA", na=False)].copy()
        if not df_agenda_pura.empty:
            df_agenda_pura = df_agenda_pura.sort_values(by="data")
            
            for idx, row in df_agenda_pura.iterrows():
                id_item = int(row["id"])
                desc_pura = str(row["descricao"]).replace("[AGENDA COMPROMISSO] ", "")
                valor_item = float(row["valor"])
                
                col_c1, col_c2, col_c3 = st.columns([4, 2, 2])
                col_c1.write(f"📅 **{row['data']}** - {desc_pura} | **R$ {valor_item:,.2f}**")
                
                if "PAGAR" in str(row["grupo_orcamentario"]).upper():
                    col_c2.caption("🔴 A Pagar")
                    if col_c3.button("✅ Pagar", key=f"pay_{id_item}"):
                        supabase.table("movimentacoes").delete().eq("id", id_item).execute()
                        supabase.table("movimentacoes").insert({"data": str(hoje), "valor": valor_item, "tipo": "📱 Saída Dinheiro / Pix (Débito)", "descricao": f"{desc_pura} (Pago)", "grupo_orcamentario": "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)", "subcategoria": "Contas Fixas (Luz, Água, Internet)", "satisfacao": "3 - Indispensável", "user_id": USER_ID}).execute()
                        st.rerun()
                else:
                    col_c2.caption("🟢 A Receber")
                    if col_c3.button("💰 Receber", key=f"rec_{id_item}"):
                        supabase.table("movimentacoes").delete().eq("id", id_item).execute()
                        supabase.table("movimentacoes").insert({"data": str(hoje), "valor": valor_item, "tipo": "Faturamento ou Receita (Entrada)", "descricao": f"{desc_pura} (Recebido)", "grupo_orcamentario": "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)", "subcategoria": "Renda Base Nativa", "satisfacao": "3 - Indispensável", "user_id": USER_ID}).execute()
                        st.rerun()

# ==================== ABA 4 (GESTÃO DE DÍVIDAS) ====================
with aba_dividas:
    st.title("📋 Controle Estrutural de Passivos e Dívidas")
    st.caption("Gerenciamento inteligente de contas consolidadas de longo prazo de forma simplificada.")
    
    divida_bruta_total = sum([d["valor_original"] for d in lista_dividas_cadastradas])
    total_amortizado_historico = sum(amortizacoes_totais_historicas.values())
    divida_restante_real = max(divida_bruta_total - total_amortizado_historico, 0.0)
    
    comprometimento_parcelas_mensais = sum([d["parcela"] for d in lista_dividas_cadastradas])
    indice_comprometimento = (comprometimento_parcelas_mensais / renda_base_usuario * 100) if renda_base_usuario > 0 else 0.0

    c_div1, c_div2, c_div3 = st.columns(3)
    c_div1.metric(label="🚨 Saldo Devedor Restante", value=f"R$ {divida_restante_real:,.2f}")
    c_div2.metric(label="📉 Comprometimento de Renda", value=f"{indice_comprometimento:.1f}%")
    c_div3.metric(label="✅ Total Amortizado", value=f"R$ {total_amortizado_historico:,.2f}")
    
    if indice_comprometimento > 30.0:
        st.error(f"⚠️ Atenção Crítica: Suas parcelas de passivos consomem {indice_comprometimento:.1f}% da sua Renda. Recomenda-se ajustar o planejamento.")
    elif indice_comprometimento > 0:
        st.warning(f"⚡ Atenção: {indice_comprometimento:.1f}% da sua renda está comprometida com o pagamento de dívidas.")

    st.markdown("---")
    st.subheader("🚀 Cadastrar Nova Dívida Estrutural")
    with st.form("form_cadastro_divida_passiva", clear_on_submit=True):
        col_d1, col_d2, col_d3 = st.columns(3)
        nome_credor = col_d1.text_input("Nome da Dívida / Credor:", placeholder="Ex: Empréstimo Banco X")
        saldo_devedor_inicial = col_d2.number_input("Valor Total Atual da Dívida (R$):", min_value=0.0, step=100.0)
        valor_parcela_mensal = col_d3.number_input("Valor da Parcela Mensal (R$):", min_value=0.0, step=10.0)
        
        if st.form_submit_button("Registrar Passivo no Sistema") and nome_credor and saldo_devedor_inicial > 0:
            try:
                supabase.table("movimentacoes").insert({
                    "data": str(hoje), "valor": float(saldo_devedor_inicial), "tipo": "📱 Saída Dinheiro / Pix (Débito)",
                    "descricao": "[DIVIDA_ATIVA] Registro de Passivo Estrutural", "grupo_orcamentario": "📋 QUITAÇÃO DE DÍVIDAS (ATIVO)",
                    "subcategoria": nome_credor, "satisfacao": f"{valor_parcela_mensal} - Parcela Cadastrada", "user_id": USER_ID
                }).execute()
                st.success("✅ Dívida estrutural integrada com sucesso!")
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
                    supabase.table("movimentacoes").delete().eq("id", divida["id"]).execute()
                    st.success("Registro removido do painel!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao deletar: {e}")
            st.markdown("<br>", unsafe_allow_html=True)
