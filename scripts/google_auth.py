from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow


DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _dedupe_scopes(scopes: Iterable[str]) -> list[str]:
    unique_scopes: list[str] = []
    for scope in scopes:
        value = str(scope or "").strip()
        if value and value not in unique_scopes:
            unique_scopes.append(value)
    return unique_scopes


def _log(logger: Any, level: str, message: str) -> None:
    if logger is None:
        return
    log_method = getattr(logger, level, None)
    if callable(log_method):
        log_method(message)


def _load_payload(credentials_path: Path) -> dict[str, Any]:
    with open(credentials_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _resolve_client_config(payload: dict[str, Any]) -> dict[str, Any]:
    client_config = payload.get("installed") or payload.get("web")
    if not isinstance(client_config, dict):
        raise RuntimeError("El archivo de credenciales de Google no es válido para OAuth de usuario.")
    return client_config


def _load_token_data(token_path: Path) -> Optional[dict[str, Any]]:
    if not token_path.exists():
        return None
    try:
        with open(token_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def _save_user_token(credentials: UserCredentials, token_path: Path) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri or DEFAULT_TOKEN_URI,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes or []),
    }
    with open(token_path, "w", encoding="utf-8") as handle:
        json.dump(token_data, handle, indent=2, ensure_ascii=False)


def _token_matches_client(token_data: dict[str, Any], client_config: dict[str, Any]) -> bool:
    return str(token_data.get("client_id") or "").strip() == str(client_config.get("client_id") or "").strip()


def _credentials_have_scopes(credentials: UserCredentials, requested_scopes: list[str]) -> bool:
    available_scopes = list(getattr(credentials, "scopes", []) or [])
    return set(requested_scopes).issubset(set(available_scopes))


def load_google_credentials(
    *,
    credentials_path: str | Path,
    scopes: Iterable[str],
    token_path: str | Path | None = None,
    allow_interactive: bool = True,
    logger: Any = None,
) -> tuple[UserCredentials | ServiceAccountCredentials, str]:
    credentials_file = Path(credentials_path)
    if not credentials_file.exists():
        raise RuntimeError(f"Archivo de credenciales no encontrado: {credentials_file}")

    requested_scopes = _dedupe_scopes(scopes)
    if not requested_scopes:
        raise RuntimeError("Debes indicar al menos un scope de Google.")

    payload = _load_payload(credentials_file)
    credential_type = str(payload.get("type") or "").strip().lower()

    if credential_type == "service_account":
        credentials = ServiceAccountCredentials.from_service_account_file(
            str(credentials_file),
            scopes=requested_scopes,
        )
        return credentials, "service_account"

    client_config = _resolve_client_config(payload)
    oauth_token_path = Path(token_path) if token_path else credentials_file.with_name("token.json")
    token_data = _load_token_data(oauth_token_path)
    combined_scopes = list(requested_scopes)
    credentials: Optional[UserCredentials] = None

    if token_data is not None:
        if not _token_matches_client(token_data, client_config):
            _log(
                logger,
                "warning",
                "El token OAuth existente pertenece a otro client_id. Se solicitará una autorización nueva.",
            )
        else:
            combined_scopes = _dedupe_scopes(list(token_data.get("scopes") or []) + requested_scopes)
            try:
                credentials = UserCredentials.from_authorized_user_info(token_data, combined_scopes)
            except Exception as exc:
                _log(logger, "warning", f"No se pudo reutilizar el token OAuth actual: {exc}")
                credentials = None

    if credentials is not None:
        if not credentials.valid and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                _save_user_token(credentials, oauth_token_path)
            except Exception as exc:
                _log(logger, "warning", f"No se pudo refrescar el token OAuth: {exc}")
                credentials = None

        if credentials is not None and credentials.valid and _credentials_have_scopes(credentials, requested_scopes):
            return credentials, "oauth"

    if not allow_interactive:
        raise RuntimeError(
            "No hay un token OAuth válido con los scopes requeridos. Ejecuta una autorización interactiva."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), combined_scopes)
    credentials = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
    )
    _save_user_token(credentials, oauth_token_path)
    return credentials, "oauth"