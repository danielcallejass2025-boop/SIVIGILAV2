"""
scripts/detector_evento.py
Módulo para detectar el código del evento epidemiológico de un archivo
Identifica la columna de evento y obtiene información de la base de datos
"""

import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from scripts.utils import Logger, ConfigManager, DetectorColumnas


class DetectorEvento:
    """
    Detecta automáticamente el código y tipo de evento en un dataframe
    Busca la columna de código de evento y la mapea a la base de datos interna
    """
    
    def __init__(self):
        self.logger = Logger()
        self.config = ConfigManager()
        self.detector_col = DetectorColumnas()
    
    def detectar_columna_codigo_evento(self, df: pd.DataFrame) -> Optional[str]:
        """
        Detecta la columna que contiene el código del evento
        Busca entre sinónimos comunes de código de evento
        
        Args:
            df: Dataframe a analizar
            
        Returns:
            Nombre de la columna detectada o None
        """
        sinonimos_evento = [
            "codigo_evento", "cod_evento", "id_evento", "evento_cod",
            "codigo", "event_code", "cod_ev"
        ]
        
        columnas_df = df.columns.tolist()
        
        for sinonimo in sinonimos_evento:
            columna = self.detector_col.detectar_columna(sinonimo, columnas_df, umbral=70)
            if columna:
                self.logger.debug(f"Columna de evento detectada: {columna}")
                return columna
        
        self.logger.warning("No se detectó columna de código de evento")
        return None
    
    def extraer_codigos_evento(self, df: pd.DataFrame, columna_evento: str) -> Dict[int, int]:
        """
        Extrae los códigos de evento únicos del dataframe y sus frecuencias
        
        Args:
            df: Dataframe
            columna_evento: Nombre de la columna con código de evento
            
        Returns:
            Diccionario {codigo: frecuencia}
        """
        if columna_evento not in df.columns:
            self.logger.error(f"Columna {columna_evento} no existe en el dataframe")
            return {}
        
        # Convertir a numérico si es posible
        try:
            codigos = pd.to_numeric(df[columna_evento], errors='coerce').dropna().astype(int)
        except Exception as e:
            self.logger.warning(f"Error convirtiendo códigos a int: {e}")
            codigos = df[columna_evento].dropna()
        
        # Contar frecuencias
        frecuencias = codigos.value_counts().to_dict()
        
        self.logger.info(f"Códigos de evento encontrados: {frecuencias}")
        
        return frecuencias
    
    def detectar_evento_predominante(self, df: pd.DataFrame, columna_evento: str) -> Tuple[Optional[int], Dict]:
        """
        Detecta el evento predominante en el dataframe
        
        Args:
            df: Dataframe
            columna_evento: Nombre de la columna con código de evento
            
        Returns:
            Tupla (codigo_evento, diccionario_info)
        """
        frecuencias = self.extraer_codigos_evento(df, columna_evento)
        
        if not frecuencias:
            self.logger.error("No se encontraron códigos de evento")
            return None, {}
        
        # El evento predominante es el más frecuente
        codigo_predominante = max(frecuencias, key=frecuencias.get)
        frecuencia = frecuencias[codigo_predominante]
        
        info_evento = self.config.obtener_evento(codigo_predominante)
        nombre_evento = info_evento.get("nombre", "Desconocido") if info_evento else "Desconocido"
        
        reporte = {
            "codigo": codigo_predominante,
            "nombre": nombre_evento,
            "frecuencia": frecuencia,
            "porcentaje_del_total": round((frecuencia / len(df)) * 100, 2),
            "otros_codigos": {k: v for k, v in frecuencias.items() if k != codigo_predominante}
        }
        
        self.logger.info(f"Evento predominante: {codigo_predominante} ({nombre_evento})")
        
        return codigo_predominante, reporte
    
    def detectar_todos_eventos_en_archivo(self, df: pd.DataFrame, columna_evento: str) -> Dict[int, Dict[str, Any]]:
        """
        Detecta TODOS los eventos presentes en el archivo
        
        Args:
            df: Dataframe
            columna_evento: Nombre de la columna con código de evento
            
        Returns:
            Diccionario {codigo: {info_evento, frecuencia, porcentaje}}
        """
        frecuencias = self.extraer_codigos_evento(df, columna_evento)
        resultado = {}
        
        for codigo, frecuencia in frecuencias.items():
            info = self.config.obtener_evento(codigo)
            resultado[codigo] = {
                "nombre": info.get("nombre", "Desconocido") if info else "Desconocido",
                "frecuencia": frecuencia,
                "porcentaje": round((frecuencia / len(df)) * 100, 2)
            }
        
        self.logger.info(f"Eventos en archivo: {list(resultado.keys())}")
        
        return resultado
    
    def archivos_mixtos_p(self, df: pd.DataFrame, columna_evento: str, umbral_min: float = 80) -> bool:
        """
        Determina si el archivo contiene múltiples eventos significativos
        
        Args:
            df: Dataframe
            columna_evento: Columna con código de evento
            umbral_min: Porcentaje mínimo para considerar "significativo"
            
        Returns:
            True si hay múltiples eventos significativos
        """
        eventos = self.detectar_todos_eventos_en_archivo(df, columna_evento)
        
        eventos_sig = [e for e in eventos.values() if e["porcentaje"] >= (100 - umbral_min)]
        
        return len(eventos_sig) > 1
    
    def dividir_por_evento(self, df: pd.DataFrame, columna_evento: str) -> Dict[int, pd.DataFrame]:
        """
        Divide un dataframe por código de evento
        Útil cuando el archivo contiene múltiples eventos mezclados
        
        Args:
            df: Dataframe a dividir
            columna_evento: Columna con código de evento
            
        Returns:
            Diccionario {codigo_evento: dataframe_subconjunto}
        """
        try:
            # Convertir a numérico
            df_temp = df.copy()
            df_temp["_codigo_temp"] = pd.to_numeric(df_temp[columna_evento], errors='coerce')
            df_temp = df_temp.dropna(subset=["_codigo_temp"])
            df_temp["_codigo_temp"] = df_temp["_codigo_temp"].astype(int)
            
            # Dividir por evento
            resultado = {}
            for codigo in df_temp["_codigo_temp"].unique():
                subset = df_temp[df_temp["_codigo_temp"] == codigo].drop(columns=["_codigo_temp"])
                resultado[codigo] = subset
            
            self.logger.info(f"Archivo dividido en {len(resultado)} grupos por evento")
            
            return resultado
            
        except Exception as e:
            self.logger.error(f"Error dividiendo archivo por evento: {e}")
            return {}
    
    def detectar_completo(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Realiza detección completa del evento en un archivo
        Ejecuta todos los pasos de análisis
        
        Args:
            df: Dataframe a analizar
            
        Returns:
            Reporte completo de detección
        """
        reporte = {
            "exitoso": False,
            "columna_evento": None,
            "evento_predominante": None,
            "nombre_evento": None,
            "eventos_presentes": {},
            "es_archivo_mixto": False,
            "total_filas": len(df),
            "mensajes": []
        }
        
        # Paso 1: Detectar columna de evento
        columna = self.detectar_columna_codigo_evento(df)
        if not columna:
            reporte["mensajes"].append("No se encontró columna de código de evento")
            return reporte
        
        reporte["columna_evento"] = columna
        
        # Paso 2: Detectar evento predominante
        codigo, info = self.detectar_evento_predominante(df, columna)
        if not codigo:
            reporte["mensajes"].append("No se pudo detectar evento predominante")
            return reporte
        
        reporte["evento_predominante"] = codigo
        reporte["nombre_evento"] = info.get("nombre")
        reporte["eventos_presentes"] = self.detectar_todos_eventos_en_archivo(df, columna)
        reporte["es_archivo_mixto"] = self.archivos_mixtos_p(df, columna)
        reporte["exitoso"] = True
        
        if reporte["es_archivo_mixto"]:
            reporte["mensajes"].append(f"Archivo contiene múltiples eventos. Predominante: {codigo}")
        
        return reporte


if __name__ == "__main__":
    print("=== PRUEBA DEL MÓDULO DETECTOR_EVENTO ===")
    
    detector = DetectorEvento()
    print("Detector de evento inicializado")
