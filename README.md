# 🏥 SIVIGILA - Sistema de Vigilancia Epidemiológica

Sistema automatizado de procesamiento de datos epidemiológicos para la Gobernación de Risaralda.

## 📌 Inicio Rápido

### 1. Abrir el Dashboard
```bash
# Simplemente abrir en navegador:
index.html
```

Haz doble clic en `index.html` para abrir el dashboard en tu navegador.

### 2. Ejecutar el Sistema Completo
```bash
# En PowerShell/Terminal (en la carpeta SIVIGILA):
python main.py
```

### 3. Monitoreo Continuo
```bash
python main.py --monitor
```

---

## 📁 Estructura del Proyecto

```
SIVIGILA/
├── index.html                    ← DASHBOARD (Abre en navegador)
├── main.py                       ← Orquestador principal
├── monitor.py                    ← Sistema de monitoreo
├── requirements.txt              ← Dependencias Python
├── README.md                     ← Esta documentación
├── .gitignore                    ← Control de versiones
│
├── config/
│   ├── settings.py               ← Configuración del sistema
│   └── eventos.json              ← Eventos epidemiológicos (3 configurados)
│
├── scripts/
│   ├── __init__.py               ← Módulo de paquete
│   ├── utils.py                  ← Utilidades generales
│   ├── lector_archivos.py        ← Lectura de .xlsx, .xls, .csv, .ods
│   ├── lector_drive.py           ← Integración Google Drive API
│   ├── depuracion_evento_549.py  ← Depuración para Evento 549 (MME)
│   ├── detector_evento.py        ← Detección automática de evento
│   ├── normalizador_columnas.py  ← Estandarización de columnas
│   ├── validador_calidad.py      ← Validación de datos
│   ├── gestor_salida.py          ← Gestión de salida de archivos
│   ├── anonimizar.py             ← Anonimización de datos sensibles
│   └── boletin.py                ← Generador de boletines
│
├── data/
│   ├── ENTRADA_SIVIGILA/         ← Archivos de entrada
│   ├── DEPURADO/                 ← Archivos procesados
│   └── ERROR/                    ← Archivos con errores
│
├── logs/                         ← Logs de ejecución diaria
└── respaldos/                    ← Respaldos de archivos originales
```

---

## 🎯 Archivos Principales

