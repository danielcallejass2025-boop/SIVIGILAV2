/**
 * bridge_drive.js
 * Puente Node.js ↔ Google Apps Script para el sistema EPIPROCESS
 *
 * Reemplaza la autenticación OAuth directa.
 * Google Apps Script actúa como API intermedia que lee/sube archivos
 * de Google Drive y devuelve los datos en JSON.
 *
 * API endpoints:
 *   ?key=XXX&accion=listar           → Lista archivos en carpeta Drive
 *   ?key=XXX&accion=leer&id=FILE_ID  → Devuelve contenido del archivo
 *
 * Uso:
 *   node bridge_drive.js                  → Lista archivos disponibles
 *   node bridge_drive.js --descargar      → Descarga archivos nuevos a data/ENTRADA_SIVIGILA
 *   node bridge_drive.js --procesar       → Descarga + lanza main.py automáticamente
 */

const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

// ============================================================
// CONFIGURACIÓN
// ============================================================

const API_URL =
  "https://script.google.com/macros/s/AKfycbx6lFYxQtS0sUOIw3713SH5NSwatq-4vYf_eHiedqk3cJgQN_vgzd7rFa1Om-VqLGpd/exec";
const API_KEY = "123456";

// Directorios del proyecto EPIPROCESS (relativos a este script)
const BASE_DIR = __dirname;
const INPUT_DIR = path.join(BASE_DIR, "data", "ENTRADA_SIVIGILA");
const CACHE_PATH = path.join(BASE_DIR, "data", "DEPURADO", ".bridge_cache.json");
const PYTHON_EXE = path.join(BASE_DIR, "venv", "Scripts", "python.exe");
const MAIN_PY = path.join(BASE_DIR, "main.py");

// ============================================================
// CACHE DE ARCHIVOS YA PROCESADOS
// ============================================================

/**
 * Carga el registro de archivos previamente descargados
 * @returns {Set<string>} IDs de archivos ya procesados
 */
function cargarCache() {
  try {
    if (fs.existsSync(CACHE_PATH)) {
      const data = JSON.parse(fs.readFileSync(CACHE_PATH, "utf-8"));
      return new Set(data.procesados || []);
    }
  } catch (err) {
    console.warn("[WARN] No se pudo leer cache, iniciando vacío:", err.message);
  }
  return new Set();
}

/**
 * Guarda el registro de archivos procesados
 * @param {Set<string>} ids - IDs procesados
 */
function guardarCache(ids) {
  try {
    const dir = path.dirname(CACHE_PATH);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    const data = {
      procesados: [...ids],
      ultima_actualizacion: new Date().toISOString(),
    };
    fs.writeFileSync(CACHE_PATH, JSON.stringify(data, null, 2), "utf-8");
  } catch (err) {
    console.error("[ERROR] No se pudo guardar cache:", err.message);
  }
}

// ============================================================
// FUNCIONES PRINCIPALES
// ============================================================

/**
 * Obtiene la lista de archivos desde Google Apps Script (accion=listar)
 * @returns {Promise<Array>} Lista de archivos o array vacío
 */
async function obtenerArchivos() {
  try {
    const url = `${API_URL}?key=${encodeURIComponent(API_KEY)}&accion=listar`;

    console.log("[INFO] Consultando API de Google Apps Script...");

    const response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      redirect: "follow",
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();

    // Validar respuesta
    if (!data || data.status === "error") {
      throw new Error(data?.mensaje || "Respuesta con error de la API");
    }

    const archivos = data.archivos || [];

    if (archivos.length === 0) {
      console.log("[INFO] No se encontraron archivos en la carpeta de Drive.");
      return [];
    }

    console.log(`[OK] ${archivos.length} archivo(s) encontrado(s)\n`);
    return archivos;
  } catch (err) {
    console.error(`[ERROR] Fallo al obtener archivos: ${err.message}`);
    return [];
  }
}

/**
 * Muestra información detallada de un archivo en consola
 * @param {Object} file - Objeto de archivo de la API
 * @param {number} index - Índice en la lista
 */
