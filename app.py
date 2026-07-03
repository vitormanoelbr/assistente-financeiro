import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Assistente Financeiro Vitor Manoel", layout="wide")

st.title("📊 Assistente Financeiro Vitor Manoel")
st.subheader("Inteligência Orçamentária | Banco Inter")
st.markdown("---")

# 1. REGRAS DE CATEGORIZAÇÃO
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
        if termo in str(descricao).upper():
            return categoria, grupo
    return 'Outros', 'A Classificar'

# 2. INTERFACE DE UPLOAD
st.sidebar.header("📥 Alimentar o Assistente")
arquivo_carregado = st.sidebar.file_uploader("Suba o CSV do Banco Inter aqui:", type=["csv"])

if arquivo_carregado is not None:
    try:
        # Tenta ler primeiro com ';' (padrão Inter Web)
        try:
            df_bruto = pd.read_csv(arquivo_carregado, sep=';', encoding='utf-8', decimal=',', thousands='.')
            if len(df_bruto.columns) < 3:
                raise ValueError
        except:
            # Se falhar ou ler errado, tenta com ',' (padrão Inter App)
            arquivo_carregado.seek(0)
            df_bruto = pd.read_csv(arquivo_carregado, sep=',', encoding='utf-8', decimal='.', thousands=',')
        
        df_bruto.columns = [col.strip() for col in df_bruto.columns]
        
        # Identificação dinâmica de colunas por eliminação
        col_data = df_bruto.columns[0]
        col_desc = df_bruto.columns[1]
        col_valor = df_bruto.columns[2]
        
        # Criar dataframe limpo convertendo valores para numérico puro
        df = pd.DataFrame()
        df['Data'] = df_bruto[col_data]
        df['Descricao'] = df_bruto[col_desc]
        
        # Limpeza pesada no campo de valor para garantir que vire número absoluto
        valores_limpos = df_bruto[col_valor].astype(str).str.replace('R$', '', regex=False).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).str.strip()
        df['Valor'] = pd.to_numeric(valores_limpos, errors='coerce')
        
        # Se os valores vieram positivos por padrão no extrato novo do Inter, tratamos depois
        res_classif = df['Descricao'].apply(classificar_transacao)
        df['Categoria'] = [r[0] for r in res_classif]
        df['Grupo_Orcamentario'] = [r[1] for r in res_classif]
        
        # Remove movimentações internas
        df_despesas = df[~df['Grupo_Orcamentario'].isin(['Movimentação Interna', 'Descontinuado'])].copy()
        df_despesas['Valor_Absoluto'] = df_despesas['Valor'].abs()
        
        if not df_despesas.empty:
            # Cálculos de Métricas
            total_essencial = df_despesas[df_despesas['Grupo_Orcamentario'] == '50% Essencial']['Valor_Absoluto'].sum()
            total_estilo = df_despesas[df_despesas['Grupo_Orcamentario'] == '30% Estilo de Vida']['Valor_Absoluto'].sum()
            total_negocio = df_despesas[df_despesas['Grupo_Orcamentario'] == 'Custos de Negócio']['Valor_Absoluto'].sum()
            total_geral = df_despesas['Valor_Absoluto'].sum()
            
            # Exibição das Métricas
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
        else:
            st.warning("Nenhum dado financeiro pôde ser extraído deste arquivo.")
                
    except Exception as e:
        st.error(f"Erro ao processar estrutura do arquivo: {e}")
else:
    st.info("👋 Olá Vitor! O sistema está pronto. Vá no app do Banco Inter, exporte seu extrato em formato CSV e faça o upload aqui para ativar os seus gráficos reais.")
