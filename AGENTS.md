# AGENTS.md — Meu Planner Financeiro

Este repositório é um aplicativo financeiro pessoal multiusuário.
As regras abaixo são obrigatórias para qualquer agente que altere o código.

## Branch e entrega
- Trabalhar na branch `nova-arquitetura`.
- Não fazer merge direto em `main`.
- Produção só recebe mudanças após testes e revisão.

## Arquitetura
- Não voltar para um `app.py` monolítico.
- Cada área funcional deve ficar em módulo próprio.
- A interface Streamlit não deve concentrar regras financeiras.
- Cada página consulta apenas os dados necessários.
- Não carregar todos os módulos e todos os dados em cada rerun.

## Supabase
- Usar HTTP/REST.
- Não reintroduzir o SDK do Supabase sem decisão explícita.
- Toda leitura, atualização e exclusão deve ser limitada ao `user_id` autenticado.
- Nunca remover o filtro de usuário como otimização.
- Nunca apagar dados ou executar migração destrutiva sem autorização explícita.
- RLS no Supabase é obrigatório antes de disponibilizar o app a um segundo usuário.

## Invariantes
Consulte `docs/rules/`.

Regras fundamentais:
- renda-base não é saldo bancário;
- compra no cartão não reduz a conta no momento da compra;
- pagamento da fatura reduz a conta;
- Agenda futura afeta projeção, não saldo realizado;
- baixa da Agenda deve gerar exatamente uma movimentação real;
- exclusão de Agenda sem baixa não cria movimentação;
- configurações internas não são receita nem despesa;
- dados de usuários diferentes nunca podem ser misturados.

## Harness
Antes de concluir qualquer mudança:

```bash
python -m pytest -q
```

Todos os testes precisam passar.

Se uma mudança legítima exigir alterar um teste:
1. identifique a regra alterada;
2. atualize `docs/rules/`;
3. explique o motivo;
4. só então atualize o teste.

Nunca altere um teste apenas para fazer o código passar.

## Baseline V1
Já validados:
- autenticação;
- isolamento de usuário no cliente REST;
- Diagnóstico;
- Conta / saldo;
- Agenda: leitura, cadastro, edição, baixa e exclusão.

## Critério de conclusão
Uma tarefa só está concluída quando:
- código compila;
- harness passa;
- regras continuam satisfeitas;
- regressões conhecidas não foram introduzidas;
- limitações restantes foram declaradas.
