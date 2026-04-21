"""
scripts/gestor_salida.py
Módulo gestor de salida de archivos
Guarda archivos procesados en formatos especificados (xlsx, csv)
Maneja respaldos y movimiento de archivos
"""

import pandas as pd
import shutil
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
from config.settings import Settings
from scripts.utils import Logger


class GestorSalida:
    """
    Gestor centralizado de salida de archivos
    Guarda archivos depurados en formatos especificados
    Genera respaldos automáticos
    """
    
    def __init__(self):
        self.logger = Logger()
        self.settings = Settings()
        
        # Crear directorios si no existen
        self.settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.settings.ERROR_DIR.mkdir(parents=True, exist_ok=True)
        self.settings.RESPALDO_DIR.mkdir(parents=True, exist_ok=True)
    
    def guardar_archivo(self, df: pd.DataFrame, nombre_archivo: str,
                       formato: str = "xlsx", subfolder: str = "") -> Tuple[bool, str]:
        """
        Guarda un dataframe en archivo
        
        Args:
            df: Dataframe a guardar
            nombre_archivo: Nombre del archivo (sin extensión)
            formato: 'xlsx' o 'csv'
            subfolder: Subcarpeta dentro de OUTPUT_DIR
            
        Returns:
            Tupla (exitoso, mensaje)
        """
        try:
            # Determinar ruta
            if subfolder:
                ruta_salida = self.settings.OUTPUT_DIR / subfolder
                ruta_salida.mkdir(parents=True, exist_ok=True)
            else:
                ruta_salida = self.settings.OUTPUT_DIR
            
            # Agregar extensión
            if formato.lower() == "xlsx":
                archivo_salida = ruta_salida / f"{nombre_archivo}.xlsx"
                df.to_excel(archivo_salida, index=False, engine='openpyxl')
            elif formato.lower() == "csv":
                archivo_salida = ruta_salida / f"{nombre_archivo}.csv"
                df.to_csv(archivo_salida, index=False, encoding='utf-8')
            else:
                return False, f"Formato no soportado: {formato}"
            
            self.logger.info(f"Archivo guardado: {archivo_salida}")
            return True, str(archivo_salida)
            
        except Exception as e:
            self.logger.error(f"Error guardando archivo: {e}")
            return False, f"Error: {e}"
    
    def guardar_multiformato(self, df: pd.DataFrame, nombre_archivo: str,
                            formatos: List[str] = None) -> Dict[str, Tuple[bool, str]]:
        """
        Guarda un dataframe en múltiples formatos
        
        Args:
            df: Dataframe
            nombre_archivo: Nombre base (sin extensión)
            formatos: Lista de formatos ['xlsx', 'csv'] o None = usar config
            
        Returns:
            Diccionario {formato: (exitoso, mensaje)}
        """
        if formatos is None:
            format_config = self.settings.OUTPUT_FORMAT
            formatos = format_config.split(',') if ',' in format_config else [format_config]
        
        resultados = {}
        for formato in formatos:
            formato = formato.strip().lower()
            if formato:
                exitoso, mensaje = self.guardar_archivo(df, nombre_archivo, formato)
                resultados[formato] = (exitoso, mensaje)
        
        return resultados

    def limpiar_archivos_depurados_previos(self) -> Dict[str, Any]:
        """
        Elimina archivos previos de la carpeta de salida (DEPURADO).
        Conserva archivos ocultos/de control (ej. .gitkeep, .monitor_cache.json).

        Returns:
            Resumen de limpieza
        """
        resumen = {
            "carpeta": str(self.settings.OUTPUT_DIR),
            "eliminados": 0,
            "errores": 0,
            "detalles": []
        }

        try:
            if not self.settings.OUTPUT_DIR.exists():
                return resumen

            for item in self.settings.OUTPUT_DIR.iterdir():
                # Mantener archivos ocultos/de control
                if item.name.startswith('.'):
                    continue

                try:
                    if item.is_file():
                        item.unlink()
                        resumen["eliminados"] += 1
                        resumen["detalles"].append({"tipo": "archivo", "ruta": str(item)})
                    elif item.is_dir():
                        shutil.rmtree(item)
                        resumen["eliminados"] += 1
                        resumen["detalles"].append({"tipo": "carpeta", "ruta": str(item)})
                except Exception as e:
                    resumen["errores"] += 1
                    resumen["detalles"].append({"tipo": "error", "ruta": str(item), "error": str(e)})

            self.logger.info(
                f"Limpieza DEPURADO completada: {resumen['eliminados']} elementos eliminados, "
                f"{resumen['errores']} errores"
            )
            return resumen

        except Exception as e:
            self.logger.error(f"Error limpiando carpeta DEPURADO: {e}")
            resumen["errores"] += 1
            resumen["detalles"].append({"tipo": "error_general", "error": str(e)})
            return resumen
    
    def guardar_con_respaldo(self, df: pd.DataFrame, nombre_archivo: str,
                            archivo_original: Optional[str] = None) -> Dict[str, Any]:
        """
        Guarda un archivo y genera respaldo del original
        
        Args:
            df: Dataframe depurado
            nombre_archivo: Nombre del archivo de salida
            archivo_original: Ruta del archivo original (para respaldo)
            
        Returns:
            Reporte con ubicaciones y estados
        """
        reporte = {
            "archivo_salida": None,
            "respaldo_original": None,
            "exitoso": False
        }
        
        # Guardar archivo depurado
        formatos = self.settings.OUTPUT_FORMAT.split(',') if ',' in self.settings.OUTPUT_FORMAT else [self.settings.OUTPUT_FORMAT]
        formatos = [f.strip() for f in formatos]
        
        exitoso = False
        for formato in formatos:
            ok, ruta = self.guardar_archivo(df, nombre_archivo, formato)
            if ok:
                exitoso = True
                reporte["archivo_salida"] = ruta
        
        # Hacer respaldo del original si se especifica
        if archivo_original and Path(archivo_original).exists() and exitoso:
            try:
                ruta_original = Path(archivo_original)
                nombre_respaldo = (
                    f"{ruta_original.stem}_"
                    f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    f"{ruta_original.suffix}"
                )
                ruta_respaldo = self.settings.RESPALDO_DIR / nombre_respaldo
                
                shutil.copy2(archivo_original, ruta_respaldo)
                reporte["respaldo_original"] = str(ruta_respaldo)
                self.logger.info(f"Respaldo creado: {ruta_respaldo}")
                
            except Exception as e:
                self.logger.warning(f"Error creando respaldo: {e}")
        
        reporte["exitoso"] = exitoso
        return reporte
    
    def guardar_reporte_json(self, datos: Dict[str, Any], nombre_archivo: str) -> Tuple[bool, str]:
        """
        Guarda un reporte en formato JSON
        
        Args:
            datos: Diccionario con datos a guardar
            nombre_archivo: Nombre del archivo (sin extensión)
            
        Returns:
            Tupla (exitoso, ruta)
        """
        try:
            ruta = self.settings.OUTPUT_DIR / f"{nombre_archivo}.json"
            
            with open(ruta, 'w', encoding='utf-8') as f:
                json.dump(datos, f, indent=2, ensure_ascii=False, default=str)
            
            self.logger.info(f"Reporte JSON guardado: {ruta}")
            return True, str(ruta)
            
        except Exception as e:
            self.logger.error(f"Error guardando reporte JSON: {e}")
            return False, f"Error: {e}"
    
    def mover_archivo_error(self, ruta_archivo: str, razon_error: str = "") -> Tuple[bool, str]:
        """
        Mueve un archivo a la carpeta de ERROR
        
        Args:
            ruta_archivo: Ruta del archivo a mover
            razon_error: Razón del error (para reporte)
            
        Returns:
            Tupla (exitoso, nueva_ruta)
        """
        try:
            archivo = Path(ruta_archivo)
            
            if not archivo.exists():
                self.logger.warning(f"Archivo no existe: {ruta_archivo}")
                return False, ruta_archivo
            
            # Crear nombre único con timestamp
            nombre_nuevo = (
                f"{archivo.stem}"
                f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                f"{archivo.suffix}"
            )
            
            ruta_destino = self.settings.ERROR_DIR / nombre_nuevo
            
            # Mover archivo
            shutil.move(str(archivo), str(ruta_destino))
            
            # Crear archivo de registro del error
            archivo_log = ruta_destino.with_suffix('.error.json')
            registro_error = {
                "timestamp": datetime.now().isoformat(),
                "archivo_original": str(archivo),
                "razon": razon_error,
                "archivo_movido": str(ruta_destino)
            }
            
            with open(archivo_log, 'w', encoding='utf-8') as f:
                json.dump(registro_error, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Archivo movido a ERROR: {ruta_destino}")
            return True, str(ruta_destino)
            
        except Exception as e:
            self.logger.error(f"Error moviendo archivo a ERROR: {e}")
            return False, f"Error: {e}"
    
    def eliminar_archivo_original(self, ruta_archivo: str) -> Tuple[bool, str]:
        """
        Elimina el archivo original después de procesamiento exitoso
        
        Args:
            ruta_archivo: Ruta del archivo a eliminar
            
        Returns:
            Tupla (exitoso, mensaje)
        """
        try:
            archivo = Path(ruta_archivo)
            
            if not archivo.exists():
                return False, f"Archivo no existe: {ruta_archivo}"
            
            if not self.settings.DELETE_ORIGINAL_AFTER_PROCESS:
                return False, "Opción DELETE_ORIGINAL_AFTER_PROCESS está deshabilitada"
            
            archivo.unlink()
            self.logger.info(f"Archivo original eliminado: {ruta_archivo}")
            
            return True, f"Archivo eliminado: {ruta_archivo}"
            
        except Exception as e:
            self.logger.error(f"Error eliminando archivo: {e}")
            return False, f"Error: {e}"
    
    def listar_archivos_salida(self) -> Dict[str, List[str]]:
        """
        Lista los archivos guardados en las carpetas de salida
        
        Returns:
            Diccionario con listas de archivos
        """
        resultado = {
            "depurados": [],
            "errores": [],
            "respaldos": []
        }
        
        # Listar depurados
        if self.settings.OUTPUT_DIR.exists():
            resultado["depurados"] = [
                f.name for f in self.settings.OUTPUT_DIR.glob('*')
                if f.is_file() and not f.name.endswith('.json')
            ]
        
        # Listar errores
        if self.settings.ERROR_DIR.exists():
            resultado["errores"] = [
                f.name for f in self.settings.ERROR_DIR.glob('*')
                if f.is_file()
            ]
        
        # Listar respaldos
        if self.settings.RESPALDO_DIR.exists():
            resultado["respaldos"] = [
                f.name for f in self.settings.RESPALDO_DIR.glob('*')
                if f.is_file()
            ]
        
        return resultado


if __name__ == "__main__":
    print("=== PRUEBA DEL MÓDULO GESTOR_SALIDA ===")
    
    gestor = GestorSalida()
    print("Gestor de salida inicializado")
    print(f"Directorio salida: {gestor.settings.OUTPUT_DIR}")
