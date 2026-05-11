from __future__ import annotations

import os
import re
import json
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Optional
import requests

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    send_file,
    session,
    url_for,
)
from werkzeug.exceptions import HTTPException
from sqlalchemy import or_, text
from sqlalchemy.exc import IntegrityError

from .dashboard_data import build_dashboard_data, build_legacy_evento_549_payload
from .extensions import db
from .models import AuditLog, Bulletin, BulletinStatus, Event, User, UserRole
from .services import (
    generate_temp_password,
    generate_username,
    log_action,
    send_credentials_email,
    seed_events,
    seed_initial_secretario,
    seed_sample_bulletin,
)
from scripts.google_sheets_store import EpidemiologosSheetStore


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DEFAULT_APPS_SCRIPT_DEPLOY_URL = (
    "https://script.google.com/macros/s/AKfycbxQ2zAs2LznfhA_uEUx3bE95LjP0JdS95kWg_4qbrkxmOCxJQXj_0_s7SF378zm8WJf/exec"
)

_RISARALDA_GEOJSON_CACHE: dict[str, Any] = {
    "path": None,
    "mtime_ns": None,
    "data": None,
}


def _extract_geojson_from_layer_js(raw_text: str) -> Optional[dict[str, Any]]:
    marker = "var json_Departamento_Risaralda_1 ="
    if marker not in raw_text:
        return None

    start = raw_text.find(marker)
    if start < 0:
        return None

    payload = raw_text[start + len(marker):].strip()
    if payload.endswith(";"):
        payload = payload[:-1].strip()

    try:
        data = json.loads(payload)
    except Exception:
        return None

    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        return None

    return data


def _resolve_risaralda_layer_path(base_dir: Path) -> Optional[Path]:
    candidates = [
        base_dir / "assets" / "mapa_risaralda" / "Departamento_Risaralda_1.js",
        Path.home() / "Downloads" / "Mapa risaralda" / "Risaralda_Cosechada_2024" / "layers" / "Departamento_Risaralda_1.js",
    ]
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def _load_risaralda_geojson(base_dir: Path) -> tuple[Optional[dict[str, Any]], Optional[Path]]:
    layer_path = _resolve_risaralda_layer_path(base_dir)
    if layer_path is None:
        return None, None

    st = layer_path.stat()
    if (
        _RISARALDA_GEOJSON_CACHE.get("path") == str(layer_path)
        and _RISARALDA_GEOJSON_CACHE.get("mtime_ns") == st.st_mtime_ns
        and isinstance(_RISARALDA_GEOJSON_CACHE.get("data"), dict)
    ):
        return _RISARALDA_GEOJSON_CACHE["data"], layer_path

    raw = layer_path.read_text(encoding="utf-8", errors="ignore")
    data = _extract_geojson_from_layer_js(raw)
    if data is None:
        return None, layer_path

    _RISARALDA_GEOJSON_CACHE["path"] = str(layer_path)
    _RISARALDA_GEOJSON_CACHE["mtime_ns"] = st.st_mtime_ns
    _RISARALDA_GEOJSON_CACHE["data"] = data
    return data, layer_path


def _extract_event_code(value: Any) -> Optional[int]:
    txt = str(value or "").strip()
    if not txt:
        return None
    m = re.search(r"\b(\d{2,5})\b", txt)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _post_apps_script(payload: dict[str, Any], timeout_seconds: int = 12) -> dict[str, Any]:
    url = (os.getenv("APPS_SCRIPT_DEPLOY_URL") or DEFAULT_APPS_SCRIPT_DEPLOY_URL).strip()
    if not url:
        raise RuntimeError("APPS_SCRIPT_DEPLOY_URL no configurada.")

    api_key = (os.getenv("APPS_SCRIPT_API_KEY") or "").strip()
    body = dict(payload)
    if api_key:
        body["key"] = api_key

    response = requests.post(
        url,
        data=json.dumps(body),
        headers={"Content-Type": "text/plain;charset=utf-8"},
        timeout=timeout_seconds,
    )

    if response.status_code >= 400:
        raise RuntimeError(f"Apps Script HTTP {response.status_code}")

    try:
        data = response.json()
    except Exception as exc:  # pragma: no cover - defensive parse
        raise RuntimeError("Respuesta JSON inválida desde Apps Script") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Respuesta inesperada de Apps Script")

    return data


def _apps_script_action(action: str, timeout_seconds: int = 10, **payload: Any) -> dict[str, Any]:
    native_actions = {
        "registrar_epidemiologo",
        "listar_epidemiologos",
        "autenticar_epidemiologo",
        "actualizar_estado_epidemiologo",
        "regenerar_password_epidemiologo",
        "actualizar_evento_epidemiologo",
        "actualizar_epidemiologo",
        "eliminar_epidemiologo",
    }
    if action in native_actions:
        store = EpidemiologosSheetStore()
        if action == "registrar_epidemiologo":
            return store.create(
                nombre=str(payload.get("nombre") or "").strip(),
                cedula=str(payload.get("cedula") or "").strip(),
                correo=str(payload.get("correo") or "").strip(),
                evento=str(payload.get("evento") or "").strip(),
                usuario=str(payload.get("usuario") or payload.get("user") or payload.get("cedula") or "").strip() or None,
                password_temporal=str(payload.get("password_temporal") or payload.get("pass") or generate_temp_password()).strip(),
                estado=str(payload.get("estado") or "Activo").strip(),
            )
        if action == "listar_epidemiologos":
            return {"success": True, "items": store.list_items()}
        if action == "autenticar_epidemiologo":
            return store.authenticate(str(payload.get("usuario") or "").strip(), str(payload.get("password") or ""))
        if action == "actualizar_estado_epidemiologo":
            return store.update_status(str(payload.get("usuario") or "").strip(), str(payload.get("cedula") or "").strip(), str(payload.get("estado") or "Activo").strip())
        if action == "regenerar_password_epidemiologo":
            new_pass = generate_temp_password()
            return store.regenerate_password(str(payload.get("usuario") or "").strip(), str(payload.get("cedula") or "").strip(), new_pass)
        if action == "actualizar_evento_epidemiologo":
            return store.update_event(str(payload.get("usuario") or "").strip(), str(payload.get("cedula") or "").strip(), str(payload.get("evento") or "").strip())
        if action == "actualizar_epidemiologo":
            return store.update(payload)
        if action == "eliminar_epidemiologo":
            return store.delete(str(payload.get("usuario") or "").strip(), str(payload.get("cedula") or "").strip())

    body = {"accion": action}
    body.update(payload)
    data = _post_apps_script(body, timeout_seconds=timeout_seconds)
    if not data.get("success"):
        raise RuntimeError(str(data.get("error") or f"Apps Script fallo en accion {action}"))
    return data


def _event_display_from_code(event_code: Optional[int]) -> str:
    if not event_code:
        return "No especificado"

    event = Event.query.get(int(event_code))
    if event:
        return f"{event.code} - {event.name}"

    return str(event_code)


