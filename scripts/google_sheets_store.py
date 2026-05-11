from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Optional

from googleapiclient.discovery import build

from config.settings import Settings
from scripts.google_auth import load_google_credentials


def _column_number_to_a1(column_number: int) -> str:
    result = ""
    while column_number > 0:
        column_number, remainder = divmod(column_number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _normalize_text(value: Any) -> str:
    txt = str(value or "").strip().lower()
    return " ".join(txt.split())


@dataclass
class EpidemiologoRecord:
    nombre: str
    cedula: str
    correo: str
    evento: str
    usuario: str
    password_temporal: str
    estado: str
    fecha_registro: str


class GoogleSheetsStore:
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

    def __init__(self, credentials_path: Optional[str] = None):
        settings = Settings()
        self.settings = settings
        self.credentials_path = str(credentials_path or settings.GOOGLE_SHEETS_CREDENTIALS_PATH)
        credentials, credential_mode = load_google_credentials(
            credentials_path=self.credentials_path,
            scopes=self.SCOPES,
            token_path=self.settings.GOOGLE_DRIVE_TOKEN_PATH,
        )
        self.credential_mode = credential_mode
        self.service = build("sheets", "v4", credentials=credentials)

    def get_values(self, spreadsheet_id: str, range_name: str) -> list[list[Any]]:
        response = self.service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name,
        ).execute()
        return response.get("values") or []

    def update_values(self, spreadsheet_id: str, range_name: str, values: list[list[Any]]) -> dict[str, Any]:
        return self.service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()

    def append_values(self, spreadsheet_id: str, range_name: str, values: list[list[Any]]) -> dict[str, Any]:
        return self.service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()

    def batch_update_values(self, spreadsheet_id: str, data: list[dict[str, Any]]) -> dict[str, Any]:
        return self.service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "USER_ENTERED",
                "data": data,
            },
        ).execute()

    def delete_sheet_row(self, spreadsheet_id: str, sheet_id: int, row_number: int) -> None:
        self.service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "deleteDimension": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "ROWS",
                                "startIndex": row_number - 1,
                                "endIndex": row_number,
                            }
                        }
                    }
                ]
            },
        ).execute()

    def get_sheet_metadata(self, spreadsheet_id: str, sheet_name: str) -> dict[str, Any]:
        metadata = self.service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        for sheet in metadata.get("sheets", []):
            props = sheet.get("properties") or {}
            if props.get("title") == sheet_name:
                return props
        raise RuntimeError(f"No se encontró la pestaña {sheet_name} en el spreadsheet {spreadsheet_id}.")


