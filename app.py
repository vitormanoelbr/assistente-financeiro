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

# --- ⚙️ MENU LATERAL DE CONFIGURAÇÕES (PENSADO COMO PRODUTO) ---
st.sidebar.header("⚙️ Configurações do Perfil")
st.sidebar.caption("Defina seus parâmetros estruturais aqui. O sistema salvará as metas automaticamente.")

# Inputs dinâmicos na lateral que substituem os valores fixos do código antigo
RENDA_BASE = st.sidebar.number_input("Sua Renda Mensal Base (R$):", min_value=0.0, value=2500.00, step=100.0)
DIVIDA_TOTAL_INICIAL = st.sidebar.number_input("Valor Total da sua Dívida (R$):", min_value=0.0, value=0.0, step=100.0)

# Recalcula as metas de forma 100% dinâmica com base no input do usuário
LIMITE_ESSENCIAL = RENDA_BASE * 0.50       
LIMITE_ESTILO_DE_VIDA = RENDA_BASE * 0.30  
META_APORTE = RENDA_BASE * 0.20           

gastos_essencial = 0.0
gastos_estilo = 0.0
gastos_aporte = 0.0
total_pago_divida = 0.0
df_todos_dados = pd.DataFrame()

# --- BUSCA DE DADOS NA NUVEM ---
if supabase:
    try:
        resposta_completa = supabase.table("movimentacoes").select("id, data, descricao, grupo_orcamentario, subcategoria, valor, satisfacao").execute()
        if res_data := resposta_completa.data:
            df_todos_dados = pd.DataFrame(res_data)
            df_todos_dados["valor"] = df_todos_dados["valor"].astype(float)
            
            for item in res_data:
                val = float(item["valor"])
                grupo = item["grupo_orcamentario"]
                
                if "50% Essencial" in grupo:
                    gastos_essencial += val
                elif "30% Estilo de Vida" in grupo:
                    gastos_estilo += val
                elif "20% Aporte" in grupo:
                    gastos_aporte += val
                elif "📋 Quitação de Dívidas" in grupo:
                    total_pago_divida += val
    except Exception as e:
        pass

divida_restante = max(DIVIDA_TOTAL_INICIAL - total_pago_divida, 0.0)

# --- INTERFACE PRINCIPAL ---
st.title("📲 Meu Planner Financeiro")
st.markdown(f"**Orçamento Mensal Base Definido:** R$ {RENDA_BASE:,.2f}")
st.markdown("---")

st.subheader("📊 Painel de Limites Orçamentários")

# 1. Termômetro de Dívidas Dinâmico
st.markdown("### 🧮 Situação de Dívidas Atuais")
col1, col2 = st.columns(2)
col1.metric(label="Dívida Restante Atual", value=f"R$ {divida_restante:,.2f}")
col2.metric(label="Total Amortizado (Histórico)", value=f"R$ {total_pago_divida:,.2f}")

# Exibe o progresso de quitação se houver alguma dívida configurada
if DIVIDA_TOTAL_INICIAL > 0:
    perc_divida_paga = min(total_pago_divida / DIVIDA_TOTAL_INICIAL, 1.0)
    st.progress(perc_divida_paga)
    st.caption(f"Você já liquidou **{perc_divida_paga * 100:.1f}%** do volume total das suas dívidas estruturadas.")
else:
    st.info("🎉 Nenhuma dívida ativa configurada no seu perfil lateral.")

st.markdown("---")
st.markdown("### 🧭 Distribuição do Mês")

# 2. Limite Essencial
perc_essencial = min(gastos_essencial / LIMITE_ESSENCIAL, 1.0) if LIMITE_ESSENCIAL > 0 else 0.0
st.write(f"🔴 **Gasto Essencial Atual:** R$ {gastos_essencial:,.2f} de R$ {LIMITE_ESSENCIAL:,.2f}")
st.progress(perc_essencial)
if gastos_essencial > LIMITE_ESSENCIAL:
    st.warning("⚠️ **Análise de Realidade:** O custo essencial estourou os 50%. A estrutura fixa está pesada para a renda atual.")

# 3. Limite Estilo de Vida
perc_estilo = min(gastos_estilo / LIMITE_ESTILO_DE_VIDA, 1.0) if LIMITE_ESTILO_DE_VIDA > 0 else 0.0
st.write(f"🟡 **Estilo de Vida & Lazer:** Gastou R$ {gastos_estilo:,.2f} de R$ {LIMITE_ESTILO_DE_VIDA:,.2f}")
st.progress(perc_estilo)
if gastos_estilo == 0:
    st.info("✅ Margem de Estilo de Vida preservada (R$ 0,00 utilizados).")

