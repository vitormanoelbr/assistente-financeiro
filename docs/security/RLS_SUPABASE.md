# Segurança multiusuário — Supabase RLS

Antes de disponibilizar o aplicativo para um segundo usuário, audite as políticas atuais da tabela `public.movimentacoes`.

Objetivo:
- usuário A só lê seus registros;
- usuário A só cria registros para si;
- usuário A só atualiza seus registros;
- usuário A só exclui seus registros.

Política de referência, somente após revisar o tipo de `user_id` e as políticas existentes:

```sql
alter table public.movimentacoes enable row level security;

create policy "authenticated_users_manage_own_movements"
on public.movimentacoes
for all
to authenticated
using (auth.uid()::text = user_id::text)
with check (auth.uid()::text = user_id::text);
```

Não execute automaticamente se já houver política equivalente.

## Teste obrigatório antes de convidar outro usuário
1. Criar usuário A.
2. Criar usuário B.
3. Criar registro para A.
4. Autenticar como B.
5. Tentar ler, editar e excluir o registro de A.
6. Todos os acessos devem ser negados/ocultados pelo banco.
