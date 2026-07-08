import streamlit as st
import datetime
import pandas as pd
import plotly.express as px
from supabase import create_client, Client

st.set_page_config(page_title="Meu Planner Financeiro", layout="centered")

# --- 🔐 CONEXÃO COM BANCO ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    st.error("❌ Erro de Segurança: As credenciais não foram configuradas no painel do Streamlit.")
    st.stop()

def conectar_banco():
    """Cria um cliente Supabase por sessão do Streamlit.

    Evita compartilhar o mesmo cliente autenticado entre usuários diferentes.
    """
    if "_supabase_client" not in st.session_state:
        st.session_state["_supabase_client"] = create_client(SUPABASE_URL, SUPABASE_KEY)
    return st.session_state["_supabase_client"]

try:
    supabase: Client = conectar_banco()
except Exception as e:
    st.error(f"Falha na conexão estrutural: {e}")
    st.stop()

for chave, valor_padrao in {
    "usuario_logado": None,
    "user_token": None,
    "refresh_token": None,
}.items():
    if chave not in st.session_state:
        st.session_state[chave] = valor_padrao

def deslogar_usuario():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state["usuario_logado"] = None
    st.session_state["user_token"] = None
    st.session_state["refresh_token"] = None
    st.query_params.clear()
    st.rerun()

# ==================== TELA DE AUTENTICAÇÃO ====================
if st.session_state["usuario_logado"] is None:
    st.title("📲 Bem-vindo ao Meu Planner Financeiro")
    st.caption("Acesse sua conta para gerenciar suas finanças com segurança.")
    
    aba_login, aba_cadastro = st.tabs(["🔐 Entrar na Conta", "🚀 Criar Nova Conta"])
    
    with aba_login:
        with st.form("form_login"):
            email_login = st.text_input("E-mail:", placeholder="seu@email.com")
            senha_login = st.text_input("Senha:", type="password", placeholder="******")
            botao_login = st.form_submit_button("Acessar Painel")
            
            if botao_login:
                if email_login and senha_login:
                    try:
                        resposta = supabase.auth.sign_in_with_password({"email": email_login, "password": senha_login})
                        st.session_state["usuario_logado"] = resposta.user.id
                        st.session_state["user_token"] = resposta.session.access_token
                        st.session_state["refresh_token"] = resposta.session.refresh_token
                        st.query_params.clear()
                        st.success("🎉 Acesso autorizado! Redirecionando...")
                        st.rerun()
                    except Exception:
                        st.error("❌ Erro ao entrar: E-mail ou senha incorretos.")
                else:
                    st.warning("Preencha todos os campos.")
                    
    with aba_cadastro:
        with st.form("form_cadastro"):
            email_cad = st.text_input("Escolha um E-mail:", placeholder="seu@email.com")
            senha_cad = st.text_input("Escolha uma Senha (mínimo 6 caracteres):", type="password", placeholder="******")
            botao_cad = st.form_submit_button("Cadastrar e Criar Plataforma")
            
            if botao_cad:
                if email_cad and len(senha_cad) >= 6:
                    try:
                        resposta = supabase.auth.sign_up({"email": email_cad, "password": senha_cad})
                        st.success("✅ Conta criada com sucesso! Mude para a aba de Login para acessar.")
                    except Exception as e:
                        st.error(f"Erro ao cadastrar: {e}")
                else:
                    st.warning("O e-mail precisa ser válido e a senha ter no mínimo 6 caracteres.")
    st.stop()

# ==================== SISTEMA PRINCIPAL ====================
USER_ID = st.session_state["usuario_logado"]

if st.sidebar.button("🚪 Sair da Conta"):
    deslogar_usuario()

# --- 📅 FILTROS DE TEMPO & TAGS ---
st.sidebar.header("📅 Filtros do Painel")
hoje = datetime.date.today()
ano_selected = st.sidebar.selectbox("Ano de Análise:", [hoje.year, hoje.year - 1, hoje.year + 1], index=0)

lista_meses = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}
mes_selected_num = st.sidebar.selectbox(
    "Mês de Análise:", list(lista_meses.keys()), 
    format_func=lambda x: lista_meses[x],
    index=list(lista_meses.keys()).index(hoje.month)
)

janela_tempo = st.sidebar.radio("Intervalo do Painel:", ["Mês Completo", "Últimos 7 Dias", "Somente Hoje"])

st.sidebar.markdown("---")
st.sidebar.header("🏷️ Rastreamento Inteligente")
tag_busca = st.sidebar.text_input("Filtrar por Tag / Texto:", placeholder="Ex: #filho, #viagem").strip().lower()

# --- VARIÁVEIS DE CONTROLE ACUMULADO ---
renda_base_usuario = 0.0  
faturamento_extra_mes = 0.0
gastos_dinheiro_caixa = 0.0       
fatura_acumulada_mes = 0.0   

gastos_essencial = 0.0
gastos_estilo = 0.0
gastos_negocio = 0.0
gastos_dividas = 0.0

agenda_a_pagar_mes = 0.0
agenda_a_receber_mes = 0.0

dicionario_metas_alvo = {}
dicionario_aportes_acumulados = {}

lista_dividas_cadastradas = []
amortizacoes_totais_historicas = {}

df_todos_dados = pd.DataFrame()
df_filtrado = pd.DataFrame()

