import datetime
import time

import pandas as pd
import streamlit as st

from core.formatacao import moeda_br, numero_seguro


DESCRICAO_CONFIG_SALDO = (
    "[CONFIG_SALDO_INICIAL] Conta Principal"
)


def extrair_metadado(texto, chave: str, padrao=None):
    prefixo = f"{chave}:"

    for parte in str(texto or "").split("|"):
        parte = parte.strip()

        if parte.startswith(prefixo):
            return parte.split(":", 1)[1].strip()

    return padrao


def classificar_movimento_conta(registro) -> str:
    descricao = str(
        registro.get("descricao") or ""
    ).upper()
    grupo = str(
        registro.get("grupo_orcamentario") or ""
    ).upper()
    tipo_original = str(
        registro.get("tipo") or ""
    )
    tipo = tipo_original.upper()

    if (
        "CONFIG" in grupo
        or "AGENDA" in grupo
        or "[CONFIG_" in descricao
        or "[DIVIDA_ATIVA]" in descricao
    ):
        return "ignorar"

    # A compra no cartão cria uma obrigação, mas não reduz
    # o dinheiro da conta no dia da compra.
    if (
        "CARTÃO" in tipo
        or "CARTAO" in tipo
        or "CRÉDITO" in tipo
        or "CREDITO" in tipo
        or "💳" in tipo_original
    ):
        return "ignorar"

    if any(
        termo in tipo
        for termo in (
            "ENTRADA",
            "RECEITA",
            "FATURAMENTO",
            "RECEBIMENTO",
        )
    ):
        return "entrada"

    if (
        any(
            termo in tipo
            for termo in (
                "SAÍDA",
                "SAIDA",
                "PIX",
                "DÉBITO",
                "DEBITO",
                "PAGAMENTO",
            )
        )
        or "📱" in tipo_original
    ):
        return "saida"

    return "ignorar"


def calcular_fluxo(
    registros: list[dict],
) -> tuple[float, float, int]:
    entradas = 0.0
    saidas = 0.0
    ignorados = 0

    for registro in registros:
        valor = numero_seguro(
            registro.get("valor"),
            0.0,
        )

        if valor <= 0:
            ignorados += 1
            continue

        classe = classificar_movimento_conta(registro)

        if classe == "entrada":
            entradas += valor
        elif classe == "saida":
            saidas += valor
        else:
            ignorados += 1

    return entradas, saidas, ignorados


def buscar_fluxo_periodo(
    api,
    data_inicio: datetime.date,
    data_fim: datetime.date,
) -> list[dict]:
    if data_inicio > data_fim:
        return []

    return api.buscar_movimentacoes(
        filtros=[
            ("data", f"gte.{data_inicio.isoformat()}"),
            (
                "data",
                f"lte.{data_fim.isoformat()}",
            ),
        ],
        order="data.asc",
        limit=5000,
    )


def carregar_resumo_saldo(api) -> dict | None:
    config = api.buscar_configuracao_saldo()

    if not config:
        return None

    data_inicio = pd.to_datetime(
        config.get("data"),
        errors="coerce",
    )

    if pd.isna(data_inicio):
        raise ValueError(
            "A configuração do saldo possui data inválida."
        )

    data_inicio = data_inicio.date()
    saldo_inicial_tecnico = numero_seguro(
        config.get("valor"),
        0.0,
    )

    hoje = datetime.date.today()
    registros = buscar_fluxo_periodo(
        api,
        data_inicio,
        hoje,
    )
    entradas, saidas, ignorados = calcular_fluxo(registros)

    return {
        "config": config,
        "data_inicio": data_inicio,
        "saldo_inicial_tecnico": saldo_inicial_tecnico,
        "entradas": entradas,
        "saidas": saidas,
        "ignorados": ignorados,
        "saldo_atual": (
            saldo_inicial_tecnico
            + entradas
            - saidas
        ),
    }


def renderizar_onboarding(
    api,
    *,
    permitir_cancelar: bool = False,
) -> None:
    hoje = datetime.date.today()

    st.title("Configurar conta principal")
    st.write(
        "Informe o saldo que aparece no seu extrato agora. "
        "O sistema analisará os lançamentos já cadastrados "
        "desde a data escolhida e criará o ponto de partida "
        "correto, sem descontar despesas antigas duas vezes."
    )

    st.info(
        "A renda mensal é usada no orçamento, mas não será "
        "somada automaticamente ao saldo da conta."
    )

    with st.form("form_configurar_saldo"):
        data_inicio = st.date_input(
            "Desde quando os lançamentos existentes devem ser considerados?",
            value=hoje,
            max_value=hoje,
            format="DD/MM/YYYY",
        )

        saldo_atual = st.number_input(
            "Quanto está disponível na conta agora? (R$)",
            value=0.0,
            step=10.0,
            format="%.2f",
        )

        confirmar = st.checkbox(
            "Confirmo que o valor corresponde ao saldo "
            "mostrado no extrato neste momento."
        )

        col1, col2 = st.columns(2)

        salvar = col1.form_submit_button(
            "Confirmar e iniciar",
            width="stretch",
        )

        cancelar = col2.form_submit_button(
            "Cancelar",
            width="stretch",
            disabled=not permitir_cancelar,
        )

    if cancelar and permitir_cancelar:
        st.session_state["reconfigurando_saldo"] = False
        st.rerun()

    if not salvar:
        return

    if not confirmar:
        st.error(
            "Marque a confirmação antes de continuar."
        )
        return

    try:
        registros_existentes = buscar_fluxo_periodo(
            api,
            data_inicio,
            hoje,
        )

        entradas, saidas, _ = calcular_fluxo(
            registros_existentes
        )

        fluxo_liquido_existente = entradas - saidas

        # Esse ajuste faz o saldo calculado bater com o extrato
        # mesmo quando já existem despesas e receitas cadastradas.
        saldo_inicial_tecnico = (
            float(saldo_atual)
            - fluxo_liquido_existente
        )

        api.salvar_configuracao_saldo(
            data_inicio=data_inicio,
            saldo_atual_informado=float(saldo_atual),
            saldo_inicial_tecnico=saldo_inicial_tecnico,
            fluxo_liquido_existente=fluxo_liquido_existente,
            setup_timestamp=time.time(),
        )

        st.session_state["reconfigurando_saldo"] = False
        st.success(
            "Conta configurada e lançamentos existentes "
            "reconciliados."
        )
        st.rerun()

    except Exception as erro:
        st.error(
            "Não foi possível configurar o saldo: "
            f"{type(erro).__name__}: {erro}"
        )


