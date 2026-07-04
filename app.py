# --- 🛡️ MOTOR DO GRÁFICO TOTALMENTE BLINDADO (ANTI-TRAVAMENTO) ---
    if not df_filtrado.empty:
        try:
            # 1. Tratamos os nulos do DataFrame inteiro para evitar quebras com None
            df_Seguro = df_filtrado.copy()
            df_Seguro["grupo_orcamentario"] = df_Seguro["grupo_orcamentario"].fillna("").astype(str)
            df_Seguro["descricao"] = df_Seguro["descricao"].fillna("").astype(str)
            df_Seguro["satisfacao"] = df_Seguro["satisfacao"].fillna("2 - Útil / Desejável").astype(str)
            
            # 2. Filtramos sem risco de erro de float/None
            df_raiox_limpo = df_Seguro[~df_Seguro["grupo_orcamentario"].str.contains("📅 AGENDA", na=False)].copy()
            df_raiox_limpo = df_raiox_limpo[~df_raiox_limpo["descricao"].str.contains("Meta Criada", na=False)]
            
            if not df_raiox_limpo.empty:
                st.markdown("---")
                st.subheader("🧠 Raio-X de Necessidade Real (Mês Filtrado)")
                
                # 3. Extraímos o primeiro caractere com segurança
                df_raiox_limpo["nivel_bruto"] = df_raiox_limpo["satisfacao"].str.strip().str[0]
                
                # 4. Agrupamento estruturado
                df_necessidade = df_raiox_limpo.groupby("nivel_bruto")["valor"].sum().reset_index()
                
                # 5. Mapeamento dos nomes para exibição
                mapa_nomes = {"1": "🚨 1 - Impulsivo / Evitável", "2": "🟡 2 - Útil / Desejável", "3": "🟢 3 - Indispensável"}
                df_necessidade["Nível de Importância"] = df_necessidade["nivel_bruto"].map(mapa_nomes).fillna("🟡 2 - Útil / Desejável")
                df_necessidade["Total Gasto (R$)"] = df_necessidade["valor"].astype(float)
                
                fig_necessidade = px.bar(
                    df_necessidade, y="Nível de Importância", x="Total Gasto (R$)", 
                    orientation='h', color="Nível de Importância",
                    color_discrete_map={
                        "🚨 1 - Impulsivo / Evitável": "#FF4B4B", 
                        "🟡 2 - Útil / Desejável": "#FFD700", 
                        "🟢 3 - Indispensável": "#00FF66"
                    }
                )
                fig_necessidade.update_layout(showlegend=False, yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_necessidade, use_container_width=True)
            else:
                st.info("💡 Sem dados de necessidade avaliados para gerar o Raio-X neste mês.")
        except Exception as erro_grafico:
            # Se ainda assim algo bizarro acontecer, mostra o erro real na tela para sabermos o que é
            st.warning(f"📊 O painel gráfico está sendo recalculado. Detalhe técnico: {erro_grafico}")
