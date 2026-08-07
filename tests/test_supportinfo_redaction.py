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


# --- Round 4: the PEM matrix -------------------------------------------
# redact_secrets() sees the whole assembled report, which mixes plain
# config dumps with journalctl output ("<time> <host> <unit>[pid]: " in
# front of every line).  A PEM block therefore turns up in several shapes,
# and all of them have to lose their key material without any diagnostic
# line being deleted.


def test_complete_pem_block_keeps_markers_and_replaces_body():
    # (a) plain block, no prefixes: BEGIN/END stay, every body line is
    # replaced one-for-one.
    block = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEA1234567890abcdefghijklmnopqrstuvwxyz\n"
        "AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKKKLLLLMMMM\n"
        "-----END RSA PRIVATE KEY-----"
    )
    assert redact_secrets(block) == (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        f"{REDACTED}\n"
        f"{REDACTED}\n"
        "-----END RSA PRIVATE KEY-----"
    )


def test_pem_block_with_journal_prefixes_is_redacted():
    # (b) every line carries a journalctl prefix, so the block is not
    # anchored to the start of the line.
    prefix = "Aug 07 10:00:01 host sshd[123]: "
    report = "\n".join(
        [
            prefix + "-----BEGIN OPENSSH PRIVATE KEY-----",
            prefix + "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAA",
            prefix + "c2gtZWQyNTUxOQAAACDkZXlkZWFkYmVlZmRlYWRiZWVmZGVhZGJlZWZkZWFk",
            prefix + "-----END OPENSSH PRIVATE KEY-----",
        ]
    )
    result = redact_secrets(report)
    assert "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAA" not in result
    assert "c2gtZWQyNTUxOQAAACDkZXlkZWFkYmVlZmRlYWRiZWVmZGVhZGJlZWZkZWFk" not in result
    assert result.count(REDACTED) == 2
    assert prefix + "-----BEGIN OPENSSH PRIVATE KEY-----" in result
    assert prefix + "-----END OPENSSH PRIVATE KEY-----" in result
    # No line is added or dropped.
    assert len(result.split("\n")) == 4


def test_pem_block_with_indented_body_is_redacted():
    # (c) the block is quoted/indented inside the report.
    report = (
        "Certificate:\n"
        "    -----BEGIN EC PRIVATE KEY-----\n"
        "    MHcCAQEEIBnKrLZ0987654321abcdefghijklmnopqrstuvwxyzABCDEFGH\n"
        "    -----END EC PRIVATE KEY-----"
    )
    result = redact_secrets(report)
    assert "MHcCAQEEIBnKrLZ0987654321abcdefghijklmnopqrstuvwxyzABCDEFGH" not in result
    assert "Certificate:" in result
    assert "    -----BEGIN EC PRIVATE KEY-----" in result
    assert "    -----END EC PRIVATE KEY-----" in result
    assert REDACTED in result


def test_truncated_pem_block_at_end_of_report_is_redacted():
    # (d) BEGIN plus body, no END marker anywhere, nothing after it.
    report = (
        "Journal:\n"
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEA1111111111111111111111111111111111111111111111\n"
        "MIIEpAIBAAKCAQEA2222222222222222222222222222222222222222222222"
    )
    result = redact_secrets(report)
    assert "1111111111" not in result
    assert "2222222222" not in result
    assert "Journal:" in result
    assert "-----BEGIN RSA PRIVATE KEY-----" in result


def test_truncated_pem_block_keeps_the_diagnostics_that_follow():
    # (e) BEGIN plus body, no END marker, ordinary report lines after it.
    report = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEA1234567890abcdefghijklmnopqrstuvwxyz\n"
        "AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHH\n"
        "Sound Card: DAC2 HD\n"
        "Kernel: 6.6.31\n"
        "Uptime: 3 days"
    )
    result = redact_secrets(report)
    assert "MIIEpAIBAAKCAQEA1234567890abcdefghijklmnopqrstuvwxyz" not in result
    assert "AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHH" not in result
    assert result.endswith("Sound Card: DAC2 HD\nKernel: 6.6.31\nUptime: 3 days")


def test_secret_after_truncated_pem_block_is_still_redacted():
    # (f) the truncated block must not consume a later secret -- that line
    # still has to go through the key/value redaction.
    report = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEA1234567890abcdefghijklmnopqrstuvwxyz\n"
        "Sound Card: DAC2 HD\n"
        "password=hunter2\n"
        "Kernel: 6.6.31"
    )
    result = redact_secrets(report)
    assert "hunter2" not in result
    assert f"password={REDACTED}" in result
    assert "Sound Card: DAC2 HD" in result
    assert "Kernel: 6.6.31" in result


def test_truncated_block_does_not_reach_into_a_later_block():
    # A later, unrelated block's END marker must not turn a truncated block
    # into a terminated one -- that would redact the report in between.
    report = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEAtruncated0123456789abcdefghijklmnop\n"
        "Sound Card: DAC2 HD\n"
        "Kernel: 6.6.31\n"
        "-----BEGIN EC PRIVATE KEY-----\n"
        "MHcCAQEEIBnKrLZsecondkey0123456789abcdefghijklmnopq\n"
        "-----END EC PRIVATE KEY-----"
    )
    result = redact_secrets(report)
    assert "MIIEpAIBAAKCAQEAtruncated0123456789abcdefghijklmnop" not in result
    assert "MHcCAQEEIBnKrLZsecondkey0123456789abcdefghijklmnopq" not in result
    assert "Sound Card: DAC2 HD" in result
    assert "Kernel: 6.6.31" in result


def test_encrypted_pem_headers_do_not_end_the_block():
    # An encrypted PEM key carries RFC 1421 headers and a blank line before
    # the base64 body; neither may be mistaken for the end of the block.
    block = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "Proc-Type: 4,ENCRYPTED\n"
        "DEK-Info: AES-128-CBC,0123456789ABCDEF0123456789ABCDEF\n"
        "\n"
        "MIIEpAIBAAKCAQEAkeymaterial0123456789abcdefghijklmnopqXYZ\n"
        "-----END RSA PRIVATE KEY-----"
    )
    result = redact_secrets(block)
    assert "MIIEpAIBAAKCAQEAkeymaterial0123456789abcdefghijklmnopqXYZ" not in result
    assert "-----END RSA PRIVATE KEY-----" in result


def test_truncated_encrypted_pem_block_is_redacted():
    report = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "Proc-Type: 4,ENCRYPTED\n"
        "DEK-Info: AES-128-CBC,0123456789ABCDEF0123456789ABCDEF\n"
        "\n"
        "MIIEpAIBAAKCAQEAkeymaterial0123456789abcdefghijklmnopqXYZ\n"
        "Sound Card: DAC2 HD"
    )
    result = redact_secrets(report)
    assert "MIIEpAIBAAKCAQEAkeymaterial0123456789abcdefghijklmnopqXYZ" not in result
    assert result.endswith("Sound Card: DAC2 HD")