function mostrarInfoArchivo(file, index) {
  const nombre = file.nombre || file.name || "Sin nombre";
  const tipo = file.tipo || file.mimeType || "Desconocido";
  const tamano = file.tamaño || file.size || "N/A";
  const fecha = file.fechaCreacion || file.createdTime || "N/A";
  const url = file.url || file.webViewLink || "N/A";

  // Formatear tamaño legible
  let tamanoStr = String(tamano);
  if (typeof tamano === "number" || !isNaN(Number(tamano))) {
    const bytes = Number(tamano);
    if (bytes >= 1048576) tamanoStr = `${(bytes / 1048576).toFixed(2)} MB`;
    else if (bytes >= 1024) tamanoStr = `${(bytes / 1024).toFixed(1)} KB`;
    else tamanoStr = `${bytes} bytes`;
  }

  console.log(`  ${index + 1}. ${nombre}`);
  console.log(`     Tipo:    ${tipo}`);
  console.log(`     Tamaño:  ${tamanoStr}`);
  console.log(`     Creado:  ${fecha}`);
  console.log(`     URL:     ${url}`);
  console.log("");
}

/**
 * Placeholder para procesamiento futuro de un archivo.
 * Actualmente imprime mensaje; será reemplazado por lógica real.
 * @param {Object} file - Objeto de archivo de la API
 */
function procesarArchivo(file) {
  const nombre = file.nombre || file.name || "Sin nombre";
  console.log(`  → Procesando archivo: ${nombre}`);
}

/**
 * Descarga un archivo desde la API (accion=leer) y lo guarda localmente
 * La API devuelve el contenido del archivo como texto plano en el campo "contenido"
 * @param {Object} file - Objeto de archivo con id y nombre
 * @returns {Promise<string|null>} Ruta local del archivo descargado
 */
async function descargarArchivo(file) {
  const nombre = file.nombre || file.name;
  const fileId = file.id;

  if (!nombre || !fileId) {
    console.error("  ✗ Archivo sin nombre o ID, no se puede descargar");
    return null;
  }

  // Asegurar que la carpeta de entrada existe
  if (!fs.existsSync(INPUT_DIR)) {
    fs.mkdirSync(INPUT_DIR, { recursive: true });
  }

  const rutaLocal = path.join(INPUT_DIR, nombre);

  try {
    // Pedir contenido a la API
    const url = `${API_URL}?key=${encodeURIComponent(API_KEY)}&accion=leer&id=${encodeURIComponent(fileId)}`;

    const response = await fetch(url, { redirect: "follow" });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();

    if (!data || data.status === "error") {
      throw new Error(data?.mensaje || "Error al leer archivo");
    }

    // La API devuelve el contenido del archivo en data.contenido
    const contenido = data.contenido;

    if (!contenido) {
      console.error(`  ✗ La API no devolvió contenido para: ${nombre}`);
      return null;
    }

    // Determinar si es binario (base64) o texto plano
    if (data.codificacion === "base64") {
      // Archivo binario (xlsx, xls, ods, etc.)
      const buffer = Buffer.from(contenido, "base64");
      fs.writeFileSync(rutaLocal, buffer);
      console.log(`  ✓ Descargado (binario): ${nombre} (${buffer.length} bytes)`);
    } else {
      // Archivo de texto (csv)
      fs.writeFileSync(rutaLocal, contenido, "utf-8");
      console.log(`  ✓ Descargado (texto): ${nombre} (${contenido.length} chars)`);
    }

    return rutaLocal;
  } catch (err) {
    console.error(`  ✗ Error descargando ${nombre}: ${err.message}`);
    return null;
  }
}

/**
 * Lanza el pipeline principal de EPIPROCESS (main.py) para un archivo
 * @param {string} rutaArchivo - Ruta local del archivo descargado
 * @returns {boolean} True si el procesamiento fue exitoso
 */
