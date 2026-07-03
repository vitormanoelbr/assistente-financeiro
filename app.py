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

# --- ⚙️ PERFIL & FILTROS (SIDEBAR) ---
st.sidebar.header("⚙️ Configurações do Perfil")
RENDA_BASE = st.sidebar.number_input("Sua Renda Mensal Base (R$):", min_value=0.0, value=2500.00, step=100.0)

st.sidebar.markdown("---")
st.sidebar.header("📅 Filtros de Tempo")

hoje = datetime.date.today()
ano_atual = hoje.year
mes_atual = hoje.month

lista_anos = [ano_atual, ano_atual - 1, ano_atual + 1]
ano_selected = st.sidebar.selectbox("Ano de Análise:", lista_anos, index=0)

lista_meses = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}
mes_selected_num = st.sidebar.selectbox(
    "Mês de Análise:", 
    list(lista_meses.keys()), 
    format_func=lambda x: lista_meses[x],
    index=list(lista_meses.keys()).index(mes_atual)
)

janela_tempo = st.sidebar.radio("Intervalo do Painel:", ["Mês Completo", "Últimos 7 Dias", "Somente Hoje"])

# --- PROCESSAMENTO LÓGICO DE DADOS ---
# Metas do método base
LIMITE_ESSENCIAL = RENDA_BASE * 0.50       
LIMITE_ESTILO_DE_VIDA = RENDA_BASE * 0.30  
META_APORTE_MENSAL = RENDA_BASE * 0.20           

gastos_essencial = 0.0
gastos_estilo = 0.0
gastos_aporte_mes = 0.0

DIVIDA_TOTAL_INICIAL = 0.0
total_pago_divida = 0.0

dicionario_metas_alvo = {}
dicionario_aportes_acumulados = {}

df_todos_dados = pd.DataFrame()
df_filtrado = pd.DataFrame()

if supabase:
    try:
        resposta_completa = supabase.table("movimentacoes").select("id, data, descricao, grupo_orcamentario, subcategoria, valor, satisfacao, tipo").execute()
        if res_data := resposta_completa.data:
            df_todos_dados = pd.DataFrame(res_data)
            df_todos_dados["valor"] = df_todos_dados["valor"].astype(float)
            df_todos_dados["data_dt"] = pd.to_datetime(df_todos_dados["data"]).dt.date
            
            # Varredura Histórica Acumulada na Nuvem
            for item in res_data:
                grupo = item["grupo_orcamentario"]
                subcat = item["subcategoria"]
                tipo_mov = item.get("tipo", "Gasto ou Investimento (Saída)")
                val_mov = float(item["valor"])
                
                if "📋 Quitação de Dívidas" in grupo:
                    if "Entrada" in tipo_mov:
                        DIVIDA_TOTAL_INICIAL += val_mov
                    else:
                        total_pago_divida += val_mov
                
                if "🚀 20% Aporte" in grupo:
                    if "Entrada" in tipo_mov:
                        dicionario_metas_alvo[subcat] = val_mov
                    else:
                        dicionario_aportes_acumulados[subcat] = dicionario_aportes_acumulados.get(subcat, 0.0) + val_mov
            
            # Filtro Temporal do Período
            df_filtrado = df_todos_dados.copy()
            df_filtrado["ano"] = pd.to_datetime(df_filtrado["data_dt"]).dt.year
            df_filtrado["mes"] = pd.to_datetime(df_filtrado["data_dt"]).dt.month
            df_filtrado = df_filtrado[(df_filtrado["ano"] == ano_selected) & (df_filtrado["mes"] == mes_selected_num)]
            
            if janela_tempo == "Últimos 7 Dias":
                df_filtrado = df_filtrado[df_filtrado["data_dt"] >= (hoje - datetime.timedelta(days=7))]
            elif janela_tempo == "Somente Hoje":
                df_filtrado = df_filtrado[df_filtrado["data_dt"] == hoje]
                
            for _, row in df_filtrado.iterrows():
                val = float(row["valor"])
                grupo = row["grupo_orcamentario"]
                tipo_mov = row.get("tipo", "Gasto ou Investimento (Saída)")
                
                if "Saída" in tipo_mov:
                    if "50% Essencial" in grupo:
                        gastos_essencial += val
                    elif "30% Estilo de Vida" in grupo:
                        gastos_estilo += val
                    elif "20% Aporte" in grupo:
                        gastos_aporte_mes += val
                    
    except Exception as e:
        st.error(f"Erro no processamento técnico de dados: {e}")

divida_restante = max(DIVIDA_TOTAL_INICIAL - total_pago_divida, 0.0)

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

# --- NAVEGAÇÃO ---
aba_painel, aba_porquinhos = st.tabs(["📊 Painel & Lançamentos", "🐷 Meus Porquinhos"])

