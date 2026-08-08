# Regression Matrix V1

| Área | Invariante | Teste |
|---|---|---|
| Segurança | busca inclui `user_id` | `test_busca_sempre_filtra_usuario` |
| Segurança | update inclui `user_id` | `test_update_sempre_filtra_usuario` |
| Segurança | delete inclui `user_id` | `test_delete_sempre_filtra_usuario` |
| Saldo | entrada/saída afetam caixa | `test_entrada_e_saida_afetam_fluxo` |
| Saldo | cartão não reduz caixa | `test_compra_cartao_nao_reduz_caixa` |
| Saldo | Agenda não reduz caixa | `test_agenda_nao_reduz_caixa` |
| Saldo | configuração não altera caixa | `test_configuracao_nao_afeta_caixa` |
| Agenda | baixa a pagar cria saída | `test_baixa_a_pagar_cria_saida_real` |
| Agenda | baixa a receber cria entrada | `test_baixa_a_receber_cria_entrada_real` |
| Agenda | falha na exclusão faz rollback | `test_baixa_faz_rollback_se_compromisso_nao_for_removido` |
