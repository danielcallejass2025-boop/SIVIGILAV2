# ⚡ INICIO RÁPIDO - SIVIGILA en 5 minutos

## 1️⃣ Instalación (2 minutos)

```bash
# Ir a la carpeta del proyecto
cd c:\Users\{usuario}\Desktop\SIVIGILA

# Crear entorno virtual (opcional pero recomendado)
python -m venv venv
venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```

**¡Listo!** El proyecto está configurado con valores por defecto.

---

## 2️⃣ Preparar Archivos (1 minuto)

Coloca los archivos epidemiológicos en:
```
data/ENTRADA_SIVIGILA/
```

Formatos soportados:
- ✅ `.xlsx` / `.xls` / `.xlsm` (Excel)
- ✅ `.csv` (texto delimitado)
- ✅ `.ods` (OpenDocument)

**Requisito:** Que tengan una columna con el código del evento epidemiológico.

---

## 3️⃣ Procesar Archivos (1 minuto)

### Opción A: Procesar la carpeta completa
```bash
python main.py --local
```

### Opción B: Procesar un archivo específico
```bash
python main.py --archivo data/ENTRADA_SIVIGILA/datos.xlsx
```

### Opción C: Con boletín epidemiológico
```bash
python main.py --local --boletin
```

---

## 4️⃣ Ver Resultados (1 minuto)

### Archivos procesados
```
data/DEPURADO/
├── datos_549_20240406.xlsx
├── datos_549_20240406_reporte.json
└── datos_549_20240406_boletin.html
```

### Dashboard web interactivo
```bash
python main.py --dashboard
```
Se abre en `http://localhost:8501`

---

## 🎯 ¿Qué hace el sistema automáticamente?

✅ Lee cualquier formato de Excel/CSV/ODS
✅ Detecta el código del evento (569+ eventos soportados)
✅ Limpia datos duplicados y vacíos
✅ Elimina datos sensibles (nombres, IDs, teléfonos)
✅ Valida calidad de datos
✅ Genera archivo limpio y anonimizado
✅ Crea reporte de procesamiento
✅ Opcionalmente crea boletín epidemiológico

---

## ⚙️ Configuración Básica (.env)

El archivo `.env` controla el comportamiento:

```env
# LOCAL, DRIVE o HIBRIDO
APP_MODE=LOCAL

# Filtrar solo Risaralda
FILTER_ONLY_RISARALDA=False

# Generar boletín automáticamente
ENABLE_BOLETIN=False

# Eliminar archivo original después de procesar
DELETE_ORIGINAL_AFTER_PROCESS=False

# Formato de salida
OUTPUT_FORMAT=xlsx
```

---

## 📊 Dashboard Web

```bash
python main.py --dashboard
```

**Verás:**
- 📈 Gráficas interactivas de casos por municipio
- 👥 Distribución por sexo y edad
- 📅 Tendencias temporales
- 🔍 Filtros dinámicos importancia
- ⬇️ Opción descargar datos en Excel/CSV

---

## 📂 Estructura de carpetas después de procesar

```
SIVIGILA/
├── data/
│   ├── ENTRADA_SIVIGILA/     ← Coloca archivos aquí
│   ├── DEPURADO/             ← Archivos procesados
│   ├── ERROR/                ← Archivos con errores
│   ├── RESPALDOS/            ← Copias de originales
│   
├── logs/
│   └── sistema.log           ← Ver para troubleshooting
```

---

## 🔧 Problemas Comunes

### "No se encontró columna de código de evento"
- El archivo debe tener una columna con código del evento
- Puede llamarse: `codigo_evento`, `cod_evento`, `id_evento`, etc.

### "Error: No hay datos después de depuración"
- Algunos datos no cumplieron los criterios
- Ver `logs/sistema.log` para detalles
- Ajustar configuración en `.env`

### "Column 'XXXX' not found"
- Nombre de columna mal detectado
- Sistema intenta encontrarlo automáticamente con fuzzy matching

---

## 💡 Casos de Uso Comunes

### Procesar archivos diarios
```bash
# Cada mañana
python main.py --local --boletin
```

### Limpiar y exportar para análisis
```bash
python main.py --archivo datos.xlsx
# Ir a data/DEPURADO y usar el archivo generado
```

### Dashboard para tomar decisiones
```bash
python main.py --dashboard
# Abrir en navegador, explorar datos, descargar reportes
```

### Integración con Google Drive
```bash
# Configurar IDs de carpeta en .env
# Luego:
python main.py --hibrido
```

---

## 📚 Próximos Pasos

1. ✅ Instala las dependencias (`pip install -r requirements.txt`)
2. ✅ Lee este archivo (ya lo hiciste!)
3. ✅ Coloca un archivo de prueba en `data/ENTRADA_SIVIGILA/`
4. ✅ Ejecuta `python main.py --local`
5. ✅ Ve los resultados en `data/DEPURADO/`
6. ✅ Abre el dashboard con `python main.py --dashboard`

---

## ❓ ¿Necesitas ayuda?

- 📖 **README.md**: Documentación completa
- 📜 **logs/sistema.log**: Ver qué pasó
- 💻 **script/dashboard.py**: Ver código del dashboard
- 🔧 **config/settings.py**: Entender configuración

---

**¡Listo!** Ya puedes procesar archivos epidemiológicos de forma segura y automatizada.

Ejecuta: `python main.py --local`

¡Que comience la vigilancia epidemiológica automática!
