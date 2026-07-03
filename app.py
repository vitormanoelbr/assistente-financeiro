import streamlit as st
import datetime

st.set_page_config(page_title="Gestor Antifrágil", layout="centered")

# Cabeçalho focado em comportamento e no método
st.title("💸 Novo Lançamento")
st.subheader("Mentalidade Financeira & Fluxo de Caixa")
st.markdown("---")

# Criando o formulário que agrupa os inputs para não atualizar a página a cada clique
with st.form("fluxo_diario", clear_on_submit=False):
    
    # 1. Entrada de Valor Puro
    valor = st.number_input(
        "Qual o valor da operação? (R$)", 
        min_value=0.0, 
        step=5.0, 
        format="%.2f",
        help="Insira o valor absoluto. O sistema gerenciará se é crédito ou débito."
    )
    
    # 2. Natureza do Fluxo
    tipo = st.radio(
        "Natureza da movimentação:", 
        ["Saída (Gasto/Investimento)", "Entrada (Faturamento/Receita)"], 
        horizontal=True
    )
    
    # 3. Data (Padrão hoje, mas permite retroagir se você esqueceu de lançar ontem)
    data_movimento = st.date_input("Data do evento:", datetime.date.today())
    
    # 4. Descrição Livre (Gatilho para o futuro motor de busca do Supabase)
    descricao = st.text_input(
        "Descrição ou Estabelecimento:", 
        placeholder="Ex: Supermercado Big Master, Posto L3, Pix João..."
    )
    
    st.markdown("### 💡 Vetores da Metodologia")
    
    # 5. Grupos Baseados na Flexibilidade (Abordagem Cerbasi/Taleb)
    grupo_orcamentario = st.selectbox(
        "Grupo Estratégico:",
        [
            "🔴 50% Essencial (Custos Fixos Pesados/Sobrevivência)", 
            "🟡 30% Estilo de Vida (Custos Voláteis/Flexíveis)", 
            "💼 Custos de Negócio (Clínica/Projetos)",
            "🚀 Aporte para a Liberdade (Pague-se Primeiro / Antifrágil)",
            "🔄 Movimentação Interna (Apenas Transferência entre Contas)"
        ]
    )
    
    # 6. Categorias para granularidade dos gráficos
    categoria = st.selectbox(
        "Subcategoria:",
        [
            "Alimentação & Mercado", 
            "Transporte & Combustível", 
            "Saúde & Farmácia", 
            "Moradia & Utilidades",
            "Lazer, Viagens & Delivery",
            "Ferramentas SaaS & Marketing",
            "Educação & Livros",
            "Outros / Não Mapeado"
        ]
    )
    
    st.markdown("---")
    # 7. O Filtro Psicológico (Fator Morgan Housel)
    st.markdown("**🧠 Análise de Intencionalidade (Psicologia Financeira)**")
    satisfacao = st.select_slider(
        "Qual o nível de necessidade real ou retorno de felicidade deste gasto?",
        options=["1 - Impulsivo / Desnecessário", "2 - Útil / Moderado", "3 - Essencial / Alto Retorno"],
        value="2 - Útil / Moderado"
    )
    
    # Botão de envio do formulário
    botao_enviar = st.form_submit_button("Registrar Movimentação Real")

# Espaço temporário para simular o sucesso do clique no protótipo
if botao_enviar:
    st.success(f"Prototipagem Funcional! Dados capturados: R$ {valor:.2f} | {descricao} | {grupo_orcamentario.split(' ')[1]}")
    st.balloons()
