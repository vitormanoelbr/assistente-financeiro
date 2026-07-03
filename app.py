import streamlit as st
import pandas as pd
import plotly.express as px
import io

st.set_page_config(page_title="Assistente Financeiro Vitor Manoel", layout="wide")

st.title("📊 Assistente Financeiro Vitor Manoel")
st.subheader("Inteligência Orçamentária | Banco Inter")
st.markdown("---")

# 1. REGRAS DE CATEGORIZAÇÃO
REGRAS_ORCAMENTO = {
    'ATACADAO': ('Mercado', '50% Essencial'),
    'BIG MASTE': ('Mercado', '50% Essencial'),
    'WMS SUPERMERCADOS': ('Mercado', '50% Essencial'),
    'AMERICANAS': ('Mercado', '50% Essencial'),
    'VIDA  SAUDE': ('Saúde', '50% Essencial'),
    'DENISE KATER': ('Farmácia', '50% Essencial'),
    'DROGARIAS FARMARELA': ('Farmácia', '50% Essencial'),
    'C. P. DA SILVA': ('Gás de Cozinha', '50% Essencial'),
    'SEGUNDO OFICIO': ('Taxas/Cartório', '50% Essencial'),
    'VIVO MT': ('Telecom', '50% Essencial'),
    'CLARO': ('Telecom', '50% Essencial'),
    'TALIA ROCHA RIBEIRO': ('Babá/Filho', '50% Essencial'),
    'ISABELA LUISA STANGHERLIM': ('Pensão/Filho', '50% Essencial'),
    'AUTO POSTO L3': ('Transporte', '50% Essencial'),
    'ME COMERCIO DE COMBUSTIVEIS': ('Transporte', '50% Essencial'),
    'RECEITA FEDERAL': ('Impostos', '50% Essencial'),
    'SEFAZ MT': ('Impostos', '50% Essencial'),
    'IFOODCOM': ('Alimentação/Delivery', '30% Estilo de Vida'),
    'NETSHOES': ('Presente Namorada', '30% Estilo de Vida'),
    'ROTARY CLUB': ('Doações/Social', '30% Estilo de Vida'),
    'IGREJA BATISTA': ('Contribuições/Religião', '30% Estilo de Vida'),
    'GOOGLE ONE': ('Assinaturas Tech', '30% Estilo de Vida'),
    'CDB PORQUINHO': ('Aplicação/Resgate', 'Movimentação Interna'),
    'CDB PORQ': ('Aplicação/Resgate', 'Movimentação Interna'),
    'CHATGPT': ('Ferramentas SaaS', 'Custos de Negócio'),
    'HTM JMM': ('Plataformas Cursos', 'Custos de Negócio')
}

def classificar_transacao(descricao):
    desc_upper = str(descricao).upper()
    for termo, (categoria, grupo) in REGRAS_ORCAMENTO.items():
        if termo in desc_upper:
            return categoria, grupo
    return 'Outros', 'A Classificar'

# 2. INTERFACE DE UPLOAD
st.sidebar.header("📥 Alimentar o Assistente")
arquivo_carregado = st.sidebar.file_uploader("Suba o CSV do Banco Inter aqui:", type=["csv"])

if arquivo_carregado is not None:
    try:
        # Lê o conteúdo bruto
        conteudo_bruto = arquivo_carregado.read().decode('utf-8', errors='ignore')
        linhas = conteudo_bruto.splitlines()
        
        # Encontra a linha onde começa a tabela real
        linha_inicio_tabela = 0
        for i, linha in enumerate(linhas):
            if 'data lançamento' in linha.lower():
                linha_inicio_tabela = i
                break
                
        linhas_tabela = lines_tabela = linhas[linha_inicio_tabela:]
        arquivo_limpo = io.StringIO('\n'.join(linhas_tabela))
        
        # Lê o CSV tratando ponto e vírgula
        df_bruto = pd.read_csv(arquivo_limpo, sep=';')
        df_bruto.columns = [col.strip() for col in df_bruto.columns]
        
        df = pd.DataFrame()
        df['Data'] = df_bruto['Data Lançamento']
        df['Descricao'] = df_bruto['Descrição']
        
        # CORREÇÃO DA CONVERSÃO: Trata o formato numérico sem multiplicar valores por 10000
        valores_raw = df_bruto['Valor'].astype(str).str.replace('R$', '', regex=False).str.strip()
        # Se contiver pontos de milhar, removemos. Substitui a vírgula decimal por ponto.
        valores_corrigidos = valores_raw.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
        df['Valor'] = pd.to_numeric(valores_corrigidos, errors='coerce')
        
        # Classificação
        res_classif = df['Descricao'].apply(classificar_transacao)
        df['Categoria'] = [r[0] for r in res_classif]
        df['Grupo_Orcamentario'] = [r[1] for r in res_classif]
        
        # Filtrar apenas saídas legítimas (Valores negativos) e ignorar investimentos/resgates
        df_despesas = df[(df['Valor'] < 0) & (~df['Grupo_Orcamentario'].isin(['Movimentação Interna', 'Descontinuado']))].copy()
        df_despesas['Valor_Absoluto'] = df_despesas['Valor'].abs()
        
        if not df_despesas.empty:
            total_essencial = df_despesas[df_despesas['Grupo_Orcamentario'] == '50% Essencial']['Valor_Absoluto'].sum()
            total_estilo = df_despesas[df_despesas['Grupo_Orcamentario'] == '30% Estilo de Vida']['Valor_Absoluto'].sum()
            total_negocio = df_despesas[df_despesas['Grupo_Orcamentario'] == 'Custos de Negócio']['Valor_Absoluto'].sum()
            total_geral = df_despesas['Valor_Absoluto'].sum()
            
            # Cards de Métricas corrigidos
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
            st.warning("Nenhuma despesa de saída encontrada neste período do extrato.")
                
    except Exception as e:
        st.error(f"Erro ao processar estrutura do arquivo: {e}")
else:
    st.info("👋 Olá Vitor! O sistema está pronto. Suba seu extrato do Inter em formato CSV para ativar seus gráficos reais.")
