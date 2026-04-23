from __future__ import annotations

import copy
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd


@dataclass
class DataCache:
    path: Optional[str] = None
    mtime_ns: Optional[int] = None
    df: Optional[pd.DataFrame] = None


CACHE = DataCache()
CACHE_LOCK = threading.Lock()
PAYLOAD_CACHE: dict[str, dict[str, Any]] = {}
PAYLOAD_CACHE_LOCK = threading.Lock()
MAX_PAYLOAD_CACHE_ITEMS = 48

MUNICIPIOS_RISARALDA = [
    "APIA",
    "BALBOA",
    "BELEN DE UMBRIA",
    "DOSQUEBRADAS",
    "GUATICA",
    "LA CELIA",
    "LA VIRGINIA",
    "MARSELLA",
    "MISTRATO",
    "PEREIRA",
    "PUEBLO RICO",
    "QUINCHIA",
    "SANTA ROSA DE CABAL",
    "SANTUARIO",
]

MUNICIPIOS_OFICIALES = {
    "apia": "APIA",
    "balboa": "BALBOA",
    "belen de umbria": "BELEN DE UMBRIA",
    "dosquebradas": "DOSQUEBRADAS",
    "guatica": "GUATICA",
    "la celia": "LA CELIA",
    "la virginia": "LA VIRGINIA",
    "marsella": "MARSELLA",
    "mistrato": "MISTRATO",
    "pereira": "PEREIRA",
    "pueblo rico": "PUEBLO RICO",
    "quinchia": "QUINCHIA",
    "santa rosa de cabal": "SANTA ROSA DE CABAL",
    "santuario": "SANTUARIO",
}

MUNICIPIOS_COORDS = {
    "pereira": (-75.70, 4.81),
    "dosquebradas": (-75.73, 4.84),
    "santa rosa de cabal": (-75.63, 4.85),
    "la virginia": (-75.88, 4.86),
    "santuario": (-75.74, 5.55),
    "marsella": (-75.73, 4.95),
    "belen de umbria": (-75.80, 5.27),
    "quinchia": (-75.69, 5.03),
    "apia": (-75.78, 5.08),
    "mistrato": (-75.93, 5.18),
    "pueblo rico": (-75.64, 5.22),
    "guatica": (-75.59, 5.30),
    "la celia": (-75.65, 4.98),
    "balboa": (-75.68, 4.75),
}


def _normalize_text(value: Any) -> str:
    txt = str(value).strip().lower()
    txt = (
        txt.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )
    return " ".join(txt.split())


def _first_existing_col(columns: list[str], candidates: list[str]) -> Optional[str]:
    normalized = {_normalize_text(c): c for c in columns}
    for cand in candidates:
        if cand in normalized:
            return normalized[cand]
    return None


