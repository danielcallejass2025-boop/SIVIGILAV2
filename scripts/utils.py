"""
scripts/utils.py
Módulo de utilidades y funciones reutilizables del sistema SIVIGILA
Incluye: logging, configuración, normalización de datos, detección de columnas
"""

import logging
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any
import pandas as pd
import numpy as np
from fuzzywuzzy import fuzz
from config.settings import Settings
import sys


# ========================================
# CONFIGURACIÓN DEL LOGGING
# ========================================

class Logger:
    """
    Gestor centralizado de logging del sistema SIVIGILA
    Registra eventos en archivo y consola con formato consistente
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._inicializar()
        return cls._instance
    
    def _inicializar(self):
        """Inicializa el logger con configuración estándar"""
        self.settings = Settings()
        
        # Asegurar que el directorio de logs existe
        self.settings.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Configurar logger principal
        self.logger = logging.getLogger("SIVIGILA")
        self.logger.setLevel(getattr(logging, self.settings.LOG_LEVEL))
        
        # Limpiar handlers existentes
        self.logger.handlers.clear()
        
        # Formato de log
        log_format = logging.Formatter(
            '%(asctime)s - [%(levelname)s] - %(name)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Handler para archivo
        try:
            file_handler = logging.FileHandler(self.settings.LOG_FILE, encoding='utf-8')
            file_handler.setLevel(getattr(logging, self.settings.LOG_LEVEL))
            file_handler.setFormatter(log_format)
            self.logger.addHandler(file_handler)
        except Exception as e:
            print(f"Error creando handler de archivo: {e}")
        
        # Handler para consola (UTF-8 para soportar emojis en Windows)
        import io
        stream = sys.stdout
        if hasattr(stream, 'buffer') and getattr(stream, 'encoding', '') != 'utf-8':
            stream = io.TextIOWrapper(stream.buffer, encoding='utf-8', errors='replace', line_buffering=True)
        console_handler = logging.StreamHandler(stream)
        console_handler.setLevel(getattr(logging, self.settings.LOG_LEVEL))
        console_handler.setFormatter(log_format)
        self.logger.addHandler(console_handler)
    
    def debug(self, mensaje: str):
        self.logger.debug(mensaje)
    
    def info(self, mensaje: str):
        self.logger.info(mensaje)
    
    def warning(self, mensaje: str):
        self.logger.warning(mensaje)
    
    def error(self, mensaje: str):
        self.logger.error(mensaje)
    
    def critical(self, mensaje: str):
        self.logger.critical(mensaje)


# ========================================
# GESTOR DE CONFIGURACIÓN
# ========================================

class ConfigManager:
    """
    Gestor de archivos de configuración JSON
    Lee eventos.json y proporciona acceso a la base de datos de eventos
    """
    
    def __init__(self, config_path: str = "config/eventos.json"):
        self.logger = Logger()
        self.config_path = Path(config_path)
        
        # Si la ruta no es absoluta, hacerla relativa al proyecto
        if not self.config_path.is_absolute():
            self.config_path = Settings().BASE_DIR / self.config_path
        
        self.eventos = []
        self.codigo_a_evento = {}
        self._cargar_eventos()
    
    def _cargar_eventos(self):
        """Carga la lista de eventos desde el archivo JSON"""
        try:
            if not self.config_path.exists():
                self.logger.error(f"Archivo de configuración no encontrado: {self.config_path}")
                return
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.eventos = json.load(f)
            
            # Construir mapeo de código -> evento
            self.codigo_a_evento = {}
            for evento in self.eventos:
                codigos = evento.get("codigo", [])
                
                # Manejar tanto eventos con código simple como listas
                if isinstance(codigos, int):
                    codigos = [codigos]
                elif isinstance(codigos, list):
                    pass
                
                for codigo in codigos:
                    self.codigo_a_evento[codigo] = evento
            
            self.logger.info(f"Cargados {len(self.eventos)} eventos epidemiológicos")
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Error al parsear JSON de eventos: {e}")
        except Exception as e:
            self.logger.error(f"Error al cargar configuración de eventos: {e}")
    
    def obtener_evento(self, codigo: int) -> Optional[Dict[str, Any]]:
        """
        Obtiene información de un evento por su código
        
        Args:
            codigo: Código del evento
            
        Returns:
            Dict con info del evento o None si no existe
        """
        return self.codigo_a_evento.get(codigo)
    
    def obtener_nombre_evento(self, codigo: int) -> str:
        """Obtiene el nombre de un evento por su código"""
        evento = self.obtener_evento(codigo)
        return evento.get("nombre", "Evento desconocido") if evento else "Evento desconocido"
    
    def listar_codigos_evento(self) -> List[int]:
        """Retorna lista de todos los códigos de evento disponibles"""
        return sorted(list(self.codigo_a_evento.keys()))


# ========================================
# DETECCIÓN Y NORMALIZACIÓN DE COLUMNAS
# ========================================

class DetectorColumnas:
    """
    Sistema inteligente para detectar y normalizar nombres de columnas
    Usa fuzzy matching para encontrar columnas similares aunque cambien de nombre
    """
    
    def __init__(self):
        self.logger = Logger()
        
        # Diccionario de sinónimos para variables clave
        self.sinonimos = {
            "codigo_evento": [
                "codigo_evento", "cod_evento", "id_evento", "evento_cod",
                "codigo", "event_code", "cod_ev", "id_ev"
            ],
            "primer_nombre": [
                "primer_nombre", "pri_nom", "nombre1", "first_name",
                "primero_nombre", "nompri"
            ],
            "segundo_nombre": [
                "segundo_nombre", "seg_nom", "nombre2", "second_name",
                "segundo_name", "nomseg"
            ],
            "primer_apellido": [
                "primer_apellido", "pri_ape", "apellido1", "last_name",
                "apellido_principal", "apepri"
            ],
            "segundo_apellido": [
                "segundo_apellido", "seg_ape", "apellido2", "second_last_name",
                "apellido_secundario", "apeseg"
            ],
            "numero_documento": [
                "numero_documento", "num_ide", "documento", "identificacion",
                "cedula", "id_number", "numero_id", "numid", "ndoc"
            ],
            "tipo_documento": [
                "tipo_documento", "tip_ide", "tipdoc", "doc_type",
                "tipo_id", "id_type"
            ],
            "fecha_nacimiento": [
                "fecha_nacimiento", "fec_nac", "nacimiento", "date_of_birth",
                "fecha_nac", "dob", "fec_nacimiento"
            ],
            "fecha_egreso": [
                "fecha_egreso", "fec_egreso", "egreso_fecha", "discharge_date",
                "fecha_salida", "exit_date"
            ],
            "municipio": [
                "municipio", "nom_mpio", "municipio_residencia", "city",
                "municipio_notificacion", "mpio", "mun"
            ],
            "departamento": [
                "departamento", "dpto", "department", "provincia",
                "depto", "dept"
            ],
            "sexo": [
                "sexo", "genero", "gender", "sex", "sexo_afiliado", "gen"
            ],
            "edad": [
                "edad", "edad_anos", "age", "age_years", "ed", "edad_en_anos"
            ],
            "edad_meses": [
                "edad_meses", "age_months"
            ],
            "fecha_notificacion": [
                "fecha_notificacion", "fec_not", "notification_date", "fecha",
                "fec_notif", "date_notified", "fecha_registro"
            ],
            "institucion": [
                "institucion", "ips", "upgd", "prestador", "institution",
                "health_facility", "inst"
            ]
        }
    
    def normalizar_nombre_columna(self, nombre: str) -> str:
        """
        Normaliza un nombre de columna eliminando tildes, espacios, caracteres especiales
        
        Args:
            nombre: Nombre original de la columna
            
        Returns:
            Nombre normalizado
        """
        import unicodedata
        
        # Convertir a minúsculas
        nombre = nombre.lower().strip()
        
        # Eliminar tildes y acentos
        nombre = ''.join(
            c for c in unicodedata.normalize('NFD', nombre)
            if unicodedata.category(c) != 'Mn'
        )
        
        # Reemplazar espacios y caracteres especiales con guion bajo
        nombre = ''.join(c if c.isalnum() else '_' for c in nombre)
        
        # Eliminar guiones bajos duplicados
        while '__' in nombre:
            nombre = nombre.replace('__', '_')
        
        return nombre.strip('_')
    
    def detectar_columna(self, nombre_buscado: str, columnas_disponibles: List[str],
                        umbral: int = 70) -> Optional[str]:
        """
        Detecta una columna en la lista disponible usando fuzzy matching
        
        Args:
            nombre_buscado: Nombre de la columna a buscar
            columnas_disponibles: Lista de columnas disponibles en el dataframe
            umbral: Porcentaje mínimo de similitud (0-100)
            
        Returns:
            Nombre de la columna más similar o None
        """
        mejores = []
        
        nombre_buscado_norm = self.normalizar_nombre_columna(nombre_buscado)
        
        for col in columnas_disponibles:
            col_norm = self.normalizar_nombre_columna(col)
            
            # Comparación exacta después de normalizar
            if col_norm == nombre_buscado_norm:
                return col
            
            # Fuzzy matching
            similitud = fuzz.token_sort_ratio(nombre_buscado_norm, col_norm)
            if similitud >= umbral:
                mejores.append((col, similitud))
        
        if mejores:
            # Retornar la columna con mayor similitud
            return sorted(mejores, key=lambda x: x[1], reverse=True)[0][0]
        
        return None
    
    def detectar_columnas_evento_y_criticas(self, df: pd.DataFrame,
                                            columnas_criticas: List[str] = None) -> Dict[str, Optional[str]]:
        """
        Detecta automáticamente las columnas clave en un dataframe
        
        Args:
            df: Dataframe a analizar
            columnas_criticas: Lista de nombres clave a buscar
            
        Returns:
            Diccionario con {nombre_clave: columna_detectada_o_none}
        """
        if columnas_criticas is None:
            columnas_criticas = list(self.sinonimos.keys())
        
        resultado = {}
        columnas_df = df.columns.tolist()
        
        for clave in columnas_criticas:
            sinonimos_clave = self.sinonimos.get(clave, [clave])
            
            # Buscar la mejor coincidencia
            mejor_columna = None
            for sinonimo in sinonimos_clave:
                columna = self.detectar_columna(sinonimo, columnas_df, umbral=70)
                if columna:
                    mejor_columna = columna
                    break
            
            resultado[clave] = mejor_columna
        
        return resultado


# ========================================
# VALIDADOR DE CALIDAD DE DATOS
# ========================================

class ValidadorCalidad:
    """
    Valida la calidad de datos en un dataframe
    Reporta problemas encontrados y sugerencias de mejora
    """
    
    def __init__(self):
        self.logger = Logger()
    
    def validar(self, df: pd.DataFrame, nombre_archivo: str = "datos") -> Dict[str, Any]:
        """
        Realiza validación completa de un dataframe
        
        Args:
            df: Dataframe a validar
            nombre_archivo: Nombre para reportes
            
        Returns:
            Diccionario con resultados de validación
        """
        
        reporte = {
            "archivo": nombre_archivo,
            "fecha_validacion": datetime.now().isoformat(),
            "total_filas": len(df),
            "total_columnas": len(df.columns),
            "filas_completamente_vacias": 0,
            "columas_completamente_vacias": [],
            "columnas_problematicas": {},
            "duplicados": 0,
            "calidad_general": "BUENA",
            "recomendaciones": []
        }
        
        # Filas completamente vacías
        reporte["filas_completamente_vacias"] = df.isna().all(axis=1).sum()
        
        # Columnas completamente vacías
        for col in df.columns:
            if df[col].isna().all():
                reporte["columas_completamente_vacias"].append(col)
        
        # Analizar cada columna
        for col in df.columns:
            nulos = df[col].isna().sum()
            porcentaje_nulos = (nulos / len(df)) * 100
            
            if porcentaje_nulos > 0:
                reporte["columnas_problematicas"][col] = {
                    "nulos": nulos,
                    "porcentaje_nulo": round(porcentaje_nulos, 2)
                }
        
        # Duplicados exactos
        reporte["duplicados"] = df.duplicated().sum()
        
        # Determinar calidad general
        if reporte["duplicados"] > 0 or len(reporte["columas_completamente_vacias"]) > 0:
            reporte["calidad_general"] = "MEDIA"
        
        if reporte["filas_completamente_vacias"] > len(df) * 0.1:
            reporte["calidad_general"] = "BAJA"
        
        # Recomendaciones
        if reporte["filas_completamente_vacias"] > 0:
            reporte["recomendaciones"].append(
                f"Eliminar {reporte['filas_completamente_vacias']} filas completamente vacías"
            )
        
        if reporte["columas_completamente_vacias"]:
            reporte["recomendaciones"].append(
                f"Considerar eliminar columnas vacías: {reporte['columas_completamente_vacias']}"
            )
        
        if reporte["duplicados"] > 0:
            reporte["recomendaciones"].append(
                f"Se encontraron {reporte['duplicados']} filas duplicadas"
            )
        
        return reporte


# ========================================
# FUNCIONES AUXILIARES
# ========================================

def limpiar_nulos_inteligente(df: pd.DataFrame, estrategia: str = "eliminar") -> Tuple[pd.DataFrame, Dict]:
    """
    Limpia valores nulos según estrategia especificada
    
    Args:
        df: Dataframe
        estrategia: "eliminar", "media", "moda"
        
    Returns:
        Tupla (df_limpio, reporte_cambios)
    """
    logger = Logger()
    reporte = {
        "strategy": estrategia,
        "filas_eliminadas": 0,
        "celdas_imputadas": 0
    }
    
    filas_antes = len(df)
    
    if estrategia == "eliminar":
        # Eliminar filas con valores faltantes
        df_limpio = df.dropna()
        reporte["filas_eliminadas"] = filas_antes - len(df_limpio)
    
    elif estrategia == "media":
        # Imputar con media (solo columnas numéricas)
        df_limpio = df.copy()
        for col in df_limpio.select_dtypes(include=[np.number]).columns:
            if df_limpio[col].isna().any():
                media = df_limpio[col].mean()
                df_limpio[col].fillna(media, inplace=True)
                reporte["celdas_imputadas"] += df[col].isna().sum()
    
    elif estrategia == "moda":
        # Imputar con moda
        df_limpio = df.copy()
        for col in df_limpio.columns:
            if df_limpio[col].isna().any():
                moda = df_limpio[col].mode()
                if len(moda) > 0:
                    df_limpio[col].fillna(moda[0], inplace=True)
                    reporte["celdas_imputadas"] += df[col].isna().sum()
    
    else:
        df_limpio = df.copy()
    
    logger.info(f"Limpieza de nulos [{estrategia}]: {reporte}")
    return df_limpio, reporte


def crear_resumen_procesamiento(
    archivo_entrada: str,
    evento_codigo: int,
    evento_nombre: str,
    filas_entrada: int,
    filas_salida: int,
    columnas_originales: int,
    cambios_aplicados: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Crea un resumen detallado del procesamiento de un archivo
    
    Args:
        archivo_entrada: Nombre del archivo procesado
        evento_codigo: Código del evento
        evento_nombre: Nombre del evento
        filas_entrada: Cantidad de filas antes de procesar
        filas_salida: Cantidad de filas después de procesar
        columnas_originales: Cantidad de columnas originales
        cambios_aplicados: Diccionario con cambios realizados
        
    Returns:
        Diccionario con resumen completo
    """
    return {
        "timestamp": datetime.now().isoformat(),
        "archivo_entrada": archivo_entrada,
        "evento": {
            "codigo": evento_codigo,
            "nombre": evento_nombre
        },
        "estadisticas": {
            "filas_entrada": filas_entrada,
            "filas_salida": filas_salida,
            "filas_eliminadas": filas_entrada - filas_salida,
            "porcentaje_retenido": round((filas_salida / filas_entrada) * 100, 2) if filas_entrada > 0 else 0,
            "columnas_originales": columnas_originales
        },
        "cambios": cambios_aplicados,
        "exit_status": "EXITOSO" if filas_salida > 0 else "FALLIDO - SIN DATOS"
    }


if __name__ == "__main__":
    # Test del módulo
    print("=== PRUEBA DEL MÓDULO UTILS ===")
    
    logger = Logger()
    logger.info("Logger inicializado correctamente")
    
    config = ConfigManager()
    evento = config.obtener_evento(549)
    print(f"\nEvento 549: {evento}")
    
    detector = DetectorColumnas()
    print(f"\nNormalización de columna: {detector.normalizar_nombre_columna('Número_Identificación')}")