# ==================== ABA 1: PAINEL & LANÇAMENTOS ====================
with aba_painel:
    st.title("📲 Meu Planner Financeiro")
    st.markdown(f"**Competência do Painel:** {lista_meses[mes_selected_num]} / {ano_selected} ({janela_tempo})")
    st.markdown("---")
    
    # PAINEL DE DÍVIDAS
    st.subheader("📊 Painel de Limites Orçamentários")
    st.markdown("### 🧮 Situação de Dívidas Estruturadas")
    col1, col2, col3 = st.columns(3)
    col1.metric(label="Volume Devedor Inicial", value=f"R$ {DIVIDA_TOTAL_INICIAL:,.2f}")
    col2.metric(label="Total Amortizado (Pago)", value=f"R$ {total_pago_divida:,.2f}")
    if divida_restante > 0:
        col3.metric(label="Falta Pagar (Saldo Real)", value=f"R$ {divida_restante:,.2f}", delta="-Amortizando", delta_color="inverse")
    else:
        col3.metric(label="Saldo Devedor", value="R$ 0,00 🎉", delta="Quitado!")
        
    if DIVIDA_TOTAL_INICIAL > 0:
        st.progress(min(total_pago_divida / DIVIDA_TOTAL_INICIAL, 1.0))
    
    st.markdown("---")
    
    # DISTRIBUIÇÃO MENSAL LÍQUIDA
    st.write(f"🔴 **Gasto Essencial:** R$ {gastos_essencial:,.2f} de R$ {LIMITE_ESSENCIAL:,.2f}")
    st.progress(min(gastos_essencial / LIMITE_ESSENCIAL, 1.0) if LIMITE_ESSENCIAL > 0 else 0.0)
    st.write(f"🟡 **Estilo de Vida:** R$ {gastos_estilo:,.2f} de R$ {LIMITE_ESTILO_DE_VIDA:,.2f}")
    st.progress(min(gastos_estilo / LIMITE_ESTILO_DE_VIDA, 1.0) if LIMITE_ESTILO_DE_VIDA > 0 else 0.0)
    st.write(f"🚀 **Aporte Mensal Realizado:** R$ {gastos_aporte_mes:,.2f} de R$ {META_APORTE_MENSAL:,.2f}")
    st.progress(min(gastos_aporte_mes / META_APORTE_MENSAL, 1.0) if META_APORTE_MENSAL > 0 else 0.0)

    # --- 🧠 DASHBOARD DE NÍVEL DE NECESSIDADE CORRIGIDO ---
    if not df_filtrado.empty:
        st.markdown("---")
        st.subheader("🧠 Raio-X de Necessidade Real (Mês Filtrado)")
        
        df_filtrado["Nível Numérico"] = df_filtrado["satisfacao"].astype(str).str[0]
        # Correção da variável fixa de agrupamento
        df_necessidade_real = df_filtrado.groupby("Nível Numérico")["valor"].sum().reset_index()
        df_necessidade_real.columns = ["Nível de Importância", "Total Gasto (R$)"]
        
        mapa_nomes = {
            "1": "🚨 1 - Impulsivo / Evitável", 
            "2": "🟡 2 - Útil / Desejável", 
            "3": "🟢 3 - Indispensável"
        }
        df_necessidade_real["Nível de Importância"] = df_necessidade_real["Nível de Importance"].map(mapa_nomes)
        
        fig_necessidade = px.bar(
            df_necessidade_real, # Variável perfeitamente mapeada aqui
            y="Nível de Importância",
            x="Total Gasto (R$)",
            orientation='h',
            title="Volume Financeiro Alocado por Urgência Psicológica",
            color="Nível de Importância",
            color_discrete_map={
                "🚨 1 - Impulsivo / Evitável": "#FF4B4B",
                "🟡 2 - Útil / Desejável": "#FFD700",
                "🟢 3 - Indispensável": "#00FF66"
            }
        )
        fig_necessidade.update_layout(showlegend=False, yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_necessidade, use_container_width=True)

    # FORMULÁRIO DE REGISTRO
    st.markdown("---")
    st.subheader("📥 Registrar Movimentação")
    
    grupo_orcamentario = st.selectbox("Destinação Estratégica do Valor:", list(MAPA_CATEGORIAS.keys()), key="grupo_pai_main")
    opcoes_subcategoria = MAPA_CATEGORIAS[grupo_orcamentario]
    categoria = st.selectbox("Subcategoria Correspondente:", opcoes_subcategoria, key="sub_filho_main")

    criando_novo_porquinho = (categoria == "➕ [Criar Nova Meta / Porquinho]")
    nome_novo_fundo = ""
    val_alvo_novo_fundo = 0.0
    
    if criando_novo_porquinho:
        st.info("💡 Digite o nome do porquinho usando o emoji que preferir no seu teclado!")
        col_n1, col_n2 = st.columns(2)
        nome_novo_fundo = col_n1.text_input("Nome e Emoji da Nova Meta:", placeholder="Ex: ✈️ Férias, 🏍️ Moto")
        val_alvo_novo_fundo = col_n2.number_input("Valor Alvo da Meta (R$):", min_value=0.0, value=1000.00, step=500.0)

    with st.form("formulario_envio_blindado", clear_on_submit=True):
        valor = st.number_input("Qual o valor da operação? (R$)", min_value=0.0, step=5.0, format="%.2f")
        if criando_novo_porquinho:
            tipo = st.radio("Direção configurada automaticamente:", ["Faturamento ou Receita (Entrada)"])
        else:
            tipo = st.radio("Direção do dinheiro:", ["Gasto ou Investimento (Saída)", "Faturamento ou Receita (Entrada)"], horizontal=True)
            
        data_movimento = st.date_input("Data do evento:", datetime.date.today())
        descricao = st.text_input("Descrição ou Estabelecimento:", placeholder="Ex: Aporte Mensal, Depósito Inicial...")
        satisfacao = st.select_slider("🧠 Nível de necessidade real?", options=["1 - Impulsivo / Evitável", "2 - Útil / Desejável", "3 - Indispensável"], value="2 - Útil / Desejável")
        botao_enviar = st.form_submit_button("Confirmar Lançamento")
        
    if botao_enviar and supabase:
        final_subcat = nome_novo_fundo if criando_novo_porquinho else categoria
        final_valor = val_alvo_novo_fundo if criando_novo_porquinho else valor
        final_desc = f"Meta Criada: {nome_novo_fundo}" if criando_novo_porquinho else descricao
        
        if final_valor > 0 and final_desc:
            try:
                dados_gasto = {
                    "data": str(data_movimento), "valor": float(final_valor), "tipo": tipo,
                    "descricao": final_desc, "grupo_orcamentario": grupo_orcamentario,
                    "subcategoria": final_subcat, "satisfacao": satisfacao
                }
                supabase.table("movimentacoes").insert(dados_gasto).execute()
                st.success("✅ Operação registrada com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

    # GERENCIADOR
    st.markdown("---")
    st.subheader("📋 Gerenciar Lançamentos do Período")
    if supabase and not df_filtrado.empty:
        df_editor = df_filtrado[["id", "data", "descricao", "grupo_orcamentario", "subcategoria", "valor", "tipo"]].copy()
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
                st.success("🔄 Dados sincronizados perfeitamente!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar alterações: {e}")

# ==================== ABA 2: MEUS PORQUINHOS ====================
with aba_porquinhos:
    st.title("🐷 Meus Porquinhos")
    st.caption("Acompanhe o preenchimento das suas grandes metas de patrimônio armazenadas na nuvem.")
    st.markdown("---")
    
    if dicionario_metas_alvo:
        dados_metas_grafico = []
        
        for nome_meta, valor_alvo in dicionario_metas_alvo.items():
            guardado = dicionario_aportes_acumulados.get(nome_meta, 0.0)
            falta_guardar = max(valor_alvo - guardado, 0.0)
            
            dados_metas_grafico.append({
                "Meta": nome_meta,
                "Estado": "Guardado (R$)",
                "Valor": guardado
            })
            dados_metas_grafico.append({
                "Meta": nome_meta,
                "Estado": "Falta Pagar (R$)",
                "Valor": falta_guardar
            })
            
            st.subheader(f"{nome_meta}")
            c1, c2, c3 = st.columns(3)
            c1.metric(label="Valor Alvo Final", value=f"R$ {valor_alvo:,.2f}")
            c2.metric(label="Total Já Guardado", value=f"R$ {guardado:,.2f}", delta="+Patrimônio")
            c3.metric(label="Quanto Falta Alocar", value=f"R$ {falta_guardar:,.2f}")
            
            st.progress(min(guardado / valor_alvo, 1.0) if valor_alvo > 0 else 0.0)
            st.markdown(f"**Preenchimento:** {(guardado / valor_alvo) * 100:.1f}%")
            st.markdown("---")
            
        st.subheader("📈 Dashboard Comparativo de Objetivos")
        df_porquinhos_fig = pd.DataFrame(dados_metas_grafico)
        
        fig_porquinhos = px.bar(
            df_porquinhos_fig, 
            x="Meta", 
            y="Valor", 
            color="Estado", 
            title="Raio-X de Evolução Patrimonial Combinada",
            color_discrete_map={"Guardado (R$)": "#00FF66", "Falta Pagar (R$)": "#444444"}
        )
        st.plotly_chart(fig_porquinhos, use_container_width=True)
    else:
        st.info("💡 Você ainda não criou nenhum porquinho na nuvem.")
