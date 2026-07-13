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

    def _url_movimentacoes(self) -> str:
        return f"{self.base_url}/rest/v1/movimentacoes"

    def _validar_resposta(
        self,
        resposta: httpx.Response,
        operacao: str,
        codigos_aceitos: tuple[int, ...],
    ) -> None:
        if resposta.status_code not in codigos_aceitos:
            raise RuntimeError(
                f"{operacao} retornou HTTP "
                f"{resposta.status_code}: "
                f"{resposta.text[:500]}"
            )

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
                self._url_movimentacoes(),
                headers=self.headers,
                params=parametros,
            )

        self._validar_resposta(
            resposta,
            "Consulta",
            (200, 206),
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

    def criar_movimentacao(self, payload: dict) -> dict:
        registro = {
            **payload,
            "user_id": self.user_id,
        }

        headers = {
            **self.headers,
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

        with httpx.Client(timeout=25.0) as cliente:
            resposta = cliente.post(
                self._url_movimentacoes(),
                headers=headers,
                json=registro,
            )

        self._validar_resposta(
            resposta,
            "Cadastro",
            (200, 201),
        )

        dados = resposta.json()

        if (
            not isinstance(dados, list)
            or not dados
            or dados[0].get("id") is None
        ):
            raise RuntimeError(
                "O banco não confirmou o cadastro "
                "com um identificador seguro."
            )

        return dados[0]

    def atualizar_movimentacao(
        self,
        registro_id,
        payload: dict,
    ) -> dict:
        headers = {
            **self.headers,
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

        parametros = [
            ("id", f"eq.{registro_id}"),
            ("user_id", f"eq.{self.user_id}"),
        ]

        with httpx.Client(timeout=25.0) as cliente:
            resposta = cliente.patch(
                self._url_movimentacoes(),
                headers=headers,
                params=parametros,
                json=payload,
            )

        self._validar_resposta(
            resposta,
            "Edição",
            (200, 204),
        )

        if resposta.status_code == 204 or not resposta.text.strip():
            return payload

        dados = resposta.json()

        if isinstance(dados, list) and dados:
            return dados[0]

        if isinstance(dados, dict):
            return dados

        return payload

    def excluir_movimentacao(self, registro_id) -> None:
        headers = {
            **self.headers,
            "Prefer": "return=representation",
        }

        parametros = [
            ("id", f"eq.{registro_id}"),
            ("user_id", f"eq.{self.user_id}"),
        ]

        with httpx.Client(timeout=25.0) as cliente:
            resposta = cliente.delete(
                self._url_movimentacoes(),
                headers=headers,
                params=parametros,
            )

        self._validar_resposta(
            resposta,
            "Exclusão",
            (200, 204),
        )

    def cadastrar_compromisso(
        self,
        *,
        descricao: str,
        natureza: str,
        data_compromisso: datetime.date,
        valor: float,
        categoria: str,
    ) -> dict:
        eh_recebimento = natureza.strip() == "A receber"

        return self.criar_movimentacao({
            "data": data_compromisso.isoformat(),
            "descricao": (
                f"[AGENDA COMPROMISSO] {descricao.strip()}"
            ),
            "grupo_orcamentario": (
                "AGENDA - A RECEBER"
                if eh_recebimento
                else "AGENDA - A PAGAR"
            ),
            "subcategoria": categoria.strip(),
            "valor": float(valor),
            "satisfacao": "3 - Indispensável",
            "tipo": "Entrada" if eh_recebimento else "Saída",
        })

    def atualizar_compromisso(
        self,
        compromisso_id,
        *,
        descricao: str,
        natureza: str,
        data_compromisso: datetime.date,
        valor: float,
        categoria: str,
    ) -> dict:
        eh_recebimento = natureza.strip() == "A receber"

        return self.atualizar_movimentacao(
            compromisso_id,
            {
                "data": data_compromisso.isoformat(),
                "descricao": (
                    f"[AGENDA COMPROMISSO] {descricao.strip()}"
                ),
                "grupo_orcamentario": (
                    "AGENDA - A RECEBER"
                    if eh_recebimento
                    else "AGENDA - A PAGAR"
                ),
                "subcategoria": categoria.strip(),
                "valor": float(valor),
                "satisfacao": "3 - Indispensável",
                "tipo": (
                    "Entrada"
                    if eh_recebimento
                    else "Saída"
                ),
            },
        )

    def baixar_compromisso(
        self,
        compromisso_id,
        *,
        descricao: str,
        natureza: str,
        data_baixa: datetime.date,
        valor: float,
        grupo_destino: str,
        categoria_destino: str,
    ) -> dict:
        """
        Cria o lançamento real e remove o compromisso.

        Se a exclusão do compromisso falhar, tenta apagar o lançamento
        recém-criado para evitar duplicidade.
        """
        eh_recebimento = natureza.strip() == "A receber"

        novo_registro = self.criar_movimentacao({
            "data": data_baixa.isoformat(),
            "descricao": (
                f"{descricao.strip()} "
                f"({'Recebido' if eh_recebimento else 'Pago'})"
            ),
            "grupo_orcamentario": (
                "RECEITAS"
                if eh_recebimento
                else grupo_destino.strip()
            ),
            "subcategoria": categoria_destino.strip(),
            "valor": float(valor),
            "satisfacao": "3 - Indispensável",
            "tipo": (
                "Faturamento ou Receita (Entrada)"
                if eh_recebimento
                else "Saída Dinheiro / Pix (Débito)"
            ),
        })

        novo_id = novo_registro["id"]

        try:
            self.excluir_movimentacao(compromisso_id)
        except Exception as erro_exclusao:
            try:
                self.excluir_movimentacao(novo_id)
            except Exception as erro_rollback:
                raise RuntimeError(
                    "Falha crítica: o lançamento real foi criado, "
                    "mas o compromisso não foi removido e o sistema "
                    "também não conseguiu desfazer o lançamento. "
                    "Confira os registros antes de tentar novamente. "
                    f"Erro original: {erro_exclusao}. "
                    f"Erro ao desfazer: {erro_rollback}"
                ) from erro_rollback

            raise RuntimeError(
                "A baixa foi desfeita porque o compromisso "
                "não pôde ser removido."
            ) from erro_exclusao

        return novo_registro

    def buscar_configuracao_saldo(self) -> dict | None:
        registros = self.buscar_movimentacoes(
            filtros=[
                (
                    "descricao",
                    "eq.[CONFIG_SALDO_INICIAL] Conta Principal",
                )
            ],
            order="data.desc",
            limit=100,
        )

        if not registros:
            return None

        def timestamp_config(registro: dict) -> float:
            texto = str(registro.get("satisfacao") or "")

            for parte in texto.split("|"):
                parte = parte.strip()

                if parte.startswith("SETUP_TS:"):
                    try:
                        return float(
                            parte.split(":", 1)[1].strip()
                        )
                    except (TypeError, ValueError):
                        return 0.0

            return 0.0

        return max(
            registros,
            key=timestamp_config,
        )

    def salvar_configuracao_saldo(
        self,
        *,
        data_inicio: datetime.date,
        saldo_atual_informado: float,
        saldo_inicial_tecnico: float,
        fluxo_liquido_existente: float,
        setup_timestamp: float,
    ) -> dict:
        antigas = self.buscar_movimentacoes(
            filtros=[
                (
                    "descricao",
                    "eq.[CONFIG_SALDO_INICIAL] Conta Principal",
                )
            ],
            select="id,user_id",
            limit=100,
        )

        nova = self.criar_movimentacao({
            "data": data_inicio.isoformat(),
            "descricao": (
                "[CONFIG_SALDO_INICIAL] Conta Principal"
            ),
            "grupo_orcamentario": "CONFIGURAÇÃO",
            "subcategoria": "Saldo Inicial da Conta",
            "valor": float(saldo_inicial_tecnico),
            "satisfacao": (
                f"SETUP_TS:{float(setup_timestamp)}"
                f"|SALDO_ATUAL:{float(saldo_atual_informado)}"
                f"|FLUXO_EXISTENTE:{float(fluxo_liquido_existente)}"
            ),
            "tipo": "Configuração",
        })

        novo_id = nova.get("id")

        for antiga in antigas:
            id_antigo = antiga.get("id")

            if id_antigo is None or id_antigo == novo_id:
                continue

            try:
                self.excluir_movimentacao(id_antigo)
            except Exception:
                # A configuração mais recente continua prevalecendo
                # pelo SETUP_TS salvo nos metadados.
                pass

        return nova
