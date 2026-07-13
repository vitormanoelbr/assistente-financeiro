import pandas as pd


def moeda_br(valor) -> str:
    try:
        numero = float(valor)
    except Exception:
        numero = 0.0

    texto = f"{numero:,.2f}"
    texto = (
        texto.replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )
    return f"R$ {texto}"


def numero_seguro(valor, padrao: float = 0.0) -> float:
    convertido = pd.to_numeric(valor, errors="coerce")

    if pd.isna(convertido):
        return padrao

    return float(convertido)


def classificar_tipo(tipo: str) -> str:
    texto = str(tipo or "").upper()

    if any(
        termo in texto
        for termo in (
            "ENTRADA",
            "RECEITA",
            "FATURAMENTO",
            "RECEBIMENTO",
        )
    ):
        return "entrada"

    if any(
        termo in texto
        for termo in (
            "CARTÃO",
            "CARTAO",
            "CRÉDITO",
            "CREDITO",
        )
    ) or "💳" in str(tipo or ""):
        return "cartao"

    return "saida"
