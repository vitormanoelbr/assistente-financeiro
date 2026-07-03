import streamlit as st
import datetime
import pandas as pd
import plotly.express as px
from supabase import create_client, Client

st.set_page_config(page_title="Meu Planner Financeiro", layout="centered")

# --- 🔐 CONEXÃO SECRETA ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    st.error("❌ Erro de Segurança: As credenciais (Secrets) não foram configuradas no painel do Streamlit.")
    st.stop()

@st.cache_resource
def conectar_banco():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase: Client = conectar_banco()
except Exception as e:
    st.error(f"Falha na conexão estrutural: {e}")

# --- ⚙️ PERFIL & FILTROS (SIDEBAR) ---
st.sidebar.header("⚙️ Configurações do Perfil")
RENDA_BASE = st.sidebar.number_input("Sua Renda Mensal Base (R$):", min_value=0.0, value=2500.00, step=100.0)

st.sidebar.markdown("---")
st.sidebar.header("📅 Filtros de Tempo")

hoje = datetime.date.today()
ano_atual = hoje.year
mes_atual = hoje.month

lista_anos = [ano_atual, ano_atual - 1, ano_atual + 1]
ano_selecionado = st.sidebar.selectbox("Ano de Análise:", lista_anos, index=0)

lista_meses = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}
mes_selecionado_num = st.sidebar.selectbox(
    "Mês de Análise:", 
    list(lista_meses.keys()), 
    format_func=lambda x: lista_meses[x],
    index=list(lista_meses.keys()).index(mes_atual)
)

janela_tempo = st.sidebar.radio("Visualizar intervalo:", ["Mês Completo", "Últimos 7 Dias", "Somente Hoje"])

# --- CÁLCULO DE METAS ---
LIMITE_ESSENCIAL = RENDA_BASE * 0.50       
LIMITE_ESTILO_DE_VIDA = RENDA_BASE * 0.30  
META_APORTE = RENDA_BASE * 0.20           

gastos_essencial = 0.0
gastos_estilo = 0.0
gastos_aporte = 0.0

# Novas variáveis dinâmicas de dívida baseadas puramente no banco de dados
DIVIDA_TOTAL_INICIAL = 0.0
total_pago_divida = 0.0

df_todos_dados = pd.DataFrame()
df_filtrado = pd.DataFrame()

if supabase:
    try:
        resposta_completa = supabase.table("movimentacoes").select("id, data, descricao, grupo_orcamentario, subcategoria, valor, satisfacao, tipo").execute()
        if res_data := resposta_completa.data:
            df_todos_dados = pd.DataFrame(res_data)
            df_todos_dados["valor"] = df_todos_dados["valor"].astype(float)
            df_todos_dados["data_dt"] = pd.to_datetime(df_todos_dados["data"]).dt.date
            
            # INTELIGÊNCIA UNIFICADA DE DÍVIDAS: Varre o histórico completo para calcular o saldo real
            for item in res_data:
                grupo = item["grupo_orcamentario"]
                tipo_mov = item.get("tipo", "Gasto ou Investimento (Saída)")
                val_mov = float(item["valor"])
                
                if "📋 Quitação de Dívidas" in grupo:
                    if "Entrada" in tipo_mov:
                        # Se entrou como receita/registro, acumula o tamanho da dívida real
                        DIVIDA_TOTAL_INICIAL += val_mov
                    else:
                        # Se saiu como gasto, foi um pagamento de parcela (amortização)
                        total_pago_divida += val_mov
            
            # Filtros temporais normais para o restante do painel líquido do mês
            df_filtrado = df_todos_dados.copy()
            df_filtrado["ano"] = pd.to_datetime(df_filtrado["data_dt"]).dt.year
            df_filtrado["mes"] = pd.to_datetime(df_filtrado["data_dt"]).dt.month
            
            df_filtrado = df_filtrado[(df_filtrado["ano"] == ano_selecionado) & (df_filtrado["mes"] == mes_selecionado_num)]
            
            if janela_tempo == "Últimos 7 Dias":
                setem_dias_atras = hoje - datetime.timedelta(days=7)
                df_filtrado = df_filtrado[df_filtrado["data_dt"] >= setem_dias_atras]
            elif janela_tempo == "Somente Hoje":
                df_filtrado = df_filtrado[df_filtrado["data_dt"] == hoje]
                
            for _, row in df_filtrado.iterrows():
                val = float(row["valor"])
                grupo = row["grupo_orcamentario"]
                tipo_mov = row.get("tipo", "Gasto ou Investimento (Saída)")
                
                if "Saída" in tipo_mov:
                    if "50% Essencial" in grupo:
                        gastos_essencial += val
                    elif "30% Estilo de Vida" in grupo:
                        gastos_estilo += val
                    elif "20% Aporte" in grupo:
                        gastos_aporte += val
                    
    except Exception as e:
        st.error(f"Erro no processamento de dados: {e}")

