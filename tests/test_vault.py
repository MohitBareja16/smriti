import pytest

from smriti.vault import Vault, VaultLockedError, WrongPassphraseError


def test_roundtrip(tmp_path):
    v = Vault(tmp_path, "correct horse")
    name = v.put("doc", b"secret marksheet")
    assert b"secret" not in (tmp_path / name).read_bytes()
    assert v.get(name) == b"secret marksheet"


def test_wrong_passphrase_fails(tmp_path):
    name = Vault(tmp_path, "right").put("doc", b"data")
    with pytest.raises(WrongPassphraseError):
        Vault(tmp_path, "wrong").get(name)


def test_locked_vault_refuses(tmp_path):
    with pytest.raises(VaultLockedError):
        Vault(tmp_path, None).put("doc", b"data")
