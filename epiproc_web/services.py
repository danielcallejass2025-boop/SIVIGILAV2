import json
import os
import secrets
import smtplib
import string
import base64
import html
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path
from typing import Optional

from flask import request, session

from .extensions import db
from .models import AuditLog, Bulletin, BulletinStatus, Event, User, UserRole
from config.settings import Settings
from scripts.google_auth import load_google_credentials

try:
    from googleapiclient.discovery import build

    GOOGLE_GMAIL_API_AVAILABLE = True
except ImportError:
    GOOGLE_GMAIL_API_AVAILABLE = False


INITIAL_SECRETARIO_USERNAME = "AndresGob"
INITIAL_SECRETARIO_PASSWORD = "Risa2027*"


def generate_username(full_name: str, cedula: str) -> str:
    tokens = [t for t in full_name.strip().split() if t]
    base = tokens[0].lower() if tokens else "epi"
    suffix = cedula[-4:] if cedula else str(secrets.randbelow(9999)).zfill(4)
    return f"{base}{suffix}"


def generate_temp_password(length: int = 16) -> str:
    # Contraseñas totalmente aleatorias con entropia alta y caracteres seguros.
    safe_symbols = "@#$%*+-_"
    alphabet = string.ascii_letters + string.digits + safe_symbols
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _load_email_logo_asset() -> tuple[Optional[bytes], Optional[str]]:
        logo_path = Path(__file__).resolve().parent / "static" / "img" / "logo_epiproc.png"
        if not logo_path.exists() or not logo_path.is_file():
                return None, None

        subtype = logo_path.suffix.lower().lstrip(".")
        if subtype == "jpg":
                subtype = "jpeg"

        try:
                return logo_path.read_bytes(), subtype
        except Exception:
                return None, None


def _build_credentials_email_bodies(full_name: str, username: str, temp_password: str, logo_src: str) -> tuple[str, str]:
        safe_name = html.escape(full_name)
        safe_user = html.escape(username)
        safe_pass = html.escape(temp_password)

        text_body = (
                f"Hola {full_name},\n\n"
                "Tu cuenta de EPIPROC ha sido creada.\n"
                f"Usuario: {username}\n"
                f"Contraseña temporal: {temp_password}\n\n"
                "Debes cambiar tu contraseña en el primer inicio de sesión.\n"
                "EPIPROC - Procesamiento Epidemiológico"
        )

        logo_html = ""
        if logo_src:
                logo_html = (
                        f'<img src="{logo_src}" alt="Logo EPIPROC" '
                        'style="height:52px;width:auto;display:block;border:0;outline:none;text-decoration:none;" />'
                )

        html_body = f"""
<!doctype html>
<html lang="es">
    <body style="margin:0;padding:0;background:#eef2f8;font-family:'Segoe UI',Arial,sans-serif;color:#1f2937;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;background:#eef2f8;">
            <tr>
                <td style="background:#2853a6;color:#ffffff;padding:10px 24px;font-size:14px;font-weight:700;">gov.co</td>
            </tr>
            <tr>
                <td align="center" style="padding:22px 14px;">
                    <table role="presentation" width="680" cellspacing="0" cellpadding="0" style="max-width:680px;width:100%;border-collapse:collapse;background:#ffffff;border:1px solid #dbe3ef;border-radius:14px;overflow:hidden;">
                        <tr>
                            <td style="padding:18px 24px;border-bottom:1px solid #e5ebf4;">
                                <table role="presentation" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
                                    <tr>
                                        <td style="vertical-align:middle;padding-right:12px;">{logo_html}</td>
                                        <td style="vertical-align:middle;">
                                            <div style="font-size:30px;line-height:1;font-weight:800;color:#163f7a;letter-spacing:0.2px;">EPIPROC</div>
                                            <div style="margin-top:4px;font-size:18px;color:#45607f;">Procesamiento Epidemiológico</div>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding:24px;">
                                <h1 style="margin:0 0 14px;font-size:24px;line-height:1.2;color:#0f274a;">Credenciales de acceso</h1>
                                <p style="margin:0 0 12px;font-size:16px;line-height:1.6;">Hola {safe_name},</p>
                                <p style="margin:0 0 18px;font-size:15px;line-height:1.6;color:#374151;">Tu cuenta de EPIPROC ha sido creada exitosamente.</p>

                                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;background:#f3f7fc;border:1px solid #d6e3f3;border-radius:10px;overflow:hidden;">
                                    <tr>
                                        <td style="padding:16px;">
                                            <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.08em;color:#60758f;font-weight:700;">Usuario</div>
                                            <div style="font-size:20px;font-weight:700;color:#102a4d;margin-top:4px;">{safe_user}</div>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding:0 16px 16px;">
                                            <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.08em;color:#60758f;font-weight:700;">Contraseña temporal</div>
                                            <div style="font-size:18px;font-weight:700;color:#0f5132;margin-top:4px;word-break:break-word;">{safe_pass}</div>
                                        </td>
                                    </tr>
                                </table>

                                <p style="margin:18px 0 0;font-size:14px;line-height:1.6;color:#334155;">
                                    Debes cambiar tu contraseña en el primer inicio de sesión.
                                </p>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding:14px 24px;background:#f8fbff;border-top:1px solid #e5ebf4;font-size:12px;color:#60758f;">
                                EPIPROC - Procesamiento Epidemiológico
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
</html>
"""

        return text_body, html_body


