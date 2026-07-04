# --- 🛡️ MOTOR DO GRÁFICO TOTALMENTE BLINDADO (ANTI-TRAVAMENTO) ---
    if not df_filtrado.empty:
        try:
            # Isolamos os dados limpando o que for agenda ou criação de meta
            df_raiox_limpo = df_filtrado[~df_filtrado["grupo_orcamentario"].str.contains("📅 AGENDA", na=False)].copy()
            df_raiox_limpo = df_raiox_limpo[~df_raiox_limpo["descricao"].str.contains("Meta Criada", na=False)]
            
            # Verificamos se a coluna existe e se não está totalmente vazia
            if not df_raiox_limpo.empty and "satisfacao" in df_raiox_limpo.columns:
                st.markdown("---")
                st.subheader("🧠 Raio-X de Necessidade Real (Mês Filtrado)")
                
                # Tratamento de nulos: se tiver algo vazio, vira "2 - Útil" por padrão para não quebrar
                df_raiox_limpo["satisfacao"] = df_raiox_limpo["satisfacao"].fillna("2 - Útil / Desejável").astype(str)
                
                # Pegamos apenas o primeiro caractere com segurança
                df_raiox_limpo["nivel_bruto"] = df_raiox_limpo["satisfacao"].str[0]
                
                # Agrupamos e limpamos o index
                df_necessidade = df_raiox_limpo.groupby("nivel_bruto")["valor"].sum().reset_index()
                
                # Mapeamento explícito
                mapa_nomes = {"1": "🚨 1 - Impulsivo / Evitável", "2": "🟡 2 - Útil / Desejável", "3": "🟢 3 - Indispensável"}
                df_necessidade["Nível de Importância"] = df_necessidade["nivel_bruto"].map(mapa_nomes).fillna("🟡 2 - Útil / Desejável")
                
                df_necessidade["Total Gasto (R$)"] = df_necessidade["valor"].astype(float)
                
                # Geramos o gráfico finais apenas com colunas geradas manualmente
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
            # Se der qualquer erro bizarro aqui dentro, o Streamlit ignora o gráfico e não quebra a página!
            st.warning("📊 O painel gráfico está sendo recalculado ou os dados salvos estão incompletos.")