def _upsert_local_epidemiologo(
    *,
    full_name: str,
    cedula: str,
    email: str,
    username: str,
    password_plain: str,
    evento_display: str,
    estado: str = "Activo",
    update_password: bool = True,
    force_password_change: bool = True,
) -> tuple[bool, str, Optional[User]]:
    full_name = (full_name or "").strip()
    cedula = (cedula or "").strip()
    email = (email or "").strip().lower()
    username = (username or "").strip()
    password_plain = password_plain or ""
    evento_display = (evento_display or "").strip()

    if not full_name or not cedula or not email or not username:
        return False, "Datos incompletos para sincronizar usuario local.", None

    evento_code = _extract_event_code(evento_display)
    if evento_code and Event.query.get(evento_code) is None:
        evento_code = None

    user = User.query.filter_by(role=UserRole.EPIDEMIOLOGO, cedula=cedula).first()
    if user is None:
        user = User.query.filter_by(role=UserRole.EPIDEMIOLOGO, username=username).first()
    if user is None:
        user = User.query.filter_by(role=UserRole.EPIDEMIOLOGO, email=email).first()

    creating = user is None

    # Validaciones de unicidad global antes de crear para evitar IntegrityError en flush/commit.
    if creating:
        for field_name, value in (("cedula", cedula), ("email", email), ("username", username)):
            if User.query.filter(getattr(User, field_name) == value).first() is not None:
                return False, f"Conflicto local en campo {field_name}: {value}", None

    if creating:
        if not password_plain:
            return False, "No se recibio contrasena temporal para crear el usuario.", None
        user = User(
            role=UserRole.EPIDEMIOLOGO,
            full_name=full_name,
            cedula=cedula,
            email=email,
            username=username,
            assigned_event_code=evento_code,
            must_change_password=force_password_change,
            is_active=True,
            credentials_updated_at=datetime.utcnow(),
        )
        db.session.add(user)

    # Unicidad fuerte para evitar inconsistencias de login/listado.
    if not creating:
        for field_name, value in (("cedula", cedula), ("email", email), ("username", username)):
            conflict_query = User.query.filter(getattr(User, field_name) == value)
            if user.id:
                conflict_query = conflict_query.filter(User.id != user.id)
            conflict = conflict_query.first()
            if conflict:
                return False, f"Conflicto local en campo {field_name}: {value}", None

    user.full_name = full_name
    user.cedula = cedula
    user.email = email
    user.username = username
    user.assigned_event_code = evento_code
    user.is_active = str(estado or "Activo").strip().lower() != "inactivo"

    if update_password:
        if not password_plain:
            return False, "No se recibio contrasena para actualizar credenciales.", None
        user.must_change_password = force_password_change
        user.credentials_updated_at = datetime.utcnow()
        user.set_password(password_plain)
        user.set_visible_password(password_plain)
    elif creating and password_plain:
        user.must_change_password = force_password_change
        user.credentials_updated_at = datetime.utcnow()
        user.set_password(password_plain)
        user.set_visible_password(password_plain)

    try:
        db.session.commit()
        return True, "ok", user
    except IntegrityError:
        db.session.rollback()
        return False, "Conflicto de unicidad en base local al sincronizar usuario.", None
    except Exception as exc:
        db.session.rollback()
        return False, f"Error local al sincronizar usuario: {exc}", None


def _sync_all_epidemiologos_from_apps_script() -> tuple[int, int, set[str], set[str], set[str]]:
    payload = _apps_script_action("listar_epidemiologos", timeout_seconds=4)
    if not payload.get("success"):
        raise RuntimeError(str(payload.get("error") or "Error al listar epidemiologos en Google Sheets"))

    items = payload.get("items") or []
    if not isinstance(items, list):
        raise RuntimeError("Respuesta invalida en listar_epidemiologos")

    synced = 0
    total = 0
    remote_cedulas: set[str] = set()
    remote_usernames: set[str] = set()
    remote_emails: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            continue

        total += 1
        cedula = str(item.get("cedula") or "").strip()
        username = str(item.get("usuario") or item.get("cedula") or "").strip()
        email = str(item.get("correo") or "").strip().lower()

        if cedula:
            remote_cedulas.add(cedula)
        if username:
            remote_usernames.add(username)
        if email:
            remote_emails.add(email)

        existing = None
        if cedula:
            existing = User.query.filter_by(role=UserRole.EPIDEMIOLOGO, cedula=cedula).first()
        if existing is None and username:
            existing = User.query.filter_by(role=UserRole.EPIDEMIOLOGO, username=username).first()
        if existing is None and email:
            existing = User.query.filter_by(role=UserRole.EPIDEMIOLOGO, email=email).first()

        # Solo sincronizar contraseña cuando el usuario aún está en estado temporal.
        should_sync_password = existing is None or bool(existing.must_change_password)

        ok, _, _ = _upsert_local_epidemiologo(
            full_name=str(item.get("nombre") or "").strip(),
            cedula=cedula,
            email=email,
            username=username,
            password_plain=str(item.get("password_temporal") or "").strip(),
            evento_display=str(item.get("evento") or "").strip(),
            estado=str(item.get("estado") or "Activo").strip(),
            update_password=should_sync_password,
            force_password_change=True,
        )
        if ok:
            synced += 1

    return synced, total, remote_cedulas, remote_usernames, remote_emails


def _apply_remote_epidemiologo_visibility_filter(
    query: Any,
    remote_cedulas: Optional[set[str]],
    remote_usernames: Optional[set[str]],
    remote_emails: Optional[set[str]],
) -> Any:
    if remote_cedulas is None or remote_usernames is None or remote_emails is None:
        return query

    predicates = []
    if remote_cedulas:
        predicates.append(User.cedula.in_(remote_cedulas))
    if remote_usernames:
        predicates.append(User.username.in_(remote_usernames))
    if remote_emails:
        predicates.append(User.email.in_(remote_emails))

    if predicates:
        return query.filter(or_(*predicates))

    # Hoja vacia: no mostrar epidemiologos locales residuales.
    return query.filter(text("1=0"))


def _sync_from_apps_script_credentials(username: str, password: str) -> bool:
    try:
        payload = _apps_script_action(
            "autenticar_epidemiologo",
            timeout_seconds=5,
            usuario=username,
            password=password,
        )
    except Exception:
        return False

    if not payload.get("success"):
        return False

    ok, _, _ = _upsert_local_epidemiologo(
        full_name=str(payload.get("nombre") or "").strip(),
        cedula=str(payload.get("cedula") or "").strip(),
        email=str(payload.get("correo") or "").strip().lower(),
        username=str(payload.get("usuario") or username).strip(),
        password_plain=str(payload.get("password_temporal") or password).strip(),
        evento_display=str(payload.get("evento") or "").strip(),
        estado=str(payload.get("estado") or "Activo").strip(),
    )
    return ok


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    base_dir = Path(__file__).resolve().parents[1]
    db_path = base_dir / "data" / "epiproc_web.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    app.config["SECRET_KEY"] = os.getenv("EPIPROC_SECRET_KEY", "epiproc-local-dev-secret")
    app.config["EPIPROC_CREDENTIALS_KEY"] = os.getenv("EPIPROC_CREDENTIALS_KEY", "").strip()
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path.as_posix()}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    with app.app_context():
        db.create_all()
        _ensure_runtime_schema_columns()
        _migrate_legacy_visible_passwords()
        seed_events(base_dir / "config" / "eventos.json")
        seed_initial_secretario()
        seed_sample_bulletin()

    register_hooks(app, base_dir)
    register_routes(app, base_dir)
    register_error_handlers(app)

    return app


