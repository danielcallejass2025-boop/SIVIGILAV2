#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor HTTP Local para Dashboard Evento 549
Morbilidad Materna Extrema - SIVIGILA Risaralda
"""

import http.server
import socketserver
import warnings
import threading
import os
import webbrowser
import json
import re
from pathlib import Path
from datetime import datetime
import sys
import pandas as pd
from urllib.parse import urlparse, parse_qs

# Configuración
PORT = 8000

class ColoredHandler(http.server.SimpleHTTPRequestHandler):
    """Handler con mensajes coloreados y API endpoints"""

    CACHE_LOCK = threading.Lock()
    CACHE_DATA = {
        'path': None,
        'mtime': None,
        'df': None,
    }

    MUNICIPIOS_RISARALDA = [
        'APIA',
        'BALBOA',
        'BELEN DE UMBRIA',
        'DOSQUEBRADAS',
        'GUATICA',
        'LA CELIA',
        'LA VIRGINIA',
        'MARSELLA',
        'MISTRATO',
        'PEREIRA',
        'PUEBLO RICO',
        'QUINCHIA',
        'SANTA ROSA DE CABAL',
        'SANTUARIO'
    ]

    MUNICIPIOS_OFICIALES = {
        'apia': 'APIA',
        'balboa': 'BALBOA',
        'belen de umbria': 'BELEN DE UMBRIA',
        'dosquebradas': 'DOSQUEBRADAS',
        'guatica': 'GUATICA',
        'la celia': 'LA CELIA',
        'la virginia': 'LA VIRGINIA',
        'marsella': 'MARSELLA',
        'mistrato': 'MISTRATO',
        'pereira': 'PEREIRA',
        'pueblo rico': 'PUEBLO RICO',
        'quinchia': 'QUINCHIA',
        'santa rosa de cabal': 'SANTA ROSA DE CABAL',
        'santuario': 'SANTUARIO'
    }

    MUNICIPIOS_COORDS = {
        'pereira': (-75.70, 4.81),
        'dosquebradas': (-75.73, 4.84),
        'santa rosa de cabal': (-75.63, 4.85),
        'la virginia': (-75.88, 4.86),
        'santuario': (-75.74, 5.55),
        'marsella': (-75.73, 4.95),
        'belen de umbria': (-75.80, 5.27),
        'quinchia': (-75.69, 5.03),
        'apia': (-75.78, 5.08),
        'mistrato': (-75.93, 5.18),
        'pueblo rico': (-75.64, 5.22),
        'guatica': (-75.59, 5.30),
        'la celia': (-75.65, 4.98),
        'balboa': (-75.68, 4.75)
    }

    def _normalize_text(self, value):
        if value is None:
            return ''
        txt = str(value).strip().lower()
        txt = txt.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
        txt = txt.replace('ñ', 'n')
        txt = re.sub(r'\s+', ' ', txt)
        return txt

    def _first_existing_col(self, columns, candidates):
        normalized = {self._normalize_text(c): c for c in columns}
        for cand in candidates:
            if cand in normalized:
                return normalized[cand]
        return None

    def _canonical_municipio(self, value):
        txt = str(value).strip()
        if not txt:
            return 'SIN MUNICIPIO'
        norm = self._normalize_text(txt)
        return self.MUNICIPIOS_OFICIALES.get(norm, txt.upper())

    def _to_datetime(self, series):
        if series is None:
            return pd.to_datetime(series, errors='coerce')

        s = series.astype(str).str.strip()
        s = s.replace({'nan': '', 'NaN': '', 'None': '', 'none': '', 'NaT': '', 'nat': '', 'NULL': '', 'null': ''})
        s = s.where(~s.str.match(r'^[\-\s/]+$', na=False), '')

        parsed = pd.Series(pd.NaT, index=series.index, dtype='datetime64[ns]')
        formatos = [
            '%d/%m/%Y',
            '%Y-%m-%d',
            '%d/%m/%Y %H:%M:%S',
            '%Y-%m-%d %H:%M:%S'
        ]

        for fmt in formatos:
            mask = parsed.isna() & s.ne('')
            if mask.any():
                parsed.loc[mask] = pd.to_datetime(s.loc[mask], format=fmt, errors='coerce')

        # Fallback silencioso para casos atipicos sin inundar el log
        mask_restante = parsed.isna() & s.ne('')
        if mask_restante.any():
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', category=UserWarning)
                parsed.loc[mask_restante] = pd.to_datetime(
                    s.loc[mask_restante],
                    errors='coerce',
                    dayfirst=True
                )

        return parsed

    def _to_numeric(self, series):
        return pd.to_numeric(series, errors='coerce')

    def _load_dataframe_cached(self, archivo):
        """Carga archivo depurado con cache para acelerar filtros consecutivos."""
        path = str(archivo)
        mtime = float(archivo.stat().st_mtime)

        with self.CACHE_LOCK:
            cached = self.CACHE_DATA
            if cached['path'] == path and cached['mtime'] == mtime and cached['df'] is not None:
                return cached['df'].copy()

        if archivo.suffix in ['.xlsx', '.xls']:
            df = pd.read_excel(archivo)
        else:
            df = pd.read_csv(archivo, encoding='utf-8')

        with self.CACHE_LOCK:
            self.CACHE_DATA['path'] = path
            self.CACHE_DATA['mtime'] = mtime
            self.CACHE_DATA['df'] = df

        return df.copy()

    def _is_yes(self, value):
        if pd.isna(value):
            return False
        txt = self._normalize_text(value)
        return txt in {'1', 'si', 's', 'true', 'verdadero', 'yes', 'y'}

    def _clasificacion_razon(self, razon):
        if razon >= 400:
            return 'CRITICO'
        if razon >= 300:
            return 'MUY ALTO'
        if razon >= 200:
            return 'ALTO'
        if razon >= 150:
            return 'MOD-ALTO'
        if razon >= 100:
            return 'MODERADO'
        if razon >= 50:
            return 'BAJO'
        if razon > 0:
            return 'MUY BAJO'
        return 'SIN CASOS'

    def _build_dashboard_data(self, df, archivo):
        total = int(len(df))
        cols = list(df.columns)

        col_edad = self._first_existing_col(cols, ['edad'])
        col_semana = self._first_existing_col(cols, ['semana'])
        col_ano = self._first_existing_col(cols, ['ano', 'año'])
        col_afiliacion = self._first_existing_col(cols, ['tip_ss', 'tipo_afiliacion', 'afiliacion'])
        col_municipio = self._first_existing_col(cols, ['nmun_resi', 'municipio', 'mun_resi', 'nom_mun_r'])
        col_fec_not = self._first_existing_col(cols, ['fec_not', 'fecha_notificacion'])
        col_ini_sin = self._first_existing_col(cols, ['ini_sin', 'fecha_inicio_sintomas'])
        col_fec_hos = self._first_existing_col(cols, ['fec_hos', 'fecha_hospitalizacion'])
        col_hos = self._first_existing_col(cols, ['pac_hos', 'hospitalizado'])
        col_reconsulta = self._first_existing_col(cols, ['pte_remtda', 'reconsulta'])
        col_control = self._first_existing_col(cols, ['no_con_pre', 'control_prenatal'])
        col_uci = self._first_existing_col(cols, ['ingres_uci', 'uci'])
        col_dias_hospi = self._first_existing_col(cols, ['dias_hospi', 'dias_hospitalizacion'])
        col_causa = self._first_existing_col(cols, ['caus_agrup', 'caus_princ'])
        col_momento = self._first_existing_col(cols, ['term_gesta', 'moc_rel_tg'])
        col_num_vivos = self._first_existing_col(cols, ['num_vivos'])

        anio = datetime.now().year
        anos = pd.Series(dtype='int64')
        if col_ano:
            anos = self._to_numeric(df[col_ano]).dropna().astype(int)
            if not anos.empty:
                # Año de análisis: el más reciente presente en el archivo depurado.
                anio = int(anos.max())

        grupos_edad = []
        if col_edad:
            edades = self._to_numeric(df[col_edad])
            bins = [0, 19, 24, 29, 34, 39, 200]
            labels = ['15-19 años', '20-24 años', '25-29 años', '30-34 años', '35-39 años', '40+ años']
            cat = pd.cut(edades, bins=bins, labels=labels, include_lowest=True)
            for label in labels:
                casos = int((cat == label).sum())
                grupos_edad.append({
                    'grupo': label,
                    'casos': casos,
                    'porcentaje': round((casos / total) * 100, 1) if total else 0
                })
        else:
            grupos_edad = [
                {'grupo': '15-19 años', 'casos': 0, 'porcentaje': 0},
                {'grupo': '20-24 años', 'casos': 0, 'porcentaje': 0},
                {'grupo': '25-29 años', 'casos': 0, 'porcentaje': 0},
                {'grupo': '30-34 años', 'casos': 0, 'porcentaje': 0},
                {'grupo': '35-39 años', 'casos': 0, 'porcentaje': 0},
                {'grupo': '40+ años', 'casos': 0, 'porcentaje': 0}
            ]

        afiliacion = []
        if col_afiliacion:
            mapa = {
                '1': 'Contributivo', '2': 'Subsidiado', '3': 'Especial', '4': 'Excepción', '5': 'No asegurado',
                'C': 'Contributivo', 'S': 'Subsidiado', 'E': 'Especial', 'P': 'Excepción',
                'N': 'No asegurado', 'I': 'Indeterminado'
            }
            serie = df[col_afiliacion].fillna('No especificado').astype(str).str.strip().str.upper()
            serie = serie.apply(lambda v: mapa.get(v, v.title() if len(v) > 2 else v))
            vc = serie.value_counts()
            for tipo, casos in vc.items():
                afiliacion.append({
                    'tipo': str(tipo),
                    'casos': int(casos),
                    'porcentaje': round((int(casos) / total) * 100, 1) if total else 0
                })

        semanas = []
        if col_semana:
            sem_series = self._to_numeric(df[col_semana]).dropna().astype(int)
            if col_ano:
                an_series = self._to_numeric(df[col_ano]).fillna(anio).astype(int)
                tmp = pd.DataFrame({'sem': sem_series, 'ano': an_series.loc[sem_series.index]})
                g = tmp.groupby(['ano', 'sem']).size().reset_index(name='casos')
                sems = sorted(tmp['sem'].unique().tolist())
                for sem in sems:
                    actual = int(g[(g['ano'] == anio) & (g['sem'] == sem)]['casos'].sum())
                    previo = int(g[(g['ano'] == anio - 1) & (g['sem'] == sem)]['casos'].sum())
                    semanas.append({'semana': int(sem), 'casos': actual, 'año2025': previo})
            else:
                vc = sem_series.value_counts().sort_index()
                for sem, casos in vc.items():
                    semanas.append({'semana': int(sem), 'casos': int(casos), 'año2025': 0})

        causas = []
        mapa_causas = {
            '1': 'Trastornos hipertensivos', '2': 'Hemorragia obstétrica', '3': 'Sepsis obstétrica',
            '4': 'Otra causa', '5': 'Complicación del aborto', '6': 'Enfermedad preexistente',
            '7': 'Complicación anestésica', '8': 'Evento tromboembólico'
        }
        if col_causa:
            serie_c = df[col_causa].fillna('No especificada').astype(str).str.strip().replace('', 'No especificada')
            serie_c = serie_c.apply(lambda v: mapa_causas.get(v, v))
            vc = serie_c.value_counts().head(5)
            for causa, casos in vc.items():
                causas.append({'causa': str(causa), 'casos': int(casos), 'porcentaje': round((int(casos) / total) * 100, 1) if total else 0})

        momento_evento = []
        mapa_momento = {
            '1': 'Aborto', '2': 'Embarazo ectópico/molar', '3': 'Anteparto',
            '4': 'Intraparto', '5': 'Postparto', '6': 'Puerperio tardío'
        }
        if col_momento:
            serie_m2 = df[col_momento].fillna('No especificado').astype(str).str.strip().replace('', 'No especificado')
            serie_m2 = serie_m2.apply(lambda v: mapa_momento.get(v, v))
            vc = serie_m2.value_counts().head(3)
            for momento, casos in vc.items():
                momento_evento.append({'momento': str(momento), 'casos': int(casos), 'porcentaje': round((int(casos) / total) * 100, 1) if total else 0})

        municipios = []
        territoriales = []
        if col_municipio:
            serie_m = df[col_municipio].fillna('Sin municipio').astype(str).str.strip().replace('', 'Sin municipio')
            serie_m = serie_m.apply(self._canonical_municipio)
            vc = serie_m.value_counts()

            num_vivos_map = {}
            if col_num_vivos:
                tmp = pd.DataFrame({'mun': serie_m, 'nv': self._to_numeric(df[col_num_vivos]).fillna(0)})
                num_vivos_map = tmp.groupby('mun')['nv'].sum().to_dict()

            for mun, casos in vc.items():
                casos_i = int(casos)
                nv = int(round(float(num_vivos_map.get(mun, 0)))) if num_vivos_map else 0
                razon = round((casos_i / nv) * 1000, 1) if nv > 0 else 0.0
                norm = self._normalize_text(mun)
                lon, lat = self.MUNICIPIOS_COORDS.get(norm, (-75.73, 4.95))

                municipios.append({
                    'nombre': str(mun),
                    'casos': casos_i,
                    'latitud': lat,
                    'longitud': lon,
                    'estado': 'PRIORITARIO' if casos_i >= max(1, round(total * 0.1)) else 'MONITOREO'
                })

                territoriales.append({
                    'nombre': str(mun),
                    'casos': casos_i,
                    'nv2025': nv,
                    'razonMME': razon,
                    'latitud': lat,
                    'longitud': lon,
                    'clasificacion': self._clasificacion_razon(razon)
                })

            # Garantizar presencia de los 14 municipios de Risaralda (aunque queden en 0)
            existentes = {self._normalize_text(m['nombre']) for m in municipios}
            for mun in self.MUNICIPIOS_RISARALDA:
                norm = self._normalize_text(mun)
                if norm in existentes:
                    continue
                lon, lat = self.MUNICIPIOS_COORDS.get(norm, (-75.73, 4.95))
                municipios.append({
                    'nombre': mun,
                    'casos': 0,
                    'latitud': lat,
                    'longitud': lon,
                    'estado': 'SIN CASOS'
                })
                territoriales.append({
                    'nombre': mun,
                    'casos': 0,
                    'nv2025': 0,
                    'razonMME': 0.0,
                    'latitud': lat,
                    'longitud': lon,
                    'clasificacion': self._clasificacion_razon(0)
                })

        notif_oportuna = 0
        notif_tardia = 0
        if col_fec_not:
            f_not = self._to_datetime(df[col_fec_not])
            f_ref = None
            if col_ini_sin:
                f_ini = self._to_datetime(df[col_ini_sin])
                if f_ini.notna().sum() > 0:
                    f_ref = f_ini
            if f_ref is None and col_fec_hos:
                f_hos = self._to_datetime(df[col_fec_hos])
                if f_hos.notna().sum() > 0:
                    f_ref = f_hos

            if f_ref is not None:
                delta = (f_not - f_ref).dt.days
                delta = delta[delta >= 0]
            else:
                delta = pd.Series(dtype='float64')

            valid = delta.notna()
            if valid.sum() > 0:
                notif_oportuna = int((delta[valid] <= 7).sum())
                notif_tardia = int((delta[valid] > 7).sum())

        hospitalizacion = 0
        if col_hos:
            hospitalizacion = int(df[col_hos].apply(self._is_yes).sum())
        elif col_dias_hospi:
            hospitalizacion = int((self._to_numeric(df[col_dias_hospi]).fillna(0) > 0).sum())

        reconsulta = int(df[col_reconsulta].apply(self._is_yes).sum()) if col_reconsulta else 0
        control_prenatal = int((self._to_numeric(df[col_control]).fillna(0) > 0).sum()) if col_control else 0
        requiere_uci = int(df[col_uci].apply(self._is_yes).sum()) if col_uci else 0
        dias_promedio = round(float(self._to_numeric(df[col_dias_hospi]).dropna().mean()), 1) if col_dias_hospi else 0

        criticas = [c for c in [col_edad, col_afiliacion, col_municipio, col_fec_not, col_ini_sin, col_hos, col_dias_hospi] if c]
        completitud = 0
        if criticas and total > 0:
            total_celdas = len(criticas) * total
            completas = 0
            for c in criticas:
                s = df[c]
                completas += int((s.notna() & (s.astype(str).str.strip() != '')).sum())
            completitud = round((completas / total_celdas) * 100, 1)

        calidad_municipios = []
        if col_municipio and col_fec_not:
            f_not = self._to_datetime(df[col_fec_not])
            f_ref = None
            if col_ini_sin:
                f_ini = self._to_datetime(df[col_ini_sin])
                if f_ini.notna().sum() > 0:
                    f_ref = f_ini
            if f_ref is None and col_fec_hos:
                f_hos = self._to_datetime(df[col_fec_hos])
                if f_hos.notna().sum() > 0:
                    f_ref = f_hos

            if f_ref is not None:
                delta = (f_not - f_ref).dt.days
                delta = delta.where(delta >= 0)
                tmp = pd.DataFrame({'mun': df[col_municipio].fillna('Sin municipio').astype(str), 'delta': delta})
                for mun, grp in tmp.groupby('mun'):
                    valid = grp['delta'].dropna()
                    if valid.empty:
                        oport = tard = 0
                    else:
                        oport = int((valid <= 7).sum())
                        tard = int((valid > 7).sum())
                    denom = oport + tard
                    calidad_municipios.append({
                        'municipio': str(mun),
                        'oportunos': oport,
                        'tardios': tard,
                        'porcentaje': round((oport / denom) * 100, 1) if denom else 0
                    })

        casos_actuales = total
        casos_bases = 0
        if not anos.empty:
            casos_actuales = int((anos == anio).sum())
            casos_bases = int((anos == (anio - 1)).sum())

        variacion = None
        if casos_bases > 0:
            variacion = round(((casos_actuales - casos_bases) / casos_bases) * 100, 1)

        # Distribución de días de notificación
        dias_notificacion = [
            {'rango': '1-7 días (Oportuno)', 'casos': 0, 'porcentaje': 0},
            {'rango': '8-14 días (Tardío)', 'casos': 0, 'porcentaje': 0},
            {'rango': '15-30 días (Muy tardío)', 'casos': 0, 'porcentaje': 0},
            {'rango': '>30 días (Crítico)', 'casos': 0, 'porcentaje': 0}
        ]
        if col_fec_not:
            f_not2 = self._to_datetime(df[col_fec_not])
            # Intentar primero ini_sin, si falla usar fec_hos como proxy
            f_ref = None
            if col_ini_sin:
                f_ref = self._to_datetime(df[col_ini_sin])
                if f_ref.isna().sum() == len(f_ref):
                    f_ref = None
            if f_ref is None and col_fec_hos:
                f_ref = self._to_datetime(df[col_fec_hos])
            if f_ref is not None:
                delta2 = (f_not2 - f_ref).dt.days.dropna()
                delta2 = delta2[delta2 >= 0]
                if not delta2.empty:
                    bins_d = [(-999, 7), (8, 14), (15, 30), (31, 9999)]
                    for i, (lo, hi) in enumerate(bins_d):
                        c = int(((delta2 >= lo) & (delta2 <= hi)).sum())
                        dias_notificacion[i]['casos'] = c
                        dias_notificacion[i]['porcentaje'] = round((c / total) * 100, 1) if total else 0

        # Estadísticas de edad
        edad_stats = {'promedio': 0, 'minima': 0, 'maxima': 0, 'moda': 0}
        if col_edad:
            edades_num = self._to_numeric(df[col_edad]).dropna()
            if not edades_num.empty:
                edad_stats['promedio'] = round(float(edades_num.mean()), 1)
                edad_stats['minima'] = int(edades_num.min())
                edad_stats['maxima'] = int(edades_num.max())
                edad_stats['moda'] = int(edades_num.mode().iloc[0]) if not edades_num.mode().empty else 0

        dashboard = {
            'codigo': 549,
            'nombre': 'Morbilidad materna extrema',
            'subtitulo': 'Morbilidad Materna Extrema (MME)',
            'año': anio,
            'fechaActualizacion': datetime.fromtimestamp(archivo.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            'totalCasos': total,
            'variacionAnual': variacion,
            'casosActuales': casos_actuales,
            'casosBases': casos_bases,
            'anioComparacion': anio - 1,
            'municipios': sorted(municipios, key=lambda x: x['casos'], reverse=True),
            'municipiosTerritoriales': sorted(territoriales, key=lambda x: x['razonMME'], reverse=True),
            'gruposEdad': grupos_edad,
            'afiliacion': afiliacion,
            'causas': causas,
            'momentoEvento': momento_evento,
            'semanas': semanas,
            'calidad': {
                'notificacionOportuna': notif_oportuna,
                'notificacionTardia': notif_tardia,
                'porcentajeOportunidad': round((notif_oportuna / (notif_oportuna + notif_tardia)) * 100, 1) if (notif_oportuna + notif_tardia) else 0,
                'completitud': completitud,
                'hospitalizacion': hospitalizacion,
                'porcentajeHospitalizacion': round((hospitalizacion / total) * 100, 1) if total else 0,
                'reconsulta': reconsulta,
                'porcentajeReconsulta': round((reconsulta / total) * 100, 1) if total else 0,
                'controlPrenatal': control_prenatal,
                'porcentajeControlPrenatal': round((control_prenatal / total) * 100, 1) if total else 0,
                'requiereUCI': requiere_uci,
                'porcentajeUCI': round((requiere_uci / total) * 100, 1) if total else 0,
                'diasPromedio': dias_promedio
            },
            'calidadMunicipios': sorted(calidad_municipios, key=lambda x: x['porcentaje'], reverse=True),
            'diasNotificacion': dias_notificacion,
            'edadEstadisticas': edad_stats
        }

        return dashboard
    
    def log_message(self, format, *args):
        """Sobrescribir mensajes de log con colores"""
        # Colores ANSI
        VERDE = '\033[92m'
        AMARILLO = '\033[93m'
        ROJO = '\033[91m'
        AZUL = '\033[94m'
        RESET = '\033[0m'
        BOLD = '\033[1m'
        
        # Formatear hora
        tiempo = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if "GET" in format or "POST" in format:
            # Solicitud HTTP
            mensaje = f"{AZUL}{tiempo}{RESET} {VERDE}→{RESET} " + (format % args)
            print(mensaje)
        elif "200" in str(args):
            # Éxito
            mensaje = f"{AZUL}{tiempo}{RESET} {VERDE}✓{RESET} {format % args}"
            print(mensaje)
        elif "404" in str(args):
            # No encontrado
            mensaje = f"{AZUL}{tiempo}{RESET} {ROJO}✗{RESET} {format % args}"
            print(mensaje)
        else:
            # Otros
            print(f"{AZUL}{tiempo}{RESET} {format % args}")

    def do_GET(self):
        """Manejar solicitudes GET - archivos estáticos y API"""
        parsed_path = urlparse(self.path)
        
        # Manejo de endpoints de API
        if parsed_path.path == '/api/datos-evento-549':
            self.handle_api_datos()
            return
        
        # Manejo de archivos estáticos
        if parsed_path.path == '/':
            self.path = '/evento_549_dashboard.html'
        
        return super().do_GET()
    
    def handle_api_datos(self):
        """Endpoint API para obtener datos del evento 549"""
        try:
            # Parsear query parameters
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            municipio_filtro = params.get('municipio', [None])[0]

            # Buscar archivo depurado más reciente
            data_dir = Path('data/DEPURADO')
            if not data_dir.exists():
                self.send_json_error('Data directory not found', 404)
                return
            
            # Buscar archivos Excel o CSV depurados (patrón: *_549_*.xlsx o cualquier .xlsx/.csv)
            excel_files = list(data_dir.glob('*_549_*.xlsx')) + list(data_dir.glob('*_549_*.xls'))
            csv_files = list(data_dir.glob('*_549_*.csv'))
            archivos = excel_files + csv_files
            
            # Excluir boletines y reportes JSON
            archivos = [a for a in archivos if '_boletin' not in a.name and '_reporte' not in a.name]
            
            if not archivos:
                self.send_json_error('No se encontraron archivos depurados del evento 549', 404)
                return
            
            # Tomar el más reciente
            archivo = max(archivos, key=lambda x: x.stat().st_mtime)
            
            # Leer datos (con cache en memoria para mejorar rendimiento)
            df = self._load_dataframe_cached(archivo)

            # Obtener lista de municipios disponibles ANTES de filtrar
            col_municipio = self._first_existing_col(list(df.columns), ['nmun_resi', 'municipio', 'mun_resi', 'nom_mun_r'])
            municipios_disponibles = list(self.MUNICIPIOS_RISARALDA)
            if col_municipio:
                serie_m = df[col_municipio].fillna('Sin municipio').astype(str).str.strip().apply(self._canonical_municipio)
                extras = [m for m in sorted(serie_m.unique().tolist()) if m not in municipios_disponibles and m != 'SIN MUNICIPIO']
                municipios_disponibles = sorted(municipios_disponibles + extras)

            total_sin_filtro = len(df)

            # Aplicar filtro de municipio si se proporcionó
            if municipio_filtro and col_municipio:
                norm_filtro = self._normalize_text(municipio_filtro)
                mask = df[col_municipio].fillna('').astype(str).str.strip().apply(
                    lambda v: self._normalize_text(v) == norm_filtro
                )
                df = df[mask].copy()
            
            # Procesar datos
            datos = {
                'evento': 549,
                'archivo_depurado': archivo.name,
                'archivo_depurado_ruta': str(archivo),
                'archivo_modificado': datetime.fromtimestamp(archivo.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'total_casos': len(df),
                'total_sin_filtro': total_sin_filtro,
                'municipio_filtro': municipio_filtro,
                'municipios_disponibles': municipios_disponibles,
                'columnas': df.columns.tolist(),
                'dashboard_data': self._build_dashboard_data(df, archivo)
            }
            
            self.send_json(datos)
            
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # El cliente cerró la conexión (p. ej., cambio rápido de filtro); no es error funcional del servidor.
            return
        except Exception as e:
            try:
                self.send_json_error(str(e), 500)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                return
    
    def send_json(self, data, status_code=200):
        """Enviar respuesta JSON"""
        import math

        def _sanitize(obj):
            if isinstance(obj, float):
                if math.isnan(obj) or math.isinf(obj):
                    return None
                return obj
            if isinstance(obj, dict):
                return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_sanitize(v) for v in obj]
            return obj

        try:
            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.end_headers()

            json_data = json.dumps(_sanitize(data), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            self.wfile.write(json_data)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return
    
    def send_json_error(self, error, status_code):
        """Enviar error como JSON"""
        error_data = {'error': error, 'status': status_code}
        self.send_json(error_data, status_code)


class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """Servidor HTTP concurrente para evitar bloqueos con múltiples requests."""
    allow_reuse_address = True
    daemon_threads = True

def main():
    """Función principal del servidor"""
    
    # Forzar UTF-8 en stdout/stderr para emojis en Windows
    import io
    if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding', '') != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    if hasattr(sys.stderr, 'buffer') and getattr(sys.stderr, 'encoding', '') != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    
    # Colores ANSI
    ROJO = '\033[91m'
    AZUL = '\033[94m'
    VERDE = '\033[92m'
    AMARILLO = '\033[93m'
    VIOLETA = '\033[95m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    # Banner
    print("\n" + "="*70)
    print(f"{BOLD}{VIOLETA}🏥 SERVIDOR DASHBOARD EVENTO 549 - SIVIGILA RISARALDA{RESET}")
    print("="*70)
    print(f"{AMARILLO}Morbilidad Materna Extrema (MME){RESET}\n")
    
    # Información del servidor
    print(f"{BOLD}📡 CONFIGURACIÓN DEL SERVIDOR:{RESET}")
    print(f"  {VERDE}✓{RESET} Host: {AZUL}localhost{RESET}")
    print(f"  {VERDE}✓{RESET} Puerto: {AZUL}{PORT}{RESET}")
    print(f"  {VERDE}✓{RESET} URL: {AZUL}http://localhost:{PORT}{RESET}")
    print(f"  {VERDE}✓{RESET} Ruta: {AZUL}{os.getcwd()}{RESET}\n")
    
    # Archivos servidos
    print(f"{BOLD}📁 ARCHIVOS DISPONIBLES:{RESET}")
    archivos = [
        'evento_549_dashboard.html (Structure)',
        'evento_549_dashboard.css (Styling)',
        'evento_549_dashboard.js (Interactivity)'
    ]
    for archivo in archivos:
        print(f"  {VERDE}✓{RESET} {archivo}")
    
    print(f"\n{BOLD}⌨️  CONTROLES:{RESET}")
    print(f"  {VERDE}Ctrl+C{RESET} - Pausar/Detener servidor")
    print(f"  {AMARILLO}Enter{RESET} - Abrir en navegador (si no se abre automáticamente)")
    
    print("\n" + "="*70)
    print(f"{BOLD}{VERDE}✓ Servidor iniciado - Presiona Ctrl+C para detener{RESET}")
    print("="*70 + "\n")
    
    # Intentar abrir en navegador
    try:
        webbrowser.open(f'http://localhost:{PORT}')
        print(f"{VERDE}✓ Abriendo navegador automáticamente...{RESET}\n")
    except:
        print(f"{AMARILLO}⚠ No se pudo abrir navegador automáticamente{RESET}\n")
    
    # Crear servidor
    try:
        with ThreadingHTTPServer(("", PORT), ColoredHandler) as httpd:
            print(f"{AZUL}[{datetime.now().strftime('%H:%M:%S')}]{RESET} Servidor activo y escuchando...\n")
            httpd.serve_forever()
    
    except KeyboardInterrupt:
        print(f"\n{AMARILLO}[{datetime.now().strftime('%H:%M:%S')}] ⏸ Servidor pausado por usuario{RESET}\n")
        sys.exit(0)
    
    except OSError as e:
        print(f"\n{ROJO}✗ Error: El puerto {PORT} ya está en uso{RESET}")
        print(f"{AMARILLO}  Soluciones:{RESET}")
        print(f"  1. Cierra otras aplicaciones usando ese puerto")
        print(f"  2. Usa otro puerto modificando la variable PORT en este script")
        print(f"  3. Espera unos minutos antes de reintentar\n")
        sys.exit(1)
    
    except Exception as e:
        print(f"\n{ROJO}✗ Error del servidor: {e}{RESET}\n")
        sys.exit(1)

if __name__ == '__main__':
    main()
