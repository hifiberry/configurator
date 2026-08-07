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