def _to_datetime(series: pd.Series) -> pd.Series:
    if series is None:
        return pd.to_datetime(series, errors="coerce")

    s = series.astype(str).str.strip()
    s = s.replace({"nan": "", "NaN": "", "None": "", "none": "", "NaT": "", "nat": ""})
    s = s.where(~s.str.match(r"^[\-\s/]+$", na=False), "")

    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    formats = ["%d/%m/%Y", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"]

    for fmt in formats:
        mask = parsed.isna() & s.ne("")
        if mask.any():
            parsed.loc[mask] = pd.to_datetime(s.loc[mask], format=fmt, errors="coerce")

    mask = parsed.isna() & s.ne("")
    if mask.any():
        parsed.loc[mask] = pd.to_datetime(s.loc[mask], errors="coerce", dayfirst=True)

    return parsed


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _is_yes(value: Any) -> bool:
    if pd.isna(value):
        return False
    txt = _normalize_text(value)
    return txt in {"1", "si", "s", "true", "verdadero", "yes", "y"}


def _canonical_municipio(value: Any) -> str:
    txt = str(value).strip()
    if not txt:
        return "SIN MUNICIPIO"
    norm = _normalize_text(txt)
    return MUNICIPIOS_OFICIALES.get(norm, txt.upper())


def _clasificacion_razon(razon: float) -> str:
    if razon >= 400:
        return "CRITICO"
    if razon >= 300:
        return "MUY ALTO"
    if razon >= 200:
        return "ALTO"
    if razon >= 150:
        return "MOD-ALTO"
    if razon >= 100:
        return "MODERADO"
    if razon >= 50:
        return "BAJO"
    if razon > 0:
        return "MUY BAJO"
    return "SIN CASOS"


TARGET_CLEANED_COLUMNS: dict[str, list[str]] = {
    "edad": ["edad"],
    "semana": ["semana"],
    "a_o": ["a_o", "ano", "año"],
    "pac_hos": ["pac_hos", "hospitalizado"],
    "ingres_uci": ["ingres_uci", "uci"],
    "fec_def": ["fec_def", "fecha_defuncion"],
    "dias_hospi": ["dias_hospi", "dias_hospitalizacion"],
    "hemorragia_obst_trica_severa": ["hemorragia_obst_trica_severa"],
    "eclampsia": ["eclampsia"],
    "preclampsi": ["preclampsi", "preeclampsia", "preclampsia"],
    "falla_card": ["falla_card", "falla_cardiaca"],
    "falla_rena": ["falla_rena", "falla_renal"],
    "rupt_uteri": ["rupt_uteri", "ruptura_uterina"],
    "caus_agrup": ["caus_agrup"],
    "caus_princ": ["caus_princ"],
    "nmun_resi": ["nmun_resi", "municipio", "mun_resi", "nom_mun_r"],
    "ndep_resi": ["ndep_resi", "dpto_resi", "departamento_residencia"],
    "area": ["area"],
    "estrato": ["estrato"],
    "per_etn": ["per_etn"],
    "nom_grupo": ["nom_grupo"],
    "gp_discapa": ["gp_discapa"],
    "gp_desplaz": ["gp_desplaz"],
    "gp_migrant": ["gp_migrant"],
    "gp_indigen": ["gp_indigen"],
    "gp_gestan": ["gp_gestan"],
    "num_gestac": ["num_gestac"],
    "num_vivos": ["num_vivos", "nacidos_vivos", "nv_2026", "nv"],
    "sem_ges": ["sem_ges"],
    "term_gesta": ["term_gesta"],
    "dias_notificacion": ["dias_notificacion", "dias_notif", "tiempo_notificacion", "dias_noti"],
}


def _to_json_scalar(value: Any) -> Any:
    if pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")

    if isinstance(value, (datetime,)):
        return value.strftime("%Y-%m-%d")

    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass

    return value


def _build_cleaned_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    columns = list(df.columns)
    resolved: dict[str, Optional[str]] = {}

    for target, candidates in TARGET_CLEANED_COLUMNS.items():
        resolved[target] = _first_existing_col(columns, candidates)

    records: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        out: dict[str, Any] = {}
        for target, source_col in resolved.items():
            out[target] = _to_json_scalar(row[source_col]) if source_col else None
        records.append(out)

    return records


def _load_dataframe_cached(file_path: Path) -> pd.DataFrame:
    global CACHE
    st = file_path.stat()
    path = str(file_path)

    if st.st_size == 0:
        raise ValueError(f"Archivo depurado vacío: {file_path.name}")

    with CACHE_LOCK:
        if CACHE.path == path and CACHE.mtime_ns == st.st_mtime_ns and CACHE.df is not None:
            return CACHE.df.copy()

    if file_path.suffix.lower() in [".xlsx", ".xls"]:
        df = pd.read_excel(file_path)
    else:
        last_error: Exception | None = None
        df = None
        for enc in ["utf-8", "utf-8-sig", "cp1252", "latin-1"]:
            try:
                df = pd.read_csv(file_path, encoding=enc)
                break
            except Exception as exc:  # pragma: no cover - fallback defensive
                last_error = exc
        if df is None:
            raise RuntimeError(f"No se pudo leer CSV depurado: {file_path}") from last_error

    if df.empty:
        raise ValueError(f"Archivo depurado sin registros: {file_path.name}")

    with CACHE_LOCK:
        CACHE = DataCache(path=path, mtime_ns=st.st_mtime_ns, df=df)

    return df.copy()


def _build_payload_cache_key(mode: str, file_path: Path, event_code: int, municipio: Optional[str]) -> tuple[str, Any]:
    st = file_path.stat()
    municipio_key = _normalize_text(municipio) if municipio else "all"
    key = f"{mode}:{event_code}:{file_path.resolve()}:{st.st_mtime_ns}:{st.st_size}:{municipio_key}"
    return key, st


def _get_cached_payload(cache_key: str) -> Optional[dict[str, Any]]:
    with PAYLOAD_CACHE_LOCK:
        payload = PAYLOAD_CACHE.get(cache_key)
        if payload is None:
            return None
        return copy.deepcopy(payload)


def _set_cached_payload(cache_key: str, payload: dict[str, Any]) -> None:
    with PAYLOAD_CACHE_LOCK:
        if len(PAYLOAD_CACHE) >= MAX_PAYLOAD_CACHE_ITEMS:
            oldest_key = next(iter(PAYLOAD_CACHE.keys()), None)
            if oldest_key is not None:
                PAYLOAD_CACHE.pop(oldest_key, None)
        PAYLOAD_CACHE[cache_key] = copy.deepcopy(payload)


def _error_payload(message: str, code: str, status_code: int) -> dict[str, Any]:
    return {
        "ok": False,
        "error": message,
        "error_code": code,
        "status_code": status_code,
        "data": None,
    }


def find_latest_depurado_file(base_dir: Path, event_code: int) -> Optional[Path]:
    depurado = base_dir / "data" / "DEPURADO"
    if not depurado.exists():
        return None

    files: list[Path] = []
    base_patterns = [
        f"*_{event_code}_*.xlsx",
        f"*_{event_code}_*.xls",
        f"*_{event_code}_*.csv",
        f"*{event_code}*.xlsx",
        f"*{event_code}*.xls",
        f"*{event_code}*.csv",
    ]

    if int(event_code) == 549:
        base_patterns.extend([
            "*MME_Depurado_Final*.xlsx",
            "*MME_Depurado_Final*.xls",
            "*MME_Depurado_Final*.csv",
        ])

    for pattern in base_patterns:
        files.extend(depurado.glob(pattern))

    # Deduplicar y dejar solo candidatos reales de depuración
    files = list({f.resolve(): f for f in files}.values())
    files = [
        f for f in files
        if f.is_file()
        and "_boletin" not in _normalize_text(f.name)
        and "_reporte" not in _normalize_text(f.name)
        and ".error" not in _normalize_text(f.name)
    ]
    if not files:
        return None

    # Para evento 549 priorizar salida canónica cuando exista.
    if int(event_code) == 549:
        canonicos = [f for f in files if "mme_depurado_final" in _normalize_text(f.stem)]
        if canonicos:
            return max(canonicos, key=lambda x: x.stat().st_mtime)

    return max(files, key=lambda x: x.stat().st_mtime)


def build_dashboard_data(base_dir: Path, event_code: int, municipio: Optional[str] = None) -> dict[str, Any]:
    file_path = find_latest_depurado_file(base_dir, event_code)
    if not file_path:
        return _error_payload(
            message=f"No se encontró archivo depurado para evento {event_code}",
            code="FILE_NOT_FOUND",
            status_code=404,
        )

    cache_key, st = _build_payload_cache_key("dashboard", file_path, event_code, municipio)
    cached = _get_cached_payload(cache_key)
    if cached is not None:
        return cached

    try:
        df_full = _load_dataframe_cached(file_path)
    except ValueError as exc:
        return _error_payload(str(exc), "EMPTY_FILE", 422)
    except Exception:
        return _error_payload(
            message=f"Archivo depurado corrupto o no legible: {file_path.name}",
            code="CORRUPT_FILE",
            status_code=422,
        )

    columns = list(df_full.columns)

    col_municipio = _first_existing_col(columns, ["nmun_resi", "municipio", "mun_resi", "nom_mun_r"])
    col_semana = _first_existing_col(columns, ["semana"])
    col_edad = _first_existing_col(columns, ["edad"])
    col_sexo = _first_existing_col(columns, ["sexo"])

    total_sin_filtro = len(df_full)
    df = df_full

    if municipio and col_municipio:
        norm = _normalize_text(municipio)
        mask = df[col_municipio].fillna("").astype(str).str.strip().apply(lambda v: _normalize_text(v) == norm)
        df = df[mask].copy()

    total = len(df)

    by_week = []
    if col_semana:
        week_series = pd.to_numeric(df[col_semana], errors="coerce").dropna().astype(int)
        vc = week_series.value_counts().sort_index()
        by_week = [{"semana": int(k), "casos": int(v)} for k, v in vc.items()]

    by_municipio = []
    municipios_disponibles = []
    if col_municipio:
        full_mun = (
            df_full[col_municipio]
            .fillna("Sin municipio")
            .astype(str)
            .str.strip()
            .replace("", "Sin municipio")
        )
        municipios_disponibles = sorted(full_mun.unique().tolist())

        vc = (
            df[col_municipio]
            .fillna("Sin municipio")
            .astype(str)
            .str.strip()
            .replace("", "Sin municipio")
            .value_counts()
            .head(15)
        )
        by_municipio = [{"municipio": str(k), "casos": int(v)} for k, v in vc.items()]

    age_groups = []
    if col_edad:
        ages = pd.to_numeric(df[col_edad], errors="coerce")
        bins = [0, 19, 24, 29, 34, 39, 200]
        labels = ["15-19", "20-24", "25-29", "30-34", "35-39", "40+"]
        cat = pd.cut(ages, bins=bins, labels=labels, include_lowest=True)
        age_groups = [{"grupo": lb, "casos": int((cat == lb).sum())} for lb in labels]

    by_sexo = []
    if col_sexo:
        vc = (
            df[col_sexo]
            .fillna("No especificado")
            .astype(str)
            .str.strip()
            .replace("", "No especificado")
            .value_counts()
        )
        by_sexo = [{"sexo": str(k), "casos": int(v)} for k, v in vc.items()]

    data_version = f"{file_path.name}:{st.st_mtime_ns}:{st.st_size}:{total_sin_filtro}:{total}:{municipio or 'ALL'}"

    payload = {
        "ok": True,
        "error": None,
        "data": {
            "evento": event_code,
            "fuente": "archivo_depurado_local",
            "is_local_source": True,
            "archivo_depurado": file_path.name,
            "archivo_modificado": pd.Timestamp(st.st_mtime, unit="s").strftime("%Y-%m-%d %H:%M:%S"),
            "data_version": data_version,
            "total_casos": total,
            "total_sin_filtro": total_sin_filtro,
            "municipio_filtro": municipio,
            "municipios_disponibles": municipios_disponibles,
            "charts": {
                "por_semana": by_week,
                "por_municipio": by_municipio,
                "por_grupo_edad": age_groups,
                "por_sexo": by_sexo,
            },
        },
    }

    _set_cached_payload(cache_key, payload)
    return payload


def build_legacy_evento_549_payload(base_dir: Path, municipio: Optional[str] = None) -> dict[str, Any]:
    """
    Construye el payload compatible con el dashboard legado `evento_549_dashboard.js`.
    """
    event_code = 549
    file_path = find_latest_depurado_file(base_dir, event_code)
    if not file_path:
        return _error_payload(
            message="No se encontró archivo depurado del evento 549",
            code="FILE_NOT_FOUND",
            status_code=404,
        )

    cache_key, st = _build_payload_cache_key("legacy_549", file_path, event_code, municipio)
    cached = _get_cached_payload(cache_key)
    if cached is not None:
        return cached

    try:
        df_full = _load_dataframe_cached(file_path)
    except ValueError as exc:
        return _error_payload(str(exc), "EMPTY_FILE", 422)
    except Exception:
        return _error_payload(
            message=f"Archivo depurado corrupto o no legible: {file_path.name}",
            code="CORRUPT_FILE",
            status_code=422,
        )

    columns = list(df_full.columns)

    col_municipio = _first_existing_col(columns, ["nmun_resi", "municipio", "mun_resi", "nom_mun_r"])
    col_semana = _first_existing_col(columns, ["semana"])
    col_ano = _first_existing_col(columns, ["ano", "año"])
    col_edad = _first_existing_col(columns, ["edad"])
    col_afiliacion = _first_existing_col(columns, ["tip_ss", "tipo_afiliacion", "afiliacion"])
    col_fec_not = _first_existing_col(columns, ["fec_not", "fecha_notificacion"])
    col_ini_sin = _first_existing_col(columns, ["ini_sin", "fecha_inicio_sintomas"])
    col_fec_hos = _first_existing_col(columns, ["fec_hos", "fecha_hospitalizacion"])
    col_hos = _first_existing_col(columns, ["pac_hos", "hospitalizado"])
    col_reconsulta = _first_existing_col(columns, ["pte_remtda", "reconsulta"])
    col_control = _first_existing_col(columns, ["no_con_pre", "control_prenatal"])
    col_uci = _first_existing_col(columns, ["ingres_uci", "uci"])
    col_dias_hospi = _first_existing_col(columns, ["dias_hospi", "dias_hospitalizacion"])
    col_causa = _first_existing_col(columns, ["caus_agrup", "caus_princ"])
    col_momento = _first_existing_col(columns, ["term_gesta", "moc_rel_tg"])
    col_num_vivos = _first_existing_col(columns, ["num_vivos"])

    municipios_disponibles: list[str] = []
    if col_municipio:
        full_mun = df_full[col_municipio].fillna("Sin municipio").astype(str).str.strip().apply(_canonical_municipio)
        municipios_disponibles = sorted([m for m in full_mun.unique().tolist() if m and m != "SIN MUNICIPIO"])

    total_sin_filtro = len(df_full)
    df = df_full.copy()
    if municipio and col_municipio:
        norm = _normalize_text(municipio)
        mask = df[col_municipio].fillna("").astype(str).str.strip().apply(lambda v: _normalize_text(v) == norm)
        df = df[mask].copy()

    cleaned_records = _build_cleaned_records(df)

    total = int(len(df))

    anio = datetime.now().year
    casos_actuales = total
    casos_bases = 0
    if col_ano:
        anos = _to_numeric(df[col_ano]).dropna().astype(int)
        if not anos.empty:
            anio = int(anos.max())
            casos_actuales = int((anos == anio).sum())
            casos_bases = int((anos == (anio - 1)).sum())

    variacion = None
    if casos_bases > 0:
        variacion = round(((casos_actuales - casos_bases) / casos_bases) * 100, 1)

    grupos_edad: list[dict[str, Any]] = []
    if col_edad:
        edades = _to_numeric(df[col_edad])
        bins = [0, 19, 24, 29, 34, 39, 200]
        labels = ["15-19 años", "20-24 años", "25-29 años", "30-34 años", "35-39 años", "40+ años"]
        cat = pd.cut(edades, bins=bins, labels=labels, include_lowest=True)
        for label in labels:
            casos = int((cat == label).sum())
            grupos_edad.append({"grupo": label, "casos": casos, "porcentaje": round((casos / total) * 100, 1) if total else 0})

    afiliacion: list[dict[str, Any]] = []
    if col_afiliacion:
        mapa = {
            "1": "Contributivo", "2": "Subsidiado", "3": "Especial", "4": "Excepción", "5": "No asegurado",
            "C": "Contributivo", "S": "Subsidiado", "E": "Especial", "P": "Excepción", "N": "No asegurado", "I": "Indeterminado",
        }
        serie = df[col_afiliacion].fillna("No especificado").astype(str).str.strip().str.upper()
        serie = serie.apply(lambda v: mapa.get(v, v.title() if len(v) > 2 else v))
        vc = serie.value_counts()
        for tipo, casos in vc.items():
            afiliacion.append({"tipo": str(tipo), "casos": int(casos), "porcentaje": round((int(casos) / total) * 100, 1) if total else 0})

    semanas: list[dict[str, Any]] = []
    if col_semana:
        sem_series = _to_numeric(df[col_semana]).dropna().astype(int)
        if col_ano:
            an_series = _to_numeric(df[col_ano]).fillna(anio).astype(int)
            tmp = pd.DataFrame({"sem": sem_series, "ano": an_series.loc[sem_series.index]})
            g = tmp.groupby(["ano", "sem"]).size().reset_index(name="casos")
            sems = sorted(tmp["sem"].unique().tolist())
            for sem in sems:
                actual = int(g[(g["ano"] == anio) & (g["sem"] == sem)]["casos"].sum())
                previo = int(g[(g["ano"] == anio - 1) & (g["sem"] == sem)]["casos"].sum())
                semanas.append({"semana": int(sem), "casos": actual, "año2025": previo})
        else:
            vc = sem_series.value_counts().sort_index()
            for sem, casos in vc.items():
                semanas.append({"semana": int(sem), "casos": int(casos), "año2025": 0})

    municipios: list[dict[str, Any]] = []
    municipios_territoriales: list[dict[str, Any]] = []
    if col_municipio:
        serie_m = df[col_municipio].fillna("Sin municipio").astype(str).str.strip().replace("", "Sin municipio")
        serie_m = serie_m.apply(_canonical_municipio)
        vc = serie_m.value_counts()

        num_vivos_map: dict[str, float] = {}
        if col_num_vivos:
            tmp = pd.DataFrame({"mun": serie_m, "nv": _to_numeric(df[col_num_vivos]).fillna(0)})
            num_vivos_map = tmp.groupby("mun")["nv"].sum().to_dict()

        for mun, casos in vc.items():
            casos_i = int(casos)
            nv = int(round(float(num_vivos_map.get(mun, 0)))) if num_vivos_map else 0
            razon = round((casos_i / nv) * 1000, 1) if nv > 0 else 0.0
            norm = _normalize_text(mun)
            lon, lat = MUNICIPIOS_COORDS.get(norm, (-75.73, 4.95))

            municipios.append({
                "nombre": str(mun),
                "casos": casos_i,
                "latitud": lat,
                "longitud": lon,
                "estado": "PRIORITARIO" if casos_i >= max(1, round(total * 0.1)) else "MONITOREO",
            })
            municipios_territoriales.append({
                "nombre": str(mun),
                "casos": casos_i,
                "nv2025": nv,
                "razonMME": razon,
                "latitud": lat,
                "longitud": lon,
                "clasificacion": _clasificacion_razon(razon),
            })

    causas: list[dict[str, Any]] = []
    if col_causa:
        vc = df[col_causa].fillna("No especificada").astype(str).str.strip().replace("", "No especificada").value_counts().head(5)
        for causa, casos in vc.items():
            causas.append({"causa": str(causa), "casos": int(casos), "porcentaje": round((int(casos) / total) * 100, 1) if total else 0})

    momento_evento: list[dict[str, Any]] = []
    if col_momento:
        vc = df[col_momento].fillna("No especificado").astype(str).str.strip().replace("", "No especificado").value_counts().head(3)
        for momento, casos in vc.items():
            momento_evento.append({"momento": str(momento), "casos": int(casos), "porcentaje": round((int(casos) / total) * 100, 1) if total else 0})

    notif_oportuna = 0
    notif_tardia = 0
    dias_notificacion = [
        {"rango": "1-7 días (Oportuno)", "casos": 0, "porcentaje": 0},
        {"rango": "8-14 días (Tardío)", "casos": 0, "porcentaje": 0},
        {"rango": "15-30 días (Muy tardío)", "casos": 0, "porcentaje": 0},
        {"rango": ">30 días (Crítico)", "casos": 0, "porcentaje": 0},
    ]
    calidad_municipios: list[dict[str, Any]] = []

    if col_fec_not:
        f_not = _to_datetime(df[col_fec_not])
        f_ref = None
        if col_ini_sin:
            f_ini = _to_datetime(df[col_ini_sin])
            if f_ini.notna().sum() > 0:
                f_ref = f_ini
        if f_ref is None and col_fec_hos:
            f_hos = _to_datetime(df[col_fec_hos])
            if f_hos.notna().sum() > 0:
                f_ref = f_hos

        if f_ref is not None:
            delta = (f_not - f_ref).dt.days
            delta = delta[delta >= 0]
            valid = delta.notna()
            if valid.sum() > 0:
                notif_oportuna = int((delta[valid] <= 7).sum())
                notif_tardia = int((delta[valid] > 7).sum())

                ranges = [(-999, 7), (8, 14), (15, 30), (31, 9999)]
                for i, (lo, hi) in enumerate(ranges):
                    c = int(((delta >= lo) & (delta <= hi)).sum())
                    dias_notificacion[i]["casos"] = c
                    dias_notificacion[i]["porcentaje"] = round((c / total) * 100, 1) if total else 0

                if col_municipio:
                    tmp = pd.DataFrame({
                        "mun": df[col_municipio].fillna("Sin municipio").astype(str).str.strip().replace("", "Sin municipio"),
                        "delta": delta,
                    })
                    for mun, grp in tmp.groupby("mun"):
                        valid_delta = grp["delta"].dropna()
                        if valid_delta.empty:
                            oport = tard = 0
                        else:
                            oport = int((valid_delta <= 7).sum())
                            tard = int((valid_delta > 7).sum())
                        denom = oport + tard
                        calidad_municipios.append({
                            "municipio": str(mun),
                            "oportunos": oport,
                            "tardios": tard,
                            "porcentaje": round((oport / denom) * 100, 1) if denom else 0,
                        })

    hospitalizacion = int(df[col_hos].apply(_is_yes).sum()) if col_hos else 0
    reconsulta = int(df[col_reconsulta].apply(_is_yes).sum()) if col_reconsulta else 0
    control_prenatal = int((_to_numeric(df[col_control]).fillna(0) > 0).sum()) if col_control else 0
    requiere_uci = int(df[col_uci].apply(_is_yes).sum()) if col_uci else 0
    dias_promedio = round(float(_to_numeric(df[col_dias_hospi]).dropna().mean()), 1) if col_dias_hospi else 0

    completitud = 0
    criticas = [c for c in [col_edad, col_afiliacion, col_municipio, col_fec_not, col_ini_sin, col_hos, col_dias_hospi] if c]
    if criticas and total > 0:
        total_celdas = len(criticas) * total
        completas = 0
        for c in criticas:
            s = df[c]
            completas += int((s.notna() & (s.astype(str).str.strip() != "")).sum())
        completitud = round((completas / total_celdas) * 100, 1)

    edad_stats = {"promedio": 0, "minima": 0, "maxima": 0, "moda": 0}
    if col_edad:
        edades_num = _to_numeric(df[col_edad]).dropna()
        if not edades_num.empty:
            edad_stats["promedio"] = round(float(edades_num.mean()), 1)
            edad_stats["minima"] = int(edades_num.min())
            edad_stats["maxima"] = int(edades_num.max())
            edad_stats["moda"] = int(edades_num.mode().iloc[0]) if not edades_num.mode().empty else 0

    data_version = f"{file_path.name}:{st.st_mtime_ns}:{st.st_size}:{total_sin_filtro}:{total}:{municipio or 'ALL'}"

    dashboard_data = {
        "codigo": 549,
        "nombre": "Morbilidad materna extrema",
        "subtitulo": "Morbilidad Materna Extrema (MME)",
        "año": anio,
        "anioComparacion": anio - 1,
        "fechaActualizacion": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "totalCasos": total,
        "variacionAnual": variacion,
        "casosActuales": casos_actuales,
        "casosBases": casos_bases,
        "municipios": sorted(municipios, key=lambda x: x["casos"], reverse=True),
        "municipiosTerritoriales": sorted(municipios_territoriales, key=lambda x: x["razonMME"], reverse=True),
        "gruposEdad": grupos_edad,
        "afiliacion": afiliacion,
        "causas": causas,
        "momentoEvento": momento_evento,
        "semanas": semanas,
        "calidad": {
            "notificacionOportuna": notif_oportuna,
            "notificacionTardia": notif_tardia,
            "porcentajeOportunidad": round((notif_oportuna / (notif_oportuna + notif_tardia)) * 100, 1) if (notif_oportuna + notif_tardia) else 0,
            "completitud": completitud,
            "hospitalizacion": hospitalizacion,
            "porcentajeHospitalizacion": round((hospitalizacion / total) * 100, 1) if total else 0,
            "reconsulta": reconsulta,
            "porcentajeReconsulta": round((reconsulta / total) * 100, 1) if total else 0,
            "controlPrenatal": control_prenatal,
            "porcentajeControlPrenatal": round((control_prenatal / total) * 100, 1) if total else 0,
            "requiereUCI": requiere_uci,
            "porcentajeUCI": round((requiere_uci / total) * 100, 1) if total else 0,
            "diasPromedio": dias_promedio,
        },
        "calidadMunicipios": sorted(calidad_municipios, key=lambda x: x["porcentaje"], reverse=True),
        "diasNotificacion": dias_notificacion,
        "edadEstadisticas": edad_stats,
    }

    payload = {
        "ok": True,
        "error": None,
        "data": {
            "evento": 549,
            "fuente": "archivo_depurado_local",
            "is_local_source": True,
            "archivo_depurado": file_path.name,
            "archivo_depurado_ruta": str(file_path),
            "archivo_modificado": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "total_casos": total,
            "total_sin_filtro": total_sin_filtro,
            "municipio_filtro": municipio,
            "municipios_disponibles": municipios_disponibles,
            "data_version": data_version,
            "cleanedData": cleaned_records,
            "dashboard_data": dashboard_data,
        },
    }

    _set_cached_payload(cache_key, payload)
    return payload