if supabase:
    try:
        if st.session_state.get("user_token") and st.session_state.get("refresh_token"):
            resposta_sessao = supabase.auth.set_session(
                st.session_state["user_token"],
                st.session_state["refresh_token"],
            )
            sessao_atualizada = getattr(resposta_sessao, "session", None)
            if sessao_atualizada:
                st.session_state["user_token"] = sessao_atualizada.access_token
                st.session_state["refresh_token"] = sessao_atualizada.refresh_token

        resposta_completa = supabase.table("movimentacoes").select("id, data, descricao, grupo_orcamentario, subcategoria, valor, satisfacao, tipo, user_id").eq("user_id", USER_ID).execute()
        
        if resposta_completa and hasattr(resposta_completa, 'data') and resposta_completa.data:
            res_data = resposta_completa.data
            df_todos_dados = pd.DataFrame(res_data)
            df_todos_dados["valor"] = df_todos_dados["valor"].astype(float)
            df_todos_dados["data_dt"] = pd.to_datetime(df_todos_dados["data"]).dt.date
            
            # Processamento de Configurações Globais e Metadados
            for item in res_data:
                desc = str(item.get("descricao") or "")
                subcat = str(item.get("subcategoria") or "")
                grupo = str(item.get("grupo_orcamentario") or "")
                tipo_mov = str(item.get("tipo") or "")
                val_mov = float(item["valor"] or 0.0)
                dt_item = pd.to_datetime(item["data"]).date()
                
                if "[CONFIG_PERFIL]" in desc and "Renda Base Nativa" in subcat:
                    renda_base_usuario = val_mov
                    continue
                
                if "[DIVIDA_ATIVA]" in desc:
                    lista_dividas_cadastradas.append({
                        "id": item["id"],
                        "nome": subcat,
                        "valor_original": val_mov,
                        "parcela": float(item.get("satisfacao").split(" - ")[0] if " - " in str(item.get("satisfacao")) else 0)
                    })
                    continue
                
                if "AGENDA" in grupo.upper():
                    if dt_item.year == ano_selected and dt_item.month == mes_selected_num:
                        if "PAGAR" in grupo.upper():
                            agenda_a_pagar_mes += val_mov
                        elif "RECEBER" in grupo.upper():
                            agenda_a_receber_mes += val_mov
                    continue
                
                if "APORTE" in grupo.upper() or "🚀" in grupo:
                    if "ENTRADA" in tipo_mov.upper() or "FATURAMENTO" in tipo_mov.upper() or "RECEITA" in tipo_mov.upper():
                        dicionario_metas_alvo[subcat] = val_mov
                    elif "SAÍDA" in tipo_mov.upper() or "PIX" in tipo_mov.upper() or "DÉBITO" in tipo_mov.upper() or "📱" in tipo_mov or "💳" in tipo_mov:
                        dicionario_aportes_acumulados[subcat] = dicionario_aportes_acumulados.get(subcat, 0.0) + val_mov
                
                if "QUITAÇÃO" in grupo.upper() or "DIVIDAS" in grupo.upper() or "📋" in grupo:
                    if "SAÍDA" in tipo_mov.upper() or "📱" in tipo_mov or "💳" in tipo_mov:
                        amortizacoes_totais_historicas[subcat] = amortizacoes_totais_historicas.get(subcat, 0.0) + val_mov

            # --- CORREÇÃO DO FILTRO DE TEMPO REAL ---
            if not df_todos_dados.empty:
                df_filtrado = df_todos_dados.copy()
                df_filtrado = df_filtrado[~df_filtrado["grupo_orcamentario"].astype(str).str.upper().str.contains("CONFIGURAC|CONFIGURAÇÃO|CONFIG", na=False)]
                df_filtrado = df_filtrado[~df_filtrado["descricao"].astype(str).str.upper().str.contains("CONFIG_PERFIL|DIVIDA_ATIVA", na=False)]
                df_filtrado = df_filtrado[~df_filtrado["grupo_orcamentario"].astype(str).str.upper().str.contains("AGENDA", na=False)]
                
                if not df_filtrado.empty:
                    df_filtrado["ano"] = pd.to_datetime(df_filtrado["data_dt"]).dt.year
                    df_filtrado["mes"] = pd.to_datetime(df_filtrado["data_dt"]).dt.month
                    
                    # Filtro estrito por mês do evento (Evita distorções de competência forçada)
                    df_filtrado = df_filtrado[(df_filtrado["ano"] == ano_selected) & (df_filtrado["mes"] == mes_selected_num)]

            df_acumulado_mes_cheio = df_filtrado.copy()

            if janela_tempo == "Últimos 7 Dias" and not df_filtrado.empty:
                df_filtrado = df_filtrado[(df_filtrado["data_dt"] >= (hoje - datetime.timedelta(days=7))) & (df_filtrado["data_dt"] <= hoje)]
            elif janela_tempo == "Somente Hoje" and not df_filtrado.empty:
                df_filtrado = df_filtrado[df_filtrado["data_dt"] == hoje]
            
            if tag_busca and not df_filtrado.empty:
                df_filtrado["descricao_lower"] = df_filtrado["descricao"].fillna("").astype(str).str.lower()
                df_filtrado = df_filtrado[df_filtrado["descricao_lower"].str.contains(tag_busca, na=False)]
                
            # --- CÁLCULO DA MATEMÁTICA LÍQUIDA SÓLIDA ---
            if not df_acumulado_mes_cheio.empty:
                for _, row in df_acumulado_mes_cheio.iterrows():
                    val = float(row["valor"])
                    grupo_item = str(row["grupo_orcamentario"] or "").upper()
                    tipo_mov = str(row.get("tipo") or "").upper()
                    
                    if "ENTRADA" in tipo_mov or "FATURAMENTO" in tipo_mov or "RECEITA" in tipo_mov:
                        if "APORTE" in grupo_item or "🚀" in grupo_item:
                            continue
                        faturamento_extra_mes += val
                    else:
                        if "APORTE" in grupo_item or "🚀" in grupo_item:
                            continue
                        
                        # Separação correta de fluxos de caixa imediato vs crédito
                        if "💳" in str(row.get("tipo") or "") or "CARTÃO" in tipo_mov:
                            fatura_acumulada_mes += val
                        else:
                            gastos_dinheiro_caixa += val
                        
                        # Agrupamento de limites orçamentários
                        if "ESSENCIAL" in grupo_item or "50%" in grupo_item:
                            gastos_essencial += val
                        elif "ESTILO" in grupo_item or "30%" in grupo_item:
                            gastos_estilo += val
                        elif "NEGÓCIO" in grupo_item or "💼" in grupo_item or "CUSTOS" in grupo_item:
                            gastos_negocio += val
                        elif "DÍVIDAS" in grupo_item or "QUITAÇÃO" in grupo_item or "📋" in grupo_item:
                            gastos_dividas += val
                        
    except Exception as e:
        if "JWT expired" in str(e) or "PGRST303" in str(e):
            st.warning("🔒 Sua sessão expirou por segurança. Fazendo login de renovação...")
            deslogar_usuario()
        else:
            st.error(f"Erro no processamento dos dados: {e}")