divida_restante = max(DIVIDA_TOTAL_INICIAL - total_pago_divida, 0.0)

MAPA_CATEGORIAS = {
    "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)": [
        "Alimentação Básica & Mercado", "Contas Fixas (Luz, Água, Internet)", 
        "Habitação (Aluguel / Financiamento)", "Saúde & Medicamentos", 
        "Transporte & Combustível", "Pensão / Obrigações Legais"
    ],
    "🟡 30% Estilo de Vida (Lazer e Custos Voláteis)": [
        "Lazer, Bares & Restaurantes", "Delivery / iFood / Conforto", 
        "Vestuário, Compras & Presentes", "Estética, Cuidados & Academia", 
        "Viagens & Hobbies", "Assinaturas (Netflix, Spotify)"
    ],
    "🚀 20% Aporte para a Liberdade (Investimentos e Futuro)": [
        "Reserva de Autonomia (Emergência)", "Aportes Renda Fixa", "Aportes Renda Variável"
    ],
    "📋 Quitação de Dívidas (Amortizações e Acordos)": [
        "Empréstimos Bancários", "Cartão de Crédito Atrasado", "Financiamentos de Bens", "Dívidas Pessoais / Terceiros"
    ],
    "💼 Custos de Negócio (Projetos e Clínica)": [
        "Ferramentas SaaS & Softwares", "Marketing & Anúncios", "Infraestrutura & Custos Operacionais"
    ]
}

# --- INTERFACE ---
aba_painel, aba_investimentos = st.tabs(["📊 Painel & Lançamentos", "🚀 Investimentos (Experimental)"])

