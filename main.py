"""
main.py
Orquestador principal del sistema SIVIGILA
Coordina lectura, depuración, anonimización y salida de archivos epidemiológicos
"""

import sys
import argparse
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import requests

from config.settings import Settings
from scripts.utils import Logger, ConfigManager, crear_resumen_procesamiento
from scripts.lector_archivos import LectorArchivos, LectorArchivosCarpeta
from scripts.detector_evento import DetectorEvento
from scripts.normalizador_columnas import NormalizadorColumnas
from scripts.depuracion_evento_549 import obtener_gestor_depuracion
from scripts.anonimizar import Anonimizador
from scripts.validador_calidad import ValidadorCalidadAvanzado
from scripts.gestor_salida import GestorSalida
from scripts.boletin import GeneradorBoletin
from scripts.lector_drive import obtener_lector_drive


class SistemaSegregador:
    """
    Orquestador principal del procesamiento SIVIGILA
    Coordina todos los pasos del pipeline
    """
    
    def __init__(self):
        self.logger = Logger()
        self.settings = Settings()
        self.gestor_salida = GestorSalida()
        self.lector = LectorArchivos()
        self.detector_evento = DetectorEvento()
        self.normalizador = NormalizadorColumnas()
        self.gestor_depuracion = obtener_gestor_depuracion(
            filter_only_risaralda=self.settings.FILTER_ONLY_RISARALDA
        )
        self.anonimizador = Anonimizador()
        self.validador = ValidadorCalidadAvanzado()
        
        self.logger.info(f"=== INICIANDO SISTEMA SIVIGILA (Modo: {self.settings.APP_MODE}) ===")

    @staticmethod
    def _normalizar_texto(valor: Any) -> str:
        """Normaliza texto para comparaciones robustas."""
        txt = str(valor).strip().lower()
        txt = txt.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
        txt = txt.replace("ñ", "n")
        return " ".join(txt.split())

    @staticmethod
    def _obtener_semana_epidemiologica(fecha: Optional[datetime] = None) -> int:
        """Calcula semana epidemiológica con inicio en domingo."""
        fecha = fecha or datetime.now()
        inicio_anio = datetime(fecha.year, 1, 1)
        dias_transcurridos = (fecha.date() - inicio_anio.date()).days + 1
        offset_domingo = (inicio_anio.weekday() + 1) % 7  # domingo=0
        return ((dias_transcurridos + offset_domingo - 1) // 7) + 1

    def _mapear_clasificacion(self, valor: Any) -> str:
        """Mapea clasificaciones heterogéneas a valores esperados por Apps Script."""
        txt = self._normalizar_texto(valor)
        if not txt:
            return ""
        if "confirm" in txt:
            return "CONFIRMADO"
        if "descart" in txt:
            return "DESCARTADO"
        if "probab" in txt:
            return "PROBABLE"
        return str(valor).strip().upper()

    def _guardar_resumen_historico_apps_script(self, df_depurado, codigo_evento: int) -> Dict[str, Any]:
        """
        Envía al Apps Script el resumen de la semana para guardar/actualizar la hoja HISTORICO.
        """
        if int(codigo_evento) != 549:
            return {
                "exitoso": False,
                "omitido": True,
                "mensaje": "Registro histórico habilitado únicamente para evento 549"
            }

        url = (self.settings.APPS_SCRIPT_DEPLOY_URL or "").strip()
        if not url:
            return {
                "exitoso": False,
                "mensaje": "APPS_SCRIPT_DEPLOY_URL no configurado"
            }

        columnas = list(getattr(df_depurado, "columns", []))
        col_clasificacion = None
        for col in columnas:
            norm = self._normalizar_texto(col)
            if norm == "clasificacion" or "clasif" in norm:
                col_clasificacion = col
                break

        if col_clasificacion:
            clasificaciones = [
                self._mapear_clasificacion(v)
                for v in df_depurado[col_clasificacion].fillna("").tolist()
            ]
        else:
            clasificaciones = ["" for _ in range(len(df_depurado))]

        datos_minimos = [{"clasificacion": c} for c in clasificaciones]

        params = {
            "accion": "guardar_resumen",
            "datos": json.dumps(datos_minimos, ensure_ascii=False)
        }
        if self.settings.APPS_SCRIPT_API_KEY:
            params["key"] = self.settings.APPS_SCRIPT_API_KEY

        try:
            response = requests.get(
                url,
                params=params,
                timeout=self.settings.APPS_SCRIPT_TIMEOUT_SECONDS
            )

            body_preview = response.text[:300]
            payload = None
            try:
                payload = response.json()
            except Exception:
                payload = {"raw": body_preview}

            if response.ok:
                if isinstance(payload, dict) and str(payload.get("status", "")).lower() == "error":
                    return {
                        "exitoso": False,
                        "status_code": response.status_code,
                        "mensaje": payload.get("mensaje", "Apps Script respondió con error"),
                        "detalle": payload
                    }

                return {
                    "exitoso": True,
                    "status_code": response.status_code,
                    "semana_enviada": self._obtener_semana_epidemiologica(),
                    "total_registros": len(datos_minimos),
                    "columna_clasificacion": col_clasificacion,
                    "respuesta": payload
                }

            return {
                "exitoso": False,
                "status_code": response.status_code,
                "mensaje": f"Apps Script respondió HTTP {response.status_code}",
                "detalle": payload
            }

        except Exception as e:
            return {
                "exitoso": False,
                "mensaje": f"Error comunicando Apps Script: {e}"
            }
    
    def procesar_archivo(self, ruta_archivo: str, generar_boletin: bool = None) -> Dict[str, Any]:
        """
        Procesa un archivo epidemiológico completo
        
        Args:
            ruta_archivo: Ruta al archivo a procesar
            generar_boletin: Si es True, genera boletín (default: desde settings)
            
        Returns:
            Diccionario con resultado del procesamiento
        """
        
        # Si no se especifica, usar configuración global
        if generar_boletin is None:
            generar_boletin = self.settings.ENABLE_BOLETIN
        
        resultado = {
            "archivo": ruta_archivo,
            "exitoso": False,
            "pasos": [],
            "errores": [],
            "archivo_salida": None,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # PASO 1: Lectura del archivo
            self.logger.info(f"Leyendo archivo: {ruta_archivo}")
            df, metadatos = self.lector.leer(ruta_archivo)
            
            if df is None:
                resultado["errores"].append(f"Error leyendo archivo: {metadatos.get('error')}")
                self._mover_archivo_error(ruta_archivo, resultado["errores"][0])
                return resultado
            
            resultado["pasos"].append({
                "paso": "LECTURA",
                "filas_leidas": len(df),
                "columnas": len(df.columns),
                "metadatos": metadatos
            })
            
            # PASO 2: Detección del evento
            self.logger.info("Detectando evento epidemiológico...")
            info_evento = self.detector_evento.detectar_completo(df)
            
            if not info_evento["exitoso"]:
                resultado["errores"].append("No se pudo detectar el evento")
                self._mover_archivo_error(ruta_archivo, "No se detectó evento")
                return resultado
            
            codigo_evento = info_evento["evento_predominante"]
            nombre_evento = info_evento["nombre_evento"]
            
            resultado["pasos"].append({
                "paso": "DETECCION_EVENTO",
                "evento": {
                    "codigo": codigo_evento,
                    "nombre": nombre_evento
                },
                "info_completa": info_evento
            })
            
            # PASO 3: Normalización de columnas
            self.logger.info("Normalizando columnas...")
            mapeo_columnas = self.normalizador.mapear_columnas(df)
            df_normalizado = self.normalizador.estandarizar_dataframe(df, mapeo_columnas)
            
            # Filtrar por departamento si está habilitado
            if self.settings.FILTER_ONLY_RISARALDA and "departamento" in df_normalizado.columns:
                df_normalizado, filas_elim = self.normalizador.agrupar_por_departamento(
                    df_normalizado, "RISARALDA"
                )
            
            # Estandarizar campos demográficos
            df_normalizado = self.normalizador.estandarizar_sexo(df_normalizado)
            df_normalizado = self.normalizador.estandarizar_edad(df_normalizado)
            df_normalizado = self.normalizador.estandarizar_municipio(df_normalizado)
            
            resultado["pasos"].append({
                "paso": "NORMALIZACION",
                "mapeo_columnas": mapeo_columnas,
                "columnas_encontradas": len([v for v in mapeo_columnas.values() if v is not None])
            })
            
            # PASO 4: Depuración general + específica
            self.logger.info(f"Depurando evento {codigo_evento}...")
            df_depurado, rep_depuracion = self.gestor_depuracion.depurar_evento_549(
                df_normalizado
            )
            
            if len(df_depurado) == 0:
                resultado["errores"].append("Depuración resultó en cero filas")
                self._mover_archivo_error(ruta_archivo, "Sin datos después de depuración")
                return resultado
            
            resultado["pasos"].append({
                "paso": "DEPURACION",
                "reporte": rep_depuracion
            })
            
            # PASO 5: Anonimización obligatoria
            self.logger.info("Anonimizando datos sensibles...")
            df_anonimo, rep_anonimizacion = self.anonimizador.anonimizar_completo(df_depurado)
            
            resultado["pasos"].append({
                "paso": "ANONIMIZACION",
                "reporte": rep_anonimizacion
            })
            
            # PASO 6: Validación de calidad
            self.logger.info("Validando calidad de datos...")
            rep_calidad = self.validador.generar_reporte_calidad(df_anonimo, Path(ruta_archivo).name)
            
            resultado["pasos"].append({
                "paso": "VALIDACION_CALIDAD",
                "puntuacion": rep_calidad["puntuacion_calidad"],
                "recomendaciones": rep_calidad["recomendaciones"]
            })
            
            # PASO 7: Guardar archivo depurado
            self.logger.info("Guardando archivo depurado...")
            limpieza_depurado = self.gestor_salida.limpiar_archivos_depurados_previos()
            resultado["pasos"].append({
                "paso": "LIMPIEZA_DEPURADO",
                "reporte": limpieza_depurado
            })

            nombre_salida = (
                f"{Path(ruta_archivo).stem}_"
                f"{codigo_evento}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            
            resultados_salida = self.gestor_salida.guardar_multiformato(df_anonimo, nombre_salida)
            
            archivo_guardado = None
            for formato, (exitoso, ruta) in resultados_salida.items():
                if exitoso:
                    archivo_guardado = ruta
                    break
            
            if not archivo_guardado:
                resultado["errores"].append("Error guardando archivo")
                self._mover_archivo_error(ruta_archivo, "No se pudo guardar archivo")
                return resultado
            
            # Subir archivo a Google Drive si está en modo DRIVE o HIBRIDO
            archivos_subidos_drive = {}
            resumen_historico = None
            if self.settings.APP_MODE in ["DRIVE", "HIBRIDO"]:
                self.logger.info("Subiendo archivo depurado a Google Drive...")
                
                # Validar que existe OUTPUT_FOLDER_ID
                if not self.settings.GOOGLE_DRIVE_OUTPUT_FOLDER_ID:
                    self.logger.warning("⚠️ GOOGLE_DRIVE_OUTPUT_FOLDER_ID no configurado en .env")
                else:
                    # Obtener lector de Drive
                    lector_drive = obtener_lector_drive()
                    
                    if lector_drive and lector_drive.esta_conectado():
                        # Subir cada formato generado
                        for formato, (exitoso, ruta) in resultados_salida.items():
                            if exitoso and Path(ruta).exists():
                                try:
                                    nombre_archivo_drive = f"{nombre_salida}.{formato.lower()}"
                                    ok_subida, resultado_subida = lector_drive.subir_archivo(
                                        ruta,
                                        self.settings.GOOGLE_DRIVE_OUTPUT_FOLDER_ID,
                                        nombre_archivo_drive
                                    )
                                    
                                    if ok_subida:
                                        self.logger.info(f"✅ Archivo subido a Drive: {nombre_archivo_drive}")
                                        archivos_subidos_drive[formato] = {
                                            "exitoso": True,
                                            "file_id": resultado_subida,
                                            "nombre_drive": nombre_archivo_drive
                                        }
                                    else:
                                        self.logger.warning(f"⚠️ No se pudo subir {formato}: {resultado_subida}")
                                        archivos_subidos_drive[formato] = {
                                            "exitoso": False,
                                            "error": resultado_subida
                                        }
                                except Exception as e:
                                    self.logger.warning(f"Error subiendo {formato}: {e}")
                                    archivos_subidos_drive[formato] = {
                                        "exitoso": False,
                                        "error": str(e)
                                    }
                    else:
                        self.logger.warning("⚠️ No hay conexión con Google Drive para subir archivos")

                hubo_subida_exitosa = any(
                    (info or {}).get("exitoso") for info in archivos_subidos_drive.values()
                )
                if hubo_subida_exitosa:
                    self.logger.info("Registrando resumen histórico interanual en Apps Script...")
                    resumen_historico = self._guardar_resumen_historico_apps_script(df_anonimo, codigo_evento)
                    if resumen_historico.get("exitoso"):
                        self.logger.info("✅ Resumen histórico registrado correctamente")
                    else:
                        self.logger.warning(
                            f"⚠️ No se pudo registrar resumen histórico: {resumen_historico.get('mensaje', 'sin detalle')}"
                        )
                else:
                    resumen_historico = {
                        "exitoso": False,
                        "omitido": True,
                        "mensaje": "No se registró resumen histórico porque no hubo subida exitosa a Drive"
                    }
            
            resultado["pasos"].append({
                "paso": "SALIDA",
                "archivo_guardado": archivo_guardado,
                "formatos": resultados_salida,
                "subida_drive": archivos_subidos_drive if archivos_subidos_drive else None,
                "resumen_historico": resumen_historico
            })
            
            # PASO 8: Generar resumen
            resumen = crear_resumen_procesamiento(
                ruta_archivo,
                codigo_evento,
                nombre_evento,
                len(df),
                len(df_anonimo),
                len(df.columns),
                {
                    "filas_depuradas": len(df) - len(df_anonimo),
                    "columnas_eliminadas": len(df.columns) - len(df_anonimo.columns)
                }
            )
            
            resultado["pasos"].append({
                "paso": "RESUMEN",
                "resumen": resumen
            })
            
            # PASO 9: Generar boletín si está habilitado
            if generar_boletin:
                self.logger.info("Generando boletín epidemiológico...")
                generador = GeneradorBoletin()
                
                # Generar boletín en HTML
                contenido_html = generador.generar_boletin(df_anonimo, codigo_evento, "html")
                ok_html, ruta_html = generador.guardar_boletin(
                    contenido_html,
                    f"{nombre_salida}_boletin",
                    "html"
                )
                
                # Generar boletín en texto
                contenido_txt = generador.generar_boletin(df_anonimo, codigo_evento, "texto")
                ok_txt, ruta_txt = generador.guardar_boletin(
                    contenido_txt,
                    f"{nombre_salida}_boletin",
                    "texto"
                )
                
                if ok_html or ok_txt:
                    resultado["pasos"].append({
                        "paso": "BOLETIN",
                        "boletin_html": ruta_html if ok_html else None,
                        "boletin_texto": ruta_txt if ok_txt else None
                    })
            
            # Guardar reporte en JSON
            self.logger.info("Guardando reporte de procesamiento...")
            ok_json, ruta_json = self.gestor_salida.guardar_reporte_json(
                resultado,
                f"{nombre_salida}_reporte"
            )
            
            # PASO 10: Opcionalmente eliminar original
            if self.settings.DELETE_ORIGINAL_AFTER_PROCESS:
                ok_eliminar, msg = self.gestor_salida.eliminar_archivo_original(ruta_archivo)
                resultado["pasos"].append({
                    "paso": "ELIMINAR_ORIGINAL",
                    "exitoso": ok_eliminar,
                    "mensaje": msg
                })
            
            resultado["exitoso"] = True
            resultado["archivo_salida"] = archivo_guardado
            
            self.logger.info(f"✓ Archivo procesado exitosamente: {archivo_guardado}")
            
            return resultado
            
        except Exception as e:
            self.logger.error(f"Error procesando archivo: {e}")
            resultado["errores"].append(f"Excepción: {str(e)}")
            self._mover_archivo_error(ruta_archivo, str(e))
            return resultado
    
    def procesar_carpeta(self) -> Dict[str, Any]:
        """
        Procesa todos los archivos de la carpeta de entrada
        
        Returns:
            Reporte de procesamiento
        """
        lector_carpeta = LectorArchivosCarpeta(str(self.settings.INPUT_DIR))
        archivos = lector_carpeta.listar_archivos_por_procesar()
        
        reporte_general = {
            "timestamp": datetime.now().isoformat(),
            "modo": self.settings.APP_MODE,
            "carpeta_entrada": str(self.settings.INPUT_DIR),
            "total_archivos": len(archivos),
            "resultados": [],
            "resumen": {
                "exitosos": 0,
                "fallidos": 0,
                "archivos_procesados": []
            }
        }
        
        self.logger.info(f"Procesando {len(archivos)} archivos...")
        
        for archivo in archivos:
            self.logger.info(f"\nProcesando: {archivo.name}")
            
            resultado = self.procesar_archivo(str(archivo))
            reporte_general["resultados"].append(resultado)
            
            if resultado["exitoso"]:
                reporte_general["resumen"]["exitosos"] += 1
                reporte_general["resumen"]["archivos_procesados"].append(archivo.name)
            else:
                reporte_general["resumen"]["fallidos"] += 1
        
        # Guardar reporte general
        self.gestor_salida.guardar_reporte_json(
            reporte_general,
            f"reporte_general_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        
        return reporte_general
    
    def _mover_archivo_error(self, ruta_archivo: str, razon: str):
        """Mueve un archivo a la carpeta de errores"""
        ok, _ = self.gestor_salida.mover_archivo_error(ruta_archivo, razon)
        if not ok:
            self.logger.error(f"No se pudo mover archivo a ERROR: {ruta_archivo}")
    
    def mostrar_dashboard(self):
        """Inicia el dashboard Streamlit"""
        import subprocess
        
        # Usar el script wrapper que configura correctamente los paths
        script_dashboard = Path(__file__).parent / "run_dashboard.py"
        
        self.logger.info(f"Iniciando dashboard en puerto {self.settings.STREAMLIT_PORT}...")
        
        try:
            # Ejecutar con python para asegurar que el path esté configurado
            subprocess.run([
                sys.executable,  # Usa el Python del venv
                str(script_dashboard)
            ])
        except Exception as e:
            self.logger.error(f"Error iniciando dashboard: {e}")


def main():
    """Función principal"""
    
    # Parser de argumentos
    parser = argparse.ArgumentParser(
        description="Sistema SIVIGILA - Procesamiento de datos epidemiológicos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:

  # Procesar archivos locales
  python main.py --local

  # Procesar archivo específico
  python main.py --archivo data/ENTRADA_SIVIGILA/datos.xlsx

  # Iniciar dashboard
  python main.py --dashboard

  # Procesar y generar boletín
  python main.py --local --boletin

  # Procesar desde Google Drive (híbrido)
  python main.py --hibrido --boletin
        """
    )
    
    parser.add_argument(
        '--local',
        action='store_true',
        help='Procesar archivos de la carpeta local'
    )
    
    parser.add_argument(
        '--archivo',
        type=str,
        help='Procesar un archivo específico'
    )
    
    parser.add_argument(
        '--dashboard',
        action='store_true',
        help='Iniciar el dashboard web'
    )
    
    parser.add_argument(
        '--boletin',
        action='store_true',
        help='Generar boletín epidemiológico'
    )
    
    parser.add_argument(
        '--hibrido',
        action='store_true',
        help='Modo híbrido (local + Google Drive)'
    )
    
    parser.add_argument(
        '--drive',
        action='store_true',
        help='Procesar desde Google Drive'
    )
    
    parser.add_argument(
        '--monitor',
        action='store_true',
        help='Activar monitoreo continuo de Google Drive'
    )
    
    parser.add_argument(
        '--intervalo',
        type=int,
        default=None,
        help='Intervalo de monitoreo en segundos'
    )
    
    args = parser.parse_args()
    
    # Crear sistema
    sistema = SistemaSegregador()
    
    # Procesar opciones
    
    # Si se pide monitoreo, activar en lugar de procesamiento único
    if args.monitor:
        from monitor import MonitorGoogleDrive
        
        monitor = MonitorGoogleDrive()
        
        if args.intervalo:
            monitor.intervalo = args.intervalo
        
        monitor.iniciar_monitoreo()
        return
    
    if args.archivo:
        # Procesar archivo específico
        resultado = sistema.procesar_archivo(args.archivo)
        print(f"\n{'='*60}")
        print(f"Procesamiento: {'EXITOSO' if resultado['exitoso'] else 'FALLIDO'}")
        print(f"{'='*60}\n")
    
    elif args.local or (not args.dashboard and not args.hibrido and not args.drive):
        # Procesar carpeta local (default)
        reporte = sistema.procesar_carpeta()
        print(f"\n{'='*60}")
        print(f"Resumen: {reporte['resumen']['exitosos']} exitosos, "
              f"{reporte['resumen']['fallidos']} fallidos")
        print(f"{'='*60}\n")
    
    elif args.hibrido:
        # Modo híbrido - sincronizar desde Drive y procesar
        lector_drive = obtener_lector_drive()
        if lector_drive and lector_drive.esta_conectado():
            sistema.logger.info("Sincronizando archivos de Google Drive...")
            try:
                lector_drive.sincronizar_carpeta(
                    sistema.settings.GOOGLE_DRIVE_INPUT_FOLDER_ID,
                    str(sistema.settings.INPUT_DIR)
                )
                sistema.logger.info("✅ Sincronización completada")
            except Exception as e:
                sistema.logger.warning(f"⚠️ Error sincronizando Drive: {e}")
        else:
            sistema.logger.warning("⚠️ No hay conexión con Google Drive")
        
        # Procesar todos los archivos (locales + descargados)
        reporte = sistema.procesar_carpeta()
    
    elif args.drive:
        # Solo Google Drive - descargar, procesar y subir
        lector_drive = obtener_lector_drive()
        if not lector_drive:
            sistema.logger.error("Google Drive no disponible")
            return
        
        # Sincronizar desde Drive
        sistema.logger.info("Sincronizando archivos desde Google Drive...")
        try:
            lector_drive.sincronizar_carpeta(
                sistema.settings.GOOGLE_DRIVE_INPUT_FOLDER_ID,
                str(sistema.settings.INPUT_DIR)
            )
            sistema.logger.info("Sincronización completada")
        except Exception as e:
            sistema.logger.error(f"Error sincronizando: {e}")
        
        # Procesar archivos descargados
        reporte = sistema.procesar_carpeta()
    
    if args.dashboard:
        sistema.mostrar_dashboard()


if __name__ == "__main__":
    main()