# --- ORIGENS DE VERDADE MATEMÁTICA ---
saldo_real_exibido = renda_base_usuario + faturamento_extra_mes - gastos_dinheiro_caixa
total_consumido_orcamento = gastos_dinheiro_caixa + fatura_acumulada_mes
receita_total_reconhecida_mes = renda_base_usuario + faturamento_extra_mes
saldo_projetado_fim_mes = saldo_real_exibido + agenda_a_receber_mes - agenda_a_pagar_mes - fatura_acumulada_mes

porcentagem_cartao_renda = (fatura_acumulada_mes / renda_base_usuario) if renda_base_usuario > 0 else 0.0
porcentagem_consumo_total = (total_consumido_orcamento / receita_total_reconhecida_mes) if receita_total_reconhecida_mes > 0 else 0.0
porcentagem_gasto_caixa = (gastos_dinheiro_caixa / receita_total_reconhecida_mes) if receita_total_reconhecida_mes > 0 else 0.0
porcentagem_essencial = (gastos_essencial / (renda_base_usuario * 0.50)) if renda_base_usuario > 0 else 0.0
porcentagem_estilo = (gastos_estilo / (renda_base_usuario * 0.30)) if renda_base_usuario > 0 else 0.0

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Configurações do Usuário")

nova_renda_input = st.sidebar.number_input("Sua Renda Mensal Base (R$):", min_value=0.0, value=renda_base_usuario if renda_base_usuario > 0 else 2500.00, step=50.0, format="%.2f")
if st.sidebar.button("💾 Salvar/Atualizar Renda Base"):
    try:
        supabase.table("movimentacoes").delete().eq("subcategoria", "Renda Base Nativa").eq("user_id", USER_ID).execute()
        supabase.table("movimentacoes").insert({
            "data": str(hoje), "valor": float(nova_renda_input), "tipo": "Faturamento ou Receita (Entrada)",
            "descricao": "[CONFIG_PERFIL] Renda Base", "grupo_orcamentario": "⚙️ CONFIGURAÇÃO",
            "subcategoria": "Renda Base Nativa", "satisfacao": "3 - Indispensável", "user_id": USER_ID
        }).execute()
        st.sidebar.success("Renda salva!")
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Erro: {e}")

LIMITE_ESSENCIAL = renda_base_usuario * 0.50       
text_limite_essencial = f"R$ {LIMITE_ESSENCIAL:,.2f}" if LIMITE_ESSENCIAL > 0 else "Não Definido"
LIMITE_ESTILO_DE_VIDA = renda_base_usuario * 0.30  
text_limite_estilo = f"R$ {LIMITE_ESTILO_DE_VIDA:,.2f}" if LIMITE_ESTILO_DE_VIDA > 0 else "Não Definido"

lista_nomes_dividas = [d["nome"] for d in lista_dividas_cadastradas] if lista_dividas_cadastradas else ["Empréstimos Bancários", "Cartão de Crédito Atrasado"]
comprometimento_parcelas_mensais = sum([d["parcela"] for d in lista_dividas_cadastradas])
indice_comprometimento = (comprometimento_parcelas_mensais / renda_base_usuario * 100) if renda_base_usuario > 0 else 0.0
lista_porquinhos_existentes = list(dicionario_metas_alvo.keys())
if not lista_porquinhos_existentes:
    lista_porquinhos_existentes = ["🧱 Reserva de Emergência", "🏡 Comprar Casa"]

MAPA_CATEGORIAS = {
    "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)": [
        "Alimentação Básica & Mercado", 
        "Contas Fixas (Luz, Água, Internet)", 
        "Habitação (Aluguel / Financiamento)", 
        "Saúde & Medicamentos", 
        "Transporte & Combustível",
        "👶 Pensão / Filho"
    ],
    "🟡 30% Estilo de Vida (Lazer e Custos Voláteis)": [
        "Lazer, Bares & Restaurantes", 
        "Delivery / iFood / Conforto", 
        "Vestuário, Compras & Presentes", 
        "Estética, Cuidados & Academia", 
        "Viagens & Hobbies", 
        "Assinaturas (Netflix, Spotify)"
    ],
    "🚀 20% Aporte para a Liberdade (Investimentos e Futuro)": lista_porquinhos_existentes + ["➕ [Criar Nova Meta / Porquinho]"],
    "📋 Quitação de Dívidas (Amortizações e Acordos)": lista_nomes_dividas,
    "💼 Custos de Negócio (Projetos e Clínica)": [
        "Ferramentas SaaS & Softwares", 
        "Marketing & Anúncios", 
        "Infraestrutura & Custos Operacionais"
    ]
}

