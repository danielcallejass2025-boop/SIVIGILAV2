"""
monitor.py
Sistema de monitoreo continuo de Google Drive
Revisa cada X segundos si hay nuevos archivos y los procesa automáticamente
"""

import sys
import time
import json
from pathlib import Path
from typing import List, Dict, Set
from datetime import datetime, timedelta
from collections import defaultdict

# Agregar proyecto al path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import Settings
from scripts.utils import Logger
from scripts.lector_drive import LectorDrive
from main import SistemaSegregador


class MonitorGoogleDrive:
    """
    Monitorea carpeta de Google Drive y procesa automáticamente archivos nuevos
    """
    
    def __init__(self):
        self.logger = Logger()
        self.settings = Settings()
        self.lector_drive = LectorDrive()
        self.sistema = SistemaSegregador()
        self.intervalo = self.settings.MONITOR_INTERVAL  # Segundos
        self.archivos_procesados = set()
        self.archivo_cache = Path(self.settings.OUTPUT_DIR) / ".monitor_cache.json"
        
        # Cargar archivos ya procesados
        self._cargar_cache()
        
        self.logger.info(f"Monitor inicializado. Intervalo: {self.intervalo}s")
        self.logger.info(f"Carpeta de entrada Drive: {self.settings.GOOGLE_DRIVE_INPUT_FOLDER_ID}")
        
        # Información sobre filtros
        if self.settings.MONITOR_USE_RECENT_ONLY:
            ventana_horas = self.settings.MONITOR_TIME_WINDOW / 3600
            self.logger.info(
                f"🔍 Filtro ACTIVADO: Solo archivos cargados en las últimas {ventana_horas:.1f} horas"
            )
        else:
            self.logger.info("🔍 Filtro DESACTIVADO: Se procesarán TODOS los archivos no visto antes")
    
    def _cargar_cache(self):
        """Carga el registro de archivos ya procesados"""
        if self.archivo_cache.exists():
            try:
                with open(self.archivo_cache, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.archivos_procesados = set(data.get('procesados', []))
                    self.logger.info(f"Cache cargado: {len(self.archivos_procesados)} archivos en historial")
            except Exception as e:
                self.logger.warning(f"Error cargando cache: {e}")
                self.archivos_procesados = set()
        else:
            self.archivos_procesados = set()
    
    def _guardar_cache(self):
        """Guarda el registro de archivos procesados"""
        try:
            data = {
                'procesados': list(self.archivos_procesados),
                'ultima_actualizacion': datetime.now().isoformat()
            }
            with open(self.archivo_cache, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.warning(f"Error guardando cache: {e}")

    def _asegurar_conexion_drive(self) -> bool:
        """
        Garantiza conexión activa a Google Drive.
        Reintenta autenticación cuando la conexión se pierde al iniciar.
        """
        try:
            if self.lector_drive and self.lector_drive.esta_conectado():
                return True

            self.logger.warning("Sin conexión activa a Drive. Reintentando autenticación...")

            if self.lector_drive:
                ok = self.lector_drive.reconectar()
            else:
                self.lector_drive = LectorDrive()
                ok = self.lector_drive.esta_conectado()

            if ok:
                self.logger.info("✅ Conexión con Google Drive restablecida")
                return True

            return False
        except Exception as e:
            self.logger.error(f"Error intentando reconexión a Drive: {e}")
            return False
    
    def obtener_archivos_nuevos(self) -> List[Dict]:
        """
        Obtiene lista de archivos recientemente cargados en Google Drive
        
        Filtra por:
        1. ID del archivo (no procesado antes)
        2. Fecha de creación (solo archivos recientes)
        
        Returns:
            Lista de diccionarios con información de archivos nuevos
        """
        try:
            if not self._asegurar_conexion_drive():
                self.logger.error("No hay conexión con Google Drive")
                return []
            
            # Listar archivos en carpeta de entrada
            archivos = self.lector_drive.listar_archivos(
                self.settings.GOOGLE_DRIVE_INPUT_FOLDER_ID,
                tipos_archivo=['xlsx', 'xls', 'csv', 'ods']
            )
            
            if not archivos:
                return []
            
            # FILTRO 1: Archivos no procesados antes
            archivos_filtrados = [
                a for a in archivos 
                if a['id'] not in self.archivos_procesados
            ]
            
            # FILTRO 2: Solo archivos recién cargados (si está habilitado)
            if self.settings.MONITOR_USE_RECENT_ONLY:
                ventana_tiempo = self.settings.MONITOR_TIME_WINDOW  # Segundos
                ahora = datetime.utcnow()
                tiempo_limite = ahora - timedelta(seconds=ventana_tiempo)
                
                archivos_nuevos = []
                for archivo in archivos_filtrados:
                    # Obtener fecha de creación (en Google Drive es ISO format)
                    fecha_str = archivo.get('createdTime', '')
                    
                    if fecha_str:
                        try:
                            # Parsear fecha ISO (2026-04-07T08:17:29.504Z)
                            fecha_creacion = datetime.fromisoformat(
                                fecha_str.replace('Z', '+00:00')
                            )
                            # Convertir a naive datetime (UTC)
                            fecha_creacion = fecha_creacion.replace(tzinfo=None)
                            
                            # Verificar si está dentro de la ventana de tiempo
                            if fecha_creacion >= tiempo_limite:
                                archivos_nuevos.append(archivo)
                                antigüedad = (ahora - fecha_creacion).total_seconds()
                                self.logger.info(
                                    f"  ✓ {archivo['name']} (cargado hace {int(antigüedad)}s)"
                                )
                            else:
                                # Archivo muy viejo, ignorar
                                antigüedad = (ahora - fecha_creacion).total_seconds()
                                self.logger.info(
                                    f"  ⊘ {archivo['name']} (muy viejo: {int(antigüedad)}s)"
                                )
                        except Exception as e:
                            self.logger.warning(f"Error parsing fecha de {archivo['name']}: {e}")
                            # Si no se puede parsear, incluir el archivo de todas formas
                            archivos_nuevos.append(archivo)
                    else:
                        # Sin fecha, incluir de todas formas
                        archivos_nuevos.append(archivo)
                
                return archivos_nuevos
            else:
                # Sin filtro de tiempo, retornar todos los no procesados
                return archivos_filtrados
        
        except Exception as e:
            self.logger.error(f"Error obteniendo archivos de Drive: {e}")
            return []
    
    def descargar_archivo(self, archivo_id: str, nombre_archivo: str) -> Path:
        """
        Descarga archivo de Google Drive
        
        Args:
            archivo_id: ID del archivo en Drive
            nombre_archivo: Nombre del archivo
            
        Returns:
            Ruta del archivo descargado
        """
        try:
            # Asegurar que la carpeta existe
            self.settings.INPUT_DIR.mkdir(parents=True, exist_ok=True)
            
            # Pasar solo la carpeta (lector_drive agregará el nombre)
            exito, ruta = self.lector_drive.descargar_archivo(archivo_id, str(self.settings.INPUT_DIR))
            
            if exito:
                return Path(ruta)
            else:
                self.logger.error(f"Error descargando archivo {nombre_archivo}: {ruta}")
                return None
        
        except Exception as e:
            self.logger.error(f"Error descargando archivo {nombre_archivo}: {e}")
            return None
    
    def procesar_archivo_drive(self, archivo_info: Dict) -> bool:
        """
        Procesa un archivo descargado desde Drive
        
        Args:
            archivo_info: Diccionario con información del archivo
            
        Returns:
            True si se procesó exitosamente
        """
        try:
            archivo_id = archivo_info['id']
            nombre = archivo_info['name']
            
            self.logger.info(f"Procesando archivo de Drive: {nombre}")
            
            # Descargar archivo
            ruta_local = self.descargar_archivo(archivo_id, nombre)
            if not ruta_local:
                return False
            
            self.logger.info(f"Archivo descargado: {ruta_local}")
            
            # Procesar con el sistema completo
            try:
                self.sistema.procesar_archivo(
                    str(ruta_local),
                    generar_boletin=True,
                    exportar_mme_final=True
                )
                self.logger.info(f"✅ Archivo procesado exitosamente: {nombre}")
                
                # Marcar como procesado
                self.archivos_procesados.add(archivo_id)
                self._guardar_cache()
                
                return True
            
            except Exception as e:
                self.logger.error(f"Error procesando archivo {nombre}: {e}")
                return False
        
        except Exception as e:
            self.logger.error(f"Error en procesar_archivo_drive: {e}")
            return False
    
    def ejecutar_ciclo_monitoreo(self):
        """Ejecuta un ciclo de monitoreo"""
        try:
            self.logger.info("🔍 Buscando archivos nuevos en Drive...")
            
            archivos_nuevos = self.obtener_archivos_nuevos()
            
            if not archivos_nuevos:
                self.logger.info("No hay archivos nuevos por procesar")
                return 0
            
            self.logger.info(f"📥 Encontrados {len(archivos_nuevos)} archivo(s) nuevo(s)")
            
            # Procesar cada archivo
            procesados = 0
            for archivo in archivos_nuevos:
                if self.procesar_archivo_drive(archivo):
                    procesados += 1
            
            self.logger.info(f"✅ Procesados {procesados}/{len(archivos_nuevos)} archivos")
            return procesados
        
        except Exception as e:
            self.logger.error(f"Error en ciclo de monitoreo: {e}")
            return 0
    
    def iniciar_monitoreo(self):
        """
        Inicia el monitoreo continuo de Drive
        Revisa cada X segundos y procesa solo archivos recién cargados
        """
        print("\n" + "="*70)
        print("🔄 MONITOR DE GOOGLE DRIVE INICIADO")
        print("="*70)
        print(f"\n📊 Configuración:")
        print(f"   • Modalidad: MONITOREO CONTINUO")
        print(f"   • Carpeta de entrada Drive: {self.settings.GOOGLE_DRIVE_INPUT_FOLDER_ID[:20]}...")
        print(f"   • Intervalo de revisión: {self.intervalo} segundos")
        print(f"   • Formato de archivos: Excel, CSV, ODS")
        print(f"   • Procesamiento automático: SÍ")
        print(f"   • Boletines: SÍ")
        
        # Información sobre filtros
        if self.settings.MONITOR_USE_RECENT_ONLY:
            ventana_horas = self.settings.MONITOR_TIME_WINDOW / 3600
            print(f"\n🔍 FILTRO DE TIEMPO ACTIVADO:")
            print(f"   • Solo procesa archivos cargados en las últimas {ventana_horas:.1f} horas")
            print(f"   • Archivos más viejos serán IGNORADOS automáticamente")
        else:
            print(f"\n🔍 FILTRO DE TIEMPO DESACTIVADO:")
            print(f"   • Se procesarán TODOS los archivos (podría incluir viejos)")
        
        print(f"\n✓ Presiona Ctrl+C para detener el monitoreo\n")
        print("="*70 + "\n")
        
        ciclo = 0
        try:
            while True:
                ciclo += 1
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"\n[{timestamp}] Ciclo #{ciclo}")
                print("-" * 70)
                
                # Ejecutar ciclo de monitoreo
                procesados = self.ejecutar_ciclo_monitoreo()
                
                # Mostrar siguiente revisión
                print(f"✓ Próxima revisión en {self.intervalo}s...")
                
                # Esperar intervalo
                time.sleep(self.intervalo)
        
        except KeyboardInterrupt:
            print("\n\n" + "="*70)
            print("⏹ MONITOREO DETENIDO POR EL USUARIO")
            print("="*70)
            print(f"\n📊 Estadísticas:")
            print(f"   • Ciclos ejecutados: {ciclo}")
            print(f"   • Archivos procesados: {len(self.archivos_procesados)}")
            print(f"   • Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("\n✓ Gracias por usar SIVIGILA Monitor\n")
        
        except Exception as e:
            self.logger.error(f"Error fatal en monitoreo: {e}")
            raise


def main():
    """Función principal"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Monitor de Google Drive para SIVIGILA")
    parser.add_argument(
        '--intervalo',
        type=int,
        default=None,
        help='Intervalo de revisión en segundos (default: desde .env)'
    )
    
    args = parser.parse_args()
    
    # Crear monitor
    monitor = MonitorGoogleDrive()
    
    # Cambiar intervalo si se especifica
    if args.intervalo:
        monitor.intervalo = args.intervalo
    
    # Iniciar monitoreo
    monitor.iniciar_monitoreo()


if __name__ == "__main__":
    main()
