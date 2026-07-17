import datetime
import importlib
import sys
import types
from pathlib import Path

import httpx
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
        import json
        content = json.dumps(payload)
    return httpx.Response(status_code, content=content.encode())


def install_client(monkeypatch, app, responses):
    fake = FakeClient(responses)
    monkeypatch.setattr(app.httpx, "Client", lambda **kwargs: fake)
    return fake


def auth_headers(json=True):
    headers = {
        "apikey": "test-anon-key",
        "Authorization": "Bearer test-token",
        "Prefer": "return=representation",
    }
    if json:
        headers["Content-Type"] = "application/json"
    return headers


def test_cadastrar_compromisso_a_pagar_url_headers_payload_user_id(monkeypatch, app_module):
    fake = install_client(monkeypatch, app_module, [response(201, [{"id": 10}])])

    result = app_module.cadastrar_compromisso_http(
        "user-1", " Conta luz ", "A pagar", datetime.date(2026, 7, 20), 123.45, " Casa "
    )

    assert result == {"id": 10}
    method, url, kwargs = fake.calls[0]
    assert method == "post"
    assert url == "https://example.supabase.co/rest/v1/movimentacoes"
    assert kwargs["headers"] == auth_headers()
    assert kwargs["json"] == {
        "data": "2026-07-20",
        "descricao": "[AGENDA COMPROMISSO] Conta luz",
        "grupo_orcamentario": "AGENDA - A PAGAR",
        "subcategoria": "Casa",
        "valor": 123.45,
        "satisfacao": "3 - Indispensável",
        "tipo": "Saída",
        "user_id": "user-1",
    }


def test_cadastrar_compromisso_a_receber(monkeypatch, app_module):
    fake = install_client(monkeypatch, app_module, [response(201, [{"id": 11}])])

    app_module.cadastrar_compromisso_http(
        "user-1", "Salário", "A receber", datetime.date(2026, 7, 25), 1000, "Renda"
    )

    payload = fake.calls[0][2]["json"]
    assert payload["grupo_orcamentario"] == "AGENDA - A RECEBER"
    assert payload["tipo"] == "Entrada"
    assert payload["user_id"] == "user-1"


def test_cadastrar_compromisso_erro_http(monkeypatch, app_module):
    install_client(monkeypatch, app_module, [response(500, text="boom")])

    with pytest.raises(RuntimeError, match="Cadastro retornou HTTP 500: boom"):
        app_module.cadastrar_compromisso_http(
            "user-1", "Conta", "A pagar", datetime.date(2026, 7, 20), 1, "Casa"
        )


def test_atualizar_compromisso_filtros_payload_sem_user_id(monkeypatch, app_module):
    fake = install_client(monkeypatch, app_module, [response(200, [{"id": 7}])])

    app_module.atualizar_compromisso_http(
        7, "user-1", "Aluguel", "A pagar", datetime.date(2026, 8, 1), 900, "Moradia"
    )

    method, url, kwargs = fake.calls[0]
    assert method == "patch"
    assert kwargs["params"] == [("id", "eq.7"), ("user_id", "eq.user-1")]
    assert "user_id" not in kwargs["json"]
    assert kwargs["json"]["grupo_orcamentario"] == "AGENDA - A PAGAR"


def test_atualizar_compromisso_erro_http(monkeypatch, app_module):
    install_client(monkeypatch, app_module, [response(400, text="bad")])

    with pytest.raises(RuntimeError, match="Edição retornou HTTP 400: bad"):
        app_module.atualizar_compromisso_http(
            7, "user-1", "Aluguel", "A pagar", datetime.date(2026, 8, 1), 900, "Moradia"
        )


def test_excluir_registro_filtros(monkeypatch, app_module):
    fake = install_client(monkeypatch, app_module, [response(204)])

    app_module.excluir_registro_http(5, "user-1")

    method, url, kwargs = fake.calls[0]
    assert method == "delete"
    assert kwargs["params"] == [("id", "eq.5"), ("user_id", "eq.user-1")]
    assert kwargs["headers"] == auth_headers(json=False)


def test_excluir_registro_erro_http(monkeypatch, app_module):
    install_client(monkeypatch, app_module, [response(403, text="denied")])

    with pytest.raises(RuntimeError, match="Exclusão retornou HTTP 403: denied"):
        app_module.excluir_registro_http(5, "user-1")


def test_baixar_compromisso_caminho_feliz_cria_lancamento_e_exclui(monkeypatch, app_module):
    fake = install_client(monkeypatch, app_module, [response(201, [{"id": 99}]), response(204)])

    result = app_module.baixar_compromisso_http(
        5, "user-1", "Conta", "A pagar", datetime.date(2026, 7, 21), 50, "DESPESAS", "Casa"
    )

    assert result == {"id": 99}
    assert [call[0] for call in fake.calls] == ["post", "delete"]
    assert fake.calls[1][2]["params"] == [("id", "eq.5"), ("user_id", "eq.user-1")]


def test_baixar_compromisso_falha_exclusao_executa_rollback(monkeypatch, app_module):
    fake = install_client(
        monkeypatch,
        app_module,
        [response(201, [{"id": 99}]), response(500, text="delete failed"), response(204)],
    )

    with pytest.raises(RuntimeError, match="A baixa foi desfeita"):
        app_module.baixar_compromisso_http(
            5, "user-1", "Conta", "A pagar", datetime.date(2026, 7, 21), 50, "DESPESAS", "Casa"
        )

    assert [call[0] for call in fake.calls] == ["post", "delete", "delete"]
    assert fake.calls[2][2]["params"] == [("id", "eq.99"), ("user_id", "eq.user-1")]


def test_baixar_compromisso_falha_critica(monkeypatch, app_module):
    install_client(
        monkeypatch,
        app_module,
        [response(201, [{"id": 99}]), response(500, text="delete failed"), response(500, text="rollback failed")],
    )

    with pytest.raises(RuntimeError, match="Falha crítica"):
        app_module.baixar_compromisso_http(
            5, "user-1", "Conta", "A pagar", datetime.date(2026, 7, 21), 50, "DESPESAS", "Casa"
        )


def test_baixar_compromisso_resposta_sem_id_nao_exclui(monkeypatch, app_module):
    fake = install_client(monkeypatch, app_module, [response(201, [{"descricao": "sem id"}])])

    with pytest.raises(RuntimeError, match="não retornou"):
        app_module.baixar_compromisso_http(
            5, "user-1", "Conta", "A pagar", datetime.date(2026, 7, 21), 50, "DESPESAS", "Casa"
        )

    assert [call[0] for call in fake.calls] == ["post"]


def test_funcoes_basicas(app_module):
    assert app_module.normalizar_numero("10.5") == 10.5
    assert app_module.normalizar_numero(None, padrao=7) == 7
    assert app_module.normalizar_texto("  texto  ") == "texto"
    assert app_module.normalizar_texto(None, padrao="x") == "x"
    assert app_module.classificar_agenda("AGENDA - A RECEBER") == "A receber"
    assert app_module.classificar_agenda("AGENDA - A PAGAR") == "A pagar"
    assert app_module.classificar_movimento("Faturamento ou Receita (Entrada)") == "entrada"
    assert app_module.classificar_movimento("Cartão de Crédito") == "cartao"
    assert app_module.classificar_movimento("Saída Dinheiro / Pix") == "saida"
    assert app_module.limpar_descricao_agenda("[AGENDA COMPROMISSO] Conta") == "Conta"
