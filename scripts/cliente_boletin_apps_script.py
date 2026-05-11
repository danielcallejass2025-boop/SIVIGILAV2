"""
Cliente Python para consumir directamente Google Sheets del boletín semanal.

Mantiene la misma interfaz pública histórica para evitar cambios en el resto
del proyecto, aunque ya no depende de Apps Script.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
from typing import Any, Optional
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import Settings
from scripts.google_auth import load_google_credentials
from scripts.utils import Logger


@dataclass
class BulletinAppsScriptConfig:
    credentials_path: str
    spreadsheet_id: str
    sheet_name: str
    event_code: int
    timezone: str
    treat_trailing_zeros_as_missing: bool
    timeout_seconds: int


class BulletinAppsScriptClient:
    SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

    def __init__(self, config: Optional[BulletinAppsScriptConfig] = None):
        settings = Settings()
        self.logger = Logger()
        self.config = config or BulletinAppsScriptConfig(
            credentials_path=str(settings.GOOGLE_SHEETS_CREDENTIALS_PATH or "").strip(),
            spreadsheet_id=str(settings.BULLETIN_SPREADSHEET_ID or "").strip(),
            sheet_name=str(settings.BULLETIN_SHEET_NAME or "").strip(),
            event_code=int(settings.BULLETIN_EVENT_CODE),
            timezone=str(settings.BULLETIN_TIMEZONE or "America/Bogota").strip(),
            treat_trailing_zeros_as_missing=bool(settings.BULLETIN_TREAT_TRAILING_ZEROS_AS_MISSING),
            timeout_seconds=int(settings.BULLETIN_APPS_SCRIPT_TIMEOUT_SECONDS),
        )
        self._service = None
        self._dataset_cache: Optional[dict[str, Any]] = None

    def _now_iso(self) -> str:
        return datetime.now(ZoneInfo(self.config.timezone)).isoformat()

    def _normalize_header(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return re.sub(r"[^a-z0-9]+", "", text)

    def _coerce_number(self, value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, (int, float)):
            if math.isnan(value):
                return None
            return float(value)

        text = str(value).strip()
        if not text:
            return None

        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif "," in text:
            text = text.replace(".", "").replace(",", ".")

        try:
            return float(text)
        except ValueError:
            return None

    def _clean_number(self, value: Optional[float]) -> Optional[float | int]:
        if value is None:
            return None
        if float(value).is_integer():
            return int(value)
        return round(float(value), 2)

    def _build_service(self):
        if self._service is not None:
            return self._service

        if not self.config.credentials_path:
            raise RuntimeError("GOOGLE_SHEETS_CREDENTIALS_PATH no configurado.")
        if not self.config.spreadsheet_id:
            raise RuntimeError("BULLETIN_SPREADSHEET_ID no configurado.")

        credentials, _ = load_google_credentials(
            credentials_path=self.config.credentials_path,
            scopes=self.SHEETS_SCOPES,
            token_path=Settings().GOOGLE_DRIVE_TOKEN_PATH,
            logger=self.logger,
        )
        self._service = build("sheets", "v4", credentials=credentials)
        return self._service

    def _load_dataset(self) -> dict[str, Any]:
        if self._dataset_cache is not None:
            return self._dataset_cache

        service = self._build_service()
        response = service.spreadsheets().values().get(
            spreadsheetId=self.config.spreadsheet_id,
            range=self.config.sheet_name,
            valueRenderOption="UNFORMATTED_VALUE",
        ).execute()
        values = response.get("values") or []
        if not values:
            raise RuntimeError("La hoja del boletín está vacía o no fue accesible.")

        headers = [str(item).strip() for item in values[0]]
        normalized = [self._normalize_header(item) for item in headers]

        try:
            week_index = normalized.index("semana")
        except ValueError as exc:
            raise RuntimeError("La hoja CASOS 2 no tiene columna SEMANA.") from exc

        year_columns: list[int] = []
        year_index_map: dict[int, int] = {}
        for index, header in enumerate(headers):
            txt = str(header).strip()
            if re.fullmatch(r"\d{4}", txt):
                year = int(txt)
                year_columns.append(year)
                year_index_map[year] = index

        if not year_columns:
            raise RuntimeError("La hoja CASOS 2 no tiene columnas de año.")

        year_columns.sort()
        stats_indexes = {
            "average": next((i for i, key in enumerate(normalized) if key in {"promedio", "promediohistorico"}), None),
            "upper": next((i for i, key in enumerate(normalized) if key == "limitesuperior"), None),
            "lower": next((i for i, key in enumerate(normalized) if key == "limiteinferior"), None),
            "stddev": next((i for i, key in enumerate(normalized) if key in {"desv", "desviacion"}), None),
        }

        rows: list[dict[str, Any]] = []
        for row_number, raw_row in enumerate(values[1:], start=2):
            week_raw = raw_row[week_index] if week_index < len(raw_row) else None
            week_number = self._coerce_number(week_raw)
            if week_number is None:
                continue
            week = int(week_number)
            if week < 1 or week > 53:
                continue

            cases_by_year = {
                year: self._coerce_number(raw_row[idx] if idx < len(raw_row) else None)
                for year, idx in year_index_map.items()
            }
            sheet_stats = {
                key: self._coerce_number(raw_row[idx] if idx is not None and idx < len(raw_row) else None)
                for key, idx in stats_indexes.items()
            }
            rows.append(
                {
                    "semana": week,
                    "sourceRowNumber": row_number,
                    "casesByYear": cases_by_year,
                    "sheetStats": sheet_stats,
                }
            )

        self._dataset_cache = {
            "config": {
                "eventCode": self.config.event_code,
                "spreadsheetId": self.config.spreadsheet_id,
                "sheetName": self.config.sheet_name,
                "timezone": self.config.timezone,
            },
            "rows": rows,
            "yearColumns": year_columns,
            "latestYear": max(year_columns),
        }
        return self._dataset_cache

    def _resolve_target_year(self, dataset: dict[str, Any], anio: Optional[int]) -> int:
        target_year = int(anio) if anio is not None else int(dataset["latestYear"])
        if target_year not in dataset["yearColumns"]:
            raise RuntimeError(f"El año {target_year} no existe en la hoja CASOS 2.")
        return target_year

    def _resolve_previous_year(self, dataset: dict[str, Any], target_year: int) -> int:
        previous = [year for year in dataset["yearColumns"] if year < target_year]
        if not previous:
            raise RuntimeError("No existe un año histórico previo para comparar.")
        return previous[-1]

    def _detect_year_progress(self, rows: list[dict[str, Any]], target_year: int, treat_trailing_zeros_as_missing: bool) -> dict[str, Any]:
        last_week = None
        for row in rows:
            value = row["casesByYear"].get(target_year)
            if value is None:
                continue
            if treat_trailing_zeros_as_missing:
                if float(value) > 0:
                    last_week = row["semana"]
            else:
                last_week = row["semana"]

        trailing = []
        if treat_trailing_zeros_as_missing and last_week is not None:
            for row in rows:
                value = row["casesByYear"].get(target_year)
                if row["semana"] > last_week and value is not None and float(value) == 0:
                    trailing.append(row["semana"])

        return {
            "lastWeekWithObservedData": last_week,
            "trailingPlaceholderWeeks": trailing,
        }

    def _get_comparable_value(
        self,
        row: dict[str, Any],
        target_year: int,
        progress: dict[str, Any],
        treat_trailing_zeros_as_missing: bool,
    ) -> Optional[float]:
        value = row["casesByYear"].get(target_year)
        if value is None:
            return None
        if not treat_trailing_zeros_as_missing:
            return value

        last_week = progress.get("lastWeekWithObservedData")
        if last_week is not None and row["semana"] > last_week and float(value) == 0:
            return None
        return value

    def _compute_historical_stats(self, row: dict[str, Any], year_columns: list[int], target_year: int) -> dict[str, Any]:
        years_used = [year for year in year_columns if year < target_year]
        values_used = [row["casesByYear"].get(year) for year in years_used]
        values_used = [float(value) for value in values_used if value is not None]

        if not values_used:
            return {
                "years_used": years_used,
                "values_used": [],
                "average": None,
                "stddev": None,
                "upper_limit": None,
                "lower_limit": None,
            }

        average = sum(values_used) / len(values_used)
        if len(values_used) > 1:
            variance = sum((value - average) ** 2 for value in values_used) / (len(values_used) - 1)
            stddev = math.sqrt(variance)
        else:
            stddev = 0.0

        return {
            "years_used": years_used,
            "values_used": [self._clean_number(value) for value in values_used],
            "average": self._clean_number(average),
            "stddev": self._clean_number(stddev),
            "upper_limit": self._clean_number(average + stddev),
            "lower_limit": self._clean_number(max(0.0, average - stddev)),
        }

    def _classify_against_limits(self, value: Optional[float], upper: Optional[float], lower: Optional[float]) -> str:
        if value is None or (upper is None and lower is None):
            return "sin_dato"
        if upper is not None and value > upper:
            return "sobre_lo_esperado"
        if lower is not None and value < lower:
            return "por_debajo_de_lo_esperado"
        return "dentro_de_lo_esperado"

    def _build_week_row_payload(
        self,
        dataset: dict[str, Any],
        row: dict[str, Any],
        target_year: int,
        treat_trailing_zeros_as_missing: bool,
        include_recalculated_stats: bool,
    ) -> dict[str, Any]:
        progress = self._detect_year_progress(dataset["rows"], target_year, treat_trailing_zeros_as_missing)
        comparable_value = self._get_comparable_value(row, target_year, progress, treat_trailing_zeros_as_missing)
        payload = {
            "week": row["semana"],
            "source_row_number": row["sourceRowNumber"],
            "cases_by_year": {str(year): self._clean_number(value) for year, value in row["casesByYear"].items()},
            "current_year_cases": self._clean_number(comparable_value),
            "current_year_cases_raw": self._clean_number(row["casesByYear"].get(target_year)),
            "is_current_value_placeholder": comparable_value is None and row["casesByYear"].get(target_year) is not None,
            "sheet_reference": {
                "average": self._clean_number(row["sheetStats"].get("average")),
                "upper_limit": self._clean_number(row["sheetStats"].get("upper")),
                "lower_limit": self._clean_number(row["sheetStats"].get("lower")),
                "stddev": self._clean_number(row["sheetStats"].get("stddev")),
            },
        }
        if include_recalculated_stats:
            payload["historical_reference"] = self._compute_historical_stats(row, dataset["yearColumns"], target_year)
        return payload

    def _find_week_row(self, rows: list[dict[str, Any]], week: int) -> Optional[dict[str, Any]]:
        for row in rows:
            if row["semana"] == week:
                return row
        return None

    def _build_comparison_from_row(self, dataset: dict[str, Any], row: dict[str, Any], target_year: int, basis: str) -> dict[str, Any]:
        previous_year = self._resolve_previous_year(dataset, target_year)
        progress = self._detect_year_progress(
            dataset["rows"],
            target_year,
            self.config.treat_trailing_zeros_as_missing,
        )
        current_value = self._get_comparable_value(
            row,
            target_year,
            progress,
            self.config.treat_trailing_zeros_as_missing,
        )
        current_raw_value = row["casesByYear"].get(target_year)
        previous_value = row["casesByYear"].get(previous_year)
        historical_stats = self._compute_historical_stats(row, dataset["yearColumns"], target_year)
        sheet_reference = {
            "average": self._clean_number(row["sheetStats"].get("average")),
            "upper_limit": self._clean_number(row["sheetStats"].get("upper")),
            "lower_limit": self._clean_number(row["sheetStats"].get("lower")),
            "stddev": self._clean_number(row["sheetStats"].get("stddev")),
        }

        difference = None
        percent_change = None
        trend = "sin_dato"
        if current_value is not None and previous_value is not None:
            difference = current_value - previous_value
            if difference > 0:
                trend = "aumento"
            elif difference < 0:
                trend = "disminucion"
            else:
                trend = "igual"

            if previous_value != 0:
                percent_change = ((current_value - previous_value) / previous_value) * 100

        return {
            "success": True,
            "source": "CASOS 2",
            "comparison_basis": basis,
            "event_code": dataset["config"]["eventCode"],
            "spreadsheet_id": dataset["config"]["spreadsheetId"],
            "sheet_name": dataset["config"]["sheetName"],
            "generated_at": self._now_iso(),
            "week": row["semana"],
            "target_year": target_year,
            "previous_year": previous_year,
            "current_year_cases": self._clean_number(current_value),
            "current_year_cases_raw": self._clean_number(current_raw_value),
            "previous_year_cases": self._clean_number(previous_value),
            "absolute_change": self._clean_number(difference),
            "percent_change": self._clean_number(percent_change),
            "trend": trend,
            "last_week_with_observed_data": progress["lastWeekWithObservedData"],
            "is_current_value_placeholder": current_value is None and current_raw_value is not None,
            "historical_reference": historical_stats,
            "sheet_reference": sheet_reference,
            "expected_status_sheet": self._classify_against_limits(
                current_value,
                row["sheetStats"].get("upper"),
                row["sheetStats"].get("lower"),
            ),
            "expected_status_recalculated": self._classify_against_limits(
                current_value,
                historical_stats.get("upper_limit"),
                historical_stats.get("lower_limit"),
            ),
        }

    def health(self) -> dict[str, Any]:
        dataset = self._load_dataset()
        return {
            "success": True,
            "service": "EPIPROC_BULLETIN_GOOGLE_SHEETS",
            "status": "ok",
            "event_code": dataset["config"]["eventCode"],
            "spreadsheet_id": dataset["config"]["spreadsheetId"],
            "sheet_name": dataset["config"]["sheetName"],
            "timezone": dataset["config"]["timezone"],
            "generated_at": self._now_iso(),
        }

    def leer_metadata(self, anio: Optional[int] = None) -> dict[str, Any]:
        dataset = self._load_dataset()
        target_year = self._resolve_target_year(dataset, anio)
        progress = self._detect_year_progress(
            dataset["rows"],
            target_year,
            self.config.treat_trailing_zeros_as_missing,
        )
        return {
            "success": True,
            "event_code": dataset["config"]["eventCode"],
            "spreadsheet_id": dataset["config"]["spreadsheetId"],
            "sheet_name": dataset["config"]["sheetName"],
            "generated_at": self._now_iso(),
            "year_columns": dataset["yearColumns"],
            "target_year": target_year,
            "latest_year_in_sheet": dataset["latestYear"],
            "total_weeks": len(dataset["rows"]),
            "last_week_with_observed_data": progress["lastWeekWithObservedData"],
            "trailing_placeholder_weeks": progress["trailingPlaceholderWeeks"],
        }

    def leer_base(
        self,
        anio: Optional[int] = None,
        only_until_last_observed: bool = True,
        include_diagnostics: bool = True,
        include_recalculated_stats: bool = True,
    ) -> dict[str, Any]:
        dataset = self._load_dataset()
        target_year = self._resolve_target_year(dataset, anio)
        progress = self._detect_year_progress(
            dataset["rows"],
            target_year,
            self.config.treat_trailing_zeros_as_missing,
        )
        rows = []
        for row in dataset["rows"]:
            if only_until_last_observed and progress["lastWeekWithObservedData"] is not None and row["semana"] > progress["lastWeekWithObservedData"]:
                continue
            rows.append(
                self._build_week_row_payload(
                    dataset,
                    row,
                    target_year,
                    self.config.treat_trailing_zeros_as_missing,
                    include_recalculated_stats,
                )
            )

        payload = {
            "success": True,
            "source": "CASOS 2",
            "event_code": dataset["config"]["eventCode"],
            "spreadsheet_id": dataset["config"]["spreadsheetId"],
            "sheet_name": dataset["config"]["sheetName"],
            "target_year": target_year,
            "latest_year_in_sheet": dataset["latestYear"],
            "last_week_with_observed_data": progress["lastWeekWithObservedData"],
            "treat_trailing_zeros_as_missing": self.config.treat_trailing_zeros_as_missing,
            "rows": rows,
        }
        if include_diagnostics:
            payload["diagnostics"] = {
                "total_weeks": len(dataset["rows"]),
                "trailing_placeholder_weeks": progress["trailingPlaceholderWeeks"],
            }
        return payload

    def leer_semana(self, anio: int, semana: int) -> dict[str, Any]:
        dataset = self._load_dataset()
        target_year = self._resolve_target_year(dataset, anio)
        row = self._find_week_row(dataset["rows"], semana)
        if row is None:
            raise RuntimeError("La semana solicitada no existe en la hoja.")
        return {
            "success": True,
            "source": "CASOS 2",
            "event_code": dataset["config"]["eventCode"],
            "spreadsheet_id": dataset["config"]["spreadsheetId"],
            "sheet_name": dataset["config"]["sheetName"],
            "generated_at": self._now_iso(),
            "week": semana,
            "target_year": target_year,
            "row": self._build_week_row_payload(
                dataset,
                row,
                target_year,
                self.config.treat_trailing_zeros_as_missing,
                True,
            ),
        }

    def comparar_semana(self, anio: int, semana: int) -> dict[str, Any]:
        dataset = self._load_dataset()
        target_year = self._resolve_target_year(dataset, anio)
        row = self._find_week_row(dataset["rows"], semana)
        if row is None:
            raise RuntimeError("La semana solicitada no existe en la hoja.")
        return self._build_comparison_from_row(dataset, row, target_year, "semana_solicitada")

    def boletin_ultima_semana(self, anio: Optional[int] = None) -> dict[str, Any]:
        dataset = self._load_dataset()
        target_year = self._resolve_target_year(dataset, anio)
        progress = self._detect_year_progress(
            dataset["rows"],
            target_year,
            self.config.treat_trailing_zeros_as_missing,
        )
        week = progress["lastWeekWithObservedData"]
        if week is None:
            raise RuntimeError("No se detectó una semana con datos observados para el año solicitado.")
        row = self._find_week_row(dataset["rows"], week)
        if row is None:
            raise RuntimeError("No se encontró la fila de la última semana observada.")
        return self._build_comparison_from_row(dataset, row, target_year, "ultima_semana_disponible")

    def validar_canal(self, anio: Optional[int] = None, tolerance: float = 0.05) -> dict[str, Any]:
        dataset = self._load_dataset()
        target_year = self._resolve_target_year(dataset, anio)
        averages = [
            row["sheetStats"].get("average")
            for row in dataset["rows"]
            if row["sheetStats"].get("average") is not None
        ]
        warnings = []
        if averages:
            min_avg = min(averages)
            max_avg = max(averages)
            if max_avg > 0 and (max_avg - min_avg) / max_avg <= tolerance:
                warnings.append(
                    "Los valores de promedio historico en la hoja parecen casi constantes. Verifica formulas o referencias del canal."
                )

        progress = self._detect_year_progress(
            dataset["rows"],
            target_year,
            self.config.treat_trailing_zeros_as_missing,
        )
        return {
            "success": True,
            "source": "CASOS 2",
            "event_code": dataset["config"]["eventCode"],
            "spreadsheet_id": dataset["config"]["spreadsheetId"],
            "sheet_name": dataset["config"]["sheetName"],
            "target_year": target_year,
            "last_week_with_observed_data": progress["lastWeekWithObservedData"],
            "warnings": warnings,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cliente del Apps Script del boletín semanal CASOS 2"
    )
    parser.add_argument("--anio", type=int, default=None, help="Año objetivo para la consulta")
    parser.add_argument("--semana", type=int, default=None, help="Semana epidemiológica")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Imprimir la respuesta JSON con indentación",
    )
    parser.add_argument("--health", action="store_true", help="Consultar estado del Web App")
    parser.add_argument("--metadata", action="store_true", help="Leer metadata del sheet CASOS 2")
    parser.add_argument("--leer-base", action="store_true", help="Leer base completa CASOS 2")
    parser.add_argument("--leer-semana", action="store_true", help="Leer una semana puntual")
    parser.add_argument("--comparar-semana", action="store_true", help="Comparar una semana con el año anterior")
    parser.add_argument(
        "--boletin-ultima-semana",
        action="store_true",
        help="Obtener comparación de la última semana disponible para el boletín",
    )
    parser.add_argument("--validar-canal", action="store_true", help="Validar fórmulas del canal histórico")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    client = BulletinAppsScriptClient()

    try:
        if args.health:
            data = client.health()
        elif args.metadata:
            data = client.leer_metadata(anio=args.anio)
        elif args.leer_base:
            data = client.leer_base(anio=args.anio)
        elif args.leer_semana:
            if args.anio is None or args.semana is None:
                raise RuntimeError("--leer-semana requiere --anio y --semana")
            data = client.leer_semana(anio=args.anio, semana=args.semana)
        elif args.comparar_semana:
            if args.anio is None or args.semana is None:
                raise RuntimeError("--comparar-semana requiere --anio y --semana")
            data = client.comparar_semana(anio=args.anio, semana=args.semana)
        elif args.boletin_ultima_semana:
            data = client.boletin_ultima_semana(anio=args.anio)
        elif args.validar_canal:
            data = client.validar_canal(anio=args.anio)
        else:
            parser.print_help()
            return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    if args.pretty:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(data, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())