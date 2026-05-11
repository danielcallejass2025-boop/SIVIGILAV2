"""
scripts/depuracion_evento_549.py
Depuracion del evento 549 (Morbilidad Materna Extrema).

Secuencia implementada (exactamente 11 pasos):
1) Analisis por departamento de residencia
2) Eliminar ajustes 6, D, R
3) Quitar duplicados exactos
4) Marcar no-cumplen definicion
5) Ordenar por nombre + documento
6) Formato condicional num_ide
7) Depurar repetidos por documento (criterios A-B-C-D)
8) Concatenar nombre + apellido + formato condicional
9) Revisar fecha nacimiento
10) Depurar repetidos por nombre (criterios A-B-C-D)
11) Cruce muerte materna + ajuste 6 finales
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from scripts.utils import Logger


class Depuracion549:
    """Depuracion del evento 549 siguiendo la secuencia solicitada."""

    def __init__(self, filter_only_risaralda: bool = False):
        self.logger = Logger()
        self.filter_only_risaralda = filter_only_risaralda
        self.columnas: Dict[str, Optional[str]] = {}

    @staticmethod
    def es_aplicable(codigo_evento: int) -> bool:
        return int(codigo_evento) == 549

    @staticmethod
    def _norm_text(value: Any) -> str:
        txt = str(value).strip().lower()
        txt = (
            txt.replace("á", "a")
            .replace("é", "e")
            .replace("í", "i")
            .replace("ó", "o")
            .replace("ú", "u")
            .replace("ñ", "n")
        )
        txt = txt.replace("-", "_").replace(" ", "_")
        while "__" in txt:
            txt = txt.replace("__", "_")
        return txt

    @staticmethod
    def _norm_human_text(value: Any) -> str:
        txt = str(value or "").strip().lower()
        txt = (
            txt.replace("á", "a")
            .replace("é", "e")
            .replace("í", "i")
            .replace("ó", "o")
            .replace("ú", "u")
            .replace("ñ", "n")
        )
        return " ".join(txt.split())

    def _buscar_columna(self, df: pd.DataFrame, patrones: List[str]) -> Optional[str]:
        cols_norm = {self._norm_text(c): c for c in df.columns}

        for patron in patrones:
            p = self._norm_text(patron)
            for c_norm, c_real in cols_norm.items():
                if c_norm == p:
                    return c_real

        for patron in patrones:
            p = self._norm_text(patron)
            for c_norm, c_real in cols_norm.items():
                if p in c_norm:
                    return c_real

        return None

    def _detectar_columnas(self, df: pd.DataFrame) -> None:
        self.columnas = {
            "ndep_resi": self._buscar_columna(
                df,
                [
                    "ndep_resi",
                    "cod_dpto_r",
                    "cod_dpto_resi",
                    "departamento_residencia",
                    "dpto_residencia",
                ],
            ),
            "ajuste": self._buscar_columna(df, ["ajuste"]),
            "fuente": self._buscar_columna(df, ["fuente"]),
            "fec_arc_xl": self._buscar_columna(df, ["fec_arc_xl"]),
            "version": self._buscar_columna(df, ["version", "version_"]),
            "nreg": self._buscar_columna(df, ["nreg"]),
            "pri_ape": self._buscar_columna(df, ["pri_ape_", "pri_ape", "primer_apellido"]),
            "seg_ape": self._buscar_columna(df, ["seg_ape_", "seg_ape", "segundo_apellido"]),
            "pri_nom": self._buscar_columna(df, ["pri_nom_", "pri_nom", "primer_nombre"]),
            "seg_nom": self._buscar_columna(df, ["seg_nom_", "seg_nom", "segundo_nombre"]),
            "tip_ide": self._buscar_columna(df, ["tip_ide_", "tip_ide", "tipo_documento"]),
            "num_ide": self._buscar_columna(df, ["num_ide_", "num_ide", "numero_documento"]),
            "fec_egreso": self._buscar_columna(df, ["fec_egreso", "fecha_egreso"]),
            "egreso": self._buscar_columna(df, ["egreso", "tipo_egreso"]),
            "nom_upgd": self._buscar_columna(df, ["nom_upgd", "nombre_upgd", "upgd"]),
            "pte_remtda": self._buscar_columna(df, ["pte_remtda"]),
            "fec_con": self._buscar_columna(df, ["fec_con", "fecha_consulta"]),
            "fecha_nto": self._buscar_columna(df, ["fecha_nto", "fecha_nacimiento"]),
            "cod_eve": self._buscar_columna(df, ["cod_eve", "codigo_evento"]),
            "fallecio": self._buscar_columna(df, ["fallecio", "defuncion", "muerte_materna"]),
            "clasificacion": self._buscar_columna(
                df,
                [
                    "clasificacion",
                    "clasificacion_caso",
                    "clasif_caso",
                    "definicion_caso",
                ],
            ),
            "cumple_def": self._buscar_columna(
                df,
                [
                    "cumple_definicion",
                    "cumple_def",
                    "cumple_caso",
                ],
            ),
        }

    @staticmethod
    def _parse_date_series(series: pd.Series) -> pd.Series:
        if series is None:
            return pd.Series(dtype="datetime64[ns]")

        if pd.api.types.is_datetime64_any_dtype(series):
            return pd.to_datetime(series, errors="coerce")

        s = series.astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA, "None": pd.NA, "NaT": pd.NA})
        out = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

        formatos = [
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%d/%m/%Y",
            "%d/%m/%Y %H:%M:%S",
            "%m/%d/%Y",
            "%m/%d/%Y %H:%M:%S",
        ]
        for fmt in formatos:
            mask = out.isna() & s.notna()
            if mask.any():
                out.loc[mask] = pd.to_datetime(s.loc[mask], format=fmt, errors="coerce")

        mask = out.isna() & s.notna()
        if mask.any():
            out.loc[mask] = pd.to_datetime(s.loc[mask], errors="coerce", dayfirst=True)

        return out

    @staticmethod
    def _is_yes(value: Any) -> bool:
        if pd.isna(value):
            return False
        txt = str(value).strip().lower()
        return txt in {"1", "si", "s", "true", "verdadero", "yes", "y"}

    @staticmethod
    def _is_empty(value: Any) -> bool:
        if pd.isna(value):
            return True
        return str(value).strip().lower() in {"", "nan", "none", "null", "nat"}

    @staticmethod
    def _normalizar_num_ide(value: Any) -> str:
        if pd.isna(value):
            return ""
        txt = str(value).strip().upper()
        if not txt:
            return ""
        return "".join(ch for ch in txt if ch.isalnum())

    def _es_residencia_risaralda(self, value: Any) -> bool:
        if pd.isna(value):
            return False

        num = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        if pd.notna(num) and int(num) == 66:
            return True

        txt = self._norm_text(value)
        return txt in {
            "66",
            "066",
            "risaralda",
            "departamento_de_risaralda",
            "depto_risaralda",
            "dpto_risaralda",
        }

    def _score_institucional(self, row: pd.Series) -> int:
        score = 0
        col_upgd = self.columnas.get("nom_upgd")
        col_rem = self.columnas.get("pte_remtda")

        if col_upgd and col_upgd in row.index and not self._is_empty(row[col_upgd]):
            score += 2
        if col_rem and col_rem in row.index and self._is_yes(row[col_rem]):
            score += 3
        return score

    def _score_completitud(self, row: pd.Series) -> int:
        total = 0
        for v in row.values:
            if not self._is_empty(v):
                total += 1
        return total

    def _seleccionar_criterio_abcd(self, group_df: pd.DataFrame) -> Tuple[int, str]:
        candidatos = group_df.copy()

        col_eg = self.columnas.get("egreso")
        col_fec_eg = self.columnas.get("fec_egreso")
        col_fec_con = self.columnas.get("fec_con")

        if col_eg and col_fec_eg and col_eg in candidatos.columns and col_fec_eg in candidatos.columns:
            eg_yes = candidatos[col_eg].apply(self._is_yes)
            fec = self._parse_date_series(candidatos[col_fec_eg])
            sub = candidatos[eg_yes & fec.notna()]
            if len(sub) > 0:
                max_fec = fec.loc[sub.index].max()
                sub = sub[fec.loc[sub.index] == max_fec]
                if len(sub) == 1:
                    return int(sub.index[0]), "A"
                candidatos = sub

        score_b = candidatos.apply(self._score_institucional, axis=1)
        if len(score_b) > 0:
            max_b = score_b.max()
            sub = candidatos[score_b == max_b]
            if len(sub) == 1:
                return int(sub.index[0]), "B"
            candidatos = sub

        score_c = candidatos.apply(self._score_completitud, axis=1)
        max_c = score_c.max()
        sub = candidatos[score_c == max_c]
        if len(sub) == 1:
            return int(sub.index[0]), "C"
        candidatos = sub

        if col_fec_con and col_fec_con in candidatos.columns:
            fec_con = self._parse_date_series(candidatos[col_fec_con])
            if fec_con.notna().any():
                idx = int(fec_con.idxmax())
                return idx, "D"

        return int(candidatos.index[0]), "D"

    def _paso1_analisis_departamento_residencia(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        col_res = self.columnas.get("ndep_resi")
        filas_antes = len(df)

        if not col_res or col_res not in df.columns:
            return df.copy(), {
                "paso": 1,
                "estado": "SALTADO",
                "razon": "No se encontro columna de departamento de residencia",
                "filas_antes": filas_antes,
                "filas_despues": filas_antes,
            }

        mask = df[col_res].apply(self._es_residencia_risaralda)
        out = df.loc[mask].copy()

        return out, {
            "paso": 1,
            "estado": "EJECUTADO",
            "descripcion": "Analisis por departamento de residencia: conservar solo Risaralda",
            "columna_residencia": col_res,
            "filas_antes": filas_antes,
            "filas_despues": len(out),
            "eliminadas": int((~mask).sum()),
        }

    def _paso2_eliminar_ajustes_6_d_r(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        col_aj = self.columnas.get("ajuste")
        filas_antes = len(df)

        if not col_aj or col_aj not in df.columns:
            return df.copy(), {
                "paso": 2,
                "estado": "SALTADO",
                "razon": "No se encontro columna ajuste",
                "filas_antes": filas_antes,
                "filas_despues": filas_antes,
            }

        serie_txt = df[col_aj].astype(str).str.strip().str.upper()
        serie_num = pd.to_numeric(serie_txt, errors="coerce")
        mask = (serie_txt == "D") | (serie_txt == "R") | (serie_num == 6)

        out = df.loc[~mask].copy()
        return out, {
            "paso": 2,
            "estado": "EJECUTADO",
            "filas_antes": filas_antes,
            "filas_despues": len(out),
            "eliminadas": int(mask.sum()),
        }

    def _paso3_quitar_duplicados_exactos(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        filas_antes = len(df)
        out = df.drop_duplicates(keep="first").copy()
        return out, {
            "paso": 3,
            "estado": "EJECUTADO",
            "filas_antes": filas_antes,
            "filas_despues": len(out),
            "eliminadas": filas_antes - len(out),
        }

    def _paso4_marcar_no_cumplen_definicion(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        out = df.copy()
        marcas = pd.Series(False, index=out.index)

        col_clas = self.columnas.get("clasificacion")
        if col_clas and col_clas in out.columns:
            clas_txt = out[col_clas].astype(str).str.strip().str.lower()
            marcas = marcas | clas_txt.str.contains("no cumple|descart", na=False)

        col_cumple = self.columnas.get("cumple_def")
        if col_cumple and col_cumple in out.columns:
            cumple_txt = out[col_cumple].astype(str).str.strip().str.lower()
            marcas = marcas | cumple_txt.isin({"0", "no", "false", "falso"})

        out["no_cumple_definicion"] = marcas

        return out, {
            "paso": 4,
            "estado": "EJECUTADO",
            "marcados_no_cumplen": int(marcas.sum()),
            "columna_salida": "no_cumple_definicion",
        }

    def _paso5_ordenar_nombre_documento(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        orden_cols = [
            self.columnas.get("pri_ape"),
            self.columnas.get("seg_ape"),
            self.columnas.get("pri_nom"),
            self.columnas.get("seg_nom"),
            self.columnas.get("tip_ide"),
            self.columnas.get("num_ide"),
        ]
        orden_cols = [c for c in orden_cols if c and c in df.columns]

        if not orden_cols:
            return df.copy(), {
                "paso": 5,
                "estado": "SALTADO",
                "razon": "No se encontraron columnas de nombre/documento para ordenar",
            }

        tmp = df.copy()
        for c in orden_cols:
            tmp[c] = tmp[c].fillna("").astype(str)

        out = tmp.sort_values(orden_cols, ascending=True, kind="mergesort").reset_index(drop=True)
        return out, {
            "paso": 5,
            "estado": "EJECUTADO",
            "columnas_orden": orden_cols,
            "filas": len(out),
        }

    def _paso6_formato_condicional_num_ide(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        out = df.copy()
        col_num = self.columnas.get("num_ide")

        if not col_num or col_num not in out.columns:
            out["num_ide_formato"] = ""
            return out, {
                "paso": 6,
                "estado": "SALTADO",
                "razon": "No se encontro num_ide para aplicar formato condicional",
                "columna_salida": "num_ide_formato",
            }

        out["num_ide_formato"] = out[col_num].apply(self._normalizar_num_ide)
        vacios = int((out["num_ide_formato"] == "").sum())

        return out, {
            "paso": 6,
            "estado": "EJECUTADO",
            "columna_entrada": col_num,
            "columna_salida": "num_ide_formato",
            "identificadores_vacios": vacios,
        }

    def _paso7_depurar_repetidos_documento_abcd(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        out = df.copy()
        if "num_ide_formato" not in out.columns:
            out["num_ide_formato"] = ""

        out["_doc_key"] = out["num_ide_formato"].astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA})

        keep_indices: List[int] = []
        criterios = {"A": 0, "B": 0, "C": 0, "D": 0}
        grupos_repetidos = 0

        vacios = out[out["_doc_key"].isna()]
        keep_indices.extend(vacios.index.tolist())

        for _, g in out[out["_doc_key"].notna()].groupby("_doc_key", dropna=False):
            if len(g) > 1:
                grupos_repetidos += 1
            idx_sel, criterio = self._seleccionar_criterio_abcd(g)
            keep_indices.append(idx_sel)
            if criterio in criterios:
                criterios[criterio] += 1

        filtrado = out.loc[sorted(set(keep_indices))].copy()
        eliminadas = len(out) - len(filtrado)
        filtrado = filtrado.drop(columns=["_doc_key"], errors="ignore").reset_index(drop=True)

        return filtrado, {
            "paso": 7,
            "estado": "EJECUTADO",
            "filas_despues": len(filtrado),
            "eliminadas": eliminadas,
            "grupos_repetidos_documento": grupos_repetidos,
            "conteo_criterios": criterios,
        }

    def _paso8_concatenar_nombre_apellido_formato(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        out = df.copy()

        col_pri_nom = self.columnas.get("pri_nom")
        col_seg_nom = self.columnas.get("seg_nom")
        col_pri_ape = self.columnas.get("pri_ape")
        col_seg_ape = self.columnas.get("seg_ape")

        def _build_nombre(row: pd.Series) -> str:
            partes = []
            for c in [col_pri_nom, col_seg_nom, col_pri_ape, col_seg_ape]:
                if c and c in row.index:
                    v = str(row[c]).strip()
                    if v and v.lower() not in {"nan", "none"}:
                        partes.append(v)
            bruto = " ".join(partes)
            return self._norm_human_text(bruto)

        out["nombre_apellido_formato"] = out.apply(_build_nombre, axis=1)

        vacios = int((out["nombre_apellido_formato"] == "").sum())
        return out, {
            "paso": 8,
            "estado": "EJECUTADO",
            "columna_salida": "nombre_apellido_formato",
            "registros_sin_nombre_concatenado": vacios,
        }

    def _paso9_revisar_fecha_nacimiento(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        out = df.copy()
        col_fn = self.columnas.get("fecha_nto")

        if not col_fn or col_fn not in out.columns:
            out["fecha_nacimiento_valida"] = False
            return out, {
                "paso": 9,
                "estado": "SALTADO",
                "razon": "No se encontro fecha de nacimiento",
                "columna_salida": "fecha_nacimiento_valida",
            }

        fechas = self._parse_date_series(out[col_fn])
        hoy = pd.Timestamp.today().normalize()
        validas = fechas.notna() & (fechas <= hoy)

        out["fecha_nacimiento_revisada"] = fechas.dt.strftime("%Y-%m-%d").fillna("")
        out["fecha_nacimiento_valida"] = validas

        return out, {
            "paso": 9,
            "estado": "EJECUTADO",
            "columna_entrada": col_fn,
            "validas": int(validas.sum()),
            "invalidas": int((~validas).sum()),
            "columnas_salida": ["fecha_nacimiento_revisada", "fecha_nacimiento_valida"],
        }

    def _paso10_depurar_repetidos_nombre_abcd(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        out = df.copy()
        if "nombre_apellido_formato" not in out.columns:
            out["nombre_apellido_formato"] = ""

        out["_name_key"] = out["nombre_apellido_formato"].astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA})

        keep_indices: List[int] = []
        criterios = {"A": 0, "B": 0, "C": 0, "D": 0}
        grupos_repetidos = 0

        vacios = out[out["_name_key"].isna()]
        keep_indices.extend(vacios.index.tolist())

        for _, g in out[out["_name_key"].notna()].groupby("_name_key", dropna=False):
            if len(g) > 1:
                grupos_repetidos += 1
            idx_sel, criterio = self._seleccionar_criterio_abcd(g)
            keep_indices.append(idx_sel)
            if criterio in criterios:
                criterios[criterio] += 1

        filtrado = out.loc[sorted(set(keep_indices))].copy()
        eliminadas = len(out) - len(filtrado)
        filtrado = filtrado.drop(columns=["_name_key"], errors="ignore").reset_index(drop=True)

        return filtrado, {
            "paso": 10,
            "estado": "EJECUTADO",
            "filas_despues": len(filtrado),
            "eliminadas": eliminadas,
            "grupos_repetidos_nombre": grupos_repetidos,
            "conteo_criterios": criterios,
        }

    def _detectar_docs_muerte(self, df: pd.DataFrame) -> set[str]:
        docs: set[str] = set()

        col_num = self.columnas.get("num_ide")
        if col_num and col_num in df.columns:
            col_cod = self.columnas.get("cod_eve")
            if col_cod and col_cod in df.columns:
                cod_num = pd.to_numeric(df[col_cod], errors="coerce")
                for v in df.loc[cod_num == 350, col_num]:
                    d = self._normalizar_num_ide(v)
                    if d:
                        docs.add(d)

            col_fall = self.columnas.get("fallecio")
            if col_fall and col_fall in df.columns:
                fall_txt = df[col_fall].astype(str).str.lower()
                mask = df[col_fall].apply(self._is_yes) | fall_txt.str.contains("fallec|muerte", na=False)
                for v in df.loc[mask, col_num]:
                    d = self._normalizar_num_ide(v)
                    if d:
                        docs.add(d)

        base_dir = Path(__file__).resolve().parents[1]
        candidatos = list((base_dir / "data" / "DEPURADO").glob("*_350_*.xlsx"))
        candidatos += list((base_dir / "data" / "DEPURADO").glob("*_350_*.xls"))
        candidatos += list((base_dir / "data" / "DEPURADO").glob("*_350_*.csv"))

        if candidatos:
            archivo_350 = max(candidatos, key=lambda p: p.stat().st_mtime)
            try:
                if archivo_350.suffix.lower() in {".xlsx", ".xls"}:
                    df350 = pd.read_excel(archivo_350)
                else:
                    df350 = pd.read_csv(archivo_350, sep=None, engine="python", encoding="utf-8")

                col_num_350 = self._buscar_columna(
                    df350,
                    ["num_ide_", "num_ide", "numero_documento", "numero_id"],
                )
                if col_num_350 and col_num_350 in df350.columns:
                    for v in df350[col_num_350]:
                        d = self._normalizar_num_ide(v)
                        if d:
                            docs.add(d)
            except Exception as exc:
                self.logger.warning(f"Cruce 350 no disponible por lectura fallida: {exc}")

        return docs

    def _paso11_cruce_muerte_materna_ajuste6_finales(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        out = df.copy()

        col_num = self.columnas.get("num_ide")
        if "num_ide_formato" not in out.columns:
            if col_num and col_num in out.columns:
                out["num_ide_formato"] = out[col_num].apply(self._normalizar_num_ide)
            else:
                out["num_ide_formato"] = ""

        col_aj = self.columnas.get("ajuste")
        if not col_aj or col_aj not in out.columns:
            out["ajuste"] = ""
            col_aj = "ajuste"

        docs_muerte = self._detectar_docs_muerte(out)
        if not docs_muerte:
            return out, {
                "paso": 11,
                "estado": "EJECUTADO",
                "coincidencias_docs_muerte": 0,
                "marcados_ajuste_6": 0,
                "descartados_finales": 0,
            }

        mask_docs = out["num_ide_formato"].astype(str).isin(docs_muerte)
        out.loc[mask_docs, col_aj] = "6"

        aj_txt = out[col_aj].astype(str).str.strip().str.upper()
        aj_num = pd.to_numeric(aj_txt, errors="coerce")
        mask_6 = (aj_txt == "6") | (aj_num == 6)

        descartados = int(mask_6.sum())
        out_final = out.loc[~mask_6].copy().reset_index(drop=True)

        return out_final, {
            "paso": 11,
            "estado": "EJECUTADO",
            "coincidencias_docs_muerte": int(mask_docs.sum()),
            "marcados_ajuste_6": int(mask_docs.sum()),
            "descartados_finales": descartados,
        }

    def depurar_evento_549(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Ejecuta los 11 pasos definidos para el evento 549."""
        self._detectar_columnas(df)

        reporte: Dict[str, Any] = {
            "evento": 549,
            "rutina": "SECUENCIA_EXACTA_11_PASOS",
            "filas_inicio": len(df),
            "columnas_detectadas": {k: v for k, v in self.columnas.items() if v},
            "pasos": {},
        }

        trabajo = df.copy()

        trabajo, rep1 = self._paso1_analisis_departamento_residencia(trabajo)
        reporte["pasos"]["analisis_departamento_residencia"] = rep1

        trabajo, rep2 = self._paso2_eliminar_ajustes_6_d_r(trabajo)
        reporte["pasos"]["eliminar_ajustes_6_d_r"] = rep2

        trabajo, rep3 = self._paso3_quitar_duplicados_exactos(trabajo)
        reporte["pasos"]["quitar_duplicados_exactos"] = rep3

        trabajo, rep4 = self._paso4_marcar_no_cumplen_definicion(trabajo)
        reporte["pasos"]["marcar_no_cumplen_definicion"] = rep4

        trabajo, rep5 = self._paso5_ordenar_nombre_documento(trabajo)
        reporte["pasos"]["ordenar_nombre_documento"] = rep5

        trabajo, rep6 = self._paso6_formato_condicional_num_ide(trabajo)
        reporte["pasos"]["formato_condicional_num_ide"] = rep6

        trabajo, rep7 = self._paso7_depurar_repetidos_documento_abcd(trabajo)
        reporte["pasos"]["depurar_repetidos_documento_abcd"] = rep7

        trabajo, rep8 = self._paso8_concatenar_nombre_apellido_formato(trabajo)
        reporte["pasos"]["concatenar_nombre_apellido_formato_condicional"] = rep8

        trabajo, rep9 = self._paso9_revisar_fecha_nacimiento(trabajo)
        reporte["pasos"]["revisar_fecha_nacimiento"] = rep9

        trabajo, rep10 = self._paso10_depurar_repetidos_nombre_abcd(trabajo)
        reporte["pasos"]["depurar_repetidos_nombre_abcd"] = rep10

        trabajo, rep11 = self._paso11_cruce_muerte_materna_ajuste6_finales(trabajo)
        reporte["pasos"]["cruce_muerte_materna_ajuste_6_finales"] = rep11

        reporte["filas_fin"] = len(trabajo)
        reporte["filas_eliminadas"] = reporte["filas_inicio"] - reporte["filas_fin"]
        reporte["porcentaje_retencion"] = (
            round((reporte["filas_fin"] / reporte["filas_inicio"] * 100), 2)
            if reporte["filas_inicio"]
            else 0
        )

        return trabajo, reporte


