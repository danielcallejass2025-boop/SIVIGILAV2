"""
scripts/validador_calidad.py
Módulo de validación de calidad de datos
Genera reportes detallados sobre la calidad de los datos procesados
"""

import pandas as pd
from typing import Dict, Any, List
from datetime import datetime
from scripts.utils import Logger


class ValidadorCalidadAvanzado:
    """
    Validador avanzado de calidad de datos para archivos epidemiológicos
    Genera reportes detallados sobre completitud y consistencia
    """
    
    def __init__(self):
        self.logger = Logger()
    
    def generar_reporte_calidad(self, df: pd.DataFrame,
                               nombre_archivo: str = "archivo") -> Dict[str, Any]:
        """
        Genera un reporte completo de calidad del dataframe
        
        Args:
            df: Dataframe a analizar
            nombre_archivo: Nombre del archivo para reporte
            
        Returns:
            Diccionario con reporte detallado
        """
        
        reporte = {
            "timestamp": datetime.now().isoformat(),
            "archivo": nombre_archivo,
            "resumen_general": self._calcular_resumen_general(df),
            "completitud_columnas": self._analizar_completitud(df),
            "tipos_datos": self._analizar_tipos(df),
            "duplicados": self._analizar_duplicados(df),
            "anomalias": self._detectar_anomalias(df),
            "puntuacion_calidad": 0.0,
            "recomendaciones": []
        }
        
        # Calcular puntuación de calidad
        reporte["puntuacion_calidad"] = self._calcular_puntuacion(reporte)
        
        # Generar recomendaciones
        reporte["recomendaciones"] = self._generar_recomendaciones(reporte)
        
        return reporte
    
    def _calcular_resumen_general(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calcula estadísticas generales del dataframe"""
        return {
            "total_filas": len(df),
            "total_columnas": len(df.columns),
            "memoria_mb": df.memory_usage(deep=True).sum() / 1024 / 1024,
            "densidad_datos": round((1 - df.isna().sum().sum() / (len(df) * len(df.columns))) * 100, 2)
        }
    
    def _analizar_completitud(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analiza qué porcentaje de datos completos tiene cada columna"""
        resultado = {}
        
        for col in df.columns:
            nulos = df[col].isna().sum()
            porcentaje_completo = ((len(df) - nulos) / len(df) * 100) if len(df) > 0 else 0
            
            resultado[col] = {
                "valores_nulos": int(nulos),
                "porcentaje_nulos": round(100 - porcentaje_completo, 2),
                "porcentaje_completo": round(porcentaje_completo, 2),
                "estado": self._clasificar_completitud(porcentaje_completo)
            }
        
        return resultado
    
    def _clasificar_completitud(self, porcentaje: float) -> str:
        """Clasifica el nivel de completitud"""
        if porcentaje >= 95:
            return "EXCELENTE"
        elif porcentaje >= 80:
            return "BUENO"
        elif porcentaje >= 50:
            return "ACEPTABLE"
        else:
            return "DEFICIENTE"
    
    def _analizar_tipos(self, df: pd.DataFrame) -> Dict[str, str]:
        """Analiza los tipos de datos de cada columna"""
        resultado = {}
        for col in df.columns:
            resultado[col] = str(df[col].dtype)
        return resultado
    
    def _analizar_duplicados(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analiza filas duplicadas"""
        duplicados_exactos = df.duplicated().sum()
        duplicados_parciales = df.duplicated(keep=False).sum()
        
        return {
            "filas_duplicadas_exactas": int(duplicados_exactos),
            "filas_duplicadas_parciales": int(duplicados_parciales),
            "porcentaje_duplicados": round(
                (duplicados_exactos / len(df) * 100) if len(df) > 0 else 0, 2
            ),
            "estado": "OK" if duplicados_exactos == 0 else "ADVERTENCIA"
        }
    
    def _detectar_anomalias(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Detecta anomalías en los datos"""
        anomalias = []
        
        # Detectar columnas completamente vacías
        for col in df.columns:
            if df[col].isna().all():
                anomalias.append({
                    "tipo": "COLUMNA_VACIA",
                    "columna": col,
                    "descripcion": "Columna completamente vacía"
                })
        
        # Detectar columnas con un única valor
        for col in df.columns:
            valores_unicos = df[col].nunique()
            if valores_unicos == 1:
                anomalias.append({
                    "tipo": "COLUMNA_CONSTANTE",
                    "columna": col,
                    "valor": df[col].dropna().iloc[0] if len(df) > 0 else None,
                    "descripcion": "Columna contiene un único valor"
                })
        
        # Detectar inconsistencias de tipo
        columnas_numericas = df.select_dtypes(include=['int64', 'float64']).columns
        for col in columnas_numericas:
            # Buscar valores numéricos extremos
            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1
            limite_superior = Q3 + 1.5 * IQR
            limite_inferior = Q1 - 1.5 * IQR
            
            outliers = ((df[col] > limite_superior) | (df[col] < limite_inferior)).sum()
            if outliers > 0:
                anomalias.append({
                    "tipo": "OUTLIERS",
                    "columna": col,
                    "cantidad": int(outliers),
                    "descripcion": f"{outliers} valores outlier detectados"
                })
        
        return anomalias
    
    def _calcular_puntuacion(self, reporte: Dict[str, Any]) -> float:
        """Calcula una puntuación de calidad (0-100)"""
        puntuacion = 100.0
        
        # Restar por completitud deficiente
        completitud = reporte["completitud_columnas"]
        columnas_deficientes = sum(
            1 for col_info in completitud.values()
            if col_info["estado"] == "DEFICIENTE"
        )
        puntuacion -= columnas_deficientes * 5
        
        # Restar por duplicados
        if reporte["duplicados"]["estado"] == "ADVERTENCIA":
            puntuacion -= 10
        
        # Restar por anomalías
        anomalias = reporte["anomalias"]
        puntuacion -= len(anomalias) * 2
        
        return max(0, round(puntuacion, 2))
    
    def _generar_recomendaciones(self, reporte: Dict[str, Any]) -> List[str]:
        """Genera recomendaciones basadas en el análisis"""
        recomendaciones = []
        
        # Basadas en completitud
        completitud = reporte["completitud_columnas"]
        columnas_deficientes = [
            col for col, info in completitud.items()
            if info["estado"] == "DEFICIENTE"
        ]
        
        if columnas_deficientes:
            recomendaciones.append(
                f"Revisar completitud de columnas: {', '.join(columnas_deficientes[:3])}"
            )
        
        # Basadas en duplicados
        if reporte["duplicados"]["porcentaje_duplicados"] > 5:
            recomendaciones.append(
                f"Alto porcentaje de duplicados ({reporte['duplicados']['porcentaje_duplicados']}%). "
                f"Considere limpieza adicional"
            )
        
        # Basadas en anomalías
        anomalias_criticas = [
            a for a in reporte["anomalias"]
            if a["tipo"] in ["COLUMNA_VACIA", "COLUMNA_CONSTANTE"]
        ]
        
        if anomalias_criticas:
            recomendaciones.append(
                f"Se encontraron {len(anomalias_criticas)} columnas problemáticas"
            )
        
        # Basadas en puntuación
        if reporte["puntuacion_calidad"] < 50:
            recomendaciones.append("ALERTA: Calidad de datos baja. Revisar fuente de datos")
        
        # Genérica
        if not recomendaciones:
            recomendaciones.append("Datos en buen estado de calidad")
        
        return recomendaciones


def validar_archivo_salida(df: pd.DataFrame, nombre: str = "salida") -> Dict[str, Any]:
    """
    Valida un archivo de salida antes de guardarlo
    
    Args:
        df: Dataframe a validar
        nombre: Nombre del archivo
        
    Returns:
        Reporte de validación
    """
    validador = ValidadorCalidadAvanzado()
    return validador.generar_reporte_calidad(df, nombre)


if __name__ == "__main__":
    print("=== PRUEBA DEL MÓDULO VALIDADOR_CALIDAD ===")
    
    validador = ValidadorCalidadAvanzado()
    print("Validador de calidad inicializado")
