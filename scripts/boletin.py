"""
scripts/boletin.py
Módulo de generación de boletines epidemiológicos
Crea reportes resumidos en texto e HTML
"""

import pandas as pd
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import html
from config.settings import Settings
from scripts.cliente_boletin_apps_script import BulletinAppsScriptClient
from scripts.utils import Logger, ConfigManager


class GeneradorBoletin:
    """
    Genera boletines epidemiológicos resumidos
    Formatos: texto plano e HTML
    """
    
    def __init__(self):
        self.logger = Logger()
        self.settings = Settings()
        self.config = ConfigManager()
        self._comparacion_cache = {}
    
    def generar_boletin(self, df: pd.DataFrame, evento_codigo: int = None,
                       formato: str = "texto") -> str:
        """
        Genera un boletín epidemiológico
        
        Args:
            df: Dataframe con datos
            evento_codigo: Código del evento (None = general)
            formato: 'texto' o 'html'
            
        Returns:
            Contenido del boletín como string
        """
        
        if formato == "html":
            return self._generar_boletin_html(df, evento_codigo)
        else:
            return self._generar_boletin_texto(df, evento_codigo)
    
    def _generar_boletin_texto(self, df: pd.DataFrame, evento_codigo: int = None) -> str:
        """Genera boletín en formato de texto plano"""
        
        lineas = []
        comparacion_semanal = self._obtener_comparacion_semanal(df, evento_codigo)
        
        # Encabezado
        lineas.append("=" * 80)
        lineas.append("BOLETÍN EPIDEMIOLÓGICO SIVIGILA".center(80))
        lineas.append("=" * 80)
        lineas.append("")
        
        # Información del evento
        if evento_codigo:
            evento_info = self.config.obtener_evento(evento_codigo)
            nombre_evento = evento_info.get("nombre", "Evento desconocido") if evento_info else "Evento desconocido"
            lineas.append(f"Evento: {nombre_evento} (Código {evento_codigo})")
        else:
            lineas.append("Resumen General de Eventos")
        
        lineas.append(f"Fecha de generación: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lineas.append(f"Total registros: {len(df)}")
        lineas.append("")
        
        # Resumen estadístico
        lineas.append("-" * 80)
        lineas.append("RESUMEN ESTADÍSTICO")
        lineas.append("-" * 80)
        
        lineas.append("")
        lineas.append(f"Total de casos: {len(df)}")

        if comparacion_semanal:
            lineas.append("")
            lineas.append("Comparación semanal del boletín:")
            lineas.append(
                f"  • Semana epidemiológica {comparacion_semanal['week']} de {comparacion_semanal['target_year']}: "
                f"{comparacion_semanal['current_year_cases']} casos"
            )
            lineas.append(
                f"  • Misma semana de {comparacion_semanal['previous_year']}: "
                f"{comparacion_semanal['previous_year_cases']} casos"
            )
            lineas.append(
                f"  • Diferencia: {comparacion_semanal['difference_text']}"
            )
            lineas.append(
                f"  • Comportamiento: {comparacion_semanal['trend_label']}"
            )
            lineas.append(
                f"  • Interpretación: {comparacion_semanal['summary_sentence']}"
            )
        
        if "municipio" in df.columns:
            municipios_unicos = df["municipio"].nunique()
            lineas.append(f"Municipios afectados: {municipios_unicos}")
            
            # Top 5 municipios
            top_municipios = df["municipio"].value_counts().head(5)
            lineas.append("\nMunicipios más afectados:")
            for municipio, cantidad in top_municipios.items():
                porcentaje = (cantidad / len(df) * 100)
                lineas.append(f"  • {municipio}: {cantidad} casos ({porcentaje:.1f}%)")
        
        # Distribución por sexo
        if "sexo" in df.columns:
            lineas.append("\nDistribución por Sexo:")
            dist_sexo = df["sexo"].value_counts()
            for sexo, cantidad in dist_sexo.items():
                porcentaje = (cantidad / len(df) * 100)
                sexo_label = self._traducir_sexo(sexo)
                lineas.append(f"  • {sexo_label}: {cantidad} casos ({porcentaje:.1f}%)")
        
        # Distribución por edad
        if "edad" in df.columns:
            try:
                edad_valida = pd.to_numeric(df["edad"], errors='coerce').dropna()
                lineas.append("\nEstadísticas de Edad:")
                lineas.append(f"  • Edad promedio: {edad_valida.mean():.1f} años")
                lineas.append(f"  • Edad mínima: {edad_valida.min():.0f} años")
                lineas.append(f"  • Edad máxima: {edad_valida.max():.0f} años")
            except:
                pass
        
        # Tendencia temporal
        if "fecha_notificacion" in df.columns:
            try:
                df_temp = df.copy()
                df_temp["fecha"] = pd.to_datetime(df_temp["fecha_notificacion"], errors='coerce')
                df_temp = df_temp.dropna(subset=["fecha"])
                
                if len(df_temp) > 0:
                    fecha_min = df_temp["fecha"].min()
                    fecha_max = df_temp["fecha"].max()
                    
                    lineas.append("\nRango Temporal:")
                    lineas.append(f"  • Primer caso: {fecha_min.strftime('%Y-%m-%d')}")
                    lineas.append(f"  • Último caso: {fecha_max.strftime('%Y-%m-%d')}")
            except:
                pass
        
        lineas.append("")
        lineas.append("-" * 80)
        lineas.append("RECOMENDACIONES")
        lineas.append("-" * 80)
        
        lineas.append("""
• Realizar seguimiento epidemiológico continuo de los casos
• Implementar medidas de control según el tipo de evento
• Fortalecer la vigilancia en municipios de alto riesgo
• Garantizar la completitud de datos en futuras notificaciones
""")
        
        lineas.append("")
        lineas.append("=" * 80)
        lineas.append("Boletín generado automáticamente por Sistema SIVIGILA")
        lineas.append("=" * 80)
        
        return "\n".join(lineas)
    
    def _generar_boletin_html(self, df: pd.DataFrame, evento_codigo: int = None) -> str:
        """Genera boletín en formato HTML"""
        
        html_parts = []
        comparacion_semanal = self._obtener_comparacion_semanal(df, evento_codigo)
        
        # Estilos CSS
        html_parts.append("""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Boletín SIVIGILA</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f5f5f5;
                    margin: 0;
                    padding: 20px;
                }
                .container {
                    max-width: 900px;
                    margin: 0 auto;
                    background-color: white;
                    padding: 40px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                header {
                    text-align: center;
                    border-bottom: 3px solid #2c3e50;
                    margin-bottom: 30px;
                    padding-bottom: 20px;
                }
                h1 {
                    color: #2c3e50;
                    margin: 0;
                    font-size: 28px;
                }
                .info-evento {
                    background-color: #ecf0f1;
                    padding: 15px;
                    border-radius: 5px;
                    margin-bottom: 20px;
                }
                .section {
                    margin: 25px 0;
                }
                h2 {
                    color: #2980b9;
                    border-bottom: 2px solid #3498db;
                    padding-bottom: 10px;
                    margin-top: 30px;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    margin: 15px 0;
                }
                th, td {
                    border: 1px solid #ddd;
                    padding: 12px;
                    text-align: left;
                }
                th {
                    background-color: #3498db;
                    color: white;
                }
                tr:nth-child(even) {
                    background-color: #f9f9f9;
                }
                .metric {
                    display: inline-block;
                    margin: 10px 20px 10px 0;
                }
                .metric-value {
                    font-size: 24px;
                    font-weight: bold;
                    color: #2980b9;
                }
                .metric-label {
                    font-size: 14px;
                    color: #7f8c8d;
                }
                ul {
                    line-height: 1.8;
                }
                footer {
                    text-align: center;
                    border-top: 1px solid #ddd;
                    margin-top: 30px;
                    padding-top: 20px;
                    color: #7f8c8d;
                    font-size: 12px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <header>
                    <h1>📊 Boletín Epidemiológico SIVIGILA</h1>
        """)
        
        # Información del evento
        if evento_codigo:
            evento_info = self.config.obtener_evento(evento_codigo)
            nombre_evento = evento_info.get("nombre", "Evento desconocido") if evento_info else "Evento desconocido"
            
            html_parts.append(f"""
                    <div class="info-evento">
                        <strong>Evento:</strong> {html.escape(nombre_evento)} (Código {evento_codigo})
                    </div>
            """)
        
        html_parts.append(f"""
                    <p>Generado: {datetime.now().strftime('%d de %B de %Y a las %H:%M:%S')}</p>
                </header>
                
                <div class="section">
                    <h2>📈 Métricas Principales</h2>
                    <div class="metric">
                        <div class="metric-value">{len(df)}</div>
                        <div class="metric-label">Total de Casos</div>
                    </div>
        """)
        
        # Métricas adicionales
        if "municipio" in df.columns:
            html_parts.append(f"""
                    <div class="metric">
                        <div class="metric-value">{df['municipio'].nunique()}</div>
                        <div class="metric-label">Municipios</div>
                    </div>
            """)
        
        if "sexo" in df.columns:
            html_parts.append(f"""
                    <div class="metric">
                        <div class="metric-value">{df['sexo'].nunique()}</div>
                        <div class="metric-label">Categorías de Sexo</div>
                    </div>
            """)
        
        html_parts.append("</div>")

        if comparacion_semanal:
            html_parts.append(f"""
                <div class="section">
                    <h2>↔️ Comparación Semanal</h2>
                    <p>
                        Para la semana epidemiológica {comparacion_semanal['week']} de {comparacion_semanal['target_year']}
                        se registraron <strong>{comparacion_semanal['current_year_cases']} casos</strong>, frente a
                        <strong>{comparacion_semanal['previous_year_cases']} casos</strong> en la misma semana de
                        {comparacion_semanal['previous_year']}.
                    </p>
                    <ul>
                        <li>Diferencia: {html.escape(comparacion_semanal['difference_text'])}</li>
                        <li>Comportamiento: {html.escape(comparacion_semanal['trend_label'])}</li>
                        <li>{html.escape(comparacion_semanal['summary_sentence'])}</li>
                    </ul>
                </div>
            """)
        
        # Municipios más afectados
        if "municipio" in df.columns:
            html_parts.append("""
                <div class="section">
                    <h2>🏢 Municipios Más Afectados</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>Municipio</th>
                                <th>Casos</th>
                                <th>Porcentaje</th>
                            </tr>
                        </thead>
                        <tbody>
            """)
            
            top_mun = df["municipio"].value_counts().head(10)
            for municipio, casos in top_mun.items():
                porcentaje = (casos / len(df) * 100)
                html_parts.append(f"""
                            <tr>
                                <td>{html.escape(str(municipio))}</td>
                                <td>{casos}</td>
                                <td>{porcentaje:.1f}%</td>
                            </tr>
                """)
            
            html_parts.append("""
                        </tbody>
                    </table>
                </div>
            """)
        
        # Distribución demográfica
        html_parts.append("""
                <div class="section">
                    <h2>👥 Distribución Demográfica</h2>
        """)
        
        if "sexo" in df.columns:
            html_parts.append("<h3>Sexo</h3><ul>")
            for sexo, casos in df["sexo"].value_counts().items():
                porcentaje = (casos / len(df) * 100)
                sexo_label = self._traducir_sexo(sexo)
                html_parts.append(f"<li>{sexo_label}: {casos} casos ({porcentaje:.1f}%)</li>")
            html_parts.append("</ul>")
        
        if "edad" in df.columns:
            try:
                edad_valida = pd.to_numeric(df["edad"], errors='coerce').dropna()
                html_parts.append("<h3>Edad</h3><ul>")
                html_parts.append(f"<li>Promedio: {edad_valida.mean():.1f} años</li>")
                html_parts.append(f"<li>Mínimo: {edad_valida.min():.0f} años</li>")
                html_parts.append(f"<li>Máximo: {edad_valida.max():.0f} años</li>")
                html_parts.append("</ul>")
            except:
                pass
        
        html_parts.append("</div>")
        
        # Recomendaciones
        html_parts.append("""
                <div class="section">
                    <h2>💡 Recomendaciones</h2>
                    <ul>
                        <li>Continuar con la vigilancia epidemiológica activa</li>
                        <li>Implementar medidas de control según protocolo del evento</li>                        <li>Fortalecer la vigilancia en municipios de riesgo</li>
                        <li>Garantizar completitud de datos en futuras notificaciones</li>
                        <li>Realizar análisis de tendencias periódicamente</li>
                    </ul>
                </div>
                
                <footer>
                    <p>Boletín generado automáticamente por Sistema SIVIGILA</p>
                    <p>Información confidencial - Uso restringido a autoridades sanitarias</p>
                </footer>
            </div>
        </body>
        </html>
        """)
        
        return "".join(html_parts)

    def _obtener_comparacion_semanal(self, df: pd.DataFrame, evento_codigo: Optional[int]) -> Optional[Dict[str, Any]]:
        """Obtiene la comparación de la semana del boletín contra la misma semana del año anterior."""
        if evento_codigo is None:
            return None

        periodo = self._resolver_periodo_boletin(df)
        if periodo is None:
            return None

        anio, semana = periodo
        cache_key = (int(evento_codigo), anio, semana)
        if cache_key in self._comparacion_cache:
            return self._comparacion_cache[cache_key]

        try:
            client = BulletinAppsScriptClient()
            comparacion = client.comparar_semana(anio=anio, semana=semana)
        except Exception as exc:
            self.logger.warning(
                f"No fue posible consultar la comparación semanal del boletín para la semana {semana} de {anio}: {exc}"
            )
            self._comparacion_cache[cache_key] = None
            return None

        response_event_code = comparacion.get("event_code")
        if response_event_code is not None and int(response_event_code) != int(evento_codigo):
            self.logger.warning(
                f"Se omitió la comparación semanal: el Apps Script respondió para el evento {response_event_code} "
                f"y el boletín se está generando para el evento {evento_codigo}."
            )
            self._comparacion_cache[cache_key] = None
            return None

        trend_code = str(comparacion.get("trend") or "sin_dato").strip().lower()
        current_cases = comparacion.get("current_year_cases")
        previous_cases = comparacion.get("previous_year_cases")
        difference = comparacion.get("absolute_change")
        percent_change = comparacion.get("percent_change")
        trend_label = self._traducir_tendencia_comparativa(trend_code)

        enriched = {
            **comparacion,
            "week": int(comparacion.get("week") or semana),
            "target_year": int(comparacion.get("target_year") or anio),
            "previous_year": int(comparacion.get("previous_year") or (anio - 1)),
            "current_year_cases": current_cases,
            "previous_year_cases": previous_cases,
            "difference_text": self._formatear_diferencia(difference, percent_change),
            "trend_label": trend_label,
            "summary_sentence": self._construir_resumen_tendencia(
                week=int(comparacion.get("week") or semana),
                target_year=int(comparacion.get("target_year") or anio),
                previous_year=int(comparacion.get("previous_year") or (anio - 1)),
                current_cases=current_cases,
                previous_cases=previous_cases,
                difference=difference,
                percent_change=percent_change,
                trend_label=trend_label,
            ),
        }

        self._comparacion_cache[cache_key] = enriched
        return enriched

    @staticmethod
    def _resolver_periodo_boletin(df: pd.DataFrame) -> Optional[tuple[int, int]]:
        """Deriva año ISO y semana ISO usando la fecha más reciente del archivo del boletín."""
        if "fecha_notificacion" not in df.columns:
            return None

        fechas = pd.to_datetime(df["fecha_notificacion"], errors="coerce").dropna()
        if fechas.empty:
            return None

        fecha_referencia = fechas.max()
        iso = fecha_referencia.isocalendar()
        return int(iso.year), int(iso.week)

    @staticmethod
    def _traducir_tendencia_comparativa(trend_code: str) -> str:
        mapeo = {
            "aumento": "aumentó",
            "disminucion": "disminuyó",
            "igual": "se mantuvo",
            "sin_dato": "sin dato comparable",
        }
        return mapeo.get(trend_code, trend_code or "sin dato comparable")

    @staticmethod
    def _formatear_diferencia(difference: Any, percent_change: Any) -> str:
        if difference is None:
            return "sin diferencia calculable"

        texto = f"{difference} casos"
        if percent_change is not None:
            texto += f" ({percent_change}%)"
        return texto

    @staticmethod
    def _construir_resumen_tendencia(
        week: int,
        target_year: int,
        previous_year: int,
        current_cases: Any,
        previous_cases: Any,
        difference: Any,
        percent_change: Any,
        trend_label: str,
    ) -> str:
        if current_cases is None or previous_cases is None:
            return (
                f"No fue posible comparar la semana {week} de {target_year} con la misma semana de {previous_year}."
            )

        resumen = (
            f"La semana {week} de {target_year} presentó {current_cases} casos frente a {previous_cases} "
            f"en la misma semana de {previous_year}; el comportamiento {trend_label}"
        )

        if difference is not None:
            resumen += f" con una diferencia de {difference} casos"
            if percent_change is not None:
                resumen += f" ({percent_change}%)"

        return resumen + "."
    
    @staticmethod
    def _traducir_sexo(sexo: str) -> str:
        """Traduce códigos de sexo a etiquetas descriptivas"""
        mapeo = {
            "M": "Masculino",
            "F": "Femenino",
            "O": "Otro",
            "1": "Masculino",
            "2": "Femenino",
            "3": "Otro"
        }
        return mapeo.get(str(sexo).upper(), str(sexo))
    
    def guardar_boletin(self, contenido: str, nombre_archivo: str,
                       formato: str = "texto") -> tuple:
        """
        Guarda el boletín a archivo
        
        Args:
            contenido: Contenido del boletín
            nombre_archivo: Nombre sin extensión
            formato: 'texto' o 'html'
            
        Returns:
            Tupla (exitoso, ruta)
        """
        try:
            carpeta = self.settings.OUTPUT_DIR
            carpeta.mkdir(parents=True, exist_ok=True)
            
            extension = ".html" if formato == "html" else ".txt"
            ruta = carpeta / f"{nombre_archivo}{extension}"
            
            with open(ruta, 'w', encoding='utf-8') as f:
                f.write(contenido)
            
            self.logger.info(f"Boletín guardado: {ruta}")
            return True, str(ruta)
            
        except Exception as e:
            self.logger.error(f"Error guardando boletín: {e}")
            return False, str(e)


if __name__ == "__main__":
    print("=== PRUEBA DEL MÓDULO BOLETIN ===")
    
    generador = GeneradorBoletin()
    print("Generador de boletinesnitializado")