def renderizar(api) -> None:
    if st.session_state.get(
        "reconfigurando_saldo",
        False,
    ):
        renderizar_onboarding(
            api,
            permitir_cancelar=True,
        )
        return

    try:
        resumo = carregar_resumo_saldo(api)
    except Exception as erro:
        st.error(
            "Falha ao calcular o saldo: "
            f"{type(erro).__name__}: {erro}"
        )
        return

    if resumo is None:
        renderizar_onboarding(api)
        return

    hoje = datetime.date.today()
    config = resumo["config"]

    st.title("Conta principal")
    st.caption(
        "Saldo calculado por movimentações reais da conta."
    )

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Saldo calculado hoje",
        moeda_br(resumo["saldo_atual"]),
    )
    col2.metric(
        "Entradas desde o início",
        moeda_br(resumo["entradas"]),
    )
    col3.metric(
        "Saídas desde o início",
        moeda_br(resumo["saidas"]),
    )

    st.caption(
        "Controle iniciado em "
        f"{resumo['data_inicio'].strftime('%d/%m/%Y')}."
    )

    st.markdown("---")
    st.subheader("Próximos 30 dias")

    data_fim = hoje + datetime.timedelta(days=30)

    try:
        agenda = api.buscar_movimentacoes(
            filtros=[
                (
                    "grupo_orcamentario",
                    "ilike.*AGENDA*",
                ),
                ("data", f"gte.{hoje.isoformat()}"),
                ("data", f"lte.{data_fim.isoformat()}"),
            ],
            order="data.asc",
            limit=500,
        )

        pagar = 0.0
        receber = 0.0

        for registro in agenda:
            grupo = str(
                registro.get("grupo_orcamentario") or ""
            ).upper()
            valor = numero_seguro(
                registro.get("valor"),
                0.0,
            )

            if "RECEBER" in grupo:
                receber += valor
            elif "PAGAR" in grupo:
                pagar += valor

        saldo_projetado = (
            resumo["saldo_atual"]
            + receber
            - pagar
        )

        p1, p2, p3 = st.columns(3)
        p1.metric("Agenda a receber", moeda_br(receber))
        p2.metric("Agenda a pagar", moeda_br(pagar))
        p3.metric(
            "Saldo projetado em 30 dias",
            moeda_br(saldo_projetado),
        )

        st.caption(
            "Esta projeção considera somente a Agenda. "
            "Faturas de cartão entrarão quando o módulo "
            "de cartões for migrado."
        )

    except Exception as erro:
        st.warning(
            "O saldo atual foi calculado, mas a projeção "
            "da Agenda não pôde ser carregada: "
            f"{erro}"
        )

    st.markdown("---")

    with st.expander("Como o saldo foi calculado"):
        st.write(
            f"Saldo técnico inicial: "
            f"**{moeda_br(resumo['saldo_inicial_tecnico'])}**"
        )
        st.write(
            f"+ Entradas: **{moeda_br(resumo['entradas'])}**"
        )
        st.write(
            f"- Saídas: **{moeda_br(resumo['saidas'])}**"
        )
        st.write(
            f"= Saldo calculado: "
            f"**{moeda_br(resumo['saldo_atual'])}**"
        )
        st.caption(
            f"{resumo['ignorados']} registro(s) não alteraram "
            "a conta, como Agenda, configurações ou compras "
            "no cartão."
        )

        saldo_informado_setup = extrair_metadado(
            config.get("satisfacao"),
            "SALDO_ATUAL",
        )

        if saldo_informado_setup is not None:
            st.caption(
                "Saldo informado na última reconciliação: "
                f"{moeda_br(numero_seguro(saldo_informado_setup))}"
            )

    if st.button(
        "Reconciliar com o extrato",
        help=(
            "Use quando o saldo calculado não corresponder "
            "ao saldo real da conta."
        ),
    ):
        st.session_state["reconfigurando_saldo"] = True
        st.rerun()
