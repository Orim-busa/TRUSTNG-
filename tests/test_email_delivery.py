import pytest

import email_delivery


SMTP_SETTINGS = {
    "SMTP_HOST": "smtp.example.test",
    "SMTP_PORT": "587",
    "SMTP_USERNAME": "trustng-test",
    "SMTP_PASSWORD": "test-password",
    "EMAIL_FROM": "verify@example.test",
}


class FakeSMTP:
    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.calls = []
        self.message = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self):
        self.calls.append("starttls")

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def send_message(self, message):
        self.calls.append("send_message")
        self.message = message


def configure_smtp(monkeypatch):
    for name, value in SMTP_SETTINGS.items():
        monkeypatch.setenv(name, value)


@pytest.mark.parametrize("missing_setting", list(SMTP_SETTINGS))
def test_email_delivery_requires_all_smtp_settings(monkeypatch, missing_setting):
    configure_smtp(monkeypatch)
    monkeypatch.delenv(missing_setting)

    with pytest.raises(RuntimeError, match="configuration is incomplete"):
        email_delivery.send_verification_email(
            "person@example.test", "123456"
        )


def test_smtp_mode_enabled_is_configurable(monkeypatch):
    monkeypatch.setenv("TRUSTNG_EMAIL_DELIVERY_MODE", "smtp")
    assert email_delivery.smtp_mode_enabled() is True

    monkeypatch.setenv("TRUSTNG_EMAIL_DELIVERY_MODE", "sandbox")
    assert email_delivery.smtp_mode_enabled() is False


def test_email_delivery_uses_starttls_by_default(monkeypatch):
    configure_smtp(monkeypatch)
    monkeypatch.delenv("SMTP_USE_SSL", raising=False)
    captured = {}

    def fake_smtp(host, port, timeout):
        server = FakeSMTP(host, port, timeout)
        captured["server"] = server
        return server

    monkeypatch.setattr(email_delivery.smtplib, "SMTP", fake_smtp)

    result = email_delivery.send_verification_email(
        "person@example.test", "123456"
    )

    server = captured["server"]
    assert result is True
    assert server.host == SMTP_SETTINGS["SMTP_HOST"]
    assert server.port == 587
    assert server.timeout == 15
    assert server.calls == [
        "ehlo",
        "starttls",
        "ehlo",
        ("login", SMTP_SETTINGS["SMTP_USERNAME"], SMTP_SETTINGS["SMTP_PASSWORD"]),
        "send_message",
    ]

    message = server.message
    assert message["To"] == "person@example.test"
    assert message["From"] == SMTP_SETTINGS["EMAIL_FROM"]
    assert message["Subject"] == "Your TrustNG verification code"
    assert "123456" in message.get_content()
    assert "10 minutes" in message.get_content()
    assert "only be used once" in message.get_content()


def test_email_delivery_uses_ssl_when_enabled(monkeypatch):
    configure_smtp(monkeypatch)
    monkeypatch.setenv("SMTP_USE_SSL", "true")
    captured = {}

    def fake_smtp_ssl(host, port, timeout):
        server = FakeSMTP(host, port, timeout)
        captured["server"] = server
        return server

    monkeypatch.setattr(email_delivery.smtplib, "SMTP_SSL", fake_smtp_ssl)

    result = email_delivery.send_verification_email(
        "person@example.test", "654321"
    )

    server = captured["server"]
    assert result is True
    assert server.calls == [
        ("login", SMTP_SETTINGS["SMTP_USERNAME"], SMTP_SETTINGS["SMTP_PASSWORD"]),
        "send_message",
    ]
    assert "654321" in server.message.get_content()


def test_email_delivery_propagates_smtp_failure(monkeypatch):
    configure_smtp(monkeypatch)

    def fail_smtp(*args, **kwargs):
        raise OSError("simulated SMTP connection failure")

    monkeypatch.setattr(email_delivery.smtplib, "SMTP", fail_smtp)

    with pytest.raises(OSError, match="simulated SMTP connection failure"):
        email_delivery.send_verification_email(
            "person@example.test", "123456"
        )


@pytest.mark.parametrize(
    ("failure_stage", "error_message"),
    [
        ("login", "simulated SMTP authentication failure"),
        ("send_message", "simulated SMTP send failure"),
    ],
)
def test_email_delivery_propagates_authentication_and_send_failures(
    monkeypatch, failure_stage, error_message
):
    configure_smtp(monkeypatch)

    class FailingSMTP(FakeSMTP):
        def login(self, username, password):
            if failure_stage == "login":
                raise OSError(error_message)
            super().login(username, password)

        def send_message(self, message):
            if failure_stage == "send_message":
                raise OSError(error_message)
            super().send_message(message)

    monkeypatch.setattr(
        email_delivery.smtplib,
        "SMTP",
        lambda host, port, timeout: FailingSMTP(host, port, timeout),
    )

    with pytest.raises(OSError, match=error_message):
        email_delivery.send_verification_email(
            "person@example.test", "123456"
        )


@pytest.mark.parametrize(
    ("failure_stage", "error_message"),
    [
        ("login", "simulated SMTP authentication failure"),
        ("send_message", "simulated SMTP send failure"),
    ],
)
def test_email_delivery_propagates_authentication_and_send_failures(
    monkeypatch, failure_stage, error_message
):
    configure_smtp(monkeypatch)

    class FailingSMTP(FakeSMTP):
        def login(self, username, password):
            if failure_stage == "login":
                raise OSError(error_message)
            super().login(username, password)

        def send_message(self, message):
            if failure_stage == "send_message":
                raise OSError(error_message)
            super().send_message(message)

    monkeypatch.setattr(
        email_delivery.smtplib,
        "SMTP",
        lambda host, port, timeout: FailingSMTP(host, port, timeout),
    )

    with pytest.raises(OSError, match=error_message):
        email_delivery.send_verification_email(
            "person@example.test", "123456"
        )
