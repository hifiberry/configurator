import json
import logging

import pytest

import configurator.configdb as configdb_module
from configurator.configdb import ConfigDB


def _db(tmp_path, monkeypatch):
    """A ConfigDB with its Fernet key redirected into tmp_path.

    KEY_FILE is a module-level constant read inside _get_encryption_key, so
    patching the module attribute is enough; tests must never touch
    /etc/configdb.key.
    """
    monkeypatch.setattr(configdb_module, "KEY_FILE", str(tmp_path / "configdb.key"))
    return ConfigDB(db_path=str(tmp_path / "config.sqlite"))


def test_secure_value_round_trips(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    assert db.set("player.soloist.api_key", "s3cret-value", secure=True)
    assert db.get("player.soloist.api_key", secure=True) == "s3cret-value"


def test_secure_value_is_encrypted_at_rest(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    db.set("player.soloist.api_key", "s3cret-value", secure=True)
    raw = db.get("player.soloist.api_key")  # no secure=True: the stored blob
    assert raw is not None
    assert "s3cret-value" not in raw


def test_overwriting_a_secure_value_does_not_log_plaintext(tmp_path, monkeypatch, caplog):
    db = _db(tmp_path, monkeypatch)
    db.set("player.soloist.api_key", "old-secret", secure=True)

    with caplog.at_level(logging.DEBUG):
        db.set("player.soloist.api_key", "new-secret", secure=True)

    combined = "\n".join(record.getMessage() for record in caplog.records)
    assert "old-secret" not in combined, combined
    assert "new-secret" not in combined, combined


def test_writing_an_unchanged_secure_value_is_a_no_op(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    db.set("player.soloist.api_key", "same", secure=True)
    first = db.get("player.soloist.api_key")  # ciphertext

    assert db.set("player.soloist.api_key", "same", secure=True)
    second = db.get("player.soloist.api_key")

    # Unchanged input must not rewrite the row -- Fernet is nondeterministic,
    # so a rewrite would produce different ciphertext.
    assert first == second


def test_plain_value_logging_is_unchanged(tmp_path, monkeypatch, caplog):
    db = _db(tmp_path, monkeypatch)
    db.set("some.key", "old-plain")
    with caplog.at_level(logging.DEBUG):
        db.set("some.key", "new-plain")
    combined = "\n".join(record.getMessage() for record in caplog.records)
    # Non-secure values are ordinary configuration and stay loggable.
    assert "new-plain" in combined


def _flask_post(db, key, payload):
    """Invoke handle_set_config_value inside a request context."""
    flask = pytest.importorskip("flask", reason="Flask is absent in the build chroot")
    app = flask.Flask(__name__)
    with app.test_request_context(
        f"/key/{key}",
        method="POST",
        data=json.dumps(payload),
        content_type="application/json",
    ):
        response = db.handle_set_config_value(key)
    # Handlers return either a Response or a (Response, status) tuple.
    if isinstance(response, tuple):
        response = response[0]
    return json.loads(response.get_data(as_text=True))


def test_set_handler_does_not_echo_a_secure_value(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    body = _flask_post(db, "player.soloist.api_key",
                       {"value": "s3cret-value", "secure": True})
    assert body["status"] == "success"
    assert body["data"]["key"] == "player.soloist.api_key"
    assert "value" not in body["data"]
    assert "s3cret-value" not in json.dumps(body)
    # ...but it was actually stored
    assert db.get("player.soloist.api_key", secure=True) == "s3cret-value"


def test_set_handler_still_echoes_a_plain_value(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    body = _flask_post(db, "some.key", {"value": "plain"})
    assert body["data"]["value"] == "plain"
