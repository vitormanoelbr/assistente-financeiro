# Regras — Saldo

- **SALDO-001** Renda-base é referência orçamentária e não altera automaticamente o saldo bancário.
- **SALDO-002** Entradas efetivamente recebidas aumentam o saldo.
- **SALDO-003** Saídas efetivamente pagas reduzem o saldo.
- **SALDO-004** Compra no cartão não reduz o saldo no momento da compra.
- **SALDO-005** Pagamento da fatura reduz o saldo.
- **SALDO-006** Compromissos futuros da Agenda não alteram o saldo realizado.
- **SALDO-007** Reconciliação deve impedir dupla contagem de movimentos já refletidos no extrato.
- **SALDO-008** Registros de configuração não são receita nem despesa.

Fórmula-base:

`saldo técnico inicial + entradas reais - saídas reais = saldo calculado`