aba_diagnostico, aba_painel, aba_porquinhos, aba_agenda, aba_dividas = st.tabs([
    "🧭 Diagnóstico Financeiro",
    "📊 Painel & Lançamentos", 
    "🐷 Meus Porquinhos & Rumo ao Milhão", 
    "📅 Agenda de Compromissos", 
    "📋 Gestão de Dívidas & Passivos"
])

# ==================== ABA 0 (DIAGNÓSTICO) ====================
with aba_diagnostico:
    st.title("🧭 Diagnóstico Financeiro")
    st.caption("Uma leitura prática do mês para transformar os lançamentos em decisão.")

    pontos_risco = 0
    alertas_diagnostico = []
    recomendacoes_diagnostico = []

    if renda_base_usuario <= 0:
        pontos_risco += 3
        alertas_diagnostico.append("A renda base ainda não foi definida. Sem isso, o diagnóstico perde precisão.")
        recomendacoes_diagnostico.append("Defina sua renda base na barra lateral antes de tomar decisões maiores.")

    if saldo_projetado_fim_mes < 0:
        pontos_risco += 3
        alertas_diagnostico.append("O saldo projetado para o fim do mês está negativo se agenda e fatura forem consideradas.")
        recomendacoes_diagnostico.append("Revise contas agendadas, gastos variáveis e compras no cartão antes de assumir novos compromissos.")
    elif saldo_projetado_fim_mes < (renda_base_usuario * 0.10) and renda_base_usuario > 0:
        pontos_risco += 1
        alertas_diagnostico.append("O saldo projetado está baixo em relação à renda base.")
        recomendacoes_diagnostico.append("Evite gastos não essenciais até criar uma folga maior de caixa.")

    if porcentagem_cartao_renda > 0.50:
        pontos_risco += 3
        alertas_diagnostico.append("A fatura do cartão já passa de 50% da renda base.")
        recomendacoes_diagnostico.append("Priorize reduzir cartão e evite parcelamentos novos neste ciclo.")
    elif porcentagem_cartao_renda > 0.30:
        pontos_risco += 2
        alertas_diagnostico.append("A fatura do cartão já passa de 30% da renda base.")
        recomendacoes_diagnostico.append("Acompanhe o cartão de perto; ele já começa a pressionar o mês seguinte.")
    elif porcentagem_cartao_renda > 0.15:
        pontos_risco += 1
        alertas_diagnostico.append("A fatura do cartão está controlada, mas merece acompanhamento.")

    if porcentagem_essencial > 1.0:
        pontos_risco += 2
        alertas_diagnostico.append("Os gastos essenciais ultrapassaram o limite planejado de 50% da renda.")
        recomendacoes_diagnostico.append("Revise contas fixas, mercado, transporte e compromissos obrigatórios.")

    if porcentagem_estilo > 1.0:
        pontos_risco += 1
        alertas_diagnostico.append("Os gastos de estilo de vida ultrapassaram o limite planejado de 30% da renda.")
        recomendacoes_diagnostico.append("Corte primeiro gastos de lazer, delivery, compras e assinaturas pouco usadas.")

    if indice_comprometimento > 30.0:
        pontos_risco += 3
        alertas_diagnostico.append("As parcelas de dívidas passam de 30% da renda base.")
        recomendacoes_diagnostico.append("Organize uma estratégia de quitação antes de acelerar metas ou compras parceladas.")
    elif indice_comprometimento > 15.0:
        pontos_risco += 2
        alertas_diagnostico.append("As parcelas de dívidas já têm peso relevante na renda.")
        recomendacoes_diagnostico.append("Evite assumir novas parcelas enquanto a dívida não cair.")

    if porcentagem_consumo_total > 1.0:
        pontos_risco += 3
        alertas_diagnostico.append("O consumo total do mês já ultrapassou a renda reconhecida no período.")
        recomendacoes_diagnostico.append("Reavalie o mês imediatamente: o padrão atual está acima da renda registrada.")
    elif porcentagem_consumo_total > 0.85:
        pontos_risco += 2
        alertas_diagnostico.append("O consumo total já passou de 85% da renda reconhecida no período.")
        recomendacoes_diagnostico.append("Reduza gastos variáveis para preservar caixa até o fechamento do mês.")

    if pontos_risco >= 8:
        status_mes = "Crítico"
        mensagem_status = "Seu mês precisa de intervenção. O app indica pressão alta sobre caixa, cartão ou dívidas."
        st.error(f"🚨 Status do mês: {status_mes}")
    elif pontos_risco >= 5:
        status_mes = "Risco"
        mensagem_status = "Seu mês ainda pode ser corrigido, mas já existem sinais claros de pressão financeira."
        st.warning(f"⚠️ Status do mês: {status_mes}")
    elif pontos_risco >= 2:
        status_mes = "Atenção"
        mensagem_status = "Seu mês está administrável, mas alguns indicadores merecem cuidado."
        st.info(f"🟡 Status do mês: {status_mes}")
    else:
        status_mes = "Saudável"
        mensagem_status = "Seu mês parece saudável com base nos dados registrados até agora."
        st.success(f"✅ Status do mês: {status_mes}")

    st.write(mensagem_status)

    col_diag1, col_diag2, col_diag3 = st.columns(3)
    col_diag1.metric("Saldo atual em conta", f"R$ {saldo_real_exibido:,.2f}")
    col_diag2.metric("Saldo projetado fim do mês", f"R$ {saldo_projetado_fim_mes:,.2f}")
    col_diag3.metric("Consumo total da renda", f"{porcentagem_consumo_total * 100:.1f}%")

    col_diag4, col_diag5, col_diag6 = st.columns(3)
    col_diag4.metric("Fatura / renda base", f"{porcentagem_cartao_renda * 100:.1f}%")
    col_diag5.metric("Dívidas / renda base", f"{indice_comprometimento:.1f}%")
    col_diag6.metric("Agenda líquida", f"R$ {(agenda_a_receber_mes - agenda_a_pagar_mes):,.2f}")

    st.markdown("---")
    st.subheader("📌 Leitura dos principais riscos")

    if alertas_diagnostico:
        for alerta in dict.fromkeys(alertas_diagnostico):
            st.write(f"- {alerta}")
    else:
        st.write("- Nenhum risco relevante identificado com os dados atuais.")

    st.markdown("---")
    st.subheader("🎯 Próximas ações recomendadas")

    if recomendacoes_diagnostico:
        for recomendacao in dict.fromkeys(recomendacoes_diagnostico):
            st.write(f"- {recomendacao}")
    else:
        st.write("- Continue registrando as movimentações e mantenha a fatura sob controle.")

    st.markdown("---")
    st.subheader("📊 Barras de controle")

    st.write(f"💳 Cartão de crédito: {porcentagem_cartao_renda * 100:.1f}% da renda base")
    st.progress(min(porcentagem_cartao_renda, 1.0))

    st.write(f"🔴 Essencial: {porcentagem_essencial * 100:.1f}% do limite de 50%")
    st.progress(min(porcentagem_essencial, 1.0))

    st.write(f"🟡 Estilo de vida: {porcentagem_estilo * 100:.1f}% do limite de 30%")
    st.progress(min(porcentagem_estilo, 1.0))

    st.write(f"📋 Dívidas: {indice_comprometimento:.1f}% da renda base")
    st.progress(min(indice_comprometimento / 100, 1.0))

