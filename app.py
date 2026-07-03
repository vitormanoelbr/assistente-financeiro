import streamlit as st
import datetime
import pandas as pd
from supabase import create_client, Client

st.set_page_config(page_title="Gestor Antifrágil", layout="centered")

# Credenciais integradas diretamente para rodar instantaneamente
SUPABASE_URL = "https://knqqtoqxrrriefaueiem.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtucXF0b3F4cnJyaWVmYXVlaWVtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzA3NDIwMTgsImV4cCI6MjA4NjMxODAxOH0.u0qscE2D4y43nE5tq5-Qo9hM-YyvLpU68_2GfT16C-Y"

@st.cache_resource
def inicializar_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase: Client = inicializar_supabase()
except Exception as e:
    st.error(f"Erro ao conectar ao banco de dados: {e}")

# Cabeçalho do App
st.title("💸 Novo Lançamento")
st.subheader("Finanças Pessoais & Orçamento Inteligente")
st.markdown("---")

with st.form("fluxo_diario", clear_on_submit=True):
    
    valor = st.number_input("Qual o valor da operação? (R$)", min_value=0.0, step=5.0, format="%.2f")
    tipo = st.radio("Direção do dinheiro:", ["Gasto ou Investimento (Saída)", "Faturamento ou Receita (Entrada)"], horizontal=True)
    data_movimento = st.date_input("Data do evento:", datetime.date.today())
    descricao = st.text_input("Descrição ou Estabelecimento:", placeholder="Ex: Pensão, Supermercado Big Master, Posto L3...")
    
    st.markdown("### 🗺️ Alocação no Método 50/30/20")
    
    # CORRIGIDO: Nome da variável padronizado em todo o arquivo
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
            "Transporte, Combustível & Logística",
            "Impostos & Taxas Obrigatórias"
        ]
    elif "30% Estilo de Vida" in grupo_orcamentario:
        opcoes_subcategoria = [
            "Lazer, Bares & Restaurantes",
            "Delivery (iFood / Alimentação Conforto)",
            "Vestuário, Compras & Presentes",
            "Estética, Cuidados Pessoais & Academia",
            "Assinaturas & Entretenimento (Netflix/Spotify)",
            "Viagens & Hobbies"
        ]
    elif "20% Aporte para a Liberdade" in grupo_orcamentario:
        opcoes_subcategoria = [
            "Fundo de Autonomia (Reserva de Emergência)",
            "Aportes em Ações / Fundos / Renda Fixa",
            "Previdência & Seguros de Proteção"
        ]
    else:
        opcoes_subcategoria = [
            "Ferramentas SaaS & Softwares",
            "Marketing & Anúncios",
            "Infraestrutura & Custos Operacionais",
            "Impostos da Empresa"
        ]
        
    categoria = st.selectbox("Subcategoria Correspondente:", opcoes_subcategoria)
    
    st.markdown("---")
    st.markdown("**🧠 Análise de Intencionalidade (Psicologia Financeira)**")
    satisfacao = st.select_slider(
        "Qual o retorno de bem-estar ou necessidade real deste gasto?",
        options=["1 - Baixo retorno / Impulsivo", "2 - Moderado / Útil", "3 - Alto retorno / Indispensável"],
        value="2 - Moderado / Útil"
    )
    
    botao_enviar = st.form_submit_button("Registrar Movimentação Real")

# Envio para o Supabase
if botao_enviar:
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
            st.error(f"Erro ao salvar no banco: {e}")
    else:
        st.warning("Por favor, insira um valor e uma descrição válida.")

# CONSULTA EM TEMPO REAL: Mostra os dados inseridos logo abaixo do formulário
st.markdown("---")
st.subheader("📋 Últimos Lançamentos Registrados")
try:
    resposta = supabase.table("movimentacoes").select("data, descricao, grupo_orcamentario, valor").order("id", descending=True).limit(5).execute()
    if resposta.data:
        df_historico = pd.DataFrame(resposta.data)
        df_historico.columns = ["Data", "Descrição/Estabelecimento", "Grupo", "Valor (R$)"]
        st.dataframe(df_historico, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum registro encontrado no banco de dados ainda. Faça o seu primeiro lançamento acima!")
except Exception as e:
    st.caption(f"Aguardando dados... ({e})")