class EpidemiologosSheetStore:
    HEADERS = [
        "nombre",
        "cedula",
        "correo",
        "evento",
        "usuario",
        "password_temporal",
        "estado",
        "fecha_registro",
    ]

    def __init__(self, sheets_store: Optional[GoogleSheetsStore] = None):
        self.settings = Settings()
        self.sheets_store = sheets_store or GoogleSheetsStore()
        self.spreadsheet_id = str(self.settings.EPIDEMIOLOGOS_SPREADSHEET_ID).strip()
        self.sheet_name = str(self.settings.EPIDEMIOLOGOS_SHEET_NAME).strip()

    def _range_all(self) -> str:
        return f"{self.sheet_name}!A:H"

    def _ensure_headers(self) -> None:
        values = self.sheets_store.get_values(self.spreadsheet_id, f"{self.sheet_name}!A1:H1")
        if not values:
            self.sheets_store.update_values(self.spreadsheet_id, f"{self.sheet_name}!A1:H1", [self.HEADERS])
            return

        first_row = [str(item).strip() for item in values[0]]
        if first_row != self.HEADERS:
            self.sheets_store.update_values(self.spreadsheet_id, f"{self.sheet_name}!A1:H1", [self.HEADERS])

    def _rows_with_numbers(self) -> list[tuple[int, list[Any]]]:
        self._ensure_headers()
        values = self.sheets_store.get_values(self.spreadsheet_id, self._range_all())
        rows = []
        for row_number, row in enumerate(values[1:], start=2):
            normalized = [str(item).strip() for item in row]
            if not any(normalized):
                continue
            rows.append((row_number, row))
        return rows

    def _pad_row(self, row: list[Any]) -> list[str]:
        padded = [str(item).strip() if item is not None else "" for item in row]
        if len(padded) < len(self.HEADERS):
            padded.extend([""] * (len(self.HEADERS) - len(padded)))
        return padded[: len(self.HEADERS)]

    def _row_to_item(self, row: list[Any]) -> dict[str, Any]:
        padded = self._pad_row(row)
        return {
            "nombre": padded[0],
            "cedula": padded[1],
            "correo": padded[2],
            "evento": padded[3],
            "usuario": padded[4] or padded[1],
            "password_temporal": padded[5],
            "estado": padded[6] or "Activo",
            "fecha_registro": padded[7],
        }

    def _find_row(self, usuario: str = "", cedula: str = "") -> Optional[tuple[int, dict[str, Any]]]:
        user_target = str(usuario or "").strip()
        cedula_target = str(cedula or "").strip()
        for row_number, row in self._rows_with_numbers():
            item = self._row_to_item(row)
            if user_target and item["usuario"] == user_target:
                return row_number, item
            if cedula_target and item["cedula"] == cedula_target:
                return row_number, item
        return None

    def list_items(self) -> list[dict[str, Any]]:
        items = []
        for _, row in self._rows_with_numbers():
            item = self._row_to_item(row)
            if not item["cedula"]:
                continue
            items.append(item)
        return items

    def create(
        self,
        *,
        nombre: str,
        cedula: str,
        correo: str,
        evento: str,
        usuario: Optional[str] = None,
        password_temporal: str,
        estado: str = "Activo",
    ) -> dict[str, Any]:
        nombre = str(nombre or "").strip()
        cedula = str(cedula or "").strip()
        correo = str(correo or "").strip().lower()
        evento = str(evento or "").strip()
        usuario = str(usuario or cedula).strip()
        password_temporal = str(password_temporal or "").strip()
        estado = "Inactivo" if _normalize_text(estado) == "inactivo" else "Activo"

        if not nombre or not cedula or not correo or not evento or not password_temporal:
            raise RuntimeError("Datos incompletos para registrar epidemiológo en Google Sheets.")

        for item in self.list_items():
            if item["cedula"] == cedula:
                raise RuntimeError("Ya existe un epidemiológo registrado con esa cédula.")
            if item["usuario"] == usuario:
                raise RuntimeError("Ya existe un epidemiológo registrado con ese usuario.")
            if item["correo"] == correo:
                raise RuntimeError("Ya existe un epidemiológo registrado con ese correo.")

        self.sheets_store.append_values(
            self.spreadsheet_id,
            self._range_all(),
            [[nombre, cedula, correo, evento, usuario, password_temporal, estado, datetime.utcnow().isoformat()]],
        )
        return {"success": True, "user": usuario, "pass": password_temporal}

    def authenticate(self, usuario: str, password: str) -> dict[str, Any]:
        usuario = str(usuario or "").strip()
        password = str(password or "")
        if not usuario or not password:
            return {"success": False, "error": "Usuario y contraseña obligatorios."}

        found = self._find_row(usuario=usuario)
        if found is None:
            return {"success": False, "error": "Credenciales inválidas en Google Sheets."}

        _, item = found
        if item["estado"].strip().lower() == "inactivo":
            return {"success": False, "error": "Usuario inactivo."}
        if item["password_temporal"] != password:
            return {"success": False, "error": "Credenciales inválidas en Google Sheets."}

        payload = {"success": True}
        payload.update(item)
        return payload

    def update_status(self, usuario: str, cedula: str, estado: str) -> dict[str, Any]:
        found = self._find_row(usuario=usuario, cedula=cedula)
        if found is None:
            raise RuntimeError("No existe epidemiológo para actualizar estado.")

        row_number, item = found
        estado_txt = "Inactivo" if _normalize_text(estado) == "inactivo" else "Activo"
        self.sheets_store.update_values(self.spreadsheet_id, f"{self.sheet_name}!G{row_number}", [[estado_txt]])
        return {"success": True, "usuario": item["usuario"], "estado": estado_txt}

    def update_event(self, usuario: str, cedula: str, evento: str) -> dict[str, Any]:
        found = self._find_row(usuario=usuario, cedula=cedula)
        if found is None:
            raise RuntimeError("No existe epidemiológo para actualizar evento.")

        row_number, item = found
        evento_txt = str(evento or "").strip() or "No especificado"
        self.sheets_store.update_values(self.spreadsheet_id, f"{self.sheet_name}!D{row_number}", [[evento_txt]])
        return {"success": True, "usuario": item["usuario"], "evento": evento_txt}

    def regenerate_password(self, usuario: str, cedula: str, new_password: str) -> dict[str, Any]:
        found = self._find_row(usuario=usuario, cedula=cedula)
        if found is None:
            raise RuntimeError("No existe epidemiológo para regenerar clave.")

        row_number, item = found
        password_txt = str(new_password or "").strip()
        if not password_txt:
            raise RuntimeError("No se proporcionó la nueva contraseña temporal.")

        self.sheets_store.update_values(self.spreadsheet_id, f"{self.sheet_name}!F{row_number}", [[password_txt]])
        return {"success": True, "user": item["usuario"], "pass": password_txt, "password_temporal": password_txt}

    def update(self, body: dict[str, Any]) -> dict[str, Any]:
        old_usuario = str(body.get("old_usuario") or "").strip()
        old_cedula = str(body.get("old_cedula") or "").strip()
        found = self._find_row(usuario=old_usuario or str(body.get("usuario") or "").strip(), cedula=old_cedula or str(body.get("cedula") or "").strip())
        if found is None:
            raise RuntimeError("No existe epidemiológo para actualizar.")

        row_number, current = found
        nombre = str(body.get("nombre") or "").strip()
        cedula = str(body.get("cedula") or "").strip()
        correo = str(body.get("correo") or "").strip().lower()
        evento = str(body.get("evento") or current["evento"] or "No especificado").strip()
        usuario = str(body.get("usuario") or cedula).strip()
        estado = "Inactivo" if _normalize_text(body.get("estado")) == "inactivo" else "Activo"
        password_temporal = str(body.get("password_temporal") or current["password_temporal"]).strip()

        if not nombre or not cedula or not correo or not usuario:
            raise RuntimeError("Datos incompletos para actualizar epidemiológo.")

        for other_row_number, row in self._rows_with_numbers():
            if other_row_number == row_number:
                continue
            item = self._row_to_item(row)
            if item["cedula"] == cedula:
                raise RuntimeError("Ya existe otra fila con la cédula indicada.")
            if item["usuario"] == usuario:
                raise RuntimeError("Ya existe otra fila con el usuario indicado.")
            if item["correo"] == correo:
                raise RuntimeError("Ya existe otra fila con el correo indicado.")

        fecha_registro = current.get("fecha_registro") or datetime.utcnow().isoformat()
        self.sheets_store.update_values(
            self.spreadsheet_id,
            f"{self.sheet_name}!A{row_number}:H{row_number}",
            [[nombre, cedula, correo, evento, usuario, password_temporal, estado, fecha_registro]],
        )
        return {
            "success": True,
            "usuario": usuario,
            "cedula": cedula,
            "correo": correo,
            "evento": evento,
            "estado": estado,
            "password_temporal": password_temporal,
        }

    def delete(self, usuario: str, cedula: str) -> dict[str, Any]:
        found = self._find_row(usuario=usuario, cedula=cedula)
        if found is None:
            raise RuntimeError("No existe epidemiológo para eliminar.")

        row_number, item = found
        sheet_id = int(self.sheets_store.get_sheet_metadata(self.spreadsheet_id, self.sheet_name)["sheetId"])
        self.sheets_store.delete_sheet_row(self.spreadsheet_id, sheet_id, row_number)
        return {"success": True, "usuario": item["usuario"]}