with aba_painel:
    st.title("📲 Meu Planner Financeiro")
    st.markdown(f"**Competência:** {lista_meses[mes_selecionado_num]} / {ano_selecionado} ({janela_tempo})")
    st.markdown("---")
    
    # PAINEL DE DÍVIDAS ATUALIZADO
    st.subheader("📊 Painel de Limites Orçamentários")
    st.markdown("### 🧮 Situação de Dívidas Estruturadas (Calculado via Banco)")
    
    col1, col2, col3 = st.columns(3)
    col1.metric(label="Volume de Dívida Registrada", value=f"R$ {DIVIDA_TOTAL_INICIAL:,.2f}")
    col2.metric(label="Total Pago / Amortizado", value=f"R$ {total_pago_divida:,.2f}")
    col3.metric(label="Saldo Devedor Restante", value=f"R$ {divida_restante:,.2f}")
    
    if DIVIDA_TOTAL_INICIAL > 0:
        perc_divida_paga = min(total_pago_divida / DIVIDA_TOTAL_INICIAL, 1.0)
        st.progress(perc_divida_paga)
        st.caption(f"Progresso de Liquidação Total: **{perc_divida_paga * 100:.1f}%**")
    else:
        st.info("💡 Nenhuma dívida mapeada. Para registrar o valor inicial de uma dívida, faça um lançamento do tipo 'Faturamento ou Receita (Entrada)' selecionando o grupo 'Quitação de Dívidas'.")
    
    st.markdown("---")
    
    # LIMITES LÍQUIDOS
    st.write(f"🔴 **Gasto Essencial:** R$ {gastos_essencial:,.2f} de R$ {LIMITE_ESSENCIAL:,.2f}")
    st.progress(min(gastos_essencial / LIMITE_ESSENCIAL, 1.0) if LIMITE_ESSENCIAL > 0 else 0.0)
    
    st.write(f"🟡 **Estilo de Vida:** R$ {gastos_estilo:,.2f} de R$ {LIMITE_ESTILO_DE_VIDA:,.2f}")
    st.progress(min(gastos_estilo / LIMITE_ESTILO_DE_VIDA, 1.0) if LIMITE_ESTILO_DE_VIDA > 0 else 0.0)
    
    st.write(f"🚀 **Aportes Efetuados:** R$ {gastos_aporte:,.2f} de R$ {META_APORTE:,.2f}")
    st.progress(min(gastos_aporte / META_APORTE, 1.0) if META_APORTE > 0 else 0.0)

    # GRÁFICOS
    if not df_filtrado.empty:
        st.markdown("---")
        df_agrupado = df_filtrado.groupby("grupo_orcamentario")["valor"].sum().reset_index()
        fig_rosca = px.pie(df_agrupado, values="valor", names="grupo_orcamentario", hole=0.4, title="Distribuição Financeira Real (R$)")
        st.plotly_chart(fig_rosca, use_container_width=True)

    # LANÇAMENTO DE MOVIMENTAÇÃO
    st.markdown("---")
    st.subheader("📥 Registrar Movimentação")
    
    grupo_orcamentario = st.selectbox("Destinação Estratégica do Valor:", list(MAPA_CATEGORIAS.keys()), key="grupo_pai_main")
    opcoes_subcategoria = MAPA_CATEGORIAS[grupo_orcamentario]
    categoria = st.selectbox("Subcategoria Correspondente:", opcoes_subcategoria, key="sub_filho_main")

    with st.form("formulario_envio_blindado", clear_on_submit=True):
        valor = st.number_input("Qual o valor da operação? (R$)", min_value=0.0, step=5.0, format="%.2f")
        
        # INSTRUÇÃO VISUAL NO SELECTOR DE DIREÇÃO DO DINHEIRO
        tipo = st.radio(
            "Direção do dinheiro (Atenção para Dívidas):", 
            ["Gasto ou Investimento (Saída)", "Faturamento ou Receita (Entrada)"], 
            horizontal=True,
            help="Para registrar uma DÍVIDA NOVA, marque 'Entrada'. Para registrar o PAGAMENTO de uma parcela, marque 'Saída'."
        )
        
        data_movimento = st.date_input("Data do evento:", datetime.date.today())
        descricao = st.text_input("Descrição ou Estabelecimento:", placeholder="Ex: Parcela Banco do Brasil, Empréstimo Flavielly, Mercado...")
        satisfacao = st.select_slider("🧠 Nível de necessidade real?", options=["1 - Impulsivo / Evitável", "2 - Útil / Desejável", "3 - Indispensável"], value="2 - Útil / Desejável")
        botao_enviar = st.form_submit_button("Confirmar Lançamento")
        
    if botao_enviar and supabase:
        if valor > 0 and descricao:
            try:
                dados_gasto = {
                    "data": str(data_movimento), "valor": float(valor), "tipo": tipo,
                    "descricao": descricao, "grupo_orcamentario": grupo_orcamentario,
                    "subcategoria": categoria, "satisfacao": satisfacao
                }
                supabase.table("movimentacoes").insert(dados_gasto).execute()
                st.success("✅ Operação registrada com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

    # GERENCIADOR TOTAL INTERATIVO (O ÚNICO LUGAR DE EDICAO E EXCLUSAO)
    st.markdown("---")
    st.subheader("📋 Gerenciar Lançamentos do Período")
    st.caption("💡 Para corrigir valores errados de dívida ou gasto, altere os números abaixo e salve. Para deletar, selecione e use Delete.")
    
    if supabase and not df_filtrado.empty:
        # Adicionado o campo 'tipo' no editor para o usuário poder alterar de Entrada para Saída direto se errar
        df_editor = df_filtrado[["id", "data", "descricao", "grupo_orcamentario", "subcategoria", "valor", "tipo"]].copy()
        df_editor.columns = ["ID", "Data", "Descrição", "Grupo", "Subcategoria", "Valor (R$)", "Tipo"]
        
        dados_editados = st.data_editor(df_editor, use_container_width=True, hide_index=True, disabled=["ID"], num_rows="dynamic")
        
        if st.button("💾 Salvar Alterações da Tabela"):
            try:
                linhas_atuais_ids = set(dados_editados["ID"].tolist())
                linhas_originais_ids = set(df_editor["ID"].tolist())
                ids_deletados = linhas_originais_ids - linhas_atuais_ids
                
                for id_del in ids_deletados:
                    supabase.table("movimentacoes").delete().eq("id", int(id_del)).execute()
                for _, row in dados_editados.iterrows():
                    row_id = int(row["ID"])
                    orig_row = df_editor[df_editor["ID"] == row_id].iloc[0]
                    
                    if (row["Descrição"] != orig_row["Descrição"]) or (float(row["Valor (R$)"]) != float(orig_row["Valor (R$)"])) or (row["Tipo"] != orig_row["Tipo"]):
                        supabase.table("movimentacoes").update({
                            "descricao": row["Descrição"], 
                            "valor": float(row["Valor (R$)"]),
                            "tipo": row["Tipo"]
                        }).eq("id", row_id).execute()
                        
                st.success("🔄 Todo o ecossistema (Painel, Dívidas e Gráficos) sincronizado com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar alterações: {e}")

with aba_investimentos:
    st.header("📈 Centro de Acumulação de Patrimônio")
    st.metric(label="Total Alocado para o Futuro no Período", value=f"R$ {gastos_aporte:,.2f}", delta=f"Meta: R$ {META_APORTE:,.2f}")
