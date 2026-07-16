import builtins
import os

import pytest

from configurator.extensions.sources import InvalidSource, SourceManager

ARMORED_KEY = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nabc\n-----END PGP PUBLIC KEY BLOCK-----\n"


def _manager(tmp_path, dearmor=None):
    sources = tmp_path / "sources.list.d"
    keyrings = tmp_path / "keyrings"
    sources.mkdir()
    keyrings.mkdir()
    return SourceManager(
        sources_dir=str(sources),
        keyrings_dir=str(keyrings),
        dearmor=dearmor or (lambda armored: b"BINARY:" + armored.encode()),
    )


def test_add_source_writes_a_signed_by_list_file(tmp_path):
    manager = _manager(tmp_path)
    manager.add_source("acme", "https://repo.acme.com", "trixie", "main", ARMORED_KEY)

    path = tmp_path / "sources.list.d" / "hifiberry-ext-acme.list"
    content = path.read_text()
    assert content.startswith("deb [signed-by=")
    assert "hifiberry-ext-acme.gpg" in content
    assert "https://repo.acme.com trixie main" in content


def test_add_source_writes_the_dearmored_keyring(tmp_path):
    manager = _manager(tmp_path)
    manager.add_source("acme", "https://repo.acme.com", "trixie", "main", ARMORED_KEY)

    keyring = tmp_path / "keyrings" / "hifiberry-ext-acme.gpg"
    assert keyring.read_bytes() == b"BINARY:" + ARMORED_KEY.encode()


def test_keyring_is_world_readable_because_apt_reads_it_unprivileged(tmp_path):
    manager = _manager(tmp_path)
    manager.add_source("acme", "https://repo.acme.com", "trixie", "main", ARMORED_KEY)
    keyring = tmp_path / "keyrings" / "hifiberry-ext-acme.gpg"
    assert oct(os.stat(keyring).st_mode)[-3:] == "644"


def test_a_source_without_a_key_is_refused(tmp_path):
    manager = _manager(tmp_path)
    with pytest.raises(InvalidSource):
        manager.add_source("acme", "https://repo.acme.com", "trixie", "main", "")


def test_a_key_that_is_not_a_pgp_block_is_refused(tmp_path):
    manager = _manager(tmp_path)
    with pytest.raises(InvalidSource):
        manager.add_source("acme", "https://repo.acme.com", "trixie", "main", "hello")


def test_nothing_is_written_when_the_key_is_refused(tmp_path):
    manager = _manager(tmp_path)
    with pytest.raises(InvalidSource):
        manager.add_source("acme", "https://repo.acme.com", "trixie", "main", "")
    assert os.listdir(tmp_path / "sources.list.d") == []
    assert os.listdir(tmp_path / "keyrings") == []


def test_orphan_keyring_is_removed_when_list_write_fails(tmp_path, monkeypatch):
    manager = _manager(tmp_path)
    real_open = builtins.open
    calls = {"n": 0}

    def flaky_open(path, mode="r", *args, **kwargs):
        if str(path).endswith(".list") and "w" in mode:
            raise OSError("disk full")
        calls["n"] += 1
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", flaky_open)

    with pytest.raises(OSError):
        manager.add_source("acme", "https://repo.acme.com", "trixie", "main", ARMORED_KEY)

    assert calls["n"] > 0  # the keyring write did happen
    assert not (tmp_path / "keyrings" / "hifiberry-ext-acme.gpg").exists()


@pytest.mark.parametrize("bad_id", ["../etc/evil", "acme repo", "ACME!", "", "a/b"])
def test_unsafe_source_ids_are_refused(tmp_path, bad_id):
    manager = _manager(tmp_path)
    with pytest.raises(InvalidSource):
        manager.add_source(bad_id, "https://repo.acme.com", "trixie", "main", ARMORED_KEY)


@pytest.mark.parametrize("bad_uri", [
    "ftp://repo.acme.com",
    "file:///etc",
    "not a url",
    "https://repo.acme.com\ndeb https://evil.com trixie main",
])
def test_unsafe_uris_are_refused(tmp_path, bad_uri):
    manager = _manager(tmp_path)
    with pytest.raises(InvalidSource):
        manager.add_source("acme", bad_uri, "trixie", "main", ARMORED_KEY)


def test_newline_injection_in_suite_is_refused(tmp_path):
    manager = _manager(tmp_path)
    with pytest.raises(InvalidSource):
        manager.add_source("acme", "https://repo.acme.com",
                           "trixie main\ndeb https://evil.com trixie", "main",
                           ARMORED_KEY)


@pytest.mark.parametrize("args", [
    ("acme", "https://repo.acme.com", "trixie\n", "main"),      # suite
    ("acme", "https://repo.acme.com", "trixie", "main\n"),      # components
    ("acme", "https://repo.acme.com\n", "trixie", "main"),      # uri
    ("acme\n", "https://repo.acme.com", "trixie", "main"),      # id
])
def test_bare_trailing_newline_in_any_field_is_refused(tmp_path, args):
    manager = _manager(tmp_path)
    with pytest.raises(InvalidSource):
        manager.add_source(*args, ARMORED_KEY)


def test_list_sources_returns_managed_sources(tmp_path):
    manager = _manager(tmp_path)
    manager.add_source("acme", "https://repo.acme.com", "trixie", "main", ARMORED_KEY)

    sources = manager.list_sources()
    assert len(sources) == 1
    assert sources[0]["id"] == "acme"
    assert sources[0]["uri"] == "https://repo.acme.com"
    assert sources[0]["suite"] == "trixie"
    assert sources[0]["components"] == "main"


def test_list_sources_ignores_unmanaged_files(tmp_path):
    manager = _manager(tmp_path)
    (tmp_path / "sources.list.d" / "debian.list").write_text(
        "deb https://deb.debian.org/debian trixie main\n"
    )
    assert manager.list_sources() == []


def test_remove_source_deletes_both_files(tmp_path):
    manager = _manager(tmp_path)
    manager.add_source("acme", "https://repo.acme.com", "trixie", "main", ARMORED_KEY)
    manager.remove_source("acme")

    assert not (tmp_path / "sources.list.d" / "hifiberry-ext-acme.list").exists()
    assert not (tmp_path / "keyrings" / "hifiberry-ext-acme.gpg").exists()
    assert manager.list_sources() == []


def test_remove_unknown_source_raises(tmp_path):
    with pytest.raises(InvalidSource):
        _manager(tmp_path).remove_source("nope")


def test_remove_refuses_an_unsafe_id(tmp_path):
    with pytest.raises(InvalidSource):
        _manager(tmp_path).remove_source("../../etc/passwd")
