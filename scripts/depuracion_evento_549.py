"""
scripts/depuracion_evento_549.py
Depuración del evento 549: Morbilidad Materna Extrema

Implementa la RUTINA COMPLETA de depuración según el Documento Técnico
"Rutina para el análisis de datos del evento <<morbilidad materna extrema>>" (versión ajustada 2019)

PASOS (en orden exacto):
1. Quitar casos con ajuste 6, D, R
2. Quitar duplicados exactos
3. Señalar casos que NO cumplen definición de caso
4. Ordenar base por apellidos, nombres, tipo/número ID
5. Dar formato condicional (identificar repetidos por num_ide)
6. Depurar repetidos por documento (criterios A,B,C,D)
7. Concatenar nombre+apellido, dar formato condicional
8. Revisar fecha de nacimiento en repetidos por nombre
9. Depurar repetidos por nombre+fecha nacimiento
10. Cruce con evento 350 (muerte materna)
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict, Any, Optional, List
from pathlib import Path
from scripts.utils import Logger
from datetime import datetime, timedelta


class Depuracion549:
    """
    Depuración del evento 549: Morbilidad Materna Extrema
    Lee automáticamente TODAS las columnas del archivo
    """
    
    # Variables clínicas que deben evaluarse
    VARIABLES_CLINICAS = [
        'eclampsia', 'choq_septi', 'choq_hipov', 'preclampsi', 'rupt_uteri',
        'falla_card', 'falla_vasc', 'falla_rena', 'falla_hepa', 'falla_meta',
        'falla_cere', 'falla_resp', 'falla_coag', 'ingres_uci', 'cir_adicio', 'transfusio'
    ]
    
    def __init__(self, filter_only_risaralda: bool = False):
        self.logger = Logger()
        self.columnas_detectadas = {}  # Para guardar columnas detectadas automáticamente
        self.filter_only_risaralda = filter_only_risaralda
    
    @staticmethod
    def es_aplicable(codigo_evento: int) -> bool:
        """Verifica si este depurador aplica al evento"""
        return codigo_evento == 549
    
    def _detectar_columnas(self, df: pd.DataFrame) -> Dict[str, Optional[str]]:
        """
        Detecta automáticamente las columnas clave en el dataframe
        Retorna diccionario con columnas detectadas
        """
        cols = {col.lower(): col for col in df.columns}  # Mapeo case-insensitive
        
        # Detectar columnas por patrón
        detectadas = {
            'pri_nom': self._buscar_columna(cols, ['pri_nom', 'primer_nombre']),
            'seg_nom': self._buscar_columna(cols, ['seg_nom', 'segundo_nombre']),
            'pri_ape': self._buscar_columna(cols, ['pri_ape', 'primer_apellido']),
            'seg_ape': self._buscar_columna(cols, ['seg_ape', 'segundo_apellido']),
            'tip_ide': self._buscar_columna(cols, ['tip_ide', 'tipo_id']),
            'num_ide': self._buscar_columna(cols, ['num_ide', 'numero_id']),
            'ajuste': self._buscar_columna(cols, ['ajuste']),
            'fec_con': self._buscar_columna(cols, ['fec_con', 'fecha_consulta']),
            'fec_egreso': self._buscar_columna(cols, ['fec_egreso', 'fecha_egreso']),
            'egreso': self._buscar_columna(cols, ['egreso', 'tipo_egreso']),
            'fecha_nto': self._buscar_columna(cols, ['fecha_nto', 'fecha_nacimiento']),
            'nom_upgd': self._buscar_columna(cols, ['nom_upgd', 'nombre_upgd']),
            'pte_remtda': self._buscar_columna(cols, ['pte_remtda']),
            'codinst_r1': self._buscar_columna(cols, ['codinst_r1']),
            'inst_refe1': self._buscar_columna(cols, ['inst_refe1']),
            'codinst_r2': self._buscar_columna(cols, ['codinst_r2']),
            'inst_refe2': self._buscar_columna(cols, ['inst_refe2']),
            'dias_hospi': self._buscar_columna(cols, ['dias_hospi']),
            'fec_hos': self._buscar_columna(cols, ['fec_hos', 'fecha_hospitalizacion']),
            'fec_not': self._buscar_columna(cols, ['fec_not', 'fecha_notificacion']),
            'fec_aju': self._buscar_columna(cols, ['fec_aju', 'fecha_ajuste']),
            'fuente': self._buscar_columna(cols, ['fuente']),
            'fec_arc_xl': self._buscar_columna(cols, ['fec_arc_xl']),
            'version': self._buscar_columna(cols, ['version']),
            'nreg': self._buscar_columna(cols, ['nreg']),
            'cod_dpto_r': self._buscar_columna(cols, ['cod_dpto_r', 'ndep_resi', 'departamento_r', 'codigo_dpto_residencia']),
            'cod_mun_r': self._buscar_columna(cols, ['cod_mun_r', 'municipio_r', 'codigo_mun_residencia']),
            'dpto_r': self._buscar_columna(cols, ['dpto_r', 'nom_dpto_r', 'nombre_departamento_r']),
            'cod_eve': self._buscar_columna(cols, ['cod_eve', 'codigo_evento']),
        }
        
        self.columnas_detectadas = {k: v for k, v in detectadas.items() if v}
        return detectadas
    
    def _buscar_columna(self, cols_dict: Dict[str, str], patrones: List[str]) -> Optional[str]:
        """Busca una columna por patrón (case-insensitive)"""
        cols_lower = {k.lower(): v for k, v in cols_dict.items()}
        for patron in patrones:
            patron_lower = patron.lower()
            for col_lower, col_original in cols_lower.items():
                if patron_lower in col_lower:
                    return col_original
        return None

    @staticmethod
    def _to_num(value, default: float = 0.0) -> float:
        try:
            n = pd.to_numeric(pd.Series([value]), errors='coerce').iloc[0]
            if pd.isna(n):
                return default
            return float(n)
        except Exception:
            return default

    @staticmethod
    def _to_date(value):
        try:
            return pd.to_datetime(value, errors='coerce', dayfirst=True)
        except Exception:
            return pd.NaT

    @staticmethod
    def _value_is_yes(value) -> bool:
        if pd.isna(value):
            return False
        txt = str(value).strip().lower()
        return txt in {'1', 'si', 's', 'true', 'verdadero', 'yes', 'y'}

    def _score_institucional(self, row: pd.Series) -> int:
        """Criterio B: priorización institucional cuando faltan egreso/fechas."""
        score = 0
        col_nom_upgd = self.columnas_detectadas.get('nom_upgd')
        col_pte_remtda = self.columnas_detectadas.get('pte_remtda')
        col_ref1 = self.columnas_detectadas.get('inst_refe1')
        col_ref2 = self.columnas_detectadas.get('inst_refe2')

        if col_nom_upgd and col_nom_upgd in row.index and pd.notna(row[col_nom_upgd]) and str(row[col_nom_upgd]).strip():
            score += 4
        if col_pte_remtda and col_pte_remtda in row.index and self._value_is_yes(row[col_pte_remtda]):
            score += 3
        if col_ref1 and col_ref1 in row.index and pd.notna(row[col_ref1]) and str(row[col_ref1]).strip():
            score += 2
        if col_ref2 and col_ref2 in row.index and pd.notna(row[col_ref2]) and str(row[col_ref2]).strip():
            score += 1
        return score

    def _score_completitud(self, row: pd.Series) -> int:
        """Cuenta variables no vacías para desempates por completitud."""
        return int((row.notna() & (row.astype(str).str.strip() != '')).sum())

    def _seleccionar_mejor_registro(self, grupo_df: pd.DataFrame) -> int:
        """
        Selecciona el mejor registro aplicando criterios A, B, C y D.
        Retorna índice del registro a mantener.
        """
        col_fec_con = self.columnas_detectadas.get('fec_con')
        col_fec_egreso = self.columnas_detectadas.get('fec_egreso')
        col_egreso = self.columnas_detectadas.get('egreso')
        col_fec_aju = self.columnas_detectadas.get('fec_aju')
        col_ajuste = self.columnas_detectadas.get('ajuste')
        col_nom_upgd = self.columnas_detectadas.get('nom_upgd')
        col_fec_not = self.columnas_detectadas.get('fec_not')

        # D) Ajuste 7 misma UPGD + misma fecha de notificación: preferir ajuste más reciente y más completo
        if col_ajuste and col_ajuste in grupo_df.columns and col_nom_upgd and col_fec_not:
            g7 = grupo_df[grupo_df[col_ajuste].astype(str).str.strip() == '7']
            if len(g7) > 1:
                subgrupos = g7.groupby([col_nom_upgd, col_fec_not], dropna=False)
                for _, sg in subgrupos:
                    if len(sg) > 1:
                        if col_fec_aju and col_fec_aju in sg.columns:
                            fechas_aju = pd.to_datetime(sg[col_fec_aju], errors='coerce', dayfirst=True)
                            idx_max_aju = fechas_aju.idxmax()
                            if pd.notna(fechas_aju.loc[idx_max_aju]):
                                return idx_max_aju
                        scores = sg.apply(self._score_completitud, axis=1)
                        return scores.idxmax()

        # A) Mantener mayor fecha de egreso donde egreso=1
        if col_fec_egreso and col_egreso and col_fec_egreso in grupo_df.columns and col_egreso in grupo_df.columns:
            egreso_ok = grupo_df[grupo_df[col_egreso].apply(self._value_is_yes)].copy()
            if len(egreso_ok) > 0:
                fechas = pd.to_datetime(egreso_ok[col_fec_egreso], errors='coerce', dayfirst=True)
                idx = fechas.idxmax()
                if pd.notna(fechas.loc[idx]):
                    return idx

        # C) Si reingresos (>=7 días), mantener primera hospitalización
        if col_fec_con and col_fec_egreso and col_fec_con in grupo_df.columns and col_fec_egreso in grupo_df.columns:
            temp = grupo_df.copy()
            temp['_fec_con_dt'] = pd.to_datetime(temp[col_fec_con], errors='coerce', dayfirst=True)
            temp['_fec_eg_dt'] = pd.to_datetime(temp[col_fec_egreso], errors='coerce', dayfirst=True)
            temp = temp.sort_values('_fec_con_dt')
            if len(temp) > 1:
                for i in range(1, len(temp)):
                    actual = temp.iloc[i]
                    previo = temp.iloc[i - 1]
                    if pd.notna(actual['_fec_con_dt']) and pd.notna(previo['_fec_eg_dt']):
                        if (actual['_fec_con_dt'] - previo['_fec_eg_dt']).days >= 7:
                            return temp.iloc[0].name

        # B) Si no hay fechas claras, priorizar por ruta institucional
        institucional = grupo_df.apply(self._score_institucional, axis=1)
        if institucional.max() > 0:
            top = grupo_df[institucional == institucional.max()]
            if len(top) == 1:
                return top.index[0]
            completitud = top.apply(self._score_completitud, axis=1)
            return completitud.idxmax()

        # Fallback estable: registro con mayor completitud
        scores = grupo_df.apply(self._score_completitud, axis=1)
        return scores.idxmax()
    
    def depurar_evento_549(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Ejecuta los 10 pasos de depuración del evento 549
        """
        filas_inicio = len(df)
        df_trabajo = df.copy()
        
        reporte = {
            "evento": 549,
            "nombre_evento": "Morbilidad Materna Extrema",
            "documento": "Rutina para el análisis - versión ajustada 2019",
            "filas_inicio": filas_inicio,
            "pasos": {},
            "columnas_detectadas": {}
        }
        
        # Detectar columnas
        self._detectar_columnas(df_trabajo)
        reporte["columnas_detectadas"] = self.columnas_detectadas
        
        self.logger.info(f"Columnas detectadas: {len(self.columnas_detectadas)}")
        
        # PASO 1
        self.logger.info("PASO 1/10: Eliminar ajuste 6, D, R...")
        df_trabajo, rep1 = self._paso1_eliminar_ajustes(df_trabajo)
        reporte["pasos"]["paso_1"] = rep1
        
        # PASO 2
        self.logger.info("PASO 2/10: Eliminar duplicados exactos...")
        df_trabajo, rep2 = self._paso2_eliminar_duplicados(df_trabajo)
        reporte["pasos"]["paso_2"] = rep2
        
        # PASO 3
        self.logger.info("PASO 3/10: Señalar no cumple definición...")
        df_trabajo, rep3 = self._paso3_no_cumple_definicion(df_trabajo)
        reporte["pasos"]["paso_3"] = rep3
        
        # ANÁLISIS POR DEPARTAMENTO DE RESIDENCIA (Evento Multifactorial)
        self.logger.info("ANÁLISIS POR DPTO DE RESIDENCIA: Evento multifactorial no transmisible...")
        df_trabajo, rep_dpto = self._analizar_departamento_residencia(df_trabajo)
        reporte["pasos"]["analisis_dpto"] = rep_dpto
        
        # PASO 4
        self.logger.info("PASO 4/10: Ordenar base...")
        df_trabajo, rep4 = self._paso4_ordenar(df_trabajo)
        reporte["pasos"]["paso_4"] = rep4
        
        # PASO 5
        self.logger.info("PASO 5/10: Identificar repetidos por num_ide...")
        df_trabajo, rep5 = self._paso5_identificar_duplicados_doc(df_trabajo)
        reporte["pasos"]["paso_5"] = rep5
        
        # PASO 6
        self.logger.info("PASO 6/10: Depurar repetidos por documento...")
        df_trabajo, rep6 = self._paso6_depurar_duplicados_doc(df_trabajo)
        reporte["pasos"]["paso_6"] = rep6
        
        # PASO 7
        self.logger.info("PASO 7/10: Identificar repetidos por nombre...")
        df_trabajo, rep7 = self._paso7_identificar_nombre(df_trabajo)
        reporte["pasos"]["paso_7"] = rep7
        
        # PASO 8
        self.logger.info("PASO 8/10: Revisar fecha nacimiento...")
        df_trabajo, rep8 = self._paso8_revisar_fecha_nac(df_trabajo)
        reporte["pasos"]["paso_8"] = rep8
        
        # PASO 9
        self.logger.info("PASO 9/10: Depurar repetidos por nombre+fecha...")
        df_trabajo, rep9 = self._paso9_depurar_repetidos_nombre(df_trabajo)
        reporte["pasos"]["paso_9"] = rep9
        
        # PASO 10
        self.logger.info("PASO 10/10: Cruce con evento 350...")
        df_trabajo, rep10 = self._paso10_cruce_muerte_materna(df_trabajo)
        reporte["pasos"]["paso_10"] = rep10
        
        # Resumen final
        reporte["filas_fin"] = len(df_trabajo)
        reporte["filas_eliminadas"] = filas_inicio - len(df_trabajo)
        reporte["porcentaje_retencion"] = round(
            (len(df_trabajo) / filas_inicio * 100) if filas_inicio > 0 else 0, 2
        )
        
        self.logger.info(f"Depuración 549 completada: {filas_inicio} → {len(df_trabajo)} ({reporte['porcentaje_retencion']}%)")
        
        return df_trabajo, reporte
    
    def _paso1_eliminar_ajustes(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """PASO 1: Quitar ajuste 6, D, R"""
        filas_antes = len(df)
        col_ajuste = self.columnas_detectadas.get('ajuste')
        
        if not col_ajuste or col_ajuste not in df.columns:
            return df, {"paso": 1, "estado": "SALTADO", "razon": "Columna ajuste no existe"}
        
        # Eliminar filas con ajuste 6, D, R
        df_limpio = df[~df[col_ajuste].isin(['6', 'D', 'R', 6, '6D', '6R'])].copy()
        
        eliminadas = filas_antes - len(df_limpio)
        
        return df_limpio, {
            "paso": 1,
            "descripcion": "Quitar ajuste 6, D, R",
            "estado": "EJECUTADO",
            "filas_antes": filas_antes,
            "eliminadas": eliminadas,
            "filas_despues": len(df_limpio)
        }
    
    def _paso2_eliminar_duplicados(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """PASO 2: Quitar duplicados exactos (desmarcar: fuente, fec_arc_xl, version, nreg)"""
        filas_antes = len(df)
        
        # Columnas a excluir
        cols_excluir = {
            self.columnas_detectadas.get('fuente'),
            self.columnas_detectadas.get('fec_arc_xl'),
            self.columnas_detectadas.get('version'),
            self.columnas_detectadas.get('nreg')
        }
        cols_excluir.discard(None)  # Remover None
        
        # Columnas a considerar para duplicados
        cols_duplicate = [col for col in df.columns if col not in cols_excluir]
        
        df_sin_dup = df.drop_duplicates(subset=cols_duplicate, keep='first').copy()
        
        eliminadas = filas_antes - len(df_sin_dup)
        
        return df_sin_dup, {
            "paso": 2,
            "descripcion": "Quitar duplicados exactos",
            "estado": "EJECUTADO",
            "columnas_excluidas": list(cols_excluir),
            "filas_antes": filas_antes,
            "eliminadas": eliminadas,
            "filas_despues": len(df_sin_dup)
        }
    
    def _paso3_no_cumple_definicion(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """
        PASO 3: Señalar casos que NO cumplen definición de caso
        Debe tener MÍNIMO 1 variable clínica = 1 (no 2, no vacía)
        """
        filas_antes = len(df)
        
        # Buscar variables clínicas presentes
        vars_presentes = []
        for var in self.VARIABLES_CLINICAS:
            col = self._buscar_columna(
                {col.lower(): col for col in df.columns},
                [var]
            )
            if col:
                vars_presentes.append(col)
        
        if not vars_presentes:
            return df, {
                "paso": 3,
                "estado": "SALTADO",
                "razon": "No se encontraron variables clínicas"
            }
        
        # Marcar casos: cumple si tiene al menos una variable clínica en 1/Si/True
        mascara_cumple = pd.Series([False] * len(df), index=df.index)
        
        for col in vars_presentes:
            try:
                serie = df[col]
                mascara_col = (pd.to_numeric(serie, errors='coerce') == 1) | serie.apply(self._value_is_yes)
                mascara_cumple = mascara_cumple | mascara_col
            except:
                pass

            df_marcado = df.copy()
            df_marcado['_no_cumple_definicion_549'] = ~mascara_cumple
            df_validos = df_marcado[mascara_cumple].copy()
        eliminadas = filas_antes - len(df_validos)
        
        return df_validos, {
            "paso": 3,
            "descripcion": "Señalar no cumple definición",
            "estado": "EJECUTADO",
            "variables_evaluadas": len(vars_presentes),
            "filas_antes": filas_antes,
            "marcados_no_cumplen": int((~mascara_cumple).sum()),
            "no_cumplen_eliminadas": eliminadas,
            "filas_despues": len(df_validos)
        }
    
    def _analizar_departamento_residencia(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """
        ANÁLISIS POR DEPARTAMENTO DE RESIDENCIA
        
        Evento 549 es MULTIFACTORIAL y NO TRANSMISIBLE (en contexto territorial)
        Los factores de riesgo dependen fuertemente del:
        - Contexto socioeconómico local
        - Cobertura de servicios de salud por departamento
        - Políticas de salud pública departamentales
        
        Este análisis agrupa casos por departamento de residencia
        """
        col_dpto_r = self.columnas_detectadas.get('cod_dpto_r')
        col_nom_dpto = self.columnas_detectadas.get('dpto_r')
        
        reporte = {
            "analisis": "DEPARTAMENTO DE RESIDENCIA",
            "razon": "Evento multifactorial no transmisible - análisis territorial",
            "estado": "SALTADO"
        }
        
        if not col_dpto_r or col_dpto_r not in df.columns:
            reporte["razon"] = "Columna cod_dpto_r no encontrada"
            return df, reporte

        # Evento 549 es de RESIDENCIA: SIEMPRE filtrar por Risaralda (cod 66)
        # Solo se dejan filas donde ndep_resi/cod_dpto_r == 66 (Risaralda)
        filas_antes = len(df)
        serie_dpto = pd.to_numeric(df[col_dpto_r], errors='coerce')
        df = df[serie_dpto == 66].copy()
        self.logger.info(f"Filtro residencia Risaralda (66) aplicado: {filas_antes} -> {len(df)}")
        
        # Análisis por departamento
        distribucion = df[col_dpto_r].value_counts().to_dict()
        dptos_totales = len(distribucion)
        casos_totales = len(df)
        
        # Información por departamento
        info_dptos = []
        for cod_dpto, cantidad in sorted(distribucion.items(), key=lambda x: x[1], reverse=True):
            porcentaje = round((cantidad / casos_totales) * 100, 2) if casos_totales > 0 else 0
            info_dptos.append({
                "codigo": cod_dpto,
                "casos": cantidad,
                "porcentaje": porcentaje
            })
        
        # Validación de cobertura territorial
        dptos_sin_casos = 0
        casos_sin_dpto = df[col_dpto_r].isna().sum()
        
        reporte = {
            "analisis": "DEPARTAMENTO DE RESIDENCIA",
            "razon": "Evento multifactorial no transmisible - requiere análisis territorial",
            "estado": "EJECUTADO",
            "filtro_residencia_risaralda": bool(self.filter_only_risaralda),
            "filas_antes_filtro": filas_antes,
            "filas_despues_filtro": len(df),
            "departamentos_representados": dptos_totales,
            "casos_total": casos_totales,
            "casos_sin_dpto": casos_sin_dpto,
            "distribucion_por_dpto": info_dptos[:10],  # Top 10 departamentos
            "interpretacion": "Análisis territorial completado - considerar contexto socioeconómico local"
        }
        
        self.logger.info(f"Análisis departamental: {dptos_totales} dtos, {casos_sin_dpto} sin código")
        
        return df, reporte
    
    def _paso4_ordenar(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """PASO 4: Ordenar por pri_ape, seg_ape, pri_nom, seg_nom, tip_ide, num_ide"""
        cols_ordenar = [
            self.columnas_detectadas.get('pri_ape'),
            self.columnas_detectadas.get('seg_ape'),
            self.columnas_detectadas.get('pri_nom'),
            self.columnas_detectadas.get('seg_nom'),
            self.columnas_detectadas.get('tip_ide'),
            self.columnas_detectadas.get('num_ide'),
        ]
        cols_ordenar = [c for c in cols_ordenar if c]
        
        if not cols_ordenar:
            return df, {"paso": 4, "estado": "SALTADO"}
        
        df_ordenado = df.copy()
        # Llenar NaN para poder ordenar
        for col in cols_ordenar:
            if col in df_ordenado.columns:
                df_ordenado[col] = df_ordenado[col].fillna('')
        
        df_ordenado = df_ordenado.sort_values(cols_ordenar, ascending=True).reset_index(drop=True)
        
        return df_ordenado, {
            "paso": 4,
            "descripcion": "Ordenar base",
            "estado": "EJECUTADO",
            "columnas_orden": cols_ordenar
        }
    
    def _paso5_identificar_duplicados_doc(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """PASO 5: Identificar repetidos por num_ide"""
        col_num_ide = self.columnas_detectadas.get('num_ide')
        
        if not col_num_ide or col_num_ide not in df.columns:
            return df, {"paso": 5, "estado": "SALTADO"}
        
        duplicados_mask = df[col_num_ide].duplicated(keep=False)
        grupos_dup = df[duplicados_mask].groupby(col_num_ide).size()
        
        return df, {
            "paso": 5,
            "descripcion": "Identificar repetidos por num_ide",
            "estado": "EJECUTADO",
            "grupos_duplicados": len(grupos_dup),
            "registros_con_dup": duplicados_mask.sum()
        }
    
    def _paso6_depurar_duplicados_doc(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """PASO 6: Depurar repetidos por documento con criterios A,B,C,D"""
        col_num_ide = self.columnas_detectadas.get('num_ide')
        
        if not col_num_ide or col_num_ide not in df.columns:
            return df, {"paso": 6, "estado": "SALTADO"}
        
        df_depurado = df.copy()
        indices_mantener = set()
        registros_evaluados = 0
        
        # Para cada documento duplicado
        duplicados_mask = df_depurado[col_num_ide].duplicated(keep=False)
        grupos = df_depurado[duplicados_mask].groupby(col_num_ide)
        
        for doc_id, grupo_df in grupos:
            registros_evaluados += len(grupo_df)

            mejor_idx = self._seleccionar_mejor_registro(grupo_df)
            indices_mantener.add(mejor_idx)
        
        # Mantener todos excepto los duplicados (excepto el seleccionado)
        for idx in df.index:
            if idx not in duplicados_mask[duplicados_mask].index or idx in indices_mantener:
                indices_mantener.add(idx)
        
        df_depurado = df.loc[list(indices_mantener)].reset_index(drop=True)
        eliminadas = len(df) - len(df_depurado)
        
        return df_depurado, {
            "paso": 6,
            "descripcion": "Depurar repetidos por documento",
            "estado": "EJECUTADO",
            "registros_evaluados": registros_evaluados,
            "eliminadas": eliminadas,
            "criterios": ["A", "B", "C", "D"]
        }
    
    def _paso7_identificar_nombre(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """PASO 7: Concatenar nombre+apellido, identificar duplicados"""
        col_pri_nom = self.columnas_detectadas.get('pri_nom')
        col_pri_ape = self.columnas_detectadas.get('pri_ape')
        
        if not col_pri_nom or not col_pri_ape:
            return df, {"paso": 7, "estado": "SALTADO"}
        
        # Crear columna auxiliar
        df['_nombre_ape_temp'] = (
            df[col_pri_nom].fillna('').astype(str) + ' ' +
            df[col_pri_ape].fillna('').astype(str)
        ).str.strip()
        
        duplicados_nombre = df['_nombre_ape_temp'].duplicated(keep=False).sum()
        
        return df, {
            "paso": 7,
            "descripcion": "Identificar repetidos por nombre+apellido",
            "estado": "EJECUTADO",
            "registros_con_dup_nombre": duplicados_nombre,
            "columna_temp": "_nombre_ape_temp"
        }
    
    def _paso8_revisar_fecha_nac(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """PASO 8: Revisar fecha nacimiento en repetidos por nombre"""
        if '_nombre_ape_temp' not in df.columns:
            return df, {"paso": 8, "estado": "SALTADO"}
        
        col_fec_nac = self.columnas_detectadas.get('fecha_nto')
        
        if not col_fec_nac:
            return df, {"paso": 8, "estado": "SALTADO"}
        
        return df, {
            "paso": 8,
            "descripcion": "Revisar fecha nacimiento",
            "estado": "EJECUTADO",
            "accion": "Preparar para paso 9"
        }
    
    def _paso9_depurar_repetidos_nombre(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """PASO 9: Depurar repetidos por nombre+fecha nacimiento"""
        if '_nombre_ape_temp' not in df.columns:
            return df, {"paso": 9, "estado": "SALTADO"}
        
        col_fec_nac = self.columnas_detectadas.get('fecha_nto')
        
        if not col_fec_nac:
            # Limpiar columna temporal
            df = df.drop(columns=['_nombre_ape_temp'])
            return df, {"paso": 9, "estado": "SALTADO"}

        filas_antes = len(df)
        indices_mantener = set(df.index)

        # Repetidos por nombre + fecha nacimiento
        grupos_rep = df.groupby(['_nombre_ape_temp', col_fec_nac], dropna=False)
        grupos_trabajados = 0
        for _, grupo_df in grupos_rep:
            if len(grupo_df) <= 1:
                continue
            grupos_trabajados += 1
            idx_keep = self._seleccionar_mejor_registro(grupo_df)
            for idx in grupo_df.index:
                if idx != idx_keep and idx in indices_mantener:
                    indices_mantener.remove(idx)

        df = df.loc[sorted(indices_mantener)].copy().reset_index(drop=True)
        eliminadas = filas_antes - len(df)
        
        # Eliminar columna temporal
        if '_nombre_ape_temp' in df.columns:
            df = df.drop(columns=['_nombre_ape_temp'])
        
        return df, {
            "paso": 9,
            "descripcion": "Depurar repetidos por nombre+fecha",
            "estado": "EJECUTADO",
            "grupos_trabajados": grupos_trabajados,
            "eliminadas": eliminadas,
            "criterios": ["A", "B", "C", "D"]
        }
    
    def _paso10_cruce_muerte_materna(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """PASO 10: Cruce con evento 350 (muerte materna)"""
        col_num_ide = self.columnas_detectadas.get('num_ide')
        col_egreso = self.columnas_detectadas.get('egreso')
        col_fec_con = self.columnas_detectadas.get('fec_con')
        col_fec_egreso = self.columnas_detectadas.get('fec_egreso')

        if not col_num_ide or col_num_ide not in df.columns:
            return df, {
                "paso": 10,
                "descripcion": "Cruce con evento 350",
                "estado": "SALTADO",
                "razon": "No existe columna num_ide"
            }

        base_dir = Path(__file__).resolve().parents[1]
        candidatos = list((base_dir / 'data' / 'DEPURADO').glob('*_350_*.xlsx'))
        candidatos += list((base_dir / 'data' / 'DEPURADO').glob('*_350_*.xls'))
        candidatos += list((base_dir / 'data' / 'DEPURADO').glob('*_350_*.csv'))

        if not candidatos:
            return df, {
                "paso": 10,
                "descripcion": "Cruce con evento 350",
                "estado": "PENDIENTE",
                "razon": "No se encontró base depurada del evento 350"
            }

        base350 = max(candidatos, key=lambda p: p.stat().st_mtime)
        try:
            if base350.suffix.lower() in ['.xlsx', '.xls']:
                df350 = pd.read_excel(base350)
            else:
                df350 = pd.read_csv(base350, encoding='utf-8', sep=None, engine='python')
        except Exception as e:
            return df, {
                "paso": 10,
                "descripcion": "Cruce con evento 350",
                "estado": "ERROR",
                "razon": f"No se pudo leer base 350: {e}"
            }

        cols350 = {c.lower(): c for c in df350.columns}
        col_num_ide_350 = None
        for key in ['num_ide', 'numero_id', 'num_id']:
            for c_low, c_real in cols350.items():
                if key in c_low:
                    col_num_ide_350 = c_real
                    break
            if col_num_ide_350:
                break

        if not col_num_ide_350:
            return df, {
                "paso": 10,
                "descripcion": "Cruce con evento 350",
                "estado": "SALTADO",
                "razon": "La base 350 no contiene num_ide"
            }

        docs350 = set(df350[col_num_ide_350].dropna().astype(str).str.strip().unique().tolist())
        if not docs350:
            return df, {
                "paso": 10,
                "descripcion": "Cruce con evento 350",
                "estado": "EJECUTADO",
                "base_350": str(base350),
                "coincidencias": 0,
                "eliminadas_ajuste6": 0
            }

        df_work = df.copy()
        doc_series = df_work[col_num_ide].astype(str).str.strip()
        mask_match = doc_series.isin(docs350)
        coincidencias = int(mask_match.sum())

        indices_eliminar = set()
        if coincidencias > 0:
            grupos = df_work[mask_match].groupby(col_num_ide)
            for _, grupo in grupos:
                # Caso inicial: sin egreso a casa -> ajuste 6
                if len(grupo) == 1:
                    idx = grupo.index[0]
                    if col_egreso and col_egreso in grupo.columns and not self._value_is_yes(grupo.iloc[0][col_egreso]):
                        indices_eliminar.add(idx)
                    continue

                # Caso reingreso: >=7 dias tras egreso previo -> descartar registro de reingreso
                if col_fec_con and col_fec_egreso and col_fec_con in grupo.columns and col_fec_egreso in grupo.columns:
                    g = grupo.copy()
                    g['_fc'] = pd.to_datetime(g[col_fec_con], errors='coerce', dayfirst=True)
                    g['_fe'] = pd.to_datetime(g[col_fec_egreso], errors='coerce', dayfirst=True)
                    g = g.sort_values('_fc')
                    for i in range(1, len(g)):
                        prev = g.iloc[i - 1]
                        cur = g.iloc[i]
                        if pd.notna(prev['_fe']) and pd.notna(cur['_fc']) and (cur['_fc'] - prev['_fe']).days >= 7:
                            indices_eliminar.add(cur.name)

        if indices_eliminar:
            df_work = df_work.drop(index=sorted(indices_eliminar)).reset_index(drop=True)

        return df_work, {
            "paso": 10,
            "descripcion": "Cruce con evento 350",
            "estado": "EJECUTADO",
            "base_350": str(base350),
            "coincidencias": coincidencias,
            "eliminadas_ajuste6": len(indices_eliminar)
        }


def obtener_gestor_depuracion(filter_only_risaralda: bool = False):
    """Retorna instancia del depurador de eventos"""
    return Depuracion549(filter_only_risaralda=filter_only_risaralda)


if __name__ == "__main__":
    print("Modulo depuracion_evento_549 cargado correctamente")
