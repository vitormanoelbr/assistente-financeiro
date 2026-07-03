import streamlit as st
import datetime
import pandas as pd
import plotly.express as px
from supabase import create_client, Client

st.set_page_config(page_title="Meu Planner Financeiro", layout="centered")

# Credenciais do banco
SUPABASE_URL = "https://knqqtoqxrrriefaueiem.supabase.co"
SUPABASE_KEY = "sb_publishable_BBxr66whvy4OFWdQxLs1Vw_KnMC_wmq"

@st.cache_resource
def conectar_banco():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase: Client = conectar_banco()
except Exception as e:
    st.error(f"Falha na conexão estrutural: {e}")

# --- ⚙️ MENU LATERAL DE CONFIGURAÇÕES E FILTROS ---
st.sidebar.header("⚙️ Configurações do Perfil")
RENDA_BASE = st.sidebar.number_input("Sua Renda Mensal Base (R$):", min_value=0.0, value=2500.00, step=100.0)
DIVIDA_TOTAL_INICIAL = st.sidebar.number_input("Valor Total da sua Dívida (R$):", min_value=0.0, value=0.0, step=100.0)

st.sidebar.markdown("---")
st.sidebar.header("📅 Filtros de Tempo")

# Configuração de datas padrão para abertura do app
hoje = datetime.date.today()
ano_atual = hoje.year
mes_atual = hoje.month

# Seleção de Ano e Mês (O app abre automaticamente no mês corrente)
lista_anos = [ano_atual, ano_atual - 1, ano_atual + 1]
ano_selecionado = st.sidebar.selectbox("Ano de Análise:", lista_anos, index=0)

lista_meses = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}
mes_selecionado_num = st.sidebar.selectbox(
    "Mês de Análise:", 
    list(lista_meses.keys()), 
    format_func=lambda x: lista_meses[x],
    index=list(lista_meses.keys()).index(mes_atual)
)

# Filtro rápido de granularidade
janela_tempo = st.sidebar.radio("Visualizar intervalo:", ["Mês Completo", "Últimos 7 Dias", "Somente Hoje"])

# --- PROCESSAMENTO E CÁLCULO DE METAS ---
LIMITE_ESSENCIAL = RENDA_BASE * 0.50       
LIMITE_ESTILO_DE_VIDA = RENDA_BASE * 0.30  
META_APORTE = RENDA_BASE * 0.20           

gastos_essencial = 0.0
gastos_estilo = 0.0
gastos_aporte = 0.0
total_pago_divida = 0.0
df_todos_dados = pd.DataFrame()
df_filtrado = pd.DataFrame()

if supabase:
    try:
        resposta_completa = supabase.table("movimentacoes").select("id, data, descricao, grupo_orcamentario, subcategoria, valor, satisfacao").execute()
        if res_data := resposta_completa.data:
            df_todos_dados = pd.DataFrame(res_data)
            df_todos_dados["valor"] = df_todos_dados["valor"].astype(float)
            df_todos_dados["data_dt"] = pd.to_datetime(df_todos_dados["data"]).dt.date
            
            # 1. O Termômetro de Dívidas acumula o histórico TOTAL (independente do mês)
            for item in res_data:
                if "📋 Quitação de Dívidas" in item["grupo_orcamentario"]:
                    total_pago_divida += float(item["valor"])
            
            # 2. Aplicação dos filtros temporais selecionados na lateral para o restante do painel
            df_filtrado = df_todos_dados.copy()
            df_filtrado["ano"] = pd.to_datetime(df_filtrado["data_dt"]).dt.year
            df_filtrado["mes"] = pd.to_datetime(df_filtrado["data_dt"]).dt.month
            
            # Filtra por Ano e Mês selecionados
            df_filtrado = df_filtrado[(df_filtrado["ano"] == ano_selecionado) & (df_filtrado["mes"] == mes_selecionado_num)]
            
            # Filtros de granularidade fina (Dias / Semana)
            if janela_tempo == "Últimos 7 Dias":
                setem_dias_atras = hoje - datetime.timedelta(days=7)
                df_filtrado = df_filtrado[df_filtrado["data_dt"] >= setem_dias_atras]
            elif janela_tempo == "Somente Hoje":
                df_filtrado = df_filtrado[df_filtrado["data_dt"] == hoje]
                
            # 3. Somadores do mês filtrado para alimentar as barras de progresso
            for _, row in df_filtrado.iterrows():
                val = float(row["valor"])
                grupo = row["grupo_orcamentario"]
                if "50% Essencial" in grupo:
                    gastos_essencial += val
                elif "30% Estilo de Vida" in grupo:
                    gastos_estilo += val
                elif "20% Aporte" in grupo:  # CORRIGIDO: Variável 'grupo' mapeada perfeitamente
                    gastos_aporte += val
                    
    except Exception as e:
        st.error(f"Erro no processamento dos filtros: {e}")

