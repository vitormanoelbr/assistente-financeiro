import datetime
import importlib
import json
import sys
import types
from pathlib import Path

import httpx
import pandas as pd
import pytest


class StopStreamlit(Exception):
    pass


@pytest.fixture()
def app_module(monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(repo_root))

    fake_streamlit = types.ModuleType("streamlit")
    fake_streamlit.secrets = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_KEY": "test-anon-key",
    }
    fake_streamlit.session_state = {
        "usuario_logado": "user-1",
        "user_token": "test-token",
        "refresh_token": "refresh-token",
        "token_expires_at": 9999999999,
    }
    fake_streamlit.query_params = types.SimpleNamespace(clear=lambda: None)
    fake_streamlit.sidebar = types.SimpleNamespace(
        button=lambda *args, **kwargs: False,
        markdown=lambda *args, **kwargs: None,
        header=lambda *args, **kwargs: None,
        radio=lambda *args, **kwargs: "Página vazia",
        caption=lambda *args, **kwargs: None,
    )
    for name in (
        "set_page_config", "error", "warning", "rerun", "title",
        "success", "info", "markdown", "caption",
    ):
        setattr(fake_streamlit, name, lambda *args, **kwargs: None)
    fake_streamlit.stop = lambda: (_ for _ in ()).throw(StopStreamlit())

    fake_supabase = types.ModuleType("supabase")
    fake_supabase.Client = object
    fake_supabase.create_client = lambda *args, **kwargs: object()
    fake_options = types.ModuleType("supabase.lib.client_options")
    fake_options.SyncClientOptions = lambda *args, **kwargs: object()

    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    monkeypatch.setitem(sys.modules, "supabase", fake_supabase)
    monkeypatch.setitem(sys.modules, "supabase.lib", types.ModuleType("supabase.lib"))
    monkeypatch.setitem(sys.modules, "supabase.lib.client_options", fake_options)

    sys.modules.pop("app", None)
    module = importlib.import_module("app")
    module.st.session_state["user_token"] = "test-token"
    return module


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return self.responses.pop(0)

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return self.responses.pop(0)

    def patch(self, url, **kwargs):
        self.calls.append(("patch", url, kwargs))
        return self.responses.pop(0)

    def delete(self, url, **kwargs):
        self.calls.append(("delete", url, kwargs))
        return self.responses.pop(0)


def response(status_code=200, payload=None, text=None):
    content = text if text is not None else ""
    if payload is not None:
        content = json.dumps(payload)
    return httpx.Response(status_code, content=content.encode())


def install_client(monkeypatch, app, responses):
    fake = FakeClient(responses)
    monkeypatch.setattr(app.httpx, "Client", lambda **kwargs: fake)
    return fake


def test_classificacao_regras_e_resumo(app_module):
    assert app_module.eh_registro_agenda({"grupo_orcamentario": "agenda casa"})
    assert app_module.eh_registro_agenda({"descricao": "[AGENDA COMPROMISSO] médico"})
    assert app_module.eh_registro_administrativo({"descricao": "CONFIG_PERFIL inicial"})
    assert app_module.eh_registro_administrativo({"grupo_orcamentario": "Configuração"})
    assert app_module.eh_registro_administrativo({"grupo_orcamentario": "CONFIGURACAO"})
    assert app_module.eh_lancamento_real({"descricao": "Consulta (Pago)", "grupo_orcamentario": "Saúde"})
    assert app_module.eh_lancamento_real({"descricao": "Salário (Recebido)", "grupo_orcamentario": "Renda"})
    assert app_module.eh_lancamento_real({"descricao": None, "grupo_orcamentario": pd.NA})

    df = pd.DataFrame([
        {"tipo": "Entrada", "valor": 1000},
        {"tipo": "Saída", "valor": 150},
        {"tipo": "Cartão de crédito", "valor": 250},
    ])
    original = df.copy(deep=True)
    assert app_module.calcular_resumo_lancamentos(df) == {
        "entradas": 1000.0,
        "saidas_dinheiro": 150.0,
        "cartao": 250.0,
        "despesas_totais": 400.0,
        "saldo": 600.0,
    }
    pd.testing.assert_frame_equal(df, original)


def test_filtrar_lancamentos_reais_df_nao_modifica_original(app_module):
    df = pd.DataFrame([
        {"id": 1, "descricao": "Real", "grupo_orcamentario": "Casa"},
        {"id": 2, "descricao": "[AGENDA COMPROMISSO] Médico", "grupo_orcamentario": "Saúde"},
        {"id": 3, "descricao": "CONFIG_CARTAO", "grupo_orcamentario": "Casa"},
    ])
    original = df.copy(deep=True)

    filtrado = app_module.filtrar_lancamentos_reais_df(df)

    assert filtrado["id"].tolist() == [1]
    pd.testing.assert_frame_equal(df, original)


