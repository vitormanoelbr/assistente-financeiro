import streamlit as st
import pandas as pd
import plotly.express as px
import re

st.set_page_config(page_title="Assistente Financeiro Vitor Manoel", layout="wide")

st.title("📊 Assistente Financeiro Vitor Manoel")
st.subheader("Inteligência Orçamentária e Gestão de Fluxo de Caixa")
st.markdown("---")

REGRAS_ORCAMENTO = {
    'ATACADAO': ('Mercado', '50% Essencial'),
    'BIG MASTE': ('Mercado', '50% Essencial'),
    'AMERICANAS': ('Mercado', '50% Essencial'),
    'VIDA  SAUDE': ('Saúde', '50% Essencial'),
    'DENISE KATER': ('Farmácia', '50% Essencial'),
    'C. P. DA SILVA': ('Gás de Cozinha', '50% Essencial'),
    'SEGUNDO OFICIO': ('Taxas/Cartório', '50% Essencial'),
    'VIVO MT': ('Telecom', '50% Essencial'),
    'CLARO': ('Telecom', '50% Essencial'),
    'Talia Rocha Ribeiro': ('Babá/Filho', '50% Essencial'),
    'Isabela Luisa Stangherlim': ('Pensão/Filho', '50% Essencial'),
    'AUTO POSTO L3': ('Transporte', '50% Essencial'),
    'RECEITA FEDERAL': ('Impostos', '50% Essencial'),
    'IFOODCOM': ('Alimentação/Delivery', '30% Estilo de Vida'),
    'Netshoes': ('Presente Namorada', '30% Estilo de Vida'),
    'ROTARY CLUB': ('Doações/Social', '30% Estilo de Vida'),
    'IGREJA BATISTA': ('Contribuições/Religião', '30% Estilo de Vida'),
    'Google One': ('Assinaturas Tech', '30% Estilo de Vida'),
    'CDB PORQUINHO': ('Aplicação/Resgate', 'Movimentação Interna'),
    'CDB Porq': ('Aplicação/Resgate', 'Movimentação Interna'),
    'ChatGPT': ('Ferramentas SaaS', 'Custos de Negócio'),
    'HTM JMM': ('Plataformas Cursos', 'Custos de Negócio'),
    'ORIZONTE CONNECT': ('Apostas Online', 'Descontinuado'),
    'J E C V TECHNOLOGY': ('Apostas Online', 'Descontinuado')
}

def classificar_transacao(descricao):
    for termo, (categoria, grupo) in REGRAS_ORCAMENTO.items():
        if re.search(termo, descricao, re.IGNORECASE):
            return categoria, grupo
    return 'Outros', 'A Classificar por IA'

st.sidebar.header("📥 Alimentar o Assistente")
arquivo_carregado = st.sidebar.file_uploader("Arraste seu extrato aqui (.ofx ou .csv):", type=["ofx", "csv"])

dados_brutos = [
    {"Data": "2026-06-28", "Descricao": "Pix enviado: Igreja Batista da Vila", "Valor": -10.00, "Meio": "Conta Corrente"},
    {"Data": "2026-06-22", "Descricao": "Pix recebido: Flavielly Ayadiny Delgado", "Valor": 246.02, "Meio": "Conta Corrente"},
    {"Data": "2026-06-21", "Descricao": "Pix enviado: RECEITA FEDERAL", "Valor": -86.05, "Meio": "Conta Corrente"},
    {"Data": "2026-06-15", "Descricao": "Pagamento de Convenio: VIVO MT", "Valor": -64.00, "Meio": "Conta Corrente"},
    {"Data": "2026-06-13", "Descricao": "Pix enviado: CLARO", "Valor": -45.89, "Meio": "Conta Corrente"},
    {"Data": "2026-06-06", "Descricao": "Pix enviado: Talia Rocha Ribeiro", "Valor": -275.00, "Meio": "Conta Corrente"},
    {"Data": "2026-06-06", "Descricao": "Pix enviado: Isabela Luisa Stangherlim Cavalcante", "Valor": -607.16, "Meio": "Conta Corrente"},
    {"Data": "2026-06-05", "Descricao": "Pix enviado: AUTO POSTO L3", "Valor": -18.94, "Meio": "Conta Corrente"},
    {"Data": "2026-06-05", "Descricao": "Pix enviado: VIDA  SAUDE", "Valor": -22.00, "Meio": "Conta Corrente"},
    {"Data": "2026-05-30", "Descricao": "HTM JMM Company LTDA (Parcela 12/12)", "Valor": -29.90, "Meio": "Cartão de Crédito"},
    {"Data": "2026-05-03", "Descricao": "MLP Netshoes-NS2COM IN (Parcela 02/05)", "Valor": -69.99, "Meio": "Cartão de Crédito"},
    {"Data": "2026-05-16", "Descricao": "C. P. DA SILVA COMERC (Parcela 01/03)", "Valor": -45.00, "Meio": "Cartão de Crédito"},
    {"Data": "2026-05-17", "Descricao": "ROTARY CLUB TANGARA DA", "Valor": -80.00, "Meio": "Cartão de Crédito"},
    {"Data": "2026-05-17", "Descricao": "0001 DENISE KATER LTDA", "Valor": -20.70, "Meio": "Cartão de Crédito"},
    {"Data": "2026-05-26", "Descricao": "Google One", "Valor": -12.50, "Meio": "Cartão de Crédito"},
    {"Data": "2026-05-28", "Descricao": "IGREJA BATISTA DA VILA (Parcela 01/02)", "Valor": -75.00, "Meio": "Cartão de Crédito"},
    {"Data": "2026-05-28", "Descricao": "AMERICANAS SA", "Valor": -60.97, "Meio": "Cartão de Crédito"},
    {"Data": "2026-05-28", "Descricao": "SUPERMERCADO BIG MASTE", "Valor": -65.81, "Meio": "Cartão de Crédito"},
    {"Data": "2026-05-28", "Descricao": "ATACADAO 898 AS", "Valor": -260.48, "Meio": "Cartão de Crédito"},
    {"Data": "2026-05-31", "Descricao": "Google ChatGPT", "Valor": -95.99, "Meio": "Cartão de Crédito"},
    {"Data": "2026-06-07", "Descricao": "ATACADAO 898 AS", "Valor": -107.20, "Meio": "Cartão de Crédito"},
]

