"""SMTPSender tests — verify message composition + smtplib invocation."""

from __future__ import annotations

from email.message import Message
from unittest.mock import MagicMock, patch

from newsletter.slices.distribution.sender import Mail, SMTPSender


def _mail(html: str | None = None) -> Mail:
    return Mail(
        sender="newsletter@example.com",
        recipients=("a@example.com", "b@example.com"),
        subject="[AI 뉴스레터] 2026-05-19",
        plain_body="안녕하세요.",
        html_body=html,
    )


def test_smtp_sender_sends_via_smtplib():
    sender = SMTPSender(
        host="smtp.example.com",
        port=587,
        user="user",
        password="pw",
    )
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False
    with patch(
        "newsletter.slices.distribution.sender.smtplib.SMTP",
        return_value=fake_smtp,
    ) as smtp_factory:
        sender.send(_mail(html="<p>hi</p>"))

    smtp_factory.assert_called_once()
    args, _kwargs = smtp_factory.call_args
    # SMTP("smtp.example.com", 587, timeout=30)
    assert args[0] == "smtp.example.com"
    assert args[1] == 587

    fake_smtp.starttls.assert_called_once()
    fake_smtp.login.assert_called_once_with("user", "pw")
    fake_smtp.send_message.assert_called_once()

    sent_msg: Message = fake_smtp.send_message.call_args.args[0]
    assert sent_msg["From"] == "newsletter@example.com"
    assert sent_msg["To"] == "a@example.com, b@example.com"
    assert sent_msg["Subject"] == "[AI 뉴스레터] 2026-05-19"
    # Multi-part: text + html alternative
    assert sent_msg.is_multipart()
    parts = list(sent_msg.iter_parts())
    plain = next(p for p in parts if p.get_content_type() == "text/plain")
    html = next(p for p in parts if p.get_content_type() == "text/html")
    assert "안녕하세요." in plain.get_content()
    assert "<p>hi</p>" in html.get_content()


def test_smtp_sender_skips_html_when_not_provided():
    sender = SMTPSender(host="x", port=25, user="u", password="p", use_starttls=False)
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False
    with patch("newsletter.slices.distribution.sender.smtplib.SMTP", return_value=fake_smtp):
        sender.send(_mail(html=None))

    sent_msg: Message = fake_smtp.send_message.call_args.args[0]
    assert not sent_msg.is_multipart()
    assert "안녕하세요." in sent_msg.get_content()
    # starttls disabled
    fake_smtp.starttls.assert_not_called()