def test_buscar_lancamentos_paginado_filtra_e_monta_consulta(monkeypatch, app_module):
    page1 = [{"id": i, "descricao": "Real", "grupo_orcamentario": "Casa"} for i in range(1000)]
    page2 = [
        {"id": 1001, "descricao": "[AGENDA COMPROMISSO] x", "grupo_orcamentario": "Casa"},
        {"id": 1002, "descricao": "CONFIG_CARTAO", "grupo_orcamentario": "Casa"},
        {"id": 1003, "descricao": "Mercado", "grupo_orcamentario": "Casa"},
    ]
    fake = install_client(monkeypatch, app_module, [response(206, page1), response(200, page2)])

    dados = app_module.buscar_lancamentos_painel_http("user-1", 2026, 7)

    assert len(dados) == 1001
    assert dados[-1]["id"] == 1003
    assert len(fake.calls) == 2
    _, url, kwargs = fake.calls[0]
    assert url == "https://example.supabase.co/rest/v1/movimentacoes"
    assert ("user_id", "eq.user-1") in kwargs["params"]
    assert ("data", "gte.2026-07-01") in kwargs["params"]
    assert ("data", "lt.2026-08-01") in kwargs["params"]
    assert ("order", "data.asc") in kwargs["params"]
    assert kwargs["headers"]["Range"] == "0-999"
    assert fake.calls[1][2]["headers"]["Range"] == "1000-1999"


def test_buscar_lancamentos_erros(monkeypatch, app_module):
    with pytest.raises(ValueError):
        app_module.buscar_lancamentos_painel_http("", 2026, 7)

    install_client(monkeypatch, app_module, [response(500, text="erro")])
    with pytest.raises(RuntimeError):
        app_module.buscar_lancamentos_painel_http("user-1", 2026, 7)

    install_client(monkeypatch, app_module, [response(200, {"x": 1})])
    with pytest.raises(RuntimeError):
        app_module.buscar_lancamentos_painel_http("user-1", 2026, 7)


@pytest.mark.parametrize("valor", [0, -1])
def test_validar_dados_lancamento_bloqueios(app_module, valor):
    erros = app_module.validar_dados_lancamento("", "", "", "", valor)
    assert len(erros) >= 5
    assert app_module.validar_dados_lancamento("ok", "AGENDA", "sub", "Saída", 1)
    assert app_module.validar_dados_lancamento("ok", "Configuração", "sub", "Saída", 1)
    assert app_module.validar_dados_lancamento("CONFIG_PERFIL", "Casa", "sub", "Saída", 1)
    assert app_module.validar_dados_lancamento("ok", "Casa", "sub", "Saída", 1) == []


def test_cadastrar_lancamento_payload_headers_e_erros(monkeypatch, app_module):
    fake = install_client(monkeypatch, app_module, [response(201, [{"id": 10}])])
    assert app_module.cadastrar_lancamento_http(
        "user-1", datetime.date(2026, 7, 10), " Mercado ", "Saída", "Casa", "Alimentação", 50
    ) == {"id": 10}
    method, url, kwargs = fake.calls[0]
    assert method == "post"
    assert url == "https://example.supabase.co/rest/v1/movimentacoes"
    assert kwargs["headers"]["Prefer"] == "return=representation"
    assert kwargs["json"]["user_id"] == "user-1"
    assert kwargs["json"]["satisfacao"] == ""
    assert not kwargs["json"]["descricao"].startswith("[AGENDA COMPROMISSO]")

    for payload in ([{}], [], [{"id": 1}, {"id": 2}]):
        install_client(monkeypatch, app_module, [response(201, payload)])
        with pytest.raises(RuntimeError):
            app_module.cadastrar_lancamento_http("user-1", "2026-07-10", "x", "Saída", "Casa", "Sub", 1)
    install_client(monkeypatch, app_module, [response(500, text="erro")])
    with pytest.raises(RuntimeError):
        app_module.cadastrar_lancamento_http("user-1", "2026-07-10", "x", "Saída", "Casa", "Sub", 1)


def test_atualizar_lancamento_filtros_payload_e_erros(monkeypatch, app_module):
    fake = install_client(monkeypatch, app_module, [response(200, [{"id": 5}])])
    assert app_module.atualizar_lancamento_http(5, "user-1", "2026-07-10", "x", "Entrada", "Renda", "Salário", 100) == {"id": 5}
    _, _, kwargs = fake.calls[0]
    assert ("id", "eq.5") in kwargs["params"]
    assert ("user_id", "eq.user-1") in kwargs["params"]
    assert "user_id" not in kwargs["json"]

    for payload in ([], [{"id": 1}, {"id": 2}]):
        install_client(monkeypatch, app_module, [response(200, payload)])
        with pytest.raises(RuntimeError):
            app_module.atualizar_lancamento_http(5, "user-1", "2026-07-10", "x", "Entrada", "Renda", "Salário", 100)
    install_client(monkeypatch, app_module, [response(500, text="erro")])
    with pytest.raises(RuntimeError):
        app_module.atualizar_lancamento_http(5, "user-1", "2026-07-10", "x", "Entrada", "Renda", "Salário", 100)


def test_excluir_lancamento_estrito(monkeypatch, app_module):
    fake = install_client(monkeypatch, app_module, [response(200, [{"id": 5}])])
    assert app_module.excluir_lancamento_http(5, "user-1") == {"id": 5}
    _, _, kwargs = fake.calls[0]
    assert ("id", "eq.5") in kwargs["params"]
    assert ("user_id", "eq.user-1") in kwargs["params"]

    for payload in ([], [{"id": 1}, {"id": 2}]):
        install_client(monkeypatch, app_module, [response(200, payload)])
        with pytest.raises(RuntimeError):
            app_module.excluir_lancamento_http(5, "user-1")
    install_client(monkeypatch, app_module, [response(500, text="erro")])
    with pytest.raises(RuntimeError):
        app_module.excluir_lancamento_http(5, "user-1")