### `index.html` - Dashboard Interactivo
- **Qué es:** Dashboard HTML/CSS/JavaScript con 6 tabs de análisis
- **Colores:** Paleta oficial Gobernación Risaralda (#D71E28, #003DA5)
- **Funcionalidades:**
  - ✅ Filtros en parte superior (Departamento, Sexo, Edad)
  - ✅ Menú completamente expandido (no colapsado)
  - ✅ Mapa REAL de Risaralda con 14 municipios
  - ✅ 6 tabs: Territorial, Población, Tendencias, Mapa, Clínico, Datos
  - ✅ Gráficas interactivas (Plotly, Chart.js)
  - ✅ Métricas KPI en tiempo real
  - ✅ Descarga de datos en CSV
- **Cómo usar:**
  1. Abre `index.html` en tu navegador
  2. Los filtros están en la parte superior
  3. Haz clic en los tabs para navegar
  4. Descarga CSV con un clic

### `main.py` - Orquestador Principal
- Procesa archivos de entrada
- Limpia y depura datos
- Genera boletines automáticos
- Pueden integrarse con el dashboard

### `monitor.py` - Monitoreo Continuo
- Monitorea carpeta de entrada
- Procesa archivos automáticamente
- Genera reportes periódicos

---

## 🚀 Instalación y Dependencias

### Requisitos
- Python 3.8+
- Navegador web moderno (Chrome, Firefox, Edge, Safari)
- Los archivos de entrada en `data/ENTRADA_SIVIGILA/`

### Instalar Dependencias
```bash
pip install -r requirements.txt
```

### Dependencias Principales
```
pandas               - Manipulación de datos
openpyxl            - Lectura/escritura Excel
plotly              - Gráficas interactivas
streamlit           - (opcional, no usado en versión HTML)
google-auth-oauthlib - Google Drive (opcional)
```

---

## 📊 Eventos Soportados

### Evento 549 - Morbilidad Materna Extrema (MME)
- **Descripción:** Complicaciones que ponen en peligro la vida de la gestante
- **Incluye:** Eclampsia, sepsis, hemorragia posparto
- **Análisis:** Territorial, demográfico, clínico

### Evento 52 - Dengue
- **Descripción:** Enfermedad transmitida por mosquito
- **Análisis:** Territorial, semanal, por barrio

### Evento 72 - Sarampión
- **Descripción:** Enfermedad viral altamente contagiosa
- **Análisis:** Territorial, contactos

---

## 🎨 Dashboard Features

### Visualizaciones Disponibles

#### Tab 1: 📍 Territorial
- Distribución de casos por departamento
- Gráfica de barras horizontal
- Tabla con porcentajes

#### Tab 2: 👥 Población
- Distribución por sexo (gráfica pastel)
- Distribución por edad (grupos)
- Análisis demográfico

#### Tab 3: 📈 Tendencias
- Línea temporal de casos
- Identificación de patrones
- Predicción básica

#### Tab 4: 🗺️ Mapa Risaralda
- Mapa interactivo con 14 municipios
- Círculos proporcionales a casos
- Colores gradiente (azul → rojo)
- Tabla detallada de municipios

#### Tab 5: 🔬 Clínico
- Complicaciones principales
- Frecuencia de síntomas
- Análisis de variables clínicas

#### Tab 6: 📋 Datos
- Tabla completa (sin datos sensibles)
- Descarga en CSV
- Selector de cantidad de registros

---

## 🔒 Seguridad de Datos

### Datos Sensibles Automáticamente Eliminados
- Nombres (pri_nom, seg_nom)
- Apellidos (pri_ape, seg_ape)
- Identificación (num_ide)
- Teléfono (telefono, celular)
- Correo (email)
- Dirección (direccion)

El sistema mantiene CERO datos personales identificables en salidas públicas.

---

## 📝 Uso del Sistema

### 1. Procesar Archivo Manual
```bash
python main.py --archivo data/ENTRADA_SIVIGILA/archivo.xlsx
```

### 2. Procesar con Boletín
```bash
python main.py --archivo datos.xlsx --boletin
```

### 3. Monitoreo Continuo
```bash
python main.py --monitor --boletin
```

### 4. Ver Dashboard
```
Simplemente abre: index.html
```

---

## 🎯 Flujo de Datos

```
Archivo de Entrada
    ↓
Lector de Archivos (lector_archivos.py)
    ↓
Detector de Evento (detector_evento.py)
    ↓
Depuración Específica (depuracion_evento_549.py)
    ↓
Validación de Calidad (validador_calidad.py)
    ↓
Normalización (normalizador_columnas.py)
    ↓
Anonimización (anonimizar.py)
    ↓
Archivo Depurado
    ↓
DASHBOARD (index.html) + BOLETÍN
```

---

## 🛠️ Configuración

### `config/eventos.json`
```json
{
  "549": {
    "nombre": "Morbilidad Materna Extrema",
    "tipo": "No transmisible",
    "municipios": [...]
  }
}
```

Personaliza los eventos en este archivo.

---

## 📊 Datos de Entrada

Los archivos deben:
- ✅ Estar en `data/ENTRADA_SIVIGILA/`
- ✅ Ser .xlsx, .xls, .csv o .ods
- ✅ Contener columnas de entrada estándar o similares a:
  - Departamento
  - Municipio
  - Sexo
  - Edad
  - Fecha de notificación
  - Variables clínicas

El sistema detecta automáticamente los nombres de columnas.

---

## 📈 Salida

### Archivos Generados

1. **Archivos Depurados** → `data/DEPURADO/`
   - Misma estructura que entrada
   - Sin datos sensibles
   - Nombre: `EVENTO_DESC_[TIMESTAMP].xlsx`

2. **Boletín** (opcional) → `data/DEPURADO/`
   - Resumen ejecutivo
   - Formato: HTML o TXT
   - Gráficas automáticas

3. **Logs** → `logs/`
   - Ejecución diaria
   - Errores y alertas

---

## 🐛 Solución de Problemas

### El Dashboard no se ve correctamente
- Intenta abrir en navegador diferente
- Limpia caché del navegador (Ctrl+Shift+Del)
- Asegúrate que JavaScript esté habilitado

### Los datos no cargan
- Verifica que haya archivos en `data/DEPURADO/`
- Ejecuta `python main.py` para procesar archivos
- Revisa logs en `logs/`

### Error al procesar archivo
- Verifica formato: .xlsx, .xls, .csv o .ods
- Revisa que las columnas existan
- Mira el archivo en `data/ERROR/` para detalles

---

## 📞 Soporte

Sistema SIVIGILA - Gobernación de Risaralda
Evento 549: Morbilidad Materna Extrema
Año 2026

---

## ✅ Checklist de Uso

- [ ] Archivos de entrada en `data/ENTRADA_SIVIGILA/`
- [ ] Ejecutar: `python main.py`
- [ ] Verificar salida en `data/DEPURADO/`
- [ ] Abrir `index.html` en navegador
- [ ] Explorar 6 tabs del dashboard
- [ ] Usar filtros en parte superior
- [ ] Descargar datos en CSV

---

**Sistema Listo para Producción ✨**
