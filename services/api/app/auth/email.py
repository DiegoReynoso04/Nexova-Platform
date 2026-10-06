"""Envío del email de restablecimiento de contraseña (AUTH-03) con Resend.

Sin SDK: una petición `POST https://api.resend.com/emails` con `urllib` de la
librería estándar (no hay dependencias nuevas autorizadas). La API key viene de
`RESEND_API_KEY` (`Settings.resend_api_key`) y solo viaja en la cabecera
`Authorization`; nunca se registra ni forma parte de un error.

`EmailSender` es la frontera: la app usa `ResendEmailSender` si el email está
configurado y `DisabledEmailSender` si no; los tests inyectan un sender falso
en `app.state.email_sender`.
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlencode

RESEND_EMAILS_URL = "https://api.resend.com/emails"
SEND_TIMEOUT_SECONDS = 10
# Resend está detrás de Cloudflare, que puede rechazar el User-Agent por
# defecto de urllib (`Python-urllib/x.y`). Se envía uno propio.
USER_AGENT = "nexova-api/0.1"


class EmailDeliveryError(Exception):
    """El proveedor no aceptó el email (error HTTP, red o timeout).

    El mensaje es fijo: no incluye la respuesta del proveedor, que podría
    repetir el destinatario.
    """


class EmailNotConfiguredError(EmailDeliveryError):
    """No hay proveedor configurado (faltan RESEND_API_KEY, EMAIL_FROM y PASSWORD_RESET_URL)."""


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: str
    subject: str
    # `repr=False`: el cuerpo lleva el enlace con el token.
    text: str = field(repr=False)


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class ResendEmailSender:
    def __init__(self, api_key: str, sender: str, timeout: float = SEND_TIMEOUT_SECONDS) -> None:
        self._api_key = api_key
        self._sender = sender
        self._timeout = timeout

    def __repr__(self) -> str:
        return "ResendEmailSender()"

    def build_request(self, message: EmailMessage) -> urllib.request.Request:
        body = {"from": self._sender, "to": [message.to], "subject": message.subject, "text": message.text}
        return urllib.request.Request(
            RESEND_EMAILS_URL,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
        )

    def send(self, message: EmailMessage) -> None:
        try:
            with urllib.request.urlopen(self.build_request(message), timeout=self._timeout) as response:
                if not 200 <= response.status < 300:
                    raise EmailDeliveryError("email provider rejected the message")
        except urllib.error.HTTPError as exc:
            # 4xx/5xx: se cierra la respuesta sin leerla y se descarta la causa.
            exc.close()
            raise EmailDeliveryError("email provider rejected the message") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise EmailDeliveryError("email provider rejected the message") from None


class DisabledEmailSender:
    """Sin proveedor configurado: no envía nada y lo señala como fallo de entrega."""

    def send(self, message: EmailMessage) -> None:
        raise EmailNotConfiguredError("email delivery is not configured")


def reset_link(base_url: str, token: str) -> str:
    """`PASSWORD_RESET_URL?token=<token>`: la base sale de la configuración, nunca de la petición."""
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'token': token})}"


def password_reset_message(to: str, link: str, expire_minutes: int) -> EmailMessage:
    """Email en texto plano, legible en móvil: líneas cortas y el enlace solo en su línea."""
    text = "\n".join(
        [
            "Hola:",
            "",
            "Hemos recibido una solicitud para restablecer la contraseña de tu cuenta de Nexova.",
            "",
            "Para elegir una contraseña nueva, abre este enlace:",
            "",
            link,
            "",
            f"El enlace caduca en {expire_minutes} minutos y solo se puede usar una vez.",
            "",
            "Si no has pedido este cambio, ignora este mensaje: tu contraseña no cambiará.",
            "",
            "Nexova",
        ]
    )
    return EmailMessage(to=to, subject="Restablece tu contraseña de Nexova", text=text)
