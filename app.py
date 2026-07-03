import streamlit as st
import datetime
import pandas as pd
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

# --- CONFIGURAÇÃO FIXA REQUISITADA ---
RENDA_FIXA = 2500.00
LIMITE_ESSENCIAL = RENDA_FIXA * 0.50       # R$ 1250
LIMITE_ESTILO_DE_VIDA = RENDA_FIXA * 0.30  # R$ 750
META_APORTE = RENDA_FIXA * 0.20           # R$ 500

# Meta de simulação de Dívida Total (para análise visual de quitação)
DIVIDA_TOTAL_INICIAL = 5000.00 

# Inicialização de somadores
gastos_essencial = 0.0
gastos_estilo = 0.0
gastos_aporte = 0.0
total_pago_divida = 0.0

if supabase:
    try:
        dados_banco = supabase.table("movimentacoes").select("valor, grupo_orcamentario").execute()
        if dados_banco.data:
            for item in dados_banco.data:
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

# Restante da dívida a ser paga
divida_restante = max(DIVIDA_TOTAL_INICIAL - total_pago_divida, 0.0)

# --- INTERFACE CORRIGIDA ---
st.title("📲 Meu Planner Financeiro")
st.markdown(f"**Orçamento Mensal Base:** R$ {RENDA_FIXA:,.2f}")
st.markdown("---")

# PAINEL DE LIMITES E REALIDADE FINANCEIRA
st.subheader("📊 Painel de Limites Orçamentários")

# 1. Termômetro de Dívidas (Nova Seção Estratégica)
st.markdown("### 🧮 Situação de Dívidas Atuais")
col1, col2 = st.columns(2)
col1.metric(label="Dívida Restante", value=f"R$ {divida_restante:,.2f}")
col2.metric(label="Total Amortizado/Pago", value=f"R$ {total_pago_divida:,.2f}")

perc_divida_paga = min(total_pago_divida / DIVIDA_TOTAL_INICIAL, 1.0) if DIVIDA_TOTAL_INICIAL > 0 else 1.0
st.progress(perc_divida_paga)
st.caption(f"Você já liquidou **{perc_divida_paga * 100:.1f}%** do volume total das suas dívidas estruturadas.")

st.markdown("---")
st.markdown("### 🧭 Distribuição do Mês")

# 2. Limite Essencial
perc_essencial = min(gastos_essencial / LIMITE_ESSENCIAL, 1.0) if LIMITE_ESSENCIAL > 0 else 0.0
st.write(f"🔴 **Gasto Essencial Atual:** R$ {gastos_essencial:,.2f} de R$ {LIMITE_ESSENCIAL:,.2f}")
st.progress(perc_essencial)
if gastos_essencial > LIMITE_ESSENCIAL:
    st.warning("⚠️ **Análise de Realidade:** O custo essencial estourou os 50%. Isso sinaliza que sua estrutura fixa está pesada para a renda atual.")

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

st.markdown("---")

# FORMULÁRIO ADAPTADO
st.subheader("📥 Registrar Movimentação")
with st.form("formulario_fluxo", clear_on_submit=True):
    valor = st.number_input("Qual o valor da operação? (R$)", min_value=0.0, step=5.0, format="%.2f")
    tipo = st.radio("Direção do dinheiro:", ["Gasto ou Investimento (Saída)", "Faturamento ou Receita (Entrada)"], horizontal=True)
    data_movimento = st.date_input("Data do evento:", datetime.date.today())
    descricao = st.text_input("Descrição ou Estabelecimento:", placeholder="Ex: Parcela do Empréstimo, Mercado, Luz...")
    
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
        opcoes_subcategoria = ["Habitação", "Alimentação Básica", "Saúde", "Transporte", "Pensão / Obrigações"]
    elif "30% Estilo de Vida" in grupo_orcamentario:
        opcoes_subcategoria = ["Lazer, Bares & Restaurantes", "Delivery / iFood", "Vestuário & Compras", "Cuidados Pessoais"]
    elif "20% Aporte" in grupo_orcamentario:
        opcoes_subcategoria = ["Reserva de Autonomia", "Aportes Renda Fixa/Variável"]
    elif "Quitação de Dívidas" in grupo_orcamentario:
        opcoes_subcategoria = ["Empréstimos Bancários", "Cartão de Crédito Atrasado", "Financiamentos", "Outros Acordos"]
    else:
        opcoes_subcategoria = ["Ferramentas & Softwares", "Marketing", "Custos Operacionais"]
        
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

# HISTÓRICO RECENTE
st.markdown("---")
st.subheader("📋 Últimos Lançamentos Registrados")
if supabase:
    try:
        resposta = supabase.table("movimentacoes").select("data, descricao, grupo_orcamentario, valor").order("id", desc=True).limit(5).execute()
        if respuesta.data:
            df_historico = pd.DataFrame(resposta.data)
            df_historico.columns = ["Data", "Descrição", "Grupo", "Valor (R$)"]
            st.dataframe(df_historico, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum registro encontrado.")
    except Exception as e:
        st.caption(f"Sincronizando...")
