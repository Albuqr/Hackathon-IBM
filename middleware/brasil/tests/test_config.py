import pytest

from middleware.brasil.config import ConfigInvalida, carregar


def base(tmp_path, **kw):
    env = {"DB_PATH": str(tmp_path / "crisis.db")}
    env.update(kw)
    return env


def test_padroes_seguros(tmp_path):
    c = carregar(base(tmp_path))
    assert c.orquestrador == "local" and c.notificacoes == "fila" and not c.dev_login and c.ingestao_auto_min == 0
    assert c.db_path.endswith("brasil.db")


def test_cfg001_recusa_banco_igual_ao_do_crisis(tmp_path):
    with pytest.raises(ConfigInvalida, match="BRASIL_DB_PATH"):
        carregar(base(tmp_path, BRASIL_DB_PATH=str(tmp_path / "crisis.db")))


@pytest.mark.parametrize("nome,valor", [
    ("BRASIL_ORQUESTRADOR", "gpt"), ("BRASIL_INGESTAO_AUTO_MIN", "5"),
    ("BRASIL_INGESTAO_AUTO_MIN", "abc"), ("BRASIL_NOTIFICACOES", "sms"),
])
def test_valor_invalido_impede_subida_e_nomeia_a_opcao(tmp_path, nome, valor):
    with pytest.raises(ConfigInvalida, match=f"{nome}={valor}"):
        carregar(base(tmp_path, **{nome: valor}))


def test_cfg003_dev_login_so_liga_com_1(tmp_path):
    assert carregar(base(tmp_path, BRASIL_DEV_LOGIN="1")).dev_login
    assert not carregar(base(tmp_path, BRASIL_DEV_LOGIN="true")).dev_login
