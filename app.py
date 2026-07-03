import streamlit as st
import pandas as pd
import plotly.express as px
import re

st.set_page_config(page_title="Assistente Financeiro Vitor Manoel", layout="wide")

st.title("📊 Assistente Financeiro Vitor Manoel")
st.subheader("Inteligência Orçamentária | Banco Inter")
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
arquivo_carregado = st.sidebar.file_uploader("Suba o CSV do Banco Inter aqui:", type=["csv"])

if arquivo_carregado is not None:
    try:
        df_bruto = pd.read_csv(arquivo_carregado, sep=';', encoding='utf-8', decimal=',', thousands='.')
        df_bruto.columns = [col.strip() for col in df_bruto.columns]
        
        col_data = [c for c in df_bruto.columns if 'data' in c.lower()][0]
        col_desc = [c for c in df_bruto.columns if 'desc' in c.lower() or 'historico' in c.lower()][0]
        # Lendo o CSV do Inter tratando o formato de moeda brasileiro
        df_bruto = pd.read_csv(arquivo_carregado, sep=';', encoding='utf-8', decimal=',', thousands='.')
        df_bruto.columns = [col.strip() for col in df_bruto.columns]
        
        # Mapeamento robusto: tenta por nome, se falhar pega pela posição física das colunas
        try:
            col_data = [c for c in df_bruto.columns if 'data' in c.lower()][0]
        except IndexError:
            col_data = df_bruto.columns[0] # Pega a primeira coluna se não achar pelo nome
            
        try:
            col_desc = [c for c in df_bruto.columns if 'desc' in c.lower() or 'historico' in c.lower()][0]
        except IndexError:
            col_desc = df_bruto.columns[1] # Pega a segunda coluna
            
        try:
            col_valor = [c for c in df_bruto.columns if 'valor' in c.lower()][0]
        except IndexError:
            col_valor = df_bruto.columns[2] # Pega a terceira coluna
        
        df = pd.DataFrame({
            'Data': df_bruto[col_data],
            'Descricao': df_bruto[col_desc],
            'Valor': df_bruto[col_valor]
        })
        total_estilo = df_despesas[df_despesas['Grupo_Orcamentario'] == '30% Estilo de Vida']['Valor_Absoluto'].sum()
        total_negocio = df_despesas[df_despesas['Grupo_Orcamentario'] == 'Custos de Negócio']['Valor_Absoluto'].sum()
        total_geral = df_despesas['Valor_Absoluto'].sum()
        
        st.metric(label="🔴 50% Essencial Total", value=f"R$ {total_essencial:,.2f}")
        st.metric(label="🟡 30% Estilo de Vida Total", value=f"R$ {total_estilo:,.2f}")
        st.metric(label="💼 Custos de Negócio", value=f"R$ {total_negocio:,.2f}")
        st.metric(label="💸 Total Desembolsado", value=f"R$ {total_geral:,.2f}")
        
        st.markdown("---")
        st.subheader("Distribuição do Orçamento")
        df_pizza = df_despesas.groupby('Grupo_Orcamentario')['Valor_Absoluto'].sum().reset_index()
        fig = px.pie(df_pizza, values='Valor_Absoluto', names='Grupo_Orcamentario', hole=0.5,
                     color_discrete_sequence=['#ff4b4b', '#ffaa00', '#00a86b'])
        fig.update_layout(margin=dict(l=20, r=20, t=20, b=20), showlegend=True)
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
        st.subheader("📋 Extrato Simplificado")
        df_exibicao = df_despesas[['Data', 'Descricao', 'Categoria', 'Valor_Absoluto']].copy()
        df_exibicao.columns = ['Data', 'Lançamento', 'Cat', 'Valor']
        df_exibicao['Valor'] = df_exibicao['Valor'].map("R$ {:,.2f}".format)
        st.dataframe(df_exibicao, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.subheader("💬 Chat com os dados do Extrato")
        
        if "mensagens" not in st.session_state:
            st.session_state.mensagens = []
            
        for msg in st.session_state.mensagens:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                
        pergunta_usuario = st.chat_input("Pergunte sobre os gastos do arquivo...")
        
        if pergunta_usuario:
            st.session_state.mensagens.append({"role": "user", "content": pergunta_usuario})
            with st.chat_message("user"):
                st.write(pergunta_usuario)
                
            pergunta_min = pergunta_usuario.lower()
            
            if "mercado" in pergunta_min or "atacadão" in pergunta_min or "big master" in pergunta_min:
                total_mercado = df_despesas[df_despesas['Categoria'] == 'Mercado']['Valor_Absoluto'].sum()
                resposta_ia = f"Vitor, o gasto total com **Mercado** mapeado no seu arquivo do Inter foi de **R$ {total_mercado:,.2f}**."
            elif "essencial" in pergunta_min:
                resposta_ia = f"O total consumido na categoria **50% Essencial** desse arquivo foi **R$ {total_essencial:,.2f}**."
            elif "estilo de vida" in pergunta_min:
                resposta_ia = f"Para **Estilo de Vida (30%)**, o valor total foi de **R$ {total_estilo:,.2f}**."
            else:
                resposta_ia = f"Analisei o arquivo carregado! O total de despesas identificadas foi de **R$ {total_geral:,.2f}**."
                
            st.session_state.mensagens.append({"role": "assistant", "content": resposta_ia})
            with st.chat_message("assistant"):
                st.write(resposta_ia)
                
    except Exception as e:
        st.error(f"Erro ao processar o arquivo do Inter. Certifique-se de baixar o formato padrão .CSV do aplicativo ou internet banking.")
else:
    st.info("👋 Olá Vitor! O sistema está pronto. Vá no app do Banco Inter, exporte seu extrato em formato CSV e faça o upload aqui para ativar os seus gráficos reais.")
