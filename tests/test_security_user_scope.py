from core import api as api_module
from core.api import SupabaseRestClient


class FakeResponse:
    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self._data = [] if data is None else data
        self.text = ""

    def json(self):
        return self._data


class FakeClient:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None, params=None):
        self.calls.append(("GET", list(params or [])))
        return FakeResponse(200, [])

    def patch(self, url, headers=None, params=None, json=None):
        self.calls.append(("PATCH", list(params or [])))
        return FakeResponse(204, [])

    def delete(self, url, headers=None, params=None):
        self.calls.append(("DELETE", list(params or [])))
        return FakeResponse(204, [])


def cliente():
    return SupabaseRestClient(
        "https://exemplo.supabase.co",
        "anon-key",
        "access-token",
        "usuario-a",
    )


def instalar_fake(monkeypatch):
    FakeClient.calls = []
    monkeypatch.setattr(api_module.httpx, "Client", FakeClient)


def assert_user_scope(call):
    _, params = call
    assert ("user_id", "eq.usuario-a") in params


def test_busca_sempre_filtra_usuario(monkeypatch):
    instalar_fake(monkeypatch)
    cliente().buscar_movimentacoes()
    assert_user_scope(FakeClient.calls[-1])


def test_update_sempre_filtra_usuario(monkeypatch):
    instalar_fake(monkeypatch)
    cliente().atualizar_movimentacao(10, {"valor": 100.0})
    assert FakeClient.calls[-1][0] == "PATCH"
    assert_user_scope(FakeClient.calls[-1])


def test_delete_sempre_filtra_usuario(monkeypatch):
    instalar_fake(monkeypatch)
    cliente().excluir_movimentacao(10)
    assert FakeClient.calls[-1][0] == "DELETE"
    assert_user_scope(FakeClient.calls[-1])