def current_user() -> Optional[User]:
    uid = session.get("user_id")
    if not uid:
        return None
    return User.query.get(uid)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Debes iniciar sesión para continuar.", "error")
            return redirect(url_for("login", next=request.path))
        if not user.is_active:
            session.clear()
            flash("Tu usuario está inactivo. Contacta al Secretario de Salud.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def role_required(*roles: str):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user or user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def _validate_user_payload(full_name: str, cedula: str, email: str) -> list[str]:
    errors: list[str] = []

    if not full_name or len(full_name.strip()) < 6:
        errors.append("El nombre completo debe tener al menos 6 caracteres.")

    if not cedula or not cedula.strip().isdigit() or len(cedula.strip()) < 6:
        errors.append("La cédula debe ser numérica y tener al menos 6 dígitos.")

    if not email or not EMAIL_REGEX.match(email.strip()):
        errors.append("El correo electrónico no es válido.")

    return errors


def _resolve_unique_username(base_username: str) -> str:
    candidate = base_username
    suffix = 1
    while User.query.filter_by(username=candidate).first() is not None:
        candidate = f"{base_username}{suffix}"
        suffix += 1
    return candidate


def _resolve_unique_username_for_edit(base_username: str, exclude_user_id: Optional[int] = None) -> str:
    candidate = base_username
    suffix = 1

    while True:
        query = User.query.filter_by(username=candidate)
        if exclude_user_id is not None:
            query = query.filter(User.id != exclude_user_id)
        if query.first() is None:
            break
        candidate = f"{base_username}{suffix}"
        suffix += 1

    return candidate


def _ensure_runtime_schema_columns() -> None:
    """Agrega columnas faltantes en sqlite sin requerir migraciones manuales."""
    cols_raw = db.session.execute(text("PRAGMA table_info(users)"))
    cols = {row[1] for row in cols_raw}

    if "password_visible" not in cols:
        db.session.execute(text("ALTER TABLE users ADD COLUMN password_visible VARCHAR(255)"))

    if "credentials_updated_at" not in cols:
        db.session.execute(text("ALTER TABLE users ADD COLUMN credentials_updated_at DATETIME"))

    db.session.commit()


def _migrate_legacy_visible_passwords() -> None:
    """Migra credenciales visibles legadas (texto plano) a almacenamiento cifrado."""
    changed = 0
    users = User.query.filter(User.password_visible.isnot(None)).all()

    for user in users:
        if user.password_visible and not user.has_encrypted_visible_password():
            user.set_visible_password(user.password_visible)
            changed += 1

    if changed:
        db.session.commit()


def _extract_bulletin_week_meta(bulletin: Bulletin) -> dict[str, Any]:
    roman_periods = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII"]
    roman_to_int = {txt: idx for idx, txt in enumerate(roman_periods) if idx > 0}

    def _safe_period_from_week(week: int) -> int:
        safe_week = max(1, min(53, int(week)))
        return min(13, (safe_week + 3) // 4)

    def _build_meta(week: Optional[int], year: Optional[int], period: Optional[int] = None) -> dict[str, Any]:
        if week is None or year is None:
            return {
                "week": None,
                "year": None,
                "period": None,
                "label": "Sin periodo/semana detectado",
            }

        week = int(week)
        year = int(year)
        if period is None:
            period = _safe_period_from_week(week)
        period = max(1, min(13, int(period)))
        roman = roman_periods[period] if period < len(roman_periods) else str(period)

        return {
            "week": week,
            "year": year,
            "period": period,
            "label": f"Periodo {roman} - SE {week:02d} / {year}",
        }

    content = str(bulletin.content or "").strip()
    if content:
        candidate_json_blobs: list[str] = []
        if content.startswith("{") and content.endswith("}"):
            candidate_json_blobs.append(content)

        meta_match = re.search(r"Meta:\s*(\{.*?\})", content, re.IGNORECASE)
        if meta_match:
            candidate_json_blobs.append(meta_match.group(1))

        for raw_json in candidate_json_blobs:
            try:
                parsed = json.loads(raw_json)
            except Exception:
                continue

            if isinstance(parsed, dict):
                week_raw = parsed.get("selected_week", parsed.get("selectedWeek", parsed.get("week")))
                year_raw = parsed.get("selected_year", parsed.get("selectedYear", parsed.get("year")))
                period_raw = parsed.get("selected_period", parsed.get("selectedPeriod", parsed.get("period")))

                try:
                    week = int(week_raw) if week_raw is not None else None
                    year = int(year_raw) if year_raw is not None else None
                    period = int(period_raw) if period_raw is not None else None
                except Exception:
                    week = None
                    year = None
                    period = None

                if week is not None and year is not None and 1 <= week <= 53 and 2000 <= year <= 2100:
                    if period is not None and not (1 <= period <= 13):
                        period = None
                    return _build_meta(week=week, year=year, period=period)

    sources = [content, bulletin.title or ""]

    period_regex = re.compile(
        r"Periodo\s+Epidemiol[oó]gico\s+([IVXLC]+)[^\n]*Semana\s+Epidemiol[oó]gica\s*(\d{1,2})[,\s]+(\d{4})",
        re.IGNORECASE,
    )
    week_regexes = [
        re.compile(r"Semana\s+Epidemiol[oó]gica\s*(\d{1,2})[,\s]+(\d{4})", re.IGNORECASE),
        re.compile(r"Semana\s*(\d{1,2})\s+de\s+(\d{4})", re.IGNORECASE),
        re.compile(r"SE\s*(\d{1,2})\s*/\s*(\d{4})", re.IGNORECASE),
    ]

    for source in sources:
        match_period = period_regex.search(source)
        if match_period:
            period_txt = str(match_period.group(1) or "").upper().strip()
            week = int(match_period.group(2))
            year = int(match_period.group(3))
            period = roman_to_int.get(period_txt)
            if 1 <= week <= 53 and 2000 <= year <= 2100:
                return _build_meta(week=week, year=year, period=period)

        for pattern in week_regexes:
            match = pattern.search(source)
            if match:
                week = int(match.group(1))
                year = int(match.group(2))
                if 1 <= week <= 53 and 2000 <= year <= 2100:
                    return _build_meta(week=week, year=year)

    return _build_meta(week=None, year=None, period=None)


def _get_epi_bulletin_rows(user: User, status_filter: str = "TODOS") -> list[dict[str, Any]]:
    query = Bulletin.query.filter_by(author_id=user.id)

    if user.assigned_event_code:
        query = query.filter(Bulletin.event_code == user.assigned_event_code)

    if status_filter in {BulletinStatus.BORRADOR, BulletinStatus.PUBLICADO}:
        query = query.filter(Bulletin.status == status_filter)

    bulletins = query.order_by(Bulletin.updated_at.desc()).all()
    rows: list[dict[str, Any]] = []

    for bulletin in bulletins:
        week_meta = _extract_bulletin_week_meta(bulletin)
        rows.append({
            "bulletin": bulletin,
            "week_label": week_meta["label"],
            "week": week_meta["week"],
            "year": week_meta["year"],
        })

    return rows


def _get_admin_epidemiologo_rows(
    remote_cedulas: Optional[set[str]] = None,
    remote_usernames: Optional[set[str]] = None,
    remote_emails: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    query = User.query.filter_by(role=UserRole.EPIDEMIOLOGO)
    query = _apply_remote_epidemiologo_visibility_filter(
        query,
        remote_cedulas,
        remote_usernames,
        remote_emails,
    )
    users = query.order_by(User.full_name.asc()).all()
    rows: list[dict[str, Any]] = []

    for user in users:
        assigned_event = user.assigned_event
        event_label = (
            f"{assigned_event.code} - {assigned_event.name}"
            if assigned_event is not None
            else "Sin evento asignado"
        )
        rows.append({
            "user": user,
            "event_label": event_label,
            "bulletin_count": len(user.bulletins or []),
        })

    return rows


def _get_admin_recent_bulletin_rows(status_filter: str = "TODOS", limit: int = 12) -> list[dict[str, Any]]:
    query = Bulletin.query

    if status_filter in {BulletinStatus.BORRADOR, BulletinStatus.PUBLICADO}:
        query = query.filter(Bulletin.status == status_filter)

    bulletins = query.order_by(Bulletin.updated_at.desc()).limit(limit).all()
    rows: list[dict[str, Any]] = []

    for bulletin in bulletins:
        week_meta = _extract_bulletin_week_meta(bulletin)
        rows.append({
            "bulletin": bulletin,
            "week_label": week_meta["label"],
            "week": week_meta["week"],
            "year": week_meta["year"],
        })

    return rows


def register_hooks(app: Flask, base_dir: Path) -> None:
    @app.context_processor
    def inject_globals() -> dict[str, Any]:
        return {
            "brand_name": "EPIPROC - Procesamiento Epidemiológico",
            "logo_url": "https://8upload.com/image/3ec1b5cc7de8ad31/bloque2071.png",
            "current_user": current_user(),
            "role_secretario": UserRole.SECRETARIO,
            "role_epidemiologo": UserRole.EPIDEMIOLOGO,
        }

    @app.before_request
    def force_password_change_on_first_login():
        user = current_user()
        if not user:
            return None

        safe_paths = {
            "/logout",
            "/cambiar-clave",
            "/static",
        }

        if user.must_change_password:
            current_path = request.path or ""
            if any(current_path.startswith(p) for p in safe_paths):
                return None
            if current_path.startswith("/api"):
                return jsonify({"error": "Debes cambiar la contraseña antes de continuar."}), 403
            return redirect(url_for("change_password"))

        return None


def register_routes(app: Flask, base_dir: Path) -> None:
    @app.route("/evento_549_dashboard.html")
    def legacy_dashboard_html():
        return send_from_directory(base_dir, "evento_549_dashboard.html")

    @app.route("/evento_549_dashboard.css")
    def legacy_dashboard_css():
        return send_from_directory(base_dir, "evento_549_dashboard.css")

    @app.route("/evento_549_dashboard.js")
    def legacy_dashboard_js():
        return send_from_directory(base_dir, "evento_549_dashboard.js")

    @app.route("/api/datos-evento-549")
    def api_legacy_evento_549():
        municipio = request.args.get("municipio")
        payload = build_legacy_evento_549_payload(base_dir=base_dir, municipio=municipio)
        if not payload.get("ok"):
            status_code = int(payload.get("status_code") or 500)
            return jsonify({
                "error": payload.get("error"),
                "error_code": payload.get("error_code") or "DATA_ERROR",
                "source": "archivo_depurado_local",
            }), status_code
        return jsonify(payload.get("data"))

    @app.route("/api/geojson-risaralda")
    def api_geojson_risaralda():
        geojson, source_path = _load_risaralda_geojson(base_dir)
        if geojson is None:
            path_txt = str(source_path) if source_path else "archivo no encontrado"
            return jsonify({
                "error": "No fue posible cargar el croquis municipal de Risaralda.",
                "error_code": "MAP_GEOJSON_UNAVAILABLE",
                "source": path_txt,
            }), 404

        return jsonify({
            "ok": True,
            "source": str(source_path),
            "geojson": geojson,
        })

    @app.route("/")
    def home():
        eventos = Event.query.filter_by(active=True).order_by(Event.code.asc()).all()
        return render_template("home.html", eventos=eventos)

    @app.route("/dashboard")
    def dashboard_public():
        return render_template(
            "dashboard_legacy_embed.html",
            dashboard_url=url_for("legacy_dashboard_html"),
            dashboard_context="publico",
        )

    @app.route("/api/dashboard-data")
    def api_dashboard_data():
        try:
            event_code = int(request.args.get("evento", "549"))
        except ValueError:
            return jsonify({
                "error": "El parámetro evento es inválido.",
                "error_code": "INVALID_EVENT",
                "source": "archivo_depurado_local",
            }), 400

        municipio = request.args.get("municipio")
        payload = build_dashboard_data(base_dir=base_dir, event_code=event_code, municipio=municipio)
        if not payload.get("ok"):
            status_code = int(payload.get("status_code") or 500)
            return jsonify({
                "error": payload.get("error"),
                "error_code": payload.get("error_code") or "DATA_ERROR",
                "source": "archivo_depurado_local",
            }), status_code
        return jsonify(payload.get("data"))

    @app.route("/boletines")
    def bulletins_public():
        query = Bulletin.query.filter_by(status=BulletinStatus.PUBLICADO)

        q = (request.args.get("q") or "").strip()
        evento = (request.args.get("evento") or "").strip()
        desde = (request.args.get("desde") or "").strip()
        hasta = (request.args.get("hasta") or "").strip()

        if q:
            like_q = f"%{q}%"
            query = query.filter((Bulletin.title.ilike(like_q)) | (Bulletin.content.ilike(like_q)))

        if evento.isdigit():
            query = query.filter(Bulletin.event_code == int(evento))

        if desde:
            try:
                d_from = datetime.strptime(desde, "%Y-%m-%d")
                query = query.filter(Bulletin.created_at >= d_from)
            except ValueError:
                flash("Fecha desde inválida.", "error")

        if hasta:
            try:
                d_to = datetime.strptime(hasta, "%Y-%m-%d")
                query = query.filter(Bulletin.created_at <= d_to.replace(hour=23, minute=59, second=59))
            except ValueError:
                flash("Fecha hasta inválida.", "error")

        bulletins = query.order_by(Bulletin.published_at.desc().nullslast(), Bulletin.created_at.desc()).all()
        eventos = Event.query.filter_by(active=True).order_by(Event.code.asc()).all()

        return render_template(
            "bulletins_public.html",
            bulletins=bulletins,
            eventos=eventos,
            filters={"q": q, "evento": evento, "desde": desde, "hasta": hasta},
        )

    @app.route("/boletines/<int:bulletin_id>/download")
    def download_bulletin(bulletin_id: int):
        bulletin = Bulletin.query.get_or_404(bulletin_id)

        user = current_user()
        can_view = bulletin.status == BulletinStatus.PUBLICADO

        if user and user.role == UserRole.SECRETARIO:
            can_view = True
        elif user and user.role == UserRole.EPIDEMIOLOGO and bulletin.author_id == user.id:
            can_view = True

        if not can_view:
            abort(403)

        download_dir = base_dir / "data" / "DEPURADO"
        download_dir.mkdir(parents=True, exist_ok=True)
        file_path = download_dir / f"boletin_{bulletin.id}.txt"

        text = (
            f"EPIPROC - Procesamiento Epidemiológico\n"
            f"Boletín #{bulletin.id}\n"
            f"Evento: {bulletin.event_code} - {bulletin.event.name if bulletin.event else ''}\n"
            f"Estado: {bulletin.status}\n"
            f"Autor: {bulletin.author.full_name if bulletin.author else ''}\n"
            f"Fecha: {bulletin.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Título: {bulletin.title}\n\n"
            f"Contenido:\n{bulletin.content}\n"
        )
        file_path.write_text(text, encoding="utf-8")

        return send_file(file_path, as_attachment=True, download_name=file_path.name)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            selected_profile = (request.form.get("access_profile") or "EPIDEMIOLOGO").strip().upper()
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""

            if not username or not password:
                flash("Debes ingresar usuario y contraseña.", "error")
                return render_template("login.html", selected_profile=selected_profile)

            user = User.query.filter_by(username=username).first()
            valid_login = bool(user and user.check_password(password))

            # Fallback remoto: si falla login local, validar contra Apps Script y sincronizar en caliente.
            if not valid_login and selected_profile == "EPIDEMIOLOGO":
                try:
                    if _sync_from_apps_script_credentials(username, password):
                        user = User.query.filter_by(username=username).first()
                        valid_login = bool(user and user.check_password(password))
                except Exception:
                    valid_login = False

            if not valid_login:
                flash("Credenciales inválidas.", "error")
                return render_template("login.html", selected_profile=selected_profile)

            if selected_profile == "ADMINISTRADOR" and user.role != UserRole.SECRETARIO:
                flash("Este acceso es exclusivo para secretario de salud.", "error")
                return render_template("login.html", selected_profile=selected_profile)

            if selected_profile == "EPIDEMIOLOGO" and user.role != UserRole.EPIDEMIOLOGO:
                flash("Este acceso es exclusivo para epidemiología.", "error")
                return render_template("login.html", selected_profile=selected_profile)

            if not user.is_active:
                flash("Usuario inactivo. Contacta al Secretario de Salud.", "error")
                return render_template("login.html", selected_profile=selected_profile)

            session["user_id"] = user.id
            log_action("LOGIN", "USER", str(user.id), "Inicio de sesión exitoso")

            next_url = request.args.get("next")
            if next_url:
                return redirect(next_url)
            return redirect(url_for("portal"))

        return render_template("login.html", selected_profile="EPIDEMIOLOGO")

    @app.route("/logout")
    def logout():
        user = current_user()
        if user:
            log_action("LOGOUT", "USER", str(user.id), "Cierre de sesión")
        session.clear()
        flash("Sesión cerrada exitosamente.", "success")
        return redirect(url_for("home"))

    @app.route("/cambiar-clave", methods=["GET", "POST"])
    @login_required
    def change_password():
        user = current_user()
        assert user is not None

        if request.method == "POST":
            current_password = request.form.get("current_password") or ""
            new_password = request.form.get("new_password") or ""
            confirm_password = request.form.get("confirm_password") or ""

            if not user.check_password(current_password):
                flash("La contraseña actual no es correcta.", "error")
                return render_template("change_password.html")

            if len(new_password) < 8:
                flash("La nueva contraseña debe tener al menos 8 caracteres.", "error")
                return render_template("change_password.html")

            if new_password != confirm_password:
                flash("La confirmación de contraseña no coincide.", "error")
                return render_template("change_password.html")

            if user.role == UserRole.EPIDEMIOLOGO:
                try:
                    _apps_script_action(
                        "actualizar_epidemiologo",
                        timeout_seconds=12,
                        old_usuario=user.username,
                        old_cedula=user.cedula,
                        usuario=user.username,
                        nombre=user.full_name,
                        cedula=user.cedula,
                        correo=user.email,
                        evento=_event_display_from_code(user.assigned_event_code),
                        estado="Activo" if user.is_active else "Inactivo",
                        password_temporal=new_password,
                    )
                except Exception as exc:
                    flash(f"No fue posible actualizar la contraseña en Google Sheets: {exc}", "error")
                    return render_template("change_password.html")

            user.set_password(new_password)
            if user.role == UserRole.EPIDEMIOLOGO:
                user.set_visible_password(new_password)
                user.credentials_updated_at = datetime.utcnow()
            user.must_change_password = False
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                flash("No fue posible guardar la nueva contraseña localmente. Intenta nuevamente.", "error")
                return render_template("change_password.html")
            log_action("PASSWORD_CHANGED", "USER", str(user.id), "Cambio de contraseña")

            flash("Contraseña actualizada exitosamente.", "success")
            return redirect(url_for("portal"))

        return render_template("change_password.html")

    @app.route("/portal")
    @login_required
    def portal():
        user = current_user()
        assert user is not None

        if user.role == UserRole.SECRETARIO:
            return redirect(url_for("admin_panel"))
        if user.role == UserRole.EPIDEMIOLOGO:
            return redirect(url_for("epi_panel"))
        abort(403)

    @app.route("/admin")
    @role_required(UserRole.SECRETARIO)
    def admin_panel():
        remote_cedulas: Optional[set[str]] = None
        remote_usernames: Optional[set[str]] = None
        remote_emails: Optional[set[str]] = None
        try:
            _, _, remote_cedulas, remote_usernames, remote_emails = _sync_all_epidemiologos_from_apps_script()
        except Exception:
            # Si Google Sheets no esta disponible, se muestra el estado local sin interrumpir al usuario.
            pass

        epi_rows = _get_admin_epidemiologo_rows(
            remote_cedulas=remote_cedulas,
            remote_usernames=remote_usernames,
            remote_emails=remote_emails,
        )
        total_epi = len(epi_rows)
        total_boletines = Bulletin.query.count()
        publicados = Bulletin.query.filter_by(status=BulletinStatus.PUBLICADO).count()
        status_filter = (request.args.get("estado") or "TODOS").strip().upper()
        recent_bulletin_rows = _get_admin_recent_bulletin_rows(status_filter)

        return render_template(
            "admin_panel.html",
            total_epi=total_epi,
            total_boletines=total_boletines,
            publicados=publicados,
            epi_rows=epi_rows,
            recent_bulletin_rows=recent_bulletin_rows,
            status_filter=status_filter,
            compact_topnav=True,
        )

    @app.route("/admin/dashboard")
    @role_required(UserRole.SECRETARIO)
    def admin_dashboard():
        return render_template(
            "dashboard_legacy_embed.html",
            dashboard_url=url_for("legacy_dashboard_html"),
            dashboard_context="secretario",
        )

    @app.route("/admin/epidemiologos")
    @role_required(UserRole.SECRETARIO)
    def admin_epi_list():
        remote_cedulas: Optional[set[str]] = None
        remote_usernames: Optional[set[str]] = None
        remote_emails: Optional[set[str]] = None
        try:
            _, _, remote_cedulas, remote_usernames, remote_emails = _sync_all_epidemiologos_from_apps_script()
        except Exception:
            # Si Google Sheets no esta disponible, se muestra el estado local sin interrumpir al usuario.
            pass

        q = (request.args.get("q") or "").strip()
        estado = (request.args.get("estado") or "").strip().upper()

        query = User.query.filter_by(role=UserRole.EPIDEMIOLOGO)
        query = _apply_remote_epidemiologo_visibility_filter(
            query,
            remote_cedulas,
            remote_usernames,
            remote_emails,
        )

        if q:
            like_q = f"%{q}%"
            query = query.filter(
                or_(
                    User.full_name.ilike(like_q),
                    User.username.ilike(like_q),
                    User.cedula.ilike(like_q),
                    User.email.ilike(like_q),
                )
            )

        if estado == "ACTIVO":
            query = query.filter(User.is_active.is_(True))
        elif estado == "INACTIVO":
            query = query.filter(User.is_active.is_(False))

        users = query.order_by(User.full_name.asc()).all()
        eventos = Event.query.order_by(Event.code.asc()).all()
        return render_template(
            "admin_epi_list.html",
            users=users,
            eventos=eventos,
            filters={"q": q, "estado": estado},
        )

    @app.route("/admin/api/epidemiologos/sync", methods=["POST"])
    @role_required(UserRole.SECRETARIO)
    def admin_epi_sync_from_apps_script():
        try:
            payload = request.get_json(silent=True) or {}

            full_name = str(payload.get("nombre") or "").strip()
            cedula = str(payload.get("cedula") or "").strip()
            email = str(payload.get("correo") or "").strip().lower()
            evento_display = str(payload.get("evento") or "").strip()
            username = str(payload.get("user") or payload.get("usuario") or cedula).strip()
            password_plain = str(payload.get("pass") or payload.get("password_temporal") or "").strip()
            estado = str(payload.get("estado") or "Activo").strip()

            ok, message, user = _upsert_local_epidemiologo(
                full_name=full_name,
                cedula=cedula,
                email=email,
                username=username,
                password_plain=password_plain,
                evento_display=evento_display,
                estado=estado,
            )

            if not ok or user is None:
                return jsonify({"success": False, "error": message}), 409

            return jsonify(
                {
                    "success": True,
                    "id": user.id,
                    "username": user.username,
                    "cedula": user.cedula,
                    "email": user.email,
                }
            )
        except Exception as exc:
            db.session.rollback()
            return jsonify({"success": False, "error": f"Fallo sincronizacion local: {exc}"}), 500

    @app.route("/admin/epidemiologos/nuevo", methods=["GET", "POST"])
    @role_required(UserRole.SECRETARIO)
    def admin_epi_new():
        eventos = Event.query.filter_by(active=True).order_by(Event.code.asc()).all()

        if request.method == "POST":
            full_name = (request.form.get("full_name") or "").strip()
            cedula = (request.form.get("cedula") or "").strip()
            email = (request.form.get("email") or "").strip().lower()
            assigned_event = (request.form.get("assigned_event") or "").strip()

            errors = _validate_user_payload(full_name, cedula, email)
            if assigned_event and not assigned_event.isdigit():
                errors.append("El evento asignado es inválido.")

            if errors:
                for err in errors:
                    flash(err, "error")
                return render_template(
                    "admin_epi_form.html",
                    eventos=eventos,
                    user_obj=None,
                    mode="create",
                )

            username_base = generate_username(full_name, cedula)
            username = _resolve_unique_username(username_base)
            temp_password = generate_temp_password()

            assigned_event_code = int(assigned_event) if assigned_event else None
            evento_display = _event_display_from_code(assigned_event_code)

            try:
                payload = _apps_script_action(
                    "registrar_epidemiologo",
                    timeout_seconds=12,
                    nombre=full_name,
                    cedula=cedula,
                    correo=email,
                    evento=evento_display,
                    usuario=username,
                    password_temporal=temp_password,
                    estado="Activo",
                )
            except Exception as exc:
                flash(f"No fue posible registrar en Google Sheets: {exc}", "error")
                return render_template(
                    "admin_epi_form.html",
                    eventos=eventos,
                    user_obj=None,
                    mode="create",
                )

            remote_username = str(payload.get("user") or payload.get("usuario") or username).strip()
            remote_password = str(payload.get("pass") or payload.get("password_temporal") or temp_password).strip()
            ok, message, user = _upsert_local_epidemiologo(
                full_name=full_name,
                cedula=cedula,
                email=email,
                username=remote_username,
                password_plain=remote_password,
                evento_display=evento_display,
                estado="Activo",
            )
            if not ok or user is None:
                try:
                    _apps_script_action(
                        "eliminar_epidemiologo",
                        timeout_seconds=10,
                        usuario=remote_username,
                        cedula=cedula,
                    )
                except Exception:
                    pass
                flash(message or "No fue posible sincronizar el usuario local.", "error")
                return render_template(
                    "admin_epi_form.html",
                    eventos=eventos,
                    user_obj=None,
                    mode="create",
                )

            email_ok, email_message = send_credentials_email(email, full_name, remote_username, remote_password)

            details = (
                f"Usuario creado: {remote_username}; evento={user.assigned_event_code}; sincronizado en Google Sheets"
            )
            log_action("CREATE_USER", "USER", str(user.id), details)

            flash(
                (
                    "Epidemiólogo creado exitosamente. "
                    f"Usuario: {remote_username} | Contraseña temporal: {remote_password}"
                ),
                "success",
            )
            if email_ok:
                flash(email_message, "success")
            else:
                flash(email_message, "warning")

            return redirect(url_for("admin_epi_list"))

        return render_template(
            "admin_epi_form.html",
            eventos=eventos,
            user_obj=None,
            mode="create",
        )

    @app.route("/admin/epidemiologos/<int:user_id>/eliminar", methods=["POST"])
    @role_required(UserRole.SECRETARIO)
    def admin_epi_delete(user_id: int):
        user = User.query.get_or_404(user_id)
        if user.role != UserRole.EPIDEMIOLOGO:
            abort(400)

        try:
            _apps_script_action(
                "eliminar_epidemiologo",
                timeout_seconds=10,
                usuario=user.username,
                cedula=user.cedula,
            )
        except Exception as exc:
            flash(f"No fue posible eliminar en Google Sheets: {exc}", "error")
            return redirect(url_for("admin_epi_list"))

        db.session.delete(user)
        db.session.commit()
        log_action("DELETE_USER", "USER", str(user_id), f"Usuario {user.username} eliminado")

        flash("Epidemiólogo eliminado en EPIPROC y Google Sheets.", "success")
        return redirect(url_for("admin_epi_list"))

    @app.route("/admin/epidemiologos/<int:user_id>/estado", methods=["POST"])
    @role_required(UserRole.SECRETARIO)
    def admin_epi_toggle_status(user_id: int):
        user = User.query.get_or_404(user_id)
        if user.role != UserRole.EPIDEMIOLOGO:
            abort(400)

        new_estado = "Activo" if not user.is_active else "Inactivo"
        try:
            _apps_script_action(
                "actualizar_estado_epidemiologo",
                timeout_seconds=10,
                usuario=user.username,
                cedula=user.cedula,
                estado=new_estado,
            )
        except Exception as exc:
            flash(f"No fue posible actualizar estado en Google Sheets: {exc}", "error")
            return redirect(url_for("admin_epi_list"))

        user.is_active = new_estado == "Activo"
        db.session.commit()
        log_action(
            "TOGGLE_USER_STATUS",
            "USER",
            str(user.id),
            f"{user.username} => {'ACTIVO' if user.is_active else 'INACTIVO'}",
        )

        flash(
            f"Usuario {user.username} ahora está {'activo' if user.is_active else 'inactivo'}.",
            "success",
        )
        return redirect(url_for("admin_epi_list"))

    @app.route("/admin/epidemiologos/<int:user_id>/regenerar-clave", methods=["POST"])
    @role_required(UserRole.SECRETARIO)
    def admin_epi_reset_password(user_id: int):
        user = User.query.get_or_404(user_id)
        if user.role != UserRole.EPIDEMIOLOGO:
            abort(400)

        try:
            payload = _apps_script_action(
                "regenerar_password_epidemiologo",
                timeout_seconds=12,
                usuario=user.username,
                cedula=user.cedula,
            )
        except Exception as exc:
            flash(f"No fue posible regenerar clave en Google Sheets: {exc}", "error")
            return redirect(url_for("admin_epi_list"))

        new_password = str(payload.get("pass") or payload.get("password_temporal") or "").strip()
        if not new_password:
            flash("Google Sheets no devolvió la nueva contraseña temporal.", "error")
            return redirect(url_for("admin_epi_list"))

        remote_user = str(payload.get("user") or payload.get("usuario") or user.username).strip()
        if remote_user:
            user.username = remote_user

        user.set_password(new_password)
        user.set_visible_password(new_password)
        user.credentials_updated_at = datetime.utcnow()
        user.must_change_password = True
        db.session.commit()

        log_action(
            "RESET_PASSWORD",
            "USER",
            str(user.id),
            f"Regenerada clave para {user.username}",
        )

        flash(
            f"Nueva contraseña para {user.username}: {new_password}",
            "success",
        )
        return redirect(url_for("admin_epi_list"))

    @app.route("/admin/epidemiologos/<int:user_id>/editar", methods=["GET", "POST"])
    @role_required(UserRole.SECRETARIO)
    def admin_epi_edit(user_id: int):
        user = User.query.get_or_404(user_id)
        if user.role != UserRole.EPIDEMIOLOGO:
            abort(400)

        eventos = Event.query.filter_by(active=True).order_by(Event.code.asc()).all()

        if request.method == "POST":
            full_name = (request.form.get("full_name") or "").strip()
            cedula = (request.form.get("cedula") or "").strip()
            email = (request.form.get("email") or "").strip().lower()
            username = (request.form.get("username") or "").strip().lower()
            assigned_event = (request.form.get("assigned_event") or "").strip()
            is_active = request.form.get("is_active") == "on"

            password_mode = (request.form.get("password_mode") or "keep").strip().lower()
            manual_password = request.form.get("manual_password") or ""
            force_change = request.form.get("must_change_password") == "on"

            errors = _validate_user_payload(full_name, cedula, email)

            if not username or len(username) < 4:
                errors.append("El usuario debe tener al menos 4 caracteres.")

            if assigned_event and not assigned_event.isdigit():
                errors.append("El evento asignado es inválido.")

            if User.query.filter(User.id != user.id, User.cedula == cedula).first():
                errors.append("Ya existe un usuario con esa cédula.")
            if User.query.filter(User.id != user.id, User.email == email).first():
                errors.append("Ya existe un usuario con ese correo.")
            if User.query.filter(User.id != user.id, User.username == username).first():
                errors.append("Ya existe un usuario con ese nombre de usuario.")

            if password_mode not in {"keep", "manual", "random"}:
                errors.append("Modo de contraseña inválido.")

            if password_mode == "manual" and len(manual_password) < 8:
                errors.append("La contraseña manual debe tener al menos 8 caracteres.")

            if errors:
                for err in errors:
                    flash(err, "error")
                return render_template("admin_epi_form.html", eventos=eventos, user_obj=user, mode="edit")

            old_username = user.username
            old_cedula = user.cedula
            next_username = _resolve_unique_username_for_edit(username, exclude_user_id=user.id)
            assigned_event_code = int(assigned_event) if assigned_event else None
            evento_display = _event_display_from_code(assigned_event_code)

            password_changed = False
            visible_password = None

            if password_mode == "random":
                visible_password = generate_temp_password()
                password_changed = True
            elif password_mode == "manual":
                visible_password = manual_password
                password_changed = True

            remote_payload: dict[str, Any] = {
                "old_usuario": old_username,
                "old_cedula": old_cedula,
                "usuario": next_username,
                "nombre": full_name,
                "cedula": cedula,
                "correo": email,
                "evento": evento_display,
                "estado": "Activo" if is_active else "Inactivo",
            }
            if password_changed and visible_password:
                remote_payload["password_temporal"] = visible_password

            try:
                _apps_script_action(
                    "actualizar_epidemiologo",
                    timeout_seconds=12,
                    **remote_payload,
                )
            except Exception as exc:
                flash(f"No fue posible actualizar en Google Sheets: {exc}", "error")
                return render_template("admin_epi_form.html", eventos=eventos, user_obj=user, mode="edit")

            user.full_name = full_name
            user.cedula = cedula
            user.email = email
            user.username = next_username
            user.assigned_event_code = assigned_event_code
            user.is_active = is_active

            if password_changed and visible_password:
                user.set_password(visible_password)
                user.must_change_password = force_change
                user.set_visible_password(visible_password)
                user.credentials_updated_at = datetime.utcnow()

            if not password_changed:
                user.must_change_password = force_change if request.form.get("must_change_password") is not None else user.must_change_password

            db.session.commit()

            detail = f"Editado usuario {user.username}; evento={user.assigned_event_code}; activo={user.is_active}"
            if password_changed:
                detail += "; contraseña actualizada"
            log_action("EDIT_USER", "USER", str(user.id), detail)

            if password_changed and visible_password:
                flash(
                    f"Usuario actualizado. Credenciales actuales: {user.username} | {visible_password}",
                    "success",
                )
            else:
                flash("Usuario actualizado exitosamente.", "success")

            return redirect(url_for("admin_epi_list"))

        return render_template("admin_epi_form.html", eventos=eventos, user_obj=user, mode="edit")

    @app.route("/admin/epidemiologos/<int:user_id>/asignar-evento", methods=["POST"])
    @role_required(UserRole.SECRETARIO)
    def admin_epi_assign_event(user_id: int):
        user = User.query.get_or_404(user_id)
        if user.role != UserRole.EPIDEMIOLOGO:
            abort(400)

        event_code = (request.form.get("assigned_event") or "").strip()
        event_code_value: Optional[int] = None
        if not event_code:
            event_code_value = None
        else:
            if not event_code.isdigit() or Event.query.get(int(event_code)) is None:
                flash("Evento inválido para asignación.", "error")
                return redirect(url_for("admin_epi_list"))
            event_code_value = int(event_code)

        try:
            _apps_script_action(
                "actualizar_evento_epidemiologo",
                timeout_seconds=10,
                usuario=user.username,
                cedula=user.cedula,
                evento=_event_display_from_code(event_code_value),
            )
        except Exception as exc:
            flash(f"No fue posible actualizar evento en Google Sheets: {exc}", "error")
            return redirect(url_for("admin_epi_list"))

        user.assigned_event_code = event_code_value

        db.session.commit()
        log_action(
            "ASSIGN_EVENT",
            "USER",
            str(user.id),
            f"Asignado evento {user.assigned_event_code} a {user.username}",
        )

        flash("Evento asignado correctamente.", "success")
        return redirect(url_for("admin_epi_list"))

    @app.route("/admin/boletines")
    @role_required(UserRole.SECRETARIO)
    def admin_bulletins():
        query = Bulletin.query

        q = (request.args.get("q") or "").strip()
        evento = (request.args.get("evento") or "").strip()
        estado = (request.args.get("estado") or "").strip().upper()
        desde = (request.args.get("desde") or "").strip()
        hasta = (request.args.get("hasta") or "").strip()

        if q:
            like_q = f"%{q}%"
            query = query.filter((Bulletin.title.ilike(like_q)) | (Bulletin.content.ilike(like_q)))

        if evento.isdigit():
            query = query.filter(Bulletin.event_code == int(evento))

        if estado in {BulletinStatus.BORRADOR, BulletinStatus.PUBLICADO}:
            query = query.filter(Bulletin.status == estado)

        if desde:
            try:
                d_from = datetime.strptime(desde, "%Y-%m-%d")
                query = query.filter(Bulletin.created_at >= d_from)
            except ValueError:
                flash("Fecha desde inválida.", "error")

        if hasta:
            try:
                d_to = datetime.strptime(hasta, "%Y-%m-%d")
                query = query.filter(Bulletin.created_at <= d_to.replace(hour=23, minute=59, second=59))
            except ValueError:
                flash("Fecha hasta inválida.", "error")

        bulletins = query.order_by(Bulletin.updated_at.desc()).all()
        eventos = Event.query.order_by(Event.code.asc()).all()

        return render_template(
            "admin_bulletins.html",
            bulletins=bulletins,
            eventos=eventos,
            filters={"q": q, "evento": evento, "estado": estado, "desde": desde, "hasta": hasta},
        )

    @app.route("/admin/boletines/nuevo", methods=["GET", "POST"])
    @role_required(UserRole.SECRETARIO)
    def admin_bulletin_new():
        return _save_bulletin_form(user=current_user(), is_admin=True, bulletin=None)

    @app.route("/admin/boletines/<int:bulletin_id>/editar", methods=["GET", "POST"])
    @role_required(UserRole.SECRETARIO)
    def admin_bulletin_edit(bulletin_id: int):
        bulletin = Bulletin.query.get_or_404(bulletin_id)
        return _save_bulletin_form(user=current_user(), is_admin=True, bulletin=bulletin)

    @app.route("/admin/auditoria")
    @role_required(UserRole.SECRETARIO)
    def admin_audit():
        logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(300).all()
        return render_template("admin_audit.html", logs=logs)

    @app.route("/epi")
    @role_required(UserRole.EPIDEMIOLOGO)
    def epi_panel():
        user = current_user()
        assert user is not None
        status_filter = (request.args.get("estado") or "TODOS").strip().upper()
        bulletin_rows = _get_epi_bulletin_rows(user, status_filter)
        return render_template(
            "epi_panel.html",
            assigned_event=user.assigned_event,
            bulletin_rows=bulletin_rows,
            status_filter=status_filter,
            compact_topnav=True,
        )

    @app.route("/epi/dashboard")
    @role_required(UserRole.EPIDEMIOLOGO)
    def epi_dashboard():
        user = current_user()
        assert user is not None
        if not user.assigned_event_code:
            flash("No tienes evento asignado aún. Contacta al Secretario de Salud.", "warning")
            return redirect(url_for("epi_panel"))

        return render_template(
            "dashboard_legacy_embed.html",
            dashboard_url=url_for("legacy_dashboard_html"),
            dashboard_context="epidemiologo",
        )

    @app.route("/epi/boletines")
    @role_required(UserRole.EPIDEMIOLOGO)
    def epi_bulletins():
        user = current_user()
        assert user is not None

        status_filter = (request.args.get("estado") or "TODOS").strip().upper()
        bulletin_rows = _get_epi_bulletin_rows(user, status_filter)
        return render_template(
            "epi_bulletins.html",
            bulletins=[row["bulletin"] for row in bulletin_rows],
            bulletin_rows=bulletin_rows,
            assigned_event=user.assigned_event,
            status_filter=status_filter,
        )

    @app.route("/epi/boletines/nuevo", methods=["GET", "POST"])
    @role_required(UserRole.EPIDEMIOLOGO)
    def epi_bulletin_new():
        return _save_bulletin_form(user=current_user(), is_admin=False, bulletin=None)

    @app.route("/epi/boletines/<int:bulletin_id>/editar", methods=["GET", "POST"])
    @role_required(UserRole.EPIDEMIOLOGO)
    def epi_bulletin_edit(bulletin_id: int):
        bulletin = Bulletin.query.get_or_404(bulletin_id)
        user = current_user()
        assert user is not None

        if bulletin.author_id != user.id:
            abort(403)

        return _save_bulletin_form(user=user, is_admin=False, bulletin=bulletin)

    @app.route("/epi/boletines/<int:bulletin_id>/eliminar", methods=["POST"])
    @role_required(UserRole.EPIDEMIOLOGO)
    def epi_bulletin_delete(bulletin_id: int):
        bulletin = Bulletin.query.get_or_404(bulletin_id)
        user = current_user()
        assert user is not None

        if bulletin.author_id != user.id:
            abort(403)

        deleted_title = bulletin.title
        deleted_status = bulletin.status
        deleted_event = bulletin.event_code

        db.session.delete(bulletin)
        db.session.commit()
        log_action(
            "DELETE_BULLETIN",
            "BULLETIN",
            str(bulletin_id),
            f"Titulo={deleted_title}, estado={deleted_status}, evento={deleted_event}",
        )
        flash("Boletín eliminado exitosamente.", "success")

        next_url = request.form.get("next") or request.referrer or url_for("epi_panel")
        return redirect(next_url)

    def _save_bulletin_form(user: Optional[User], is_admin: bool, bulletin: Optional[Bulletin]):
        assert user is not None

        if not is_admin and user.role == UserRole.EPIDEMIOLOGO:
            try:
                _sync_all_epidemiologos_from_apps_script()
            except Exception:
                pass
            user = User.query.get(user.id) or user

        eventos = Event.query.filter_by(active=True).order_by(Event.code.asc()).all()
        assigned_event_code = user.assigned_event_code

        if request.method == "POST":
            title = (request.form.get("title") or "").strip()
            content = (request.form.get("content") or "").strip()
            status = (request.form.get("status") or BulletinStatus.BORRADOR).strip().upper()
            event_code_raw = (request.form.get("event_code") or "").strip()

            errors: list[str] = []
            if len(title) < 6:
                errors.append("El título debe tener al menos 6 caracteres.")
            if len(content) < 20:
                errors.append("El contenido debe tener al menos 20 caracteres.")
            if status not in {BulletinStatus.BORRADOR, BulletinStatus.PUBLICADO}:
                errors.append("Estado de boletín inválido.")
            if not event_code_raw.isdigit():
                errors.append("Debes seleccionar un evento válido.")

            event_code = int(event_code_raw) if event_code_raw.isdigit() else None
            if event_code is not None and Event.query.get(event_code) is None:
                errors.append("El evento seleccionado no existe.")

            if not is_admin and assigned_event_code and event_code is not None and event_code != assigned_event_code:
                errors.append("Solo puedes crear/editar boletines para tu evento asignado.")

            if not is_admin and not assigned_event_code:
                errors.append("No tienes evento asignado para redactar boletines.")

            if errors:
                for err in errors:
                    flash(err, "error")
                template_name = "epi_bulletin_form.html"
                return render_template(template_name, bulletin=bulletin, eventos=eventos, assigned_event=assigned_event_code)

            if bulletin is None:
                bulletin = Bulletin(
                    title=title,
                    content=content,
                    status=status,
                    event_code=int(event_code),
                    author_id=user.id,
                )
                if status == BulletinStatus.PUBLICADO:
                    bulletin.published_at = datetime.utcnow()

                db.session.add(bulletin)
                db.session.commit()
                log_action(
                    "CREATE_BULLETIN",
                    "BULLETIN",
                    str(bulletin.id),
                    f"Estado={status}, evento={event_code}",
                )
                flash("Boletín creado exitosamente.", "success")
            else:
                bulletin.title = title
                bulletin.content = content
                bulletin.status = status
                bulletin.event_code = int(event_code)
                if status == BulletinStatus.PUBLICADO and bulletin.published_at is None:
                    bulletin.published_at = datetime.utcnow()
                if status == BulletinStatus.BORRADOR:
                    bulletin.published_at = None

                db.session.commit()
                log_action(
                    "EDIT_BULLETIN",
                    "BULLETIN",
                    str(bulletin.id),
                    f"Estado={status}, evento={event_code}",
                )
                flash("Boletín actualizado exitosamente.", "success")

            return redirect(url_for("admin_bulletins" if is_admin else "epi_bulletins"))

        template_name = "epi_bulletin_form.html"
        return render_template(template_name, bulletin=bulletin, eventos=eventos, assigned_event=assigned_event_code)


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(403)
    def err_403(error):
        if request.path.startswith("/api"):
            return jsonify({"error": "No autorizado para este recurso."}), 403
        return render_template("error.html", title="Acceso denegado", message="No tienes permisos para acceder a este recurso."), 403

    @app.errorhandler(404)
    def err_404(error):
        if request.path.startswith("/api"):
            return jsonify({"error": "Recurso no encontrado."}), 404
        return render_template("error.html", title="No encontrado", message="La ruta solicitada no existe."), 404

    @app.errorhandler(Exception)
    def err_any(error):
        if isinstance(error, HTTPException):
            code = error.code or 500
            if request.path.startswith("/api"):
                return jsonify({"error": error.description}), code
            return error

        if request.path.startswith("/api"):
            return jsonify({"error": f"Error interno de servidor: {error}"}), 500

        return (
            render_template(
                "error.html",
                title="Error interno",
                message="Ocurrió un error inesperado. Intenta nuevamente.",
            ),
            500,
        )