# ------------------------
# API de compatibilidad
# ------------------------

def obtener_gestor_depuracion(filter_only_risaralda: bool = False):
    return Depuracion549(filter_only_risaralda=filter_only_risaralda)


def _leer_csv_robusto(ruta_csv: Path) -> pd.DataFrame:
    errores = []
    for enc in ["utf-8", "utf-8-sig", "cp1252", "latin-1"]:
        try:
            return pd.read_csv(ruta_csv, sep=None, engine="python", encoding=enc)
        except Exception as exc:
            errores.append(f"{enc}: {exc}")

    raise RuntimeError("No fue posible leer CSV con codificaciones comunes. " + " | ".join(errores))


def procesar_csv_mme_documento_tecnico(
    ruta_csv: str,
    ruta_salida: str = "MME_Depurado_Final.csv",
) -> Tuple[Path, Dict[str, Any]]:
    ruta_in = Path(ruta_csv)
    if not ruta_in.exists():
        raise FileNotFoundError(f"No existe el archivo CSV de entrada: {ruta_in}")

    df = _leer_csv_robusto(ruta_in)
    gestor = Depuracion549()
    df_out, reporte = gestor.depurar_evento_549(df)

    ruta_out = Path(ruta_salida)
    if not ruta_out.is_absolute():
        ruta_out = Path.cwd() / ruta_out

    df_out.to_csv(ruta_out, index=False, encoding="utf-8-sig")
    return ruta_out, reporte


def _main() -> None:
    parser = argparse.ArgumentParser(description="Depuracion MME (Evento 549) - Secuencia de 11 pasos")
    parser.add_argument("csv_entrada", help="Ruta del CSV de entrada")
    parser.add_argument("--salida", default="MME_Depurado_Final.csv", help="Ruta del CSV de salida")
    args = parser.parse_args()

    salida, reporte = procesar_csv_mme_documento_tecnico(args.csv_entrada, args.salida)

    print("=" * 72)
    print("Depuracion MME finalizada")
    print("=" * 72)
    print(f"Entrada : {args.csv_entrada}")
    print(f"Salida  : {salida}")
    print(f"Filas inicio : {reporte.get('filas_inicio')}")
    print(f"Filas fin    : {reporte.get('filas_fin')}")
    print(f"Eliminadas   : {reporte.get('filas_eliminadas')}")
    print("=" * 72)


if __name__ == "__main__":
    _main()