# 4. Meta de Aportes
perc_aporte = min(gastos_aporte / META_APORTE, 1.0) if META_APORTE > 0 else 0.0
st.write(f"🚀 **Futuro & Liberdade (Aportes):** R$ {gastos_aporte:,.2f} de R$ {META_APORTE:,.2f}")
st.progress(perc_aporte)

# --- SEÇÃO DE GRÁFICOS ANALÍTICOS ---
if not df_todos_dados.empty:
    st.markdown("---")
    st.markdown("### 📈 Análise Visual do Dinheiro")
    
    df_agrupado = df_todos_dados.groupby("grupo_orcamentario")["valor"].sum().reset_index()
    fig_rosca = px.pie(
        df_agrupado, 
        values="valor", 
        names="grupo_orcamentario", 
        hole=0.4,
        title="Divisão Real dos Gastos Acumulados (R$)",
        color_discrete_sequence=["#FF4B4B", "#00F0FF", "#FFD700", "#00FF66", "#9932CC"]
    )
    fig_rosca.update_layout(showlegend=False)
    st.plotly_chart(fig_rosca, use_container_width=True)
    
    df_todos_dados["Nível Limpo"] = df_todos_dados["satisfacao"].astype(str).str[0]
    df_satisfacao = df_todos_dados.groupby("Nível Limpo")["valor"].sum().reset_index()
    df_satisfacao.columns = ["Nível de Necessidade", "Total Gasto (R$)"]
    
    mapa_nomes = {"1": "1 - Evitável / Impulsivo", "2": "2 - Útil / Desejável", "3": "3 - Indispensável"}
    df_satisfacao["Nível de Necessidade"] = df_satisfacao["Nível de Necessidade"].map(mapa_nomes)
    
    fig_barra = px.bar(
        df_satisfacao,
        x="Nível de Necessidade",
        y="Total Gasto (R$)",
        title="🧠 Raio-X de Intencionalidade (Onde estão os ralos de dinheiro?)",
        color="Nível de Necessidade",
        color_discrete_map={
            "1 - Evitável / Impulsivo": "#FF4B4B",
            "2 - Útil / Desejável": "#FFD700",
            "3 - Indispensável": "#00FF66"
        }
    )
    st.plotly_chart(fig_barra, use_container_width=True)

st.markdown("---")

# FORMULÁRIO DE ENTRADAS/SAÍDAS
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
    
    satisfacao = st.select_slider(
        "🧠 Nível de necessidade real deste evento?",
        options=["1 - Impulsivo / Evitável", "2 - Útil / Desejável", "3 - Indispensável"],
        value="2 - Útil / Desejável"
    )
    
    botao_enviar = st.form_submit_button("Salvar Lançamento")

if botao_enviar and supabase:
    if valor > 0 and descricao:
        try:
            dados_gasto = {
                "data": str(data_movimento),
                "valor": float(valor),
                "tipo": tipo,
                "descricao": descricao,
                "grupo_orcamentario": grupo_orcamentario,
                "subcategoria": categoria,
                "satisfacao": satisfacao
            }
            supabase.table("movimentacoes").insert(dados_gasto).execute()
            st.success("✅ Atualizado com sucesso!")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")

# --- GERENCIADOR INTERATIVO ---
st.markdown("---")
st.subheader("📋 Gerenciar Lançamentos Registrados")
st.caption("💡 Dica: Dê duplo clique em qualquer célula para alterar o valor ou texto. Para apagar uma linha, selecione-a e aperte Delete.")

if supabase and not df_todos_dados.empty:
    df_editor = df_todos_dados[["id", "data", "descricao", "grupo_orcamentario", "subcategoria", "valor"]].copy()
    df_editor.columns = ["ID", "Data", "Descrição", "Grupo", "Subcategoria", "Valor (R$)"]
    
    dados_editados = st.data_editor(
        df_editor, 
        use_container_width=True, 
        hide_index=True,
        disabled=["ID"], 
        num_rows="dynamic" 
    )
    
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
                    supabase.table("movimentacoes").update({
                        "descricao": row["Descrição"],
                        "valor": float(row["Valor (R$)"])
                    }).eq("id", row_id).execute()
                    
            st.success("🔄 Banco de dados sincronizado com sucesso!")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao sincronizar edições: {e}")
elif df_todos_dados.empty:
    st.info("Nenhum registro encontrado.")
