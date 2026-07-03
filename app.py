import streamlit as st
import datetime
import pandas as pd
from supabase import create_client, Client

st.set_page_config(page_title="Gestor Antifrágil", layout="centered")

# Credenciais REAIS do seu banco
SUPABASE_URL = "https://knqqtoqxrrriefaueiem.supabase.co"
SUPABASE_KEY = "sb_publishable_BBxr66whvy4OFWdQxLs1Vw_KnMC_wmq"

@st.cache_resource
def conectar_banco():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase: Client = conectar_banco()
except Exception as e:
    st.error(f"Falha na conexão estrutural: {e}")

# --- INTELIGÊNCIA DE LIMITES (SIMULAÇÃO BASEADA NA SUA IDÉIA) ---
RENDA_SIMULADA = 2500.00
LIMITE_ESSENCIAL = RENDA_SIMULADA * 0.50  # R$ 1250
LIMITE_ESTILO_DE_VIDA = RENDA_SIMULADA * 0.30  # R$ 750
META_APORTE = RENDA_SIMULADA * 0.20  # R$ 500

# Buscar gastos reais do banco para calcular o Dashboard dinâmico
gastos_essencial = 0.0
gastos_estilo = 0.0
gastos_aporte = 0.0

if supabase:
    try:
        # Puxa todas as movimentações para somar os limites na tela
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
    except Exception as e:
        pass

# --- INTERFACE DO USUÁRIO ---
st.title("💸 Gestor Antifrágil 50/30/20")
st.markdown(f"**Orçamento Mensal Base:** R$ {RENDA_SIMULADA:,.2f}")
st.markdown("---")

# DASHBOARD DE METAS E LIMITES (Aparece no topo para decisão rápida)
st.subheader("📊 Painel de Limites Orçamentários")

# 1. Limite Essencial (50%)
perc_essencial = min(gastos_essencial / LIMITE_ESSENCIAL, 1.0) if LIMITE_ESSENCIAL > 0 else 0.0
st.write(f"🔴 **50% Essencial:** Gastou R$ {gastos_essencial:,.2f} de R$ {LIMITE_ESSENCIAL:,.2f}")
st.progress(perc_essencial)
if gastos_essencial > LIMITE_ESSENCIAL:
    st.error("⚠️ Alerta: Você ultrapassou o seu limite Essencial!")

# 2. Limite Estilo de Vida / Lazer (30%)
perc_estilo = min(gastos_estilo / LIMITE_ESTILO_DE_VIDA, 1.0) if LIMITE_ESTILO_DE_VIDA > 0 else 0.0
st.write(f"🟡 **30% Estilo de Vida (Lazer/Consumo):** Gastou R$ {gastos_estilo:,.2f} de R$ {LIMITE_ESTILO_DE_VIDA:,.2f}")
st.progress(perc_estilo)
if gastos_estilo > LIMITE_ESTILO_DE_VIDA:
    st.error("🚨 Atenção: Limite de Lazer/Estilo de Vida estourado! Segure os gastos operacionais.")
elif gastos_estilo == 0:
    st.info("✅ Você ainda não utilizou nada do seu limite de Estilo de Vida/Lazer.")

# 3. Meta de Aportes (20%)
perc_aporte = min(gastos_aporte / META_APORTE, 1.0) if META_APORTE > 0 else 0.0
st.write(f"🚀 **20% Meta de Aporte (Liberdade):** Guardou R$ {gastos_aporte:,.2f} de R$ {META_APORTE:,.2f}")
st.progress(perc_aporte)

st.markdown("---")

# FORMULÁRIO DE LANÇAMENTO
st.subheader("📥 Novo Lançamento Diário")
with st.form("formulario_fluxo", clear_on_submit=True):
    valor = st.number_input("Qual o valor da operação? (R$)", min_value=0.0, step=5.0, format="%.2f")
    tipo = st.radio("Direção do dinheiro:", ["Gasto ou Investimento (Saída)", "Faturamento ou Receita (Entrada)"], horizontal=True)
    data_movimento = st.date_input("Data do evento:", datetime.date.today())
    descricao = st.text_input("Descrição ou Estabelecimento:", placeholder="Ex: Mercado, Lazer Final de Semana, Academia...")
    
    grupo_orcamentario = st.selectbox(
        "Selecione o Grupo Estratégico:",
        [
            "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)", 
            "🟡 30% Estilo de Vida (Lazer e Custos Voláteis)", 
            "🚀 20% Aporte para a Liberdade (Investimentos e Futuro)",
            "💼 Custos de Negócio (Projetos e Clínica)"
        ]
    )
    
    if "50% Essencial" in grupo_orcamentario:
        opcoes_subcategoria = ["Habitação", "Alimentação Básica", "Saúde", "Transporte", "Pensão / Obrigações"]
    elif "30% Estilo de Vida" in grupo_orcamentario:
        opcoes_subcategoria = ["Lazer, Bares & Restaurantes", "Delivery / iFood", "Vestuário & Compras", "Cuidados Pessoais", "Viagens & Hobbies"]
    elif "20% Aporte" in grupo_orcamentario:
        opcoes_subcategoria = ["Reserva de Autonomia", "Aportes Renda Fixa/Variável", "Previdência"]
    else:
        opcoes_subcategoria = ["Ferramentas & Softwares", "Marketing", "Custos Operacionais"]
        
    categoria = st.selectbox("Subcategoria Correspondente:", opcoes_subcategoria)
    
    satisfacao = st.select_slider(
        "🧠 Retorno de bem-estar deste gasto?",
        options=["1 - Baixo retorno", "2 - Moderado", "3 - Alto retorno"],
        value="2 - Moderado"
    )
    
    botao_enviar = st.form_submit_button("Registrar Movimentação Real")

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
            st.success("✅ Gravado com sucesso! Atualizando painel...")
            st.rerun()  # Recarrega a página para atualizar o progresso das barras na hora
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")

# SEÇÃO DE HISTÓRICO
st.markdown("---")
st.subheader("📋 Últimos Lançamentos Registrados")
if supabase:
    try:
        resposta = supabase.table("movimentacoes").select("data, descricao, grupo_orcamentario, valor").order("id", desc=True).limit(5).execute()
        if resposta.data:
            df_historico = pd.DataFrame(resposta.data)
            df_historico.columns = ["Data", "Descrição", "Grupo", "Valor (R$)"]
            st.dataframe(df_historico, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum registro encontrado.")
    except Exception as e:
        st.caption(f"Aguardando dados...")