divida_restante = max(DIVIDA_TOTAL_INICIAL - total_pago_divida, 0.0)

# --- CRIAÇÃO DAS ABAS PRINCIPAIS (VISÃO DE PRODUTO) ---
aba_painel, aba_investimentos = st.tabs(["📊 Painel & Lançamentos", "🚀 Investimentos (Experimental)"])

# ==================== ABA 1: PAINEL FINANCEIRO ====================
with aba_painel:
    st.title("📲 Meu Planner Financeiro")
    st.markdown(f"**Competência Atual:** {lista_meses[mes_selecionado_num]} / {ano_selecionado} ({janela_tempo})")
    st.markdown("---")
    
    st.subheader("📊 Painel de Limites Orçamentários")
    st.markdown("### 🧮 Situação de Dívidas Atuais (Volume Total)")
    col1, col2 = st.columns(2)
    col1.metric(label="Dívida Restante Atual", value=f"R$ {divida_restante:,.2f}")
    col2.metric(label="Total Amortizado (Histórico)", value=f"R$ {total_pago_divida:,.2f}")
    
    if DIVIDA_TOTAL_INICIAL > 0:
        perc_divida_paga = min(total_pago_divida / DIVIDA_TOTAL_INICIAL, 1.0)
        st.progress(perc_divida_paga)
        st.caption(f"Você já liquidou **{perc_divida_paga * 100:.1f}%** do volume total das suas dívidas estruturadas.")
    else:
        st.info("🎉 Nenhuma dívida ativa configurada no seu perfil lateral.")
        
    st.markdown("---")
    st.markdown("### 🧭 Distribuição Líquida do Período")
    
    perc_essencial = min(gastos_essencial / LIMITE_ESSENCIAL, 1.0) if LIMITE_ESSENCIAL > 0 else 0.0
    st.write(f"🔴 **Gasto Essencial Atual:** R$ {gastos_essencial:,.2f} de R$ {LIMITE_ESSENCIAL:,.2f}")
    st.progress(perc_essencial)
    
    perc_estilo = min(gastos_estilo / LIMITE_ESTILO_DE_VIDA, 1.0) if LIMITE_ESTILO_DE_VIDA > 0 else 0.0
    st.write(f"🟡 **Estilo de Vida & Lazer:** Gastou R$ {gastos_estilo:,.2f} de R$ {LIMITE_ESTILO_DE_VIDA:,.2f}")
    st.progress(perc_estilo)
    
    perc_aporte = min(gastos_aporte / META_APORTE, 1.0) if META_APORTE > 0 else 0.0
    st.write(f"🚀 **Futuro & Liberdade (Aportes):** R$ {gastos_aporte:,.2f} de R$ {META_APORTE:,.2f}")
    st.progress(perc_aporte)
    
    # Seção de Gráficos alimentada estritamente pelo filtro de tempo
    if not df_filtrado.empty:
        st.markdown("---")
        st.markdown("### 📈 Análise Visual do Dinheiro")
        
        df_agrupado = df_filtrado.groupby("grupo_orcamentario")["valor"].sum().reset_index()
        fig_rosca = px.pie(
            df_agrupado, values="valor", names="grupo_orcamentario", hole=0.4,
            title="Onde seu dinheiro foi no período filtrado",
            color_discrete_sequence=["#FF4B4B", "#00F0FF", "#FFD700", "#00FF66", "#9932CC"]
        )
        fig_rosca.update_layout(showlegend=False)
        st.plotly_chart(fig_rosca, use_container_width=True)
        
        df_filtrado["Nível Limpo"] = df_filtrado["satisfacao"].astype(str).str[0]
        df_satisfacao = df_filtrado.groupby("Nível Limpo")["valor"].sum().reset_index()
        df_satisfacao.columns = ["Nível de Necessidade", "Total Gasto (R$)"]
        mapa_nomes = {"1": "1 - Evitável / Impulsivo", "2": "2 - Útil / Desejável", "3": "3 - Indispensável"}
        df_satisfacao["Nível de Necessidade"] = df_satisfacao["Nível de Necessidade"].map(mapa_nomes)
        
        fig_barra = px.bar(
            df_satisfacao, x="Nível de Necessidade", y="Total Gasto (R$)",
            title="🧠 Volume Financeiro por Intencionalidade",
            color="Nível de Necessidade",
            color_discrete_map={"1 - Evitável / Impulsivo": "#FF4B4B", "2 - Útil / Desejável": "#FFD700", "3 - Indispensável": "#00FF66"}
        )
        st.plotly_chart(fig_barra, use_container_width=True)
        
    st.markdown("---")
    st.subheader("📥 Registrar Movimentação")
    with st.form("formulario_fluxo", clear_on_submit=True):
        valor = st.number_input("Qual o valor da operação? (R$)", min_value=0.0, step=5.0, format="%.2f")
        tipo = st.radio("Direção do dinheiro:", ["Gasto ou Investimento (Saída)", "Faturamento ou Receita (Entrada)"], horizontal=True)
        data_movimento = st.date_input("Data do evento:", datetime.date.today())
        descricao = st.text_input("Descrição ou Estabelecimento:", placeholder="Ex: Mercado, Luz, Parcela do Empréstimo...")
        
        grupo_orcamentario = st.selectbox(
            "Destinação Estratégica do Valor:",
            [
                "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)", 
                "🟡 30% Estilo de Vida (Lazer e Custos Voláteis)", 
                "🚀 20% Aporte para a Liberdade (Investimentos e Futuro)",
                "📋 Quitação de Dívidas (Amortizações e Acordos)",
                "💼 Custos de Negócio (Projetos e Clínica)"
            ]
        )
        
        if "50% Essencial" in grupo_orcamentario:
            opcoes_subcategoria = ["Alimentação Básica & Mercado", "Contas Fixas (Luz, Água, Internet)", "Habitação (Aluguel / Financiamento)", "Saúde & Medicamentos", "Transporte & Combustível", "Pensão / Obrigações Legais"]
        elif "30% Estilo de Vida" in grupo_orcamentario:
            opcoes_subcategoria = ["Lazer, Bares & Restaurantes", "Delivery / iFood / Conforto", "Vestuário, Compras & Presentes", "Estética, Cuidados & Academia", "Viagens & Hobbies", "Assinaturas (Netflix, Spotify)"]
        elif "20% Aporte" in grupo_orcamentario:
            opcoes_subcategoria = ["Reserva de Autonomia (Emergência)", "Aportes Renda Fixa", "Aportes Renda Variável"]
        elif "Quitação de Dívidas" in grupo_orcamentario:
            opcoes_subcategoria = ["Empréstimos Bancários", "Cartão de Crédito Atrasado", "Financiamentos de Bens"]
        else:
            opcoes_subcategoria = ["Ferramentas SaaS & Softwares", "Marketing & Anúncios", "Infraestrutura & Custos Operacionais"]
            
        categoria = st.selectbox("Subcategoria Correspondente:", opcoes_subcategoria)
        satisfacao = st.select_slider("🧠 Nível de necessidade real?", options=["1 - Impulsivo / Evitável", "2 - Útil / Desejável", "3 - Indispensável"], value="2 - Útil / Desejável")
        botao_enviar = st.form_submit_button("Salvar Lançamento")
        
    if botao_enviar and supabase:
        if valor > 0 and descricao:
            try:
                dados_gasto = {"data": str(data_movimento), "valor": float(valor), "tipo": tipo, "descricao": descricao, "grupo_orcamentario": grupo_orcamentario, "subcategoria": categoria, "satisfacao": satisfacao}
                supabase.table("movimentacoes").insert(dados_gasto).execute()
                st.success("✅ Lançamento gravado!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

    st.markdown("---")
    st.subheader("📋 Gerenciar Lançamentos do Período Filtrado")
    if supabase and not df_filtrado.empty:
        df_editor = df_filtrado[["id", "data", "descricao", "grupo_orcamentario", "subcategoria", "valor"]].copy()
        df_editor.columns = ["ID", "Data", "Descrição", "Grupo", "Subcategoria", "Valor (R$)"]
        
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
                    if (row["Descrição"] != orig_row["Descrição"]) or (float(row["Valor (R$)"]) != float(orig_row["Valor (R$)"])):
                        supabase.table("movimentacoes").update({"descricao": row["Descrição"], "valor": float(row["Valor (R$)"])}).eq("id", row_id).execute()
                st.success("🔄 Alterações guardadas!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar alterações: {e}")
    elif df_filtrado.empty:
        st.info("Nenhum registro para exibir neste filtro de tempo.")

# ==================== ABA 2: ÁREA DE INVESTIMENTOS ====================
with aba_investimentos:
    st.header("📈 Centro de Acumulação de Patrimônio")
    st.caption("Esta área receberá a inteligência de rentabilidade real e evolução patrimonial histórica na Fase 2.")
    
    st.subheader("🚀 Resumo do Mês Corrente")
    st.metric(label="Total Alocado para o Futuro no Período", value=f"R$ {gastos_aporte:,.2f}", delta=f"Meta: R$ {META_APORTE:,.2f}")
    
    # Estrutura visual vazia preparando a próxima sprint de código
    st.info("💡 Na próxima etapa, aqui você visualizará gráficos de evolução patrimonial por ativos (Renda Fixa vs Renda Variável) e o cálculo de juros sobre sua reserva.")
