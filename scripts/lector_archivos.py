"""
scripts/lector_archivos.py
Módulo para lectura universal de archivos epidemiológicos
Soporta: xlsx, xls, xlsm, csv, ods
Detecta automáticamente formato, codificación, hoja principal
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Tuple, Optional, Dict, List, Any
import chardet
import warnings
from scripts.utils import Logger, DetectorColumnas

warnings.filterwarnings('ignore')


class LectorArchivos:
    """
    Lector universal de archivos tabulares para SIVIGILA
    Maneja múltiples formatos y detecta automáticamente características del archivo
    """
    
    def __init__(self):
        self.logger = Logger()
        self.detector_col = DetectorColumnas()
        
        # Formatos soportados
        self.formatos_soportados = ['.xlsx', '.xls', '.xlsm', '.csv', '.ods']
    
    def detectar_formato(self, ruta_archivo: str) -> Optional[str]:
        """
        Detecta el formato de un archivo por su extensión
        
        Args:
            ruta_archivo: Ruta al archivo
            
        Returns:
            Extensión del archivo o None si no es soportado
        """
        ruta = Path(ruta_archivo)
        extension = ruta.suffix.lower()
        
        if extension in self.formatos_soportados:
            return extension
        
        self.logger.warning(f"Formato no soportado: {extension}")
        return None
    
    def detectar_codificacion(self, ruta_archivo: str) -> str:
        """
        Detecta la codificación de un archivo de texto
        Usa chardet con fallbacks robustos a encodings comunes
        
        Args:
            ruta_archivo: Ruta al archivo
            
        Returns:
            Nombre de la codificación detectada
        """
        # Lista de encodings a probar en orden de probabilidad
        encodings_fallback = [
            'utf-8',           # Más común en archivos modernos
            'utf-16',          # Posible en algunos sistemas
            'latin-1',         # ISO-8859-1, común en Europa
            'cp1252',          # Windows-1252, común en Windows Latinoamérica
            'iso-8859-1',      # Similar a latin-1
            'ascii',           # ASCII puro
        ]
        
        try:
            with open(ruta_archivo, 'rb') as f:
                contenido_raw = f.read(50000)  # Leer primeros 50KB
            
            # Intentar detectar con chardet
            resultado = chardet.detect(contenido_raw)
            encoding = resultado.get('encoding', 'utf-8')
            confianza = resultado.get('confidence', 0)
            
            # Si chardet detectó algo con confianza razonable, verificar que es válido
            if encoding and confianza > 0.7:
                try:
                    # Verificar que el encoding puede decodificar el contenido
                    contenido_raw.decode(encoding)
                    self.logger.debug(f"Codificación detectada por chardet: {encoding} (confianza: {confianza:.1%})")
                    return encoding
                except (UnicodeDecodeError, LookupError):
                    # Si falla, continuar con fallbacks
                    self.logger.debug(f"Encoding {encoding} detectado pero falla al decodificar, intentando fallbacks")
            
            # Fallback: intentar encodings comunes
            for enc in encodings_fallback:
                try:
                    contenido_raw.decode(enc)
                    self.logger.debug(f"Codificación detectada (fallback): {enc}")
                    return enc
                except (UnicodeDecodeError, LookupError):
                    continue
            
            # Si nada funciona, usar UTF-8 por defecto
            self.logger.warning(f"No se pudo detectar encoding validable, usando UTF-8 por defecto")
            return 'utf-8'
            
        except Exception as e:
            self.logger.warning(f"Error detectando codificación, usando UTF-8: {e}")
            return 'utf-8'
    
    def detectar_separador_csv(self, ruta_archivo: str, encoding: str = 'utf-8') -> str:
        """
        Detecta el separador de un archivo CSV
        Prueba: coma, punto y coma, tab
        
        Args:
            ruta_archivo: Ruta al archivo
            encoding: Codificación del archivo
            
        Returns:
            Separador detectado (defecto: ',')
        """
        separadores_a_probar = [',', ';', '\t', '|']
        encodings_fallback = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
        
        try:
            # Intentar con el encoding proporcionado
            try:
                with open(ruta_archivo, 'r', encoding=encoding) as f:
                    primera_linea = f.readline()
            except (UnicodeDecodeError, LookupError):
                # Si falla, intentar con fallbacks
                self.logger.debug(f"Encoding {encoding} falló en detectar_separador, intentando fallbacks")
                primera_linea = None
                
                for enc in encodings_fallback:
                    if enc == encoding:
                        continue
                    try:
                        with open(ruta_archivo, 'r', encoding=enc) as f:
                            primera_linea = f.readline()
                        break
                    except (UnicodeDecodeError, LookupError):
                        continue
                
                if primera_linea is None:
                    self.logger.warning(f"No se pudo leer archivo con ningún encoding, usando separador defecto")
                    return ','
            
            for sep in separadores_a_probar:
                if sep in primera_linea:
                    conteo = primera_linea.count(sep)
                    # Si hay más de 2 instancias, probablemente sea el separador
                    if conteo >= 2:
                        self.logger.debug(f"Separador CSV detectado: {repr(sep)}")
                        return sep
            
            # Por defecto devolver coma
            return ','
            
        except Exception as e:
            self.logger.warning(f"Error detectando separador CSV: {e}")
            return ','
    
    def leer_excel(self, ruta_archivo: str, leer_todas_hojas: bool = False) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Lee un archivo Excel (.xlsx, .xls, .xlsm)
        
        Args:
            ruta_archivo: Ruta al archivo
            leer_todas_hojas: Si True, leer todas las hojas
            
        Returns:
            Tupla (dataframe, diccionario_metadatos)
        """
        metadatos = {
            "formato": "excel",
            "ruta": str(ruta_archivo),
            "hojas_disponibles": [],
            "hoja_seleccionada": None,
            "filas_leidas": 0
        }
        
        try:
            # Leer todas las hojas primero para detectar la principal
            excel_file = pd.ExcelFile(ruta_archivo)
            hojas = excel_file.sheet_names
            metadatos["hojas_disponibles"] = hojas
            
            self.logger.info(f"Hojas encontradas en Excel: {hojas}")
            
            if leer_todas_hojas:
                # Concatenar todas las hojas
                dfs = {}
                for hoja in hojas:
                    df_temp = pd.read_excel(ruta_archivo, sheet_name=hoja)
                    dfs[hoja] = df_temp
                
                # Seleccionar la hoja con más datos
                hoja_principal = max(dfs.keys(), key=lambda x: len(dfs[x]))
                df = dfs[hoja_principal]
                metadatos["hoja_seleccionada"] = hoja_principal
                
            else:
                # Leer solo la hoja principal (la que contiene más datos)
                hojas_con_datos = {hoja: pd.read_excel(ruta_archivo, sheet_name=hoja).shape[0]
                                   for hoja in hojas}
                hoja_principal = max(hojas_con_datos, key=hojas_con_datos.get)
                df = pd.read_excel(ruta_archivo, sheet_name=hoja_principal)
                metadatos["hoja_seleccionada"] = hoja_principal
            
            metadatos["filas_leidas"] = len(df)
            self.logger.info(f"Archivo Excel leído: {len(df)} filas, {len(df.columns)} columnas")
            
            return df, metadatos
            
        except Exception as e:
            self.logger.error(f"Error leyendo Excel: {e}")
            raise
    
    def leer_csv(self, ruta_archivo: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Lee un archivo CSV con detección automática de codificación y separador
        
        Args:
            ruta_archivo: Ruta al archivo
            
        Returns:
            Tupla (dataframe, diccionario_metadatos)
        """
        metadatos = {
            "formato": "csv",
            "ruta": str(ruta_archivo),
            "codificacion": None,
            "separador": None,
            "filas_leidas": 0
        }
        
        try:
            # Detectar codificación y separador
            encoding = self.detectar_codificacion(ruta_archivo)
            separador = self.detectar_separador_csv(ruta_archivo, encoding)
            
            metadatos["codificacion"] = encoding
            metadatos["separador"] = separador
            
            # Leer CSV con el encoding detectado
            try:
                df = pd.read_csv(
                    ruta_archivo,
                    sep=separador,
                    encoding=encoding,
                    low_memory=False
                )
            except (UnicodeDecodeError, LookupError) as e:
                # Si falla el encoding detectado, intentar con fallbacks
                self.logger.warning(f"Fallo con encoding {encoding}: {e}")
                self.logger.info(f"Intentando con encodings alternativos...")
                
                encodings_fallback = [
                    'utf-8', 'latin-1', 'cp1252', 'iso-8859-1', 'ascii', 'utf-16'
                ]
                
                df = None
                for enc in encodings_fallback:
                    if enc == encoding:  # Saltar el que ya falló
                        continue
                    
                    try:
                        self.logger.debug(f"Intentando con encoding: {enc}")
                        df = pd.read_csv(
                            ruta_archivo,
                            sep=separador,
                            encoding=enc,
                            low_memory=False,
                            on_bad_lines='skip'  # Saltar líneas problemáticas
                        )
                        self.logger.info(f"✅ Éxito con encoding: {enc}")
                        metadatos["codificacion"] = enc
                        break
                    except (UnicodeDecodeError, LookupError):
                        continue
                
                if df is None:
                    # Si ningún encoding funcionó, intentar una última vez con errores ignorados
                    self.logger.warning(f"Intentando lectura final con encoding errors='replace'")
                    df = pd.read_csv(
                        ruta_archivo,
                        sep=separador,
                        encoding='utf-8',
                        errors='replace',
                        low_memory=False,
                        on_bad_lines='skip'
                    )
                    metadatos["codificacion"] = "utf-8 (con reemplazo de caracteres)"
            
            metadatos["filas_leidas"] = len(df)
            self.logger.info(f"CSV leído: {len(df)} filas, {len(df.columns)} columnas (encoding: {metadatos['codificacion']})")
            
            return df, metadatos
            
        except Exception as e:
            self.logger.error(f"Error leyendo CSV: {e}")
            raise
    
    def leer_ods(self, ruta_archivo: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Lee un archivo ODS (OpenDocument Spreadsheet)
        
        Args:
            ruta_archivo: Ruta al archivo
            
        Returns:
            Tupla (dataframe, diccionario_metadatos)
        """
        metadatos = {
            "formato": "ods",
            "ruta": str(ruta_archivo),
            "filas_leidas": 0
        }
        
        try:
            df = pd.read_excel(ruta_archivo, engine='odf')
            metadatos["filas_leidas"] = len(df)
            self.logger.info(f"ODS leído: {len(df)} filas, {len(df.columns)} columnas")
            
            return df, metadatos
            
        except Exception as e:
            self.logger.error(f"Error leyendo ODS: {e}")
            raise
    
    def leer(self, ruta_archivo: str, leer_todas_hojas: bool = False) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
        """
        Lee un archivo universal detectando automáticamente su formato
        
        Args:
            ruta_archivo: Ruta al archivo
            leer_todas_hojas: Para Excel, si se leen todas las hojas
            
        Returns:
            Tupla (dataframe_o_none, diccionario_metadatos)
        """
        ruta = Path(ruta_archivo)
        
        if not ruta.exists():
            self.logger.error(f"Archivo no existe: {ruta_archivo}")
            return None, {"error": "Archivo no existe", "ruta": str(ruta)}
        
        formato = self.detectar_formato(ruta_archivo)
        
        if not formato:
            self.logger.error(f"Formato no soportado: {ruta_archivo}")
            return None, {"error": "Formato no soportado", "ruta": str(ruta)}
        
        try:
            if formato in ['.xlsx', '.xls', '.xlsm']:
                df, meta = self.leer_excel(ruta_archivo, leer_todas_hojas)
            elif formato == '.csv':
                df, meta = self.leer_csv(ruta_archivo)
            elif formato == '.ods':
                df, meta = self.leer_ods(ruta_archivo)
            else:
                return None, {"error": f"Formato no implementado: {formato}"}
            
            # Normalizar nombres de columnas
            df.columns = [self.detector_col.normalizar_nombre_columna(col) for col in df.columns]
            
            self.logger.info(f"Archivo leído exitosamente: {ruta_archivo}")
            return df, meta
            
        except Exception as e:
            self.logger.error(f"Error leyendo archivo {ruta_archivo}: {e}")
            return None, {"error": str(e), "ruta": str(ruta)}


class LectorArchivosCarpeta:
    """
    Lector de múltiples archivos desde una carpeta
    Procesa automáticamente todos los archivos soportados en una ubicación
    """
    
    def __init__(self, carpeta: str):
        self.logger = Logger()
        self.lector = LectorArchivos()
        self.carpeta = Path(carpeta)
    
    def listar_archivos_por_procesar(self) -> List[Path]:
        """
        Lista todos los archivos soportados en la carpeta
        
        Returns:
            Lista de Path a archivos para procesar
        """
        if not self.carpeta.exists():
            self.logger.warning(f"Carpeta no existe: {self.carpeta}")
            return []
        
        archivos = []
        for extension in self.lector.formatos_soportados:
            archivos.extend(self.carpeta.glob(f'*{extension}'))
        
        self.logger.info(f"Archivos encontrados para procesar: {len(archivos)}")
        return sorted(archivos)
    
    def leer_todos(self) -> Dict[str, Tuple[Optional[pd.DataFrame], Dict]]:
        """
        Lee todos los archivos de la carpeta
        
        Returns:
            Diccionario {nombre_archivo: (dataframe, metadatos)}
        """
        resultados = {}
        archivos = self.listar_archivos_por_procesar()
        
        for archivo in archivos:
            self.logger.info(f"Leyendo: {archivo.name}")
            df, meta = self.lector.leer(str(archivo))
            resultados[archivo.name] = (df, meta)
        
        return resultados


if __name__ == "__main__":
    # Test del módulo
    print("=== PRUEBA DEL MÓDULO LECTOR_ARCHIVOS ===")
    
    lector = LectorArchivos()
    print(f"Formatos soportados: {lector.formatos_soportados}")