def _build_credentials_email_message(sender_email: str, to_email: str, full_name: str, username: str, temp_password: str) -> EmailMessage:
        logo_bytes, logo_subtype = _load_email_logo_asset()
        logo_cid = make_msgid(domain="epiproc.local") if logo_bytes and logo_subtype else None
        logo_src = f"cid:{logo_cid[1:-1]}" if logo_cid else ""
        text_body, html_body = _build_credentials_email_bodies(full_name, username, temp_password, logo_src)

        message = EmailMessage()
        message["Subject"] = "EPIPROC - Credenciales de acceso"
        message["From"] = formataddr(("EPIPROC - Procesamiento Epidemiológico", sender_email))
        message["To"] = to_email
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")

        if logo_cid and logo_bytes and logo_subtype:
                message.get_payload()[-1].add_related(
                        logo_bytes,
                        maintype="image",
                        subtype=logo_subtype,
                        cid=logo_cid,
                )

        return message


def send_credentials_email(to_email: str, full_name: str, username: str, temp_password: str) -> tuple[bool, str]:
    settings = Settings()
    gmail_credentials_path = os.getenv(
        "GOOGLE_GMAIL_CREDENTIALS_PATH",
        os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", os.getenv("GOOGLE_DRIVE_CREDENTIALS_PATH", "")),
    ).strip()
    gmail_token_path = os.getenv(
        "GOOGLE_GMAIL_TOKEN_PATH",
        os.getenv("GOOGLE_DRIVE_TOKEN_PATH", str(settings.GOOGLE_DRIVE_TOKEN_PATH)),
    ).strip()
    gmail_delegated_user = os.getenv("GOOGLE_GMAIL_DELEGATED_USER", "").strip()
    gmail_from = os.getenv("GOOGLE_GMAIL_FROM", gmail_delegated_user or "").strip()

    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "epiproc@local")

    if GOOGLE_GMAIL_API_AVAILABLE and gmail_credentials_path:
        try:
            credentials, credential_mode = load_google_credentials(
                credentials_path=gmail_credentials_path,
                scopes=["https://www.googleapis.com/auth/gmail.send"],
                token_path=gmail_token_path or settings.GOOGLE_DRIVE_TOKEN_PATH,
                logger=None,
            )
            if credential_mode == "service_account":
                if not gmail_delegated_user:
                    raise RuntimeError(
                        "La service account requiere GOOGLE_GMAIL_DELEGATED_USER para enviar por Gmail API."
                    )
                credentials = credentials.with_subject(gmail_delegated_user)

            service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
            if credential_mode == "oauth":
                sender_address = gmail_from
                if not sender_address:
                    drive_service = build("drive", "v3", credentials=credentials, cache_discovery=False)
                    about = drive_service.about().get(fields="user(emailAddress)").execute()
                    sender_address = ((about.get("user") or {}).get("emailAddress") or "").strip()
                if not sender_address:
                    raise RuntimeError(
                        "No fue posible determinar el correo remitente OAuth. Define GOOGLE_GMAIL_FROM manualmente."
                    )
            else:
                sender_address = gmail_from or gmail_delegated_user

            message = _build_credentials_email_message(
                sender_email=sender_address,
                to_email=to_email,
                full_name=full_name,
                username=username,
                temp_password=temp_password,
            )

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            service.users().messages().send(userId="me", body={"raw": raw_message}).execute()
            return True, "Correo enviado exitosamente por Gmail API"
        except Exception as exc:
            if not smtp_host or not smtp_user or not smtp_password:
                return False, (
                    "No fue posible enviar correo por Gmail API. "
                    "Para usar OAuth necesitas autorizar el scope de Gmail; para usar service account con Gmail necesitas delegación de dominio y GOOGLE_GMAIL_DELEGATED_USER, "
                    f"o configurar SMTP. Detalle: {exc}"
                )

    if not smtp_host or not smtp_user or not smtp_password:
        return False, (
            "SMTP no configurado. Credenciales temporales generadas localmente; "
            "configura SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, o usa Gmail API con delegación "
            "definiendo GOOGLE_GMAIL_DELEGATED_USER."
        )

    try:
        message = _build_credentials_email_message(
            sender_email=smtp_from,
            to_email=to_email,
            full_name=full_name,
            username=username,
            temp_password=temp_password,
        )
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(message)
        return True, "Correo enviado exitosamente"
    except Exception as exc:
        return False, f"No fue posible enviar correo: {exc}"