class Historico549SheetStore:
    def __init__(self, sheets_store: Optional[GoogleSheetsStore] = None):
        self.settings = Settings()
        self.sheets_store = sheets_store or GoogleSheetsStore()
        self.spreadsheet_id = str(self.settings.HISTORICO_549_SPREADSHEET_ID).strip()
        self.sheet_name = str(self.settings.HISTORICO_549_SHEET_NAME).strip()

    def _range_all(self) -> str:
        return f"{self.sheet_name}!A:ZZ"

    def _parse_week(self, value: Any) -> Optional[int]:
        txt = str(value or "").strip()
        if not txt:
            return None
        if re.fullmatch(r"\d{1,2}", txt):
            week = int(txt)
            if 1 <= week <= 53:
                return week
        return None

    def _parse_number(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            try:
                return float(value)
            except Exception:
                return None

        txt = str(value).strip()
        if not txt:
            return None

        txt = txt.replace(" ", "")
        if "," in txt and "." in txt:
            if txt.rfind(",") > txt.rfind("."):
                txt = txt.replace(".", "").replace(",", ".")
            else:
                txt = txt.replace(",", "")
        elif "," in txt:
            txt = txt.replace(".", "").replace(",", ".")

        try:
            return float(txt)
        except Exception:
            return None

    def _discover_layout(self, values: list[list[Any]]) -> dict[str, Any]:
        if not values:
            values = [["SEMANA"]]

        headers = [str(item).strip() for item in (values[0] if values else [])]
        if not headers:
            headers = ["SEMANA"]

        week_col_index = 0
        for idx, header in enumerate(headers):
            norm = _normalize_text(header)
            if norm in {"semana", "week"}:
                week_col_index = idx
                break

        year_col_map: dict[int, int] = {}
        for idx, header in enumerate(headers):
            txt = str(header).strip()
            if re.fullmatch(r"\d{4}", txt):
                year_col_map[int(txt)] = idx

        week_row_map: dict[int, int] = {}
        for row_number, row in enumerate(values[1:], start=2):
            week_value = row[week_col_index] if week_col_index < len(row) else ""
            week = self._parse_week(week_value)
            if week is None:
                continue
            week_row_map[week] = row_number

        return {
            "headers": headers,
            "week_col_index": week_col_index,
            "year_col_map": year_col_map,
            "week_row_map": week_row_map,
        }

    def _extract_row_number_from_updated_range(self, updated_range: str) -> Optional[int]:
        if not updated_range:
            return None
        m = re.search(r"!(?:[A-Z]+)(\d+)(?::[A-Z]+\d+)?$", str(updated_range).strip())
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None

    def _ensure_initial_structure(self, values: list[list[Any]]) -> None:
        if values:
            return
        self.sheets_store.update_values(self.spreadsheet_id, f"{self.sheet_name}!A1:A1", [["SEMANA"]])

    def obtener_casos_por_anio(self) -> dict[str, Any]:
        values = self.sheets_store.get_values(self.spreadsheet_id, self._range_all())
        self._ensure_initial_structure(values)
        if not values:
            values = self.sheets_store.get_values(self.spreadsheet_id, self._range_all())

        layout = self._discover_layout(values)
        year_col_map: dict[int, int] = layout["year_col_map"]
        week_row_map: dict[int, int] = layout["week_row_map"]

        cases_by_year: dict[int, dict[int, int]] = {year: {} for year in sorted(year_col_map.keys())}

        for week, row_number in week_row_map.items():
            row_index = row_number - 1
            if row_index < 0 or row_index >= len(values):
                continue
            row = values[row_index]
            for year, col_idx in year_col_map.items():
                cell = row[col_idx] if col_idx < len(row) else None
                number = self._parse_number(cell)
                if number is None:
                    continue
                cases_by_year[year][int(week)] = int(round(number))

        return {
            "success": True,
            "spreadsheet_id": self.spreadsheet_id,
            "sheet_name": self.sheet_name,
            "years_available": sorted(cases_by_year.keys()),
            "cases_by_year": cases_by_year,
        }

    def upsert_weekly_counts(self, weekly_counts_by_year: dict[int, dict[int, int]]) -> dict[str, Any]:
        cleaned: dict[int, dict[int, int]] = {}
        for raw_year, week_map in (weekly_counts_by_year or {}).items():
            try:
                year = int(raw_year)
            except Exception:
                continue

            if year < 1900 or year > 2100:
                continue

            cleaned_weeks: dict[int, int] = {}
            for raw_week, raw_value in (week_map or {}).items():
                try:
                    week = int(raw_week)
                except Exception:
                    continue
                if week < 1 or week > 53:
                    continue

                try:
                    value = int(round(float(raw_value)))
                except Exception:
                    continue

                cleaned_weeks[week] = max(0, value)

            if cleaned_weeks:
                cleaned[year] = cleaned_weeks

        if not cleaned:
            return {
                "success": False,
                "updated_cells": 0,
                "message": "No hay conteos válidos para sincronizar",
            }

        values = self.sheets_store.get_values(self.spreadsheet_id, self._range_all())
        self._ensure_initial_structure(values)
        if not values:
            values = self.sheets_store.get_values(self.spreadsheet_id, self._range_all())

        layout = self._discover_layout(values)
        headers: list[str] = layout["headers"]
        week_col_index: int = layout["week_col_index"]
        year_col_map: dict[int, int] = dict(layout["year_col_map"])
        week_row_map: dict[int, int] = dict(layout["week_row_map"])

        if week_col_index == 0 and (_normalize_text(headers[0]) not in {"semana", "week"}):
            self.sheets_store.update_values(self.spreadsheet_id, f"{self.sheet_name}!A1", [["SEMANA"]])
            headers[0] = "SEMANA"

        # Crear encabezados de años faltantes sin tocar otras columnas/fórmulas.
        for year in sorted(cleaned.keys()):
            if year in year_col_map:
                continue
            col_index = len(headers)
            headers.append(str(year))
            year_col_map[year] = col_index
            header_cell = f"{self.sheet_name}!{_column_number_to_a1(col_index + 1)}1"
            self.sheets_store.update_values(self.spreadsheet_id, header_cell, [[str(year)]])

        # Asegurar filas de semana (solo si no existen).
        weeks_needed = sorted({week for wk_map in cleaned.values() for week in wk_map.keys()})
        for week in weeks_needed:
            if week in week_row_map:
                continue
            append_result = self.sheets_store.append_values(self.spreadsheet_id, self._range_all(), [[int(week)]])
            updated_range = (((append_result or {}).get("updates") or {}).get("updatedRange") or "")
            row_number = self._extract_row_number_from_updated_range(updated_range)
            if row_number is None:
                refreshed = self.sheets_store.get_values(self.spreadsheet_id, self._range_all())
                refreshed_layout = self._discover_layout(refreshed)
                week_row_map = dict(refreshed_layout["week_row_map"])
            else:
                week_row_map[week] = row_number

        updates: list[dict[str, Any]] = []
        for year in sorted(cleaned.keys()):
            col_idx = year_col_map[year]
            col_a1 = _column_number_to_a1(col_idx + 1)
            for week, cases in sorted(cleaned[year].items()):
                row_number = week_row_map.get(week)
                if not row_number:
                    continue
                updates.append({
                    "range": f"{self.sheet_name}!{col_a1}{row_number}",
                    "values": [[int(cases)]],
                })

        if updates:
            self.sheets_store.batch_update_values(self.spreadsheet_id, updates)

        return {
            "success": True,
            "updated_cells": len(updates),
            "years_updated": sorted(cleaned.keys()),
            "weeks_updated": weeks_needed,
        }

    def comparar_semana(self, *, anio: int, semana: int) -> dict[str, Any]:
        if semana < 1 or semana > 53:
            raise RuntimeError("La semana epidemiológica debe estar entre 1 y 53.")

        dataset = self.obtener_casos_por_anio()
        years_available = [int(y) for y in dataset.get("years_available") or []]
        cases_by_year: dict[int, dict[int, int]] = dataset.get("cases_by_year") or {}

        if int(anio) not in years_available:
            raise RuntimeError(f"El año {anio} no existe en la hoja histórica.")

        previous_years = [y for y in years_available if y < int(anio)]
        if not previous_years:
            raise RuntimeError("No existe año previo para comparación.")
        anio_prev = max(previous_years)

        casos_actual = (cases_by_year.get(int(anio)) or {}).get(int(semana))
        casos_prev = (cases_by_year.get(int(anio_prev)) or {}).get(int(semana))

        variacion = None
        tendencia = "sin_dato"
        if casos_actual is not None and casos_prev is not None and casos_prev > 0:
            variacion = round(((int(casos_actual) - int(casos_prev)) / int(casos_prev)) * 100, 1)
            if variacion > 0:
                tendencia = "aumento"
            elif variacion < 0:
                tendencia = "disminucion"
            else:
                tendencia = "sin_cambio"

        return {
            "success": True,
            "week": int(semana),
            "target_year": int(anio),
            "previous_year": int(anio_prev),
            "current_year_cases": casos_actual,
            "previous_year_cases": casos_prev,
            "percent_change": variacion,
            "trend": tendencia,
        }

    def guardar_resumen(self, *, semana: int, anio: int, total_casos: int, clasificaciones: Optional[list[str]] = None) -> dict[str, Any]:
        if semana < 1 or semana > 53:
            raise RuntimeError("La semana epidemiológica debe estar entre 1 y 53.")

        values = self.sheets_store.get_values(self.spreadsheet_id, f"{self.sheet_name}!A:ZZ")
        if not values:
            raise RuntimeError("La hoja histórica 549 está vacía.")

        headers = [str(item).strip() for item in values[0]]
        year_text = str(int(anio))
        if year_text not in headers:
            raise RuntimeError(f"La hoja histórica no tiene la columna del año {anio}.")

        year_col_index = headers.index(year_text) + 1
        target_row_number = None
        previous_value = None
        for row_number, row in enumerate(values[1:], start=2):
            week_value = str(row[0]).strip() if row else ""
            if week_value == str(int(semana)):
                target_row_number = row_number
                if len(row) >= year_col_index:
                    previous_value = row[year_col_index - 1]
                break

        if target_row_number is None:
            raise RuntimeError(f"La hoja histórica no tiene una fila para la semana {semana}.")

        cell = f"{self.sheet_name}!{_column_number_to_a1(year_col_index)}{target_row_number}"
        self.sheets_store.update_values(self.spreadsheet_id, cell, [[int(total_casos)]])
        resumen_clasificaciones = {
            "confirmados": sum(1 for item in (clasificaciones or []) if _normalize_text(item) == "confirmado"),
            "probables": sum(1 for item in (clasificaciones or []) if _normalize_text(item) == "probable"),
            "descartados": sum(1 for item in (clasificaciones or []) if _normalize_text(item) == "descartado"),
        }
        return {
            "success": True,
            "updated_cell": cell,
            "week": int(semana),
            "year": int(anio),
            "total_cases": int(total_casos),
            "previous_value": previous_value,
            "clasificacion_resumen": resumen_clasificaciones,
        }