# ==================== ABA 1 ====================
with aba_painel:
    st.title("Meu Planner Financeiro")
    
    st.markdown(f"### 👑 Gestão de Teto Orçamentário ({lista_meses[mes_selected_num]})")
    c_caixa1, c_caixa2, c_caixa3 = st.columns(3)
    c_caixa1.metric(label="💰 Saldo Atual em Conta", value=f"R$ {saldo_real_exibido:,.2f}", help="Dinheiro físico disponível e líquido na sua conta corrente hoje.")
    c_caixa2.metric(label="📈 Faturamento Extra Capturado", value=f"R$ {faturamento_extra_mes:,.2f}", help="Total de receitas extras geradas neste ciclo mensal.")
    c_caixa3.metric(label="📉 Limite Total Consumido", value=f"R$ {total_consumido_orcamento:,.2f}", help="O impacto total real que seu padrão de vida gerou no seu orçamento (Dinheiro + Cartão).")

    st.markdown("---")
    col_cc_info1, col_cc_info2 = st.columns([2, 5])
    col_cc_info1.write(f"💳 **Fatura Acumulada:** R$ {fatura_acumulada_mes:,.2f}")
    
    porcentagem_cartao_renda = (fatura_acumulada_mes / renda_base_usuario) if renda_base_usuario > 0 else 0.0
    col_cc_info2.progress(min(porcentagem_cartao_renda, 1.0))
    if porcentagem_cartao_renda > 0.5:
        st.caption("⚠️ *Aviso de Risco:* Sua fatura atual já compromete mais de 50% da sua renda base fixa.")

    st.markdown("---")
    st.subheader("📊 Painel de Limites Orçamentários")
    
    st.write(f"🔴 **Gasto Essencial:** R$ {gastos_essencial:,.2f} de {text_limite_essencial}")
    st.progress(min(gastos_essencial / LIMITE_ESSENCIAL, 1.0) if LIMITE_ESSENCIAL > 0 else 0.0)
    st.write(f"🟡 **Estilo de Vida:** R$ {gastos_estilo:,.2f} de {text_limite_estilo}")
    st.progress(min(gastos_estilo / LIMITE_ESTILO_DE_VIDA, 1.0) if LIMITE_ESTILO_DE_VIDA > 0 else 0.0)
    st.write(f"📋 **Quitação de Dívidas Realizada:** R$ {gastos_dividas:,.2f}")
    
    try:
        if not df_filtrado.empty:
            df_saidas = df_filtrado[df_filtrado["tipo"].astype(str).str.contains("Saída|📱|💳", na=False)].copy()
            if not df_saidas.empty:
                st.markdown("---")
                st.subheader("🍩 Distribuição das Despesas Reais")
                df_pizza = df_saidas.groupby("grupo_orcamentario")["valor"].sum().reset_index()
                fig_donut = px.pie(df_pizza, values="valor", names="grupo_orcamentario", hole=0.4, color_discrete_sequence=px.colors.qualitative.Safe)
                fig_donut.update_layout(margin=dict(t=10, b=10, l=10, r=10))
                st.plotly_chart(fig_donut, use_container_width=True)
    except:
        pass

    st.markdown("---")
    st.subheader("📥 Registrar Movimentação Realizada")
    grupo_orcamentario = st.selectbox("Destinação Estratégica do Valor:", list(MAPA_CATEGORIAS.keys()), key="grupo_main")
    categoria = st.selectbox("Subcategoria Correspondente:", MAPA_CATEGORIAS[grupo_orcamentario], key="sub_main")

    criando_novo_porquinho = (categoria == "➕ [Criar Nova Meta / Porquinho]")
    nome_novo_fundo = ""
    val_alvo_novo_fundo = 0.0
    
    if criando_novo_porquinho:
        col_n1, col_n2 = st.columns(2)
        nome_novo_fundo = col_n1.text_input("Nome da Nova Meta:", placeholder="Ex: ✈️ Viagem")
        val_alvo_novo_fundo = col_n2.number_input("Valor Alvo da Meta (R$):", min_value=0.0, value=1000.00, step=50.0)

    tipo = st.radio("Fluxo Financeiro / Meio de Pagamento:", [
        "📱 Saída Dinheiro / Pix (Débito)", 
        "💳 Saída Cartão de Crédito", 
        "Faturamento ou Receita (Entrada)"
    ], horizontal=True, disabled=criando_novo_porquinho)

    is_parcelado = False
    num_parcelas = 1
    if tipo == "💳 Saída Cartão de Crédito" and not criando_novo_porquinho:
        col_p1, col_p2 = st.columns(2)
        is_parcelado = col_p1.checkbox("Esta compra é parcelada?")
        if is_parcelado:
            num_parcelas = col_p2.number_input("Número de parcelas:", min_value=2, max_value=24, value=2, step=1)

    with st.form("formulario_envio_blindado", clear_on_submit=True):
        valor = st.number_input("Qual o valor total da operação? (R$)", min_value=0.0, step=0.01, format="%.2f") if not is_parcelado else st.number_input("Qual o valor de CADA PARCELA? (R$)", min_value=0.0, step=0.01, format="%.2f")
        data_movimento = st.date_input("Data do evento:", datetime.date.today())
        descricao = st.text_input("Descrição ou Estabelecimento:")
        satisfacao = st.select_slider("🧠 Nível de necessidade?", options=["1 - Impulsivo / Evitável", "2 - Útil / Desejável", "3 - Indispensável"], value="2 - Útil / Desejável")
        botao_enviar = st.form_submit_button("Confirmar Lançamento")
        
    if botao_enviar and supabase:
        final_subcat = nome_novo_fundo.strip() if criando_novo_porquinho else categoria
        final_desc = f"Meta Criada: {final_subcat}" if criando_novo_porquinho else descricao.strip()
        final_tipo = "Faturamento ou Receita (Entrada)" if criando_novo_porquinho else tipo
        valor_para_salvar = float(val_alvo_novo_fundo) if criando_novo_porquinho else float(valor)

        if criando_novo_porquinho and not final_subcat:
            st.warning("Informe o nome da nova meta/porquinho.")
        elif valor_para_salvar <= 0:
            st.warning("Informe um valor maior que zero.")
        elif not final_desc:
            st.warning("Informe uma descrição para o lançamento.")
        else:
            try:
                if is_parcelado and final_tipo == "💳 Saída Cartão de Crédito":
                    base_date = data_movimento
                    for i in range(num_parcelas):
                        num_months = base_date.month - 1 + i
                        year_offset = num_months // 12
                        month_offset = (num_months % 12) + 1

                        try:
                            parcel_date = datetime.date(base_date.year + year_offset, month_offset, base_date.day)
                        except ValueError:
                            next_month_start = datetime.date(base_date.year + year_offset, month_offset + 1, 1) if month_offset < 12 else datetime.date(base_date.year + year_offset + 1, 1, 1)
                            parcel_date = next_month_start - datetime.timedelta(days=1)

                        desc_parcela = f"{final_desc} ({i+1}/{num_parcelas})"
                        supabase.table("movimentacoes").insert({
                            "data": str(parcel_date), "valor": valor_para_salvar, "tipo": final_tipo,
                            "descricao": desc_parcela, "grupo_orcamentario": grupo_orcamentario,
                            "subcategoria": final_subcat, "satisfacao": satisfacao, "user_id": USER_ID
                        }).execute()
                else:
                    supabase.table("movimentacoes").insert({
                        "data": str(data_movimento), "valor": valor_para_salvar, "tipo": final_tipo,
                        "descricao": final_desc, "grupo_orcamentario": grupo_orcamentario,
                        "subcategoria": final_subcat, "satisfacao": satisfacao, "user_id": USER_ID
                    }).execute()

                st.success("✅ Lançamento computado perfeitamente!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar movimentação: {e}")

    # --- 📋 SEÇÃO DE LANÇAMENTOS ---
    st.markdown("---")
    st.subheader("📋 Gerenciar Lançamentos do Período")
    
    if supabase and not df_filtrado.empty:
        df_editor = df_filtrado[["id", "data", "descricao", "grupo_orcamentario", "subcategoria", "valor", "tipo"]].copy()
        df_editor.columns = ["ID", "Data", "Descrição", "Grupo", "Subcategoria", "Valor (R$)", "Meio / Tipo"]
        
        dados_editados = st.data_editor(
            data=df_editor,
            use_container_width=True,
            hide_index=True,
            disabled=["ID", "Grupo", "Subcategoria"],
            num_rows="fixed"
        )
        
        if st.button("💾 Salvar Alterações da Tabela"):
            try:
                linhas_atuais_ids = set(dados_editados["ID"].dropna().astype(int).tolist())
                linhas_originais_ids = set(df_editor["ID"].astype(int).tolist())
                
                for id_del in (linhas_originais_ids - linhas_atuais_ids):
                    supabase.table("movimentacoes").delete().eq("id", id_del).eq("user_id", USER_ID).execute()
                    
                for _, row in dados_editados.iterrows():
                    if pd.notna(row["ID"]):
                        row_id = int(row["ID"])
                        supabase.table("movimentacoes").update({
                            "descricao": str(row["Descrição"]),
                            "valor": float(row["Valor (R$)"]),
                            "tipo": str(row["Meio / Tipo"]),
                            "data": str(row["Data"])
                        }).eq("id", row_id).eq("user_id", USER_ID).execute()
                        
                st.success("🔄 Alterações guardadas com total estabilidade!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao processar lote de atualizações: {e}")
    else:
        st.info("Nenhum lançamento efetuado ou encontrado para os filtros selecionados.")

