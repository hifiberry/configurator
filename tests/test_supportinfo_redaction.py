from configurator.supportinfo import REDACTED, redact_secrets


def test_key_value_secrets_are_removed():
    assert redact_secrets("password=hunter2") == f"password={REDACTED}"
    assert redact_secrets("psk = topsecret") == f"psk = {REDACTED}"
    assert redact_secrets('client_secret: "abc123"') == f'client_secret: {REDACTED}'
    assert redact_secrets("api-key=xyz") == f"api-key={REDACTED}"


def test_case_is_ignored():
    assert redact_secrets("PASSWORD=hunter2") == f"PASSWORD={REDACTED}"


def test_credentials_in_urls_are_removed():
    assert redact_secrets("smb://joe:hunter2@nas/music") == f"smb://joe:{REDACTED}@nas/music"


def test_secrets_inside_longer_lines_are_removed():
    line = "Aug 07 10:00:01 host mount[123]: mounting with username=joe,password=hunter2,vers=3.0"
    result = redact_secrets(line)
    assert "hunter2" not in result
    assert "vers=3.0" in result


def test_harmless_text_is_untouched():
    text = "Sound Card: DAC2 HD\nPi Model: Raspberry Pi 5 Model B Rev 1.0 5"
    assert redact_secrets(text) == text


def test_token_word_alone_is_not_mangled():
    assert redact_secrets("no tokens were found") == "no tokens were found"


def test_compound_psk_identifier_is_removed():
    # Finding 1: \b does not fire between "_" and "p", so WPA_PSK / WLAN_PSK
    # were previously left unredacted.
    assert redact_secrets("WPA_PSK=abcdef1234567890") == f"WPA_PSK={REDACTED}"
    assert redact_secrets("WLAN_PSK=abcdef1234567890") == f"WLAN_PSK={REDACTED}"


def test_wpa_passphrase_is_removed():
    # Finding 2: "passphrase" was missing from the word list entirely, so
    # hostapd.conf's actual key (wpa_passphrase) was never redacted.
    assert redact_secrets("wpa_passphrase=hunter2") == f"wpa_passphrase={REDACTED}"


def test_compound_secret_key_identifiers_are_removed():
    # Finding 3: compound keys where the operator does not immediately
    # follow one of the listed words.
    assert redact_secrets("secret_key=abc123") == f"secret_key={REDACTED}"
    assert (
        redact_secrets("AWS_SECRET_ACCESS_KEY=abc123")
        == f"AWS_SECRET_ACCESS_KEY={REDACTED}"
    )


def test_bearer_token_is_removed():
    # Finding 3: "Authorization: Bearer <token>" headers.
    header = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature"
    assert redact_secrets(header) == f"Authorization: Bearer {REDACTED}"


def test_pem_private_key_block_is_removed():
    # Finding 3: PEM private-key blocks, everything between the BEGIN and
    # the matching END marker.
    block = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEA1234567890abcdefghijklmnopqrstuvwxyz\n"
        "-----END RSA PRIVATE KEY-----"
    )
    result = redact_secrets(block)
    assert "MIIEpAIBAAKCAQEA1234567890abcdefghijklmnopqrstuvwxyz" not in result
    assert "-----BEGIN RSA PRIVATE KEY-----" in result
    assert "-----END RSA PRIVATE KEY-----" in result
    assert REDACTED in result


def test_truncated_pem_private_key_block_is_removed():
    # Round 2: a log excerpt (e.g. journalctl -n 40) can cut off mid-key,
    # so there is a BEGIN marker and key material but no END marker
    # anywhere in the text. The key material must still not survive.
    block = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEA1234567890abcdefghijklmnopqrstuvwxyz"
    )
    result = redact_secrets(block)
    assert "MIIEpAIBAAKCAQEA1234567890abcdefghijklmnopqrstuvwxyz" not in result
    assert "-----BEGIN RSA PRIVATE KEY-----" in result
    assert REDACTED in result


def test_truncated_pem_block_does_not_swallow_trailing_report_content():
    # Round 3: redact_secrets() runs over the whole collected report, not
    # per line. An unterminated PEM block must not consume everything that
    # follows it -- only the base64 key material.
    report = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEA1234567890abcdefghijklmnopqrstuvwxyz\n"
        "Sound Card: DAC2 HD\n"
        "Kernel: 6.6.31\n"
        "Uptime: 3 days"
    )
    result = redact_secrets(report)
    assert "MIIEpAIBAAKCAQEA1234567890abcdefghijklmnopqrstuvwxyz" not in result
    assert "Sound Card: DAC2 HD" in result
    assert "Kernel: 6.6.31" in result
    assert "Uptime: 3 days" in result