function lanzarPipelinePython(rutaArchivo) {
  try {
    const cmd = `"${PYTHON_EXE}" "${MAIN_PY}" --archivo "${rutaArchivo}" --boletin`;
    console.log(`  🐍 Ejecutando: main.py --archivo ${path.basename(rutaArchivo)}`);

    execSync(cmd, {
      cwd: BASE_DIR,
      stdio: "inherit",
      timeout: 300000, // 5 minutos máximo por archivo
    });

    console.log(`  ✅ Pipeline completado para: ${path.basename(rutaArchivo)}`);

    // Eliminar archivo de ENTRADA después de procesar exitosamente
    try {
      if (fs.existsSync(rutaArchivo)) {
        fs.unlinkSync(rutaArchivo);
        console.log(`  🗑️  Eliminado de entrada: ${path.basename(rutaArchivo)}`);
      }
    } catch (delErr) {
      console.warn(`  ⚠ No se pudo eliminar ${path.basename(rutaArchivo)}: ${delErr.message}`);
    }

    return true;
  } catch (err) {
    console.error(`  ❌ Error en pipeline: ${err.message}`);
    return false;
  }
}

// ============================================================
// MODOS DE EJECUCIÓN
// ============================================================

/**
 * Modo listar: Solo muestra los archivos disponibles en Drive
 */
async function modoListar() {
  console.log("\n" + "=".repeat(60));
  console.log("  EPIPROCESS — Bridge Google Apps Script → Drive");
  console.log("  Modo: LISTAR ARCHIVOS");
  console.log("=".repeat(60) + "\n");

  const archivos = await obtenerArchivos();

  if (archivos.length === 0) return;

  // Mostrar info de cada archivo
  console.log("─".repeat(50));
  archivos.forEach((file, i) => mostrarInfoArchivo(file, i));
  console.log("─".repeat(50));

  // Procesar (solo mensaje por ahora)
  archivos.forEach((file) => procesarArchivo(file));

  console.log(`\n[INFO] Total: ${archivos.length} archivo(s) listado(s)`);
}

/**
 * Modo descargar: Descarga archivos nuevos a la carpeta de entrada
 */
async function modoDescargar() {
  console.log("\n" + "=".repeat(60));
  console.log("  EPIPROCESS — Bridge Google Apps Script → Drive");
  console.log("  Modo: DESCARGAR ARCHIVOS NUEVOS");
  console.log("=".repeat(60) + "\n");

  const archivos = await obtenerArchivos();
  if (archivos.length === 0) return;

  const cache = cargarCache();
  let descargados = 0;

  for (const file of archivos) {
    const id = file.id;

    // Saltar si ya fue procesado
    if (cache.has(id)) {
      console.log(`  ⊘ Ya procesado: ${file.nombre}`);
      continue;
    }

    procesarArchivo(file);
    const ruta = await descargarArchivo(file);

    if (ruta) {
      cache.add(id);
      descargados++;
    }
  }

  guardarCache(cache);
  console.log(`\n[OK] ${descargados} archivo(s) descargado(s) en ${INPUT_DIR}`);
}

/**
 * Modo procesar: Descarga + ejecuta main.py automáticamente
 */
async function modoProcesar() {
  console.log("\n" + "=".repeat(60));
  console.log("  EPIPROCESS — Bridge Google Apps Script → Drive");
  console.log("  Modo: DESCARGAR + PROCESAR");
  console.log("=".repeat(60) + "\n");

  const archivos = await obtenerArchivos();
  if (archivos.length === 0) return;

  const cache = cargarCache();
  let procesados = 0;

  for (const file of archivos) {
    const id = file.id;

    if (cache.has(id)) {
      console.log(`  ⊘ Ya procesado: ${file.nombre}`);
      continue;
    }

    procesarArchivo(file);
    const ruta = await descargarArchivo(file);

    if (ruta) {
      const ok = lanzarPipelinePython(ruta);
      if (ok) {
        cache.add(id);
        procesados++;
      }
    }
  }

  guardarCache(cache);
  console.log(`\n[OK] ${procesados} archivo(s) procesado(s) por el pipeline EPIPROCESS`);
}

// ============================================================
// EJECUCIÓN PRINCIPAL
// ============================================================

async function main() {
  const args = process.argv.slice(2);

  if (args.includes("--procesar")) {
    await modoProcesar();
  } else if (args.includes("--descargar")) {
    await modoDescargar();
  } else {
    await modoListar();
  }
}

// Ejecutar automáticamente
main().catch((err) => {
  console.error(`[FATAL] Error inesperado: ${err.message}`);
  process.exit(1);
});