# ==================== ABA 2 (PORQUINHOS) ====================
with aba_porquinhos:
    st.title("🐷 Meus Porquinhos & Metas Individuais")
    total_patrimonio_guardado = 0.0
    
    if dicionario_metas_alvo:
        for nome_meta, valor_alvo in dicionario_metas_alvo.items():
            guardado = dicionario_aportes_acumulados.get(nome_meta, 0.0)
            total_patrimonio_guardado += guardado
            st.subheader(f"{nome_meta}")
            c1, c2, c3 = st.columns(3)
            c1.metric(label="Valor Alvo Final", value=f"R$ {valor_alvo:,.2f}")
            c2.metric(label="Total Já Guardado", value=f"R$ {guardado:,.2f}")
            c3.metric(label="Quanto Falta", value=f"R$ {max(valor_alvo - guardado, 0.0):,.2f}")
            st.progress(min(guardado / valor_alvo, 1.0) if valor_alvo > 0 else 0.0)
            st.markdown("---")
    else:
        st.info("Nenhum porquinho ou meta de investimento criada ainda.")

# ==================== ABA 3 (AGENDA) ====================
with aba_agenda:
    st.title("📅 Agenda de Compromissos Financeiros")
    
    st.markdown("### 📊 Fluxo de Caixa Projetado da Agenda")
    col_ag1, col_ag2 = st.columns(2)
    col_ag1.metric(label="📉 Contas Agendadas a Pagar", value=f"R$ {agenda_a_pagar_mes:,.2f}")
    col_ag2.metric(label="🟢 Recebimentos Agendados", value=f"R$ {agenda_a_receber_mes:,.2f}")
    
    st.markdown("---")
    col_agenda1, col_agenda2 = st.columns(2)
    with col_agenda1:
        st.subheader("📌 Agendar Conta Fixa (A Pagar)")
        with st.form("form_agenda_pagar", clear_on_submit=True):
            name_boleto = st.text_input("Nome da Conta / Boleto:")
            valor_boleto = st.number_input("Valor Estimado (R$):", min_value=0.0, step=0.01)
            vencimento_boleto = st.date_input("Data de Vencimento:", datetime.date.today())
            if st.form_submit_button("Agendar Conta Fixa") and name_boleto and valor_boleto > 0:
                supabase.table("movimentacoes").insert({"data": str(vencimento_boleto), "valor": float(valor_boleto), "tipo": "📱 Saída Dinheiro / Pix (Débito)", "descricao": f"[AGENDA COMPROMISSO] {name_boleto}", "grupo_orcamentario": "📅 AGENDA: CONTAS A PAGAR", "subcategoria": "Conta Fixa", "satisfacao": "3 - Indispensável", "user_id": USER_ID}).execute()
                st.rerun()
                
    with col_agenda2:
        st.subheader("💰 Agendar Valor (A Receber)")
        with st.form("form_agenda_receber", clear_on_submit=True):
            nome_recebivel = st.text_input("O que tem a receber?:")
            valor_recebivel = st.number_input("Valor (R$):", min_value=0.0, step=0.01)
            data_recebivel = st.date_input("Data de Expectativa:", datetime.date.today())
            if st.form_submit_button("Agendar Recebimento") and nome_recebivel and valor_recebivel > 0:
                supabase.table("movimentacoes").insert({"data": str(data_recebivel), "valor": float(valor_recebivel), "tipo": "Faturamento ou Receita (Entrada)", "descricao": f"[AGENDA COMPROMISSO] {nome_recebivel}", "grupo_orcamentario": "📅 AGENDA: CONTAS A RECEBER", "subcategoria": "Valores a Receber", "satisfacao": "3 - Indispensável", "user_id": USER_ID}).execute()
                st.rerun()

    st.markdown("---")
    st.subheader("📋 Seus Compromissos Mapeados")
    if supabase and not df_todos_dados.empty:
        df_agenda_pura = df_todos_dados[df_todos_dados["grupo_orcamentario"].astype(str).str.upper().str.contains("AGENDA", na=False)].copy()
        if not df_agenda_pura.empty:
            df_agenda_pura = df_agenda_pura.sort_values(by="data")
            
            for idx, row in df_agenda_pura.iterrows():
                id_item = int(row["id"])
                desc_pura = str(row["descricao"]).replace("[AGENDA COMPROMISSO] ", "")
                valor_item = float(row["valor"])
                
                col_c1, col_c2, col_c3 = st.columns([4, 2, 2])
                col_c1.write(f"📅 **{row['data']}** - {desc_pura} | **R$ {valor_item:,.2f}**")
                
                if "PAGAR" in str(row["grupo_orcamentario"]).upper():
                    col_c2.caption("🔴 A Pagar")
                    if col_c3.button("✅ Pagar", key=f"pay_{id_item}"):
                        supabase.table("movimentacoes").delete().eq("id", id_item).eq("user_id", USER_ID).execute()
                        supabase.table("movimentacoes").insert({"data": str(hoje), "valor": valor_item, "tipo": "📱 Saída Dinheiro / Pix (Débito)", "descricao": f"{desc_pura} (Pago)", "grupo_orcamentario": "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)", "subcategoria": "Contas Fixas (Luz, Água, Internet)", "satisfacao": "3 - Indispensável", "user_id": USER_ID}).execute()
                        st.rerun()
                else:
                    col_c2.caption("🟢 A Receber")
                    if col_c3.button("💰 Receber", key=f"rec_{id_item}"):
                        supabase.table("movimentacoes").delete().eq("id", id_item).eq("user_id", USER_ID).execute()
                        supabase.table("movimentacoes").insert({"data": str(hoje), "valor": valor_item, "tipo": "Faturamento ou Receita (Entrada)", "descricao": f"{desc_pura} (Recebido)", "grupo_orcamentario": "🔴 50% Essencial (Sobrevivência e Obrigações Fixas)", "subcategoria": "Renda Base Nativa", "satisfacao": "3 - Indispensável", "user_id": USER_ID}).execute()
                        st.rerun()

