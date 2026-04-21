import json
import os
import secrets
import smtplib
import string
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from flask import request, session

from .extensions import db
from .models import AuditLog, Bulletin, BulletinStatus, Event, User, UserRole


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


def send_credentials_email(to_email: str, full_name: str, username: str, temp_password: str) -> tuple[bool, str]:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "epiproc@local")

    if not smtp_host or not smtp_user or not smtp_password:
        return False, (
            "SMTP no configurado. Credenciales temporales generadas localmente; "
            "configura SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD para envío real."
        )

    subject = "EPIPROC - Credenciales de acceso"
    body = (
        f"Hola {full_name},\n\n"
        "Tu cuenta de EPIPROC ha sido creada.\n"
        f"Usuario: {username}\n"
        f"Contraseña temporal: {temp_password}\n\n"
        "Debes cambiar tu contraseña en el primer inicio de sesión.\n"
        "EPIPROC - Procesamiento Epidemiológico"
    )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = to_email

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, [to_email], msg.as_string())
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
