"""
scripts/depuracion_evento_549.py
Rutina de depuracion para Morbilidad Materna Extrema (Evento 549)

Implementa los pasos estrictos solicitados:
0) Filtro por residencia: en ndep_resi conservar solo Risaralda (66).
1) Filtro inicial: eliminar ajuste en 6, D o R.
2) Duplicados exactos: remover usando todas las columnas excepto
   fuente, fec_arc_xl, version y nreg.
3) Casos repetidos por documento:
   - Ordenar por pri_ape_, seg_ape_, pri_nom_, seg_nom_, tip_ide_ y num_ide_.
   - Resolver por jerarquia:
       a) mayor fec_egreso con egreso=1
       b) si no hay fec_egreso, priorizar nom_upgd y pte_remtda=1
4) Reingreso:
   - Si para el mismo num_ide_ la diferencia entre fec_egreso (primero)
     y fec_con (segundo) es >= 7 dias, conservar ambos como episodios distintos.
   - Si es < 7 dias, conservar solo el principal del episodio.
5) Cruce con muerte materna:
   - Si hay evidencia de muerte materna y el caso no tuvo egreso previo,
     se marca ajuste=6 y se descarta del resultado final.

Tambien incluye un modo script para procesar CSV y generar:
MME_Depurado_Final.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from scripts.utils import Logger


class Depuracion549:
    """Depuracion del evento 549 siguiendo la rutina tecnica solicitada."""

    def __init__(self, filter_only_risaralda: bool = False):
        self.logger = Logger()
        self.filter_only_risaralda = filter_only_risaralda
        self.columnas: Dict[str, str] = {}

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

    def _buscar_columna(self, df: pd.DataFrame, patrones: List[str]) -> Optional[str]:
        cols_norm = {self._norm_text(c): c for c in df.columns}

        # 1) Coincidencia exacta primero para evitar falsos positivos
        for patron in patrones:
            p = self._norm_text(patron)
            for c_norm, c_real in cols_norm.items():
                if c_norm == p:
                    return c_real

        # 2) Coincidencia parcial como fallback
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
            "cod_eve": self._buscar_columna(df, ["cod_eve", "codigo_evento"]),
            "fallecio": self._buscar_columna(df, ["fallecio", "defuncion", "muerte_materna"]),
        }

    @staticmethod
    def _parse_date_series(series: pd.Series) -> pd.Series:
        if series is None:
            return pd.Series(dtype="datetime64[ns]")

        if pd.api.types.is_datetime64_any_dtype(series):
            return pd.to_datetime(series, errors="coerce")

        s = series.astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA, "None": pd.NA, "NaT": pd.NA})
        out = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

        # Primero formatos explícitos para evitar ambigüedades (YYYY-MM-DD vs DD/MM/YYYY)
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

        # Fallback para formatos atípicos
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

    def _valor_es_risaralda(self, value: Any) -> bool:
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

    def _paso0_filtrar_residencia_risaralda(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Paso exclusivo para evento 549: conservar solo registros con residencia en Risaralda.
        """
        filas_antes = len(df)
        col_res = self.columnas.get("ndep_resi")

        if not col_res or col_res not in df.columns:
            return df.copy(), {
                "paso": 0,
                "estado": "SALTADO",
                "razon": "No se encontro columna de departamento de residencia (ndep_resi)",
                "filas_antes": filas_antes,
                "filas_despues": filas_antes,
            }

        mask = df[col_res].apply(self._valor_es_risaralda)
        out = df.loc[mask].copy()

        return out, {
            "paso": 0,
            "estado": "EJECUTADO",
            "descripcion": "Filtro residencia: conservar solo Risaralda (ndep_resi=66)",
            "columna_residencia": col_res,
            "filas_antes": filas_antes,
            "filas_despues": len(out),
            "eliminadas": int((~mask).sum()),
        }

    def _paso1_filtro_ajuste(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        col_aj = self.columnas.get("ajuste")
        filas_antes = len(df)
        if not col_aj or col_aj not in df.columns:
            return df.copy(), {
                "paso": 1,
                "estado": "SALTADO",
                "razon": "No se encontro columna ajuste",
                "filas_antes": filas_antes,
                "filas_despues": filas_antes,
            }

        serie = df[col_aj].astype(str).str.strip().str.upper()
        serie_num = pd.to_numeric(serie, errors="coerce")
        mask = (serie == "D") | (serie == "R") | (serie_num == 6)

        out = df.loc[~mask].copy()
        return out, {
            "paso": 1,
            "estado": "EJECUTADO",
            "filas_antes": filas_antes,
            "filas_despues": len(out),
            "eliminadas": int(mask.sum()),
        }

    def _paso2_duplicados_exactos(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        filas_antes = len(df)
        excluir = []
        for key in ["fuente", "fec_arc_xl", "version", "nreg"]:
            col = self.columnas.get(key)
            if col and col in df.columns:
                excluir.append(col)

        subset = [c for c in df.columns if c not in set(excluir)]
        if not subset:
            return df.copy(), {
                "paso": 2,
                "estado": "SALTADO",
                "razon": "No hay columnas para comparar duplicados",
                "filas_antes": filas_antes,
                "filas_despues": filas_antes,
            }

        out = df.drop_duplicates(subset=subset, keep="first").copy()
        return out, {
            "paso": 2,
            "estado": "EJECUTADO",
            "columnas_excluidas": excluir,
            "filas_antes": filas_antes,
            "filas_despues": len(out),
            "eliminadas": filas_antes - len(out),
        }

    def _paso3_ordenar(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
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
                "paso": 3,
                "estado": "SALTADO",
                "razon": "No se encontraron columnas de orden",
            }

        tmp = df.copy()
        for c in orden_cols:
            tmp[c] = tmp[c].fillna("").astype(str)

        out = tmp.sort_values(orden_cols, ascending=True, kind="mergesort").reset_index(drop=True)
        return out, {
            "paso": 3,
            "estado": "EJECUTADO",
            "columnas_orden": orden_cols,
            "filas": len(out),
        }

    def _segmentar_episodios(self, group_df: pd.DataFrame) -> List[List[int]]:
        """Segmenta un documento en episodios por regla de reingreso (>=7 dias)."""
        col_fec_con = self.columnas.get("fec_con")
        col_fec_eg = self.columnas.get("fec_egreso")

        if not col_fec_con or col_fec_con not in group_df.columns:
            return [group_df.index.tolist()]

        g = group_df.copy()
        g["_fec_con_dt"] = self._parse_date_series(g[col_fec_con])
        g["_fec_eg_dt"] = self._parse_date_series(g[col_fec_eg]) if col_fec_eg and col_fec_eg in g.columns else pd.NaT
        g = g.sort_values(["_fec_con_dt"], kind="mergesort")

        episodes: List[List[int]] = []
        current: List[int] = []
        prev_idx: Optional[int] = None

        for idx, row in g.iterrows():
            if prev_idx is None:
                current = [idx]
                prev_idx = idx
                continue

            prev = g.loc[prev_idx]
            prev_eg = prev.get("_fec_eg_dt", pd.NaT)
            curr_con = row.get("_fec_con_dt", pd.NaT)

            is_reingreso = False
            if pd.notna(prev_eg) and pd.notna(curr_con):
                is_reingreso = (curr_con - prev_eg).days >= 7

            if is_reingreso:
                episodes.append(current)
                current = [idx]
            else:
                current.append(idx)

            prev_idx = idx

        if current:
            episodes.append(current)

        return episodes

    def _seleccionar_principal(self, episode_df: pd.DataFrame) -> Tuple[int, str]:
        col_eg = self.columnas.get("egreso")
        col_fec_eg = self.columnas.get("fec_egreso")

        # Jerarquia A: mayor fecha de egreso con egreso=1
        if col_eg and col_fec_eg and col_eg in episode_df.columns and col_fec_eg in episode_df.columns:
            eg_yes = episode_df[col_eg].apply(self._is_yes)
            fec = self._parse_date_series(episode_df[col_fec_eg])
            candidatos = episode_df[eg_yes & fec.notna()]
            if len(candidatos) > 0:
                idx = fec.loc[candidatos.index].idxmax()
                return idx, "A"

        # Jerarquia B: institucion + pte_remtda=1
        scores = episode_df.apply(self._score_institucional, axis=1)
        if len(scores) > 0 and scores.max() > 0:
            top = episode_df[scores == scores.max()]
            if len(top) == 1:
                return top.index[0], "B"
            comp = top.apply(self._score_completitud, axis=1)
            return comp.idxmax(), "B"

        # Fallback por completitud
        comp = episode_df.apply(self._score_completitud, axis=1)
        return comp.idxmax(), "FALLBACK"

    def _paso4_repetidos_reingreso(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        col_num = self.columnas.get("num_ide")
        if not col_num or col_num not in df.columns:
            return df.copy(), {
                "paso": 4,
                "estado": "SALTADO",
                "razon": "No se encontro num_ide_",
            }

        tmp = df.copy()
        tmp["_doc_norm"] = tmp[col_num].astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA})

        keep_indices: List[int] = []
        reingresos_detectados = 0
        grupos_repetidos = 0
        criterios = {"A": 0, "B": 0, "FALLBACK": 0}

        # Mantener documentos vacios tal cual
        vacios = tmp[tmp["_doc_norm"].isna()]
        keep_indices.extend(vacios.index.tolist())

        for _, g in tmp[tmp["_doc_norm"].notna()].groupby("_doc_norm", dropna=False):
            if len(g) > 1:
                grupos_repetidos += 1

            episodios = self._segmentar_episodios(g)
            if len(episodios) > 1:
                reingresos_detectados += len(episodios) - 1

            for ep in episodios:
                ep_df = g.loc[ep]
                idx_sel, crit = self._seleccionar_principal(ep_df)
                keep_indices.append(idx_sel)
                if crit in criterios:
                    criterios[crit] += 1

        out = tmp.loc[sorted(set(keep_indices))].copy()
        out = out.drop(columns=["_doc_norm"], errors="ignore").reset_index(drop=True)

        return out, {
            "paso": 4,
            "estado": "EJECUTADO",
            "filas_despues": len(out),
            "grupos_repetidos_num_ide": grupos_repetidos,
            "reingresos_detectados": reingresos_detectados,
            "criterio_reingreso_dias": 7,
            "conteo_criterios": criterios,
        }

    def _detectar_docs_muerte(self, df: pd.DataFrame) -> set[str]:
        docs: set[str] = set()
        col_num = self.columnas.get("num_ide")
        if not col_num or col_num not in df.columns:
            return docs

        # Evidencia en el mismo dataframe
        col_cod_eve = self.columnas.get("cod_eve")
        if col_cod_eve and col_cod_eve in df.columns:
            cod = pd.to_numeric(df[col_cod_eve], errors="coerce")
            docs.update(df.loc[cod == 350, col_num].astype(str).str.strip().tolist())

        col_fallecio = self.columnas.get("fallecio")
        if col_fallecio and col_fallecio in df.columns:
            mask = df[col_fallecio].apply(self._is_yes) | df[col_fallecio].astype(str).str.lower().str.contains("fallec|muerte", na=False)
            docs.update(df.loc[mask, col_num].astype(str).str.strip().tolist())

        # Evidencia externa en archivos depurados evento 350
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

                col_num_350 = self._buscar_columna(df350, ["num_ide_", "num_ide", "numero_documento", "numero_id"])
                if col_num_350 and col_num_350 in df350.columns:
                    docs.update(df350[col_num_350].astype(str).str.strip().tolist())
            except Exception as exc:
                self.logger.warning(f"Cruce 350 no disponible por lectura fallida: {exc}")

        docs = {d for d in docs if d and d.lower() not in {"nan", "none"}}
        return docs

    def _paso5_cruce_muerte_materna(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        col_num = self.columnas.get("num_ide")
        col_eg = self.columnas.get("egreso")
        col_aj = self.columnas.get("ajuste")
        col_fec_con = self.columnas.get("fec_con")

        if not col_num or col_num not in df.columns:
            return df.copy(), {"paso": 5, "estado": "SALTADO", "razon": "No se encontro num_ide_"}

        out = df.copy()
        if not col_aj or col_aj not in out.columns:
            out["ajuste"] = ""
            col_aj = "ajuste"

        docs_muerte = self._detectar_docs_muerte(out)
        if not docs_muerte:
            return out, {
                "paso": 5,
                "estado": "EJECUTADO",
                "coincidencias_docs_muerte": 0,
                "marcados_ajuste_6": 0,
                "descartados_finales": 0,
            }

        out["_doc_norm"] = out[col_num].astype(str).str.strip()
        marcados = []

        for doc, g in out.groupby("_doc_norm", dropna=False):
            if doc not in docs_muerte:
                continue
            if not isinstance(doc, str) or not doc.strip():
                continue

            # Orden temporal por consulta para evaluar proceso inicial
            if col_fec_con and col_fec_con in g.columns:
                g = g.copy()
                g["_fec_con_dt"] = self._parse_date_series(g[col_fec_con])
                g = g.sort_values(["_fec_con_dt"], kind="mergesort")

            idx_inicial = g.index[0]
            egreso_previo = False
            if col_eg and col_eg in g.columns:
                egreso_previo = self._is_yes(g.loc[idx_inicial, col_eg])

            # Regla: si falla en proceso inicial sin egreso previo -> ajuste 6 y descartar
            if not egreso_previo:
                out.loc[idx_inicial, col_aj] = "6"
                marcados.append(idx_inicial)

        mask_6 = pd.to_numeric(out[col_aj], errors="coerce") == 6
        out_final = out.loc[~mask_6].copy().drop(columns=["_doc_norm"], errors="ignore").reset_index(drop=True)

        return out_final, {
            "paso": 5,
            "estado": "EJECUTADO",
            "coincidencias_docs_muerte": int(out["_doc_norm"].isin(docs_muerte).sum()),
            "marcados_ajuste_6": len(marcados),
            "descartados_finales": int(mask_6.sum()),
        }

    def depurar_evento_549(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Ejecuta la rutina tecnica estricta para el evento 549."""
        self._detectar_columnas(df)
        reporte: Dict[str, Any] = {
            "evento": 549,
            "rutina": "Documento tecnico MME - rutina estricta",
            "filas_inicio": len(df),
            "columnas_detectadas": {k: v for k, v in self.columnas.items() if v},
            "pasos": {},
        }

        trabajo = df.copy()

        trabajo, rep0 = self._paso0_filtrar_residencia_risaralda(trabajo)
        reporte["pasos"]["residencia_risaralda"] = rep0

        trabajo, rep1 = self._paso1_filtro_ajuste(trabajo)
        reporte["pasos"]["filtros_iniciales"] = rep1

        trabajo, rep2 = self._paso2_duplicados_exactos(trabajo)
        reporte["pasos"]["duplicados_exactos"] = rep2

        trabajo, rep3 = self._paso3_ordenar(trabajo)
        reporte["pasos"]["orden_base"] = rep3

        trabajo, rep4 = self._paso4_repetidos_reingreso(trabajo)
        reporte["pasos"]["repetidos_reingreso"] = rep4

        trabajo, rep5 = self._paso5_cruce_muerte_materna(trabajo)
        reporte["pasos"]["cruce_muerte_materna"] = rep5

        reporte["filas_fin"] = len(trabajo)
        reporte["filas_eliminadas"] = reporte["filas_inicio"] - reporte["filas_fin"]
        reporte["porcentaje_retencion"] = round((reporte["filas_fin"] / reporte["filas_inicio"] * 100), 2) if reporte["filas_inicio"] else 0

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


def procesar_csv_mme_documento_tecnico(ruta_csv: str, ruta_salida: str = "MME_Depurado_Final.csv") -> Tuple[Path, Dict[str, Any]]:
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
    parser = argparse.ArgumentParser(description="Depuracion MME (Evento 549) - Documento tecnico")
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
