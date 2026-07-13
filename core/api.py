import datetime
from typing import Iterable

import httpx


class SupabaseRestClient:
    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
        access_token: str,
        user_id: str,
    ) -> None:
        self.base_url = supabase_url.rstrip("/")
        self.headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        self.user_id = user_id

    def buscar_movimentacoes(
        self,
        *,
        filtros: Iterable[tuple[str, str]] | None = None,
        select: str = (
            "id,data,descricao,grupo_orcamentario,"
            "subcategoria,valor,satisfacao,tipo,user_id"
        ),
        order: str = "data.desc",
        limit: int = 1000,
    ) -> list[dict]:
        parametros = [
            ("select", select),
            ("user_id", f"eq.{self.user_id}"),
            ("order", order),
            ("limit", str(limit)),
        ]

        if filtros:
            parametros.extend(filtros)

        with httpx.Client(timeout=25.0) as cliente:
            resposta = cliente.get(
                f"{self.base_url}/rest/v1/movimentacoes",
                headers=self.headers,
                params=parametros,
            )

        if resposta.status_code not in (200, 206):
            raise RuntimeError(
                f"Consulta retornou HTTP "
                f"{resposta.status_code}: "
                f"{resposta.text[:500]}"
            )

        dados = resposta.json()

        if not isinstance(dados, list):
            raise RuntimeError(
                "O banco retornou um formato inesperado."
            )

        return dados

    def buscar_mes(
        self,
        ano: int,
        mes: int,
        *,
        limit: int = 1000,
    ) -> list[dict]:
        inicio = datetime.date(ano, mes, 1)

        if mes == 12:
            fim = datetime.date(ano + 1, 1, 1)
        else:
            fim = datetime.date(ano, mes + 1, 1)

        return self.buscar_movimentacoes(
            filtros=[
                ("data", f"gte.{inicio.isoformat()}"),
                ("data", f"lt.{fim.isoformat()}"),
            ],
            limit=limit,
        )
