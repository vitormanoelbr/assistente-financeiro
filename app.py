import streamlit as st
import datetime
import pandas as pd
from supabase import create_client, Client

st.set_page_config(page_title="Gestor Antifrágil", layout="centered")

# Credenciais REAIS extraídas dos seus links - 100% integradas
SUPABASE_URL = "https://knqqtoqxrrriefaueiem.supabase.co"
SUPABASE_KEY = "sb_publishable_BBxr66whvy4OFWdQxLs1Vw_KnMC_wmq"

@st.cache_resource
def conectar_banco():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase: Client = conectar_banco()
except Exception as e:
    st.error(f"Falha na conexão estrutural: {e}")

# Interface Principal
st.title("💸 Novo Lançamento")
st.subheader("Finanças Pessoais & Orçamento Inteligente")
st.markdown("---")

with st.form("formulario_fluxo", clear_on_submit=True):
    valor = st.number_input("Qual o valor da operação? (R$)", min_value=0.0, step=5.0, format="%.2f")
    tipo = st.radio("Direção do dinheiro:", ["Gasto ou Investimento (Saída)", "Faturamento ou Receita (Entrada)"], horizontal=True)
    data_movimento = st.date_input("Data do evento:", datetime.date.today())
    descricao = st.text_input("Descrição ou Estabelecimento:", placeholder="Ex: Pensão, Posto L3, Mercado...")
    
    st.markdown("### 🗺️ Alocação no Método 50/30/20")
    
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
        opcoes_subcategoria = [
            "Pensão Alimentícia / Obrigações Legais",
            "Habitação (Aluguel, Luz, Água, Gás)",
            "Alimentação Básica & Mercado",
            "Saúde, Plano Médico & Farmácia",
            "Transporte, Combustível & Logística"
        ]
    elif "30% Estilo de Vida" in grupo_orcamentario:
        opcoes_subcategoria = [
            "Lazer, Bares & Restaurantes",
            "Delivery (iFood / Alimentação Conforto)",
            "Vestuário, Compras & Presentes",
            "Estética, Cuidados Pessoais & Academia",
            "Assinaturas & Entretenimento",
            "Viagens & Hobbies"
        ]
    elif "20% Aporte para a Liberdade" in group_orcamentario:
        opcoes_subcategoria = [
            "Fundo de Autonomia (Reserva de Emergência)",
            "Aportes em Ações / Fundos / Renda Fixa",
            "Previdência & Seguros de Proteção"
        ]
    else:
        opcoes_subcategoria = [
            "Ferramentas SaaS & Softwares",
            "Marketing & Anúncios",
            "Infraestrutura & Custos Operacionais"
        ]
        
    categoria = st.selectbox("Subcategoria Correspondente:", opcoes_subcategoria)
    
    st.markdown("---")
    satisfacao = st.select_slider(
        "🧠 Retorno de bem-estar ou necessidade real deste gasto?",
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
            st.success("✅ Gravado com sucesso na nuvem do Supabase!")
            st.balloons()
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")
    else:
        st.warning("Insira um valor maior que zero e uma descrição válida.")

# Seção de histórico
st.markdown("---")
st.subheader("📋 Últimos Lançamentos")
if supabase:
    try:
        resposta = supabase.table("movimentacoes").select("data, descricao, grupo_orcamentario, valor").order("id", desc=True).limit(5).execute()
        if resposta.data:
            df_historico = pd.DataFrame(resposta.data)
            df_historico.columns = ["Data", "Descrição", "Grupo", "Valor (R$)"]
            st.dataframe(df_historico, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum registro encontrado. Faça o primeiro lançamento acima!")
    except Exception as e:
        st.caption(f"Aguardando sincronização de dados...")