df = pd.DataFrame(dados_brutos)
df['Categoria'], df['Grupo_Orcamentario'] = zip(*df['Descricao'].apply(classificar_transacao))
df_despesas = df[(df['Valor'] < 0) & (~df['Grupo_Orcamentario'].isin(['Movimentação Interna', 'Descontinuado']))].copy()
df_despesas['Valor_Absoluto'] = df_despesas['Valor'].abs()

total_essencial = df_despesas[df_despesas['Grupo_Orcamentario'] == '50% Essencial']['Valor_Absoluto'].sum()
total_estilo = df_despesas[df_despesas['Grupo_Orcamentario'] == '30% Estilo de Vida']['Valor_Absoluto'].sum()
total_negocio = df_despesas[df_despesas['Grupo_Orcamentario'] == 'Custos de Negócio']['Valor_Absoluto'].sum()
total_geral = df_despesas['Valor_Absoluto'].sum()

col1, col2, col3, col4 = st.columns(4)
col1.metric(label="🔴 50% Essencial Total", value=f"R$ {total_essencial:,.2f}")
col2.metric(label="🟡 30% Estilo de Vida Total", value=f"R$ {total_estilo:,.2f}")
col3.metric(label="💼 Custos de Negócio", value=f"R$ {total_negocio:,.2f}")
col4.metric(label="💸 Total Desembolsado", value=f"R$ {total_geral:,.2f}")

st.markdown("---")
col_grafico, col_info = st.columns([3, 2])

with col_grafico:
    st.subheader("Distribuição pelo Planejamento Orçamentário")
    df_pizza = df_despesas.groupby('Grupo_Orcamentario')['Valor_Absoluto'].sum().reset_index()
    fig = px.pie(df_pizza, values='Valor_Absoluto', names='Grupo_Orcamentario', hole=0.4,
                 color_discrete_sequence=['#ff4b4b', '#ffaa00', '#00a86b'])
    st.plotly_chart(fig, use_container_width=True)

with col_info:
    st.subheader("Filtros do Painel")
    meio_selecionado = st.multiselect("Filtrar por Meio de Pagamento:", options=df_despesas['Meio'].unique(), default=df_despesas['Meio'].unique())

st.markdown("---")
st.subheader("📋 Extrato Consolidado e Categorizado")
df_filtrado = df_despesas[df_despesas['Meio'].isin(meio_selecionado)]
df_exibicao = df_filtrado[['Data', 'Descricao', 'Meio', 'Categoria', 'Grupo_Orcamentario', 'Valor_Absoluto']].copy()
df_exibicao.columns = ['Data', 'Lançamento', 'Origem', 'Categoria', 'Grupo Orçamentário', 'Valor']
df_exibicao['Valor'] = df_exibicao['Valor'].map("R$ {:,.2f}".format)
st.dataframe(df_exibicao, use_container_width=True)

st.markdown("---")
st.subheader("💬 Converse com seu Assistente Orçamentário")

if "mensagens" not in st.session_state:
    st.session_state.mensagens = []

for msg in st.session_state.mensagens:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

pergunta_usuario = st.chat_input("Pergunte algo (Ex: Quanto gastei com Mercado em junho?)")

if pergunta_usuario:
    st.session_state.mensagens.append({"role": "user", "content": pergunta_usuario})
    with st.chat_message("user"):
        st.write(pergunta_usuario)
        
    pergunta_min = pergunta_usuario.lower()
    resposta_ia = ""
    
    if "mercado" in pergunta_min or "atacadão" in pergunta_min or "big master" in pergunta_min:
        total_mercado = df_despesas[df_despesas['Categoria'] == 'Mercado']['Valor_Absoluto'].sum()
        resposta_ia = f"Vitor, identificamos que em junho o seu gasto total com **Mercado** foi de **R$ {total_mercado:,.2f}**, englobando as compras realizadas no Atacadão e Big Master."
    elif "essencial" in pergunta_min or "necessidade" in pergunta_min:
        resposta_ia = f"O seu gasto total na categoria **50% Essencial** somou **R$ {total_essencial:,.2f}**."
    elif "estilo de vida" in pergunta_min or "desejos" in pergunta_min:
        resposta_ia = f"Para **Estilo de Vida (30%)**, o total consumido foi de **R$ {total_estilo:,.2f}**."
    elif "negócio" in pergunta_min or "custos" in pergunta_min:
        resposta_ia = f"Os seus **Custos de Negócio** totalizaram **R$ {total_negocio:,.2f}** em junho."
    else:
        resposta_ia = f"Consigo analisar os dados atuais de junho! O valor total movimentado no extrato consolidado foi de **R$ {total_geral:,.2f}**."

    st.session_state.mensagens.append({"role": "assistant", "content": resposta_ia})
    with st.chat_message("assistant"):
        st.write(resposta_ia)