def log_action(action: str, entity: str, entity_id: Optional[str] = None, details: Optional[str] = None) -> None:
    uid = session.get("user_id")
    ip = request.headers.get("X-Forwarded-For", request.remote_addr) if request else None
    record = AuditLog(
        user_id=uid,
        action=action,
        entity=entity,
        entity_id=entity_id,
        details=details,
        ip_address=ip,
    )
    db.session.add(record)
    db.session.commit()


def seed_events(events_json_path: Path) -> None:
    if not events_json_path.exists():
        return

    with open(events_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    inserted = 0
    for item in data:
        code_field = item.get("codigo")
        name = item.get("nombre", "Evento")

        if isinstance(code_field, list):
            codes = code_field
        else:
            codes = [code_field]

        for code in codes:
            if code is None:
                continue
            existing = Event.query.get(int(code))
            if not existing:
                db.session.add(Event(code=int(code), name=name, active=True))
                inserted += 1

    if inserted > 0:
        db.session.commit()


def seed_initial_secretario() -> None:
    admin = User.query.filter_by(username=INITIAL_SECRETARIO_USERNAME).first()
    if admin:
        # If the initial default password is still in use, enforce password update.
        if admin.check_password(INITIAL_SECRETARIO_PASSWORD) and not admin.must_change_password:
            admin.must_change_password = True
            db.session.commit()
        return

    admin = User(
        username=INITIAL_SECRETARIO_USERNAME,
        role=UserRole.SECRETARIO,
        full_name="Secretario de Salud",
        cedula="0000000000",
        email="secretario.salud@epiproc.local",
        must_change_password=True,
        is_active=True,
    )
    admin.set_password(INITIAL_SECRETARIO_PASSWORD)
    db.session.add(admin)
    db.session.commit()


def seed_sample_bulletin() -> None:
    existing = Bulletin.query.first()
    if existing:
        return

    event = Event.query.get(549)
    admin = User.query.filter_by(username=INITIAL_SECRETARIO_USERNAME).first()
    if not event or not admin:
        return

    b = Bulletin(
        title="Boletín inicial Morbilidad Materna Extrema",
        content=(
            "Boletín inicial de EPIPROC.\n\n"
            "Este contenido es editable por el Secretario de Salud y por el epidemiológo "
            "asignado al evento."
        ),
        status=BulletinStatus.PUBLICADO,
        event_code=event.code,
        author_id=admin.id,
        published_at=datetime.utcnow(),
    )
    db.session.add(b)
    db.session.commit()
