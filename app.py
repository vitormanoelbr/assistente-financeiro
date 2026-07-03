import streamlit as st
import datetime

st.set_page_config(page_title="Gestor Antifrágil", layout="centered")

# Cabeçalho refinado para soar menos genérico
st.title("💸 Novo Lançamento")
st.subheader("Finanças Pessoais & Orçamento Inteligente")
st.markdown("---")

with st.form("fluxo_diario", clear_on_submit=False):
    
    # 1. Operação direta
    valor = st.number_input("Qual o valor da operação? (R$)", min_value=0.0, step=5.0, format="%.2f")
    
    # Termos limpos e diretos para o usuário
    tipo = st.radio("Direção do dinheiro:", ["Gasto ou Investimento (Saída)", "Faturamento ou Receita (Entrada)"], horizontal=True)
    
    data_movimento = st.date_input("Data do evento:", datetime.date.today())
    
    descricao = st.text_input("Descrição ou Estabelecimento:", placeholder="Ex: Pensão, Supermercado Big Master, Posto L3...")
    
    st.markdown("### 🗺️ Alocação no Método 50/30/20")
    
    # O usuário escolhe o pilar do método primeiro
    grupo_orcamentario = st.selectbox(
        "Selecione o Grupo Estratégico:",
        [
            "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)", 
            "🟡 30% Estilo de Vida (Lazer e Custos Voláteis)", 
            "🚀 20% Aporte para a Liberdade (Investimentos e Futuro)",
            "💼 Custos de Negócio (Projetos e Clínica)"
        ]
    )
    
    # LÓGICA DE UX INTELIGENTE: Filtra as subcategorias com base no grupo selecionado acima
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
    
    botao_enviar = st.form_submit_button("Registrar Movimentação")

if botao_enviar:
    st.success(f"Capturado com sucesso! Categoria alocada: {categoria}")
    st.balloons()
