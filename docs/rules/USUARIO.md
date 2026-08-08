# Regras — Usuário e isolamento

- **USER-001** Todo dado financeiro pertence a exatamente um usuário autenticado.
- **USER-002** Nenhuma consulta financeira pode misturar dados de usuários diferentes.
- **USER-003** Um usuário só pode criar registros associados ao próprio `user_id`.
- **USER-004** Um usuário só pode alterar ou excluir registros do próprio `user_id`.
- **USER-005** Saldo, configurações, cartões, Agenda e demais dados são individuais.
- **USER-006** O onboarding é individual.
- **USER-007** O filtro `user_id` no aplicativo não substitui Row Level Security no banco.