# ==================== ABA 4 (GESTÃO DE DÍVIDAS) ====================
with aba_dividas:
    st.title("📋 Controle Estrutural de Passivos e Dívidas")
    
    divida_bruta_total = sum([d["valor_original"] for d in lista_dividas_cadastradas])
    total_amortizado_historico = sum(amortizacoes_totais_historicas.values())
    divida_restante_real = max(divida_bruta_total - total_amortizado_historico, 0.0)
    
    c_div1, c_div2, c_div3 = st.columns(3)
    c_div1.metric(label="🚨 Saldo Devedor Restante", value=f"R$ {divida_restante_real:,.2f}")
    c_div2.metric(label="📉 Comprometimento de Renda", value=f"{indice_comprometimento:.1f}%")
    c_div3.metric(label="✅ Total Amortizado", value=f"R$ {total_amortizado_historico:,.2f}")
    
    if indice_comprometimento > 30.0:
        st.error(f"⚠️ Atenção Crítica: Suas parcelas de passivos consomem {indice_comprometimento:.1f}% da sua Renda.")
    elif indice_comprometimento > 0:
        st.warning(f"⚡ Atenção: {indice_comprometimento:.1f}% da sua renda está comprometida com dívidas.")

    st.markdown("---")
    st.subheader("🚀 Cadastrar Nova Dívida Estrutural")
    with st.form("form_cadastro_divida_passiva", clear_on_submit=True):
        col_d1, col_d2, col_d3 = st.columns(3)
        nome_credor = col_d1.text_input("Nome da Dívida / Credor:")
        saldo_devedor_inicial = col_d2.number_input("Valor Total Atual (R$):", min_value=0.0, step=100.0)
        valor_parcela_mensal = col_d3.number_input("Valor da Parcela Mensal (R$):", min_value=0.0, step=10.0)
        
        if st.form_submit_button("Registrar Passivo no Sistema") and nome_credor and saldo_devedor_inicial > 0:
            try:
                supabase.table("movimentacoes").insert({
                    "data": str(hoje), "valor": float(saldo_devedor_inicial), "tipo": "📱 Saída Dinheiro / Pix (Débito)",
                    "descricao": "[DIVIDA_ATIVA] Registro de Passivo Estrutural", "grupo_orcamentario": "📋 QUITAÇÃO DE DÍVIDAS (ATIVO)",
                    "subcategoria": nome_credor, "satisfacao": f"{valor_parcela_mensal} - Parcela Cadastrada", "user_id": USER_ID
                }).execute()
                st.success("✅ Dívida estrutural integrada!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao registrar passivo: {e}")

    if lista_dividas_cadastradas:
        st.markdown("---")
        st.subheader("📊 Evolução e Quitação dos Passivos")
        
        for divida in lista_dividas_cadastradas:
            nome = divida["nome"]
            original = divida["valor_original"]
            pago = amortizacoes_totais_historicas.get(nome, 0.0)
            restante = max(original - pago, 0.0)
            
            st.write(f"💳 **{nome}** (Parcela Mensal: R$ {divida['parcela']:,.2f})")
            col_l1, col_l2, col_l3 = st.columns(3)
            col_l1.caption(f"Dívida Original: R$ {original:,.2f}")
            col_l2.caption(f"Restante Atual: R$ {restante:,.2f}")
            col_l3.caption(f"Amortizado: R$ {pago:,.2f}")
            
            progresso = min(pago / original, 1.0) if original > 0 else 0.0
            st.progress(progresso)
            
            if st.button(f"🗑️ Remover Registro da Dívida: {nome}", key=f"del_div_{divida['id']}"):
                try:
                    supabase.table("movimentacoes").delete().eq("id", divida["id"]).eq("user_id", USER_ID).execute()
                    st.success("Registro removido do painel!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao deletar: {e}")
            st.markdown("<br>", unsafe_allow_html=True)
