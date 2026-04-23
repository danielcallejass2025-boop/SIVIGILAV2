/* ====================================
   EVENTO 549 - DASHBOARD EPIDEMIOLÓGICO
   JavaScript: Interactividad y Gráficos
   ==================================== */

// Lista global de eventos SIVIGILA
const EVENTOS_DISPONIBLES = [
    { codigo: 100, nombre: "Accidente ofídico" },
    { codigo: 110, nombre: "Bajo peso al nacer" },
    { codigo: 200, nombre: "Cólera" },
    { codigo: 215, nombre: "Defectos congénitos" },
    { codigo: 210, nombre: "Dengue" },
    { codigo: 230, nombre: "Difteria" },
    { codigo: 205, nombre: "Enfermedad de Chagas" },
    { codigo: 605, nombre: "Enfermedad diarréica aguda por Rotavirus" },
    { codigo: 345, nombre: "Enfermedad similar a la influenza (ESI)" },
    { codigo: 348, nombre: "IRAG Inusitado" },
    { codigo: 355, nombre: "Enfermedades transmitidas por alimentos (ETAs)" },
    { codigo: 310, nombre: "Fiebre amarilla" },
    { codigo: 340, nombre: "Hepatitis B, C y coinfección" },
    { codigo: 420, nombre: "Leishmaniasis" },
    { codigo: 450, nombre: "Lepra" },
    { codigo: 455, nombre: "Leptospirosis" },
    { codigo: 549, nombre: "Morbilidad materna extrema" },
    { codigo: 560, nombre: "Mortalidad perinatal y neonatal tardía" },
    { codigo: 610, nombre: "Parálisis flácida aguda" },
    { codigo: 670, nombre: "Rabia humana" },
    { codigo: 730, nombre: "Sarampión" },
    { codigo: 740, nombre: "Sífilis congénita" },
    { codigo: 750, nombre: "Sífilis gestacional" },
    { codigo: 760, nombre: "Tétanos accidental" },
    { codigo: 770, nombre: "Tétanos neonatal" },
    { codigo: 800, nombre: "Tosferina" },
    { codigo: 850, nombre: "VIH/SIDA" },
    { codigo: 895, nombre: "Zika" },
    { codigo: 217, nombre: "Chikungunya" },
    { codigo: 813, nombre: "Tuberculosis" }
];

// Variables globales
let eventoActual = 549;
let datosActuales = {};
let municipioFiltroActual = '';  // Municipio seleccionado en filtro ('' = todos)
let municipiosDisponibles = []; // Lista de municipios del archivo depurado
let totalSinFiltroActual = 0;   // Total real sin filtro reportado por API
let controladorFiltroMunicipio = null;
let secuenciaSolicitudFiltro = 0;
let ultimaVersionDatos = null;
let fallosRefreshConsecutivos = 0;
let timerEdadDatos = null;
let timerSyncDatos = null;
let sincronizacionEnCurso = false;
let ultimoTimestampDatosMs = null;
let cleanedData = [];
const chartsEvento549 = {};
const boletinChartsEvento549 = {};
const GRAFICOS_PIE_IDS = ['grafico-afiliacion', 'grafico-momento', 'grafico-oportunidad'];
const REFRESH_TIEMPO_REAL_MS = 15000;

const BOLETIN_TEXTOS_DEFAULT = {
    introduccion: 'La Morbilidad Materna Extrema (MME) corresponde a complicaciones graves durante el embarazo, el parto o el puerperio que ponen en riesgo la vida de la mujer y requieren intervenciones inmediatas. Este boletin presenta el comportamiento epidemiologico del evento 549 en Risaralda, con enfoque en analisis temporal, territorial, sociodemografico y clinico para orientar decisiones de vigilancia en salud publica.',
    conclusiones: 'En el periodo analizado se identifican patrones territoriales y clinicos que requieren seguimiento continuo. La razon departamental y la distribucion por municipio orientan la priorizacion de acciones de respuesta institucional.',
    observaciones: 'Documento de trabajo institucional. Los textos pueden ser ajustados por epidemiologia o secretaria de salud antes de la publicacion oficial.'
};

// Respaldo del HTML original para restaurar al volver al evento 549
let _htmlOriginalBoletin = null;
let _htmlOriginalDashboardParent = null;

// Nota: el dashboard consume exclusivamente datos reales del archivo depurado vía API.

function esArchivoPurificado549Valido(nombreArchivo) {
    const nombre = String(nombreArchivo || '').trim().toLowerCase();
    return nombre === 'mme_depurado_final.csv';
}

function parsearTimestampLocal(timestamp) {
    if (!timestamp || typeof timestamp !== 'string') return null;

    const isoLike = timestamp.trim().replace(' ', 'T');
    const intentoDirecto = new Date(isoLike);
    if (!Number.isNaN(intentoDirecto.getTime())) {
        return intentoDirecto.getTime();
    }

    const match = timestamp.trim().match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})$/);
    if (!match) return null;

    const [_, y, m, d, hh, mm, ss] = match;
    const fecha = new Date(Number(y), Number(m) - 1, Number(d), Number(hh), Number(mm), Number(ss));
    return Number.isNaN(fecha.getTime()) ? null : fecha.getTime();
}

function formatearEdadDatos(ms) {
    const totalSeg = Math.max(0, Math.floor(ms / 1000));
    if (totalSeg < 60) return `${totalSeg} s`;

    const min = Math.floor(totalSeg / 60);
    const seg = totalSeg % 60;
    if (min < 60) return `${min} min ${seg} s`;

    const horas = Math.floor(min / 60);
    const minRest = min % 60;
    return `${horas} h ${minRest} min`;
}

function actualizarEdadDatosVisual() {
    const edadEl = document.getElementById('status-age');
    if (!edadEl) return;

    if (!ultimoTimestampDatosMs) {
        edadEl.textContent = '';
        return;
    }

    const diff = Date.now() - ultimoTimestampDatosMs;
    edadEl.textContent = `Edad de datos: ${formatearEdadDatos(diff)}`;
}

function mensajeErrorFuenteDatos(error) {
    const code = String(error && error.code ? error.code : '').toUpperCase();
    if (code === 'FILE_NOT_FOUND') {
        return 'No se encontró archivo depurado local para el evento 549';
    }
    if (code === 'EMPTY_FILE') {
        return 'El archivo depurado local está vacío o sin registros válidos';
    }
    if (code === 'CORRUPT_FILE') {
        return 'El archivo depurado local está corrupto o no se puede leer';
    }
    return (error && error.message) ? error.message : 'Error de conexión con la fuente local depurada';
}

/**
 * Carga datos depurados del backend.
 */
async function obtenerDatosDepurados549(municipio = '', signal = null) {
    let url = `/api/datos-evento-549?ts=${Date.now()}`;
    if (municipio) {
        url += `&municipio=${encodeURIComponent(municipio)}`;
    }
    const response = await fetch(url, {
        method: 'GET',
        cache: 'no-store',
        signal
    });

    let payload = null;
    try {
        payload = await response.json();
    } catch (_e) {
        payload = null;
    }

    if (!response.ok) {
        const err = new Error((payload && payload.error) ? payload.error : `HTTP ${response.status}`);
        err.code = (payload && payload.error_code) ? payload.error_code : `HTTP_${response.status}`;
        throw err;
    }

    if (!payload || typeof payload !== 'object') {
        const err = new Error('Respuesta inválida de la API depurada');
        err.code = 'INVALID_PAYLOAD';
        throw err;
    }

    if (payload.fuente && payload.fuente !== 'archivo_depurado_local') {
        const err = new Error('La API respondió con una fuente de datos no permitida para el dashboard');
        err.code = 'INVALID_SOURCE';
        throw err;
    }

    if (!esArchivoPurificado549Valido(payload.archivo_depurado)) {
        const err = new Error('La API no respondió con la base de datos purificada MME_Depurado_Final.csv');
        err.code = 'INVALID_PURIFIED_FILE';
        throw err;
    }

    return payload;
}

async function obtenerDatosDepurados549ConRetry(municipio = '', signal = null, reintentos = 1) {
    let ultimoError = null;
    for (let intento = 0; intento <= reintentos; intento++) {
        try {
            return await obtenerDatosDepurados549(municipio, signal);
        } catch (error) {
            if (error && error.name === 'AbortError') {
                throw error;
            }
            ultimoError = error;
            if (intento < reintentos) {
                await new Promise(resolve => setTimeout(resolve, 250));
            }
        }
    }
    throw ultimoError;
}

function crearDatosVaciosDesdeDepurado() {
    return {
        codigo: 549,
        nombre: 'Morbilidad materna extrema',
        subtitulo: 'Morbilidad Materna Extrema (MME)',
        año: new Date().getFullYear(),
        anioComparacion: new Date().getFullYear() - 1,
        fechaActualizacion: 'Sin datos',
        totalCasos: 0,
        variacionAnual: null,
        casosActuales: 0,
        casosBases: 0,
        municipios: [],
        municipiosTerritoriales: [],
        gruposEdad: [
            { grupo: '15-19 años', casos: 0, porcentaje: 0 },
            { grupo: '20-24 años', casos: 0, porcentaje: 0 },
            { grupo: '25-29 años', casos: 0, porcentaje: 0 },
            { grupo: '30-34 años', casos: 0, porcentaje: 0 },
            { grupo: '35-39 años', casos: 0, porcentaje: 0 },
            { grupo: '40+ años', casos: 0, porcentaje: 0 }
        ],
        afiliacion: [],
        causas: [],
        momentoEvento: [],
        semanas: [],
        calidad: {
            notificacionOportuna: 0,
            notificacionTardia: 0,
            porcentajeOportunidad: 0,
            completitud: 0,
            hospitalizacion: 0,
            porcentajeHospitalizacion: 0,
            reconsulta: 0,
            porcentajeReconsulta: 0,
            controlPrenatal: 0,
            porcentajeControlPrenatal: 0,
            requiereUCI: 0,
            porcentajeUCI: 0,
            diasPromedio: 0
        },
        calidadMunicipios: [],
        diasNotificacion: [
            { rango: '1-7 días (Oportuno)', casos: 0, porcentaje: 0 },
            { rango: '8-14 días (Tardío)', casos: 0, porcentaje: 0 },
            { rango: '15-30 días (Muy tardío)', casos: 0, porcentaje: 0 },
            { rango: '>30 días (Crítico)', casos: 0, porcentaje: 0 }
        ],
        edadEstadisticas: { promedio: 0, minima: 0, maxima: 0, moda: 0 }
    };
}

/**
 * Construye datos finales priorizando estructura real enviada por API.
 */
function construirDatosDesdePayload(payload) {
    if (payload && payload.dashboard_data && typeof payload.dashboard_data === 'object') {
        return payload.dashboard_data;
    }
    throw new Error('Payload sin dashboard_data real del archivo depurado');
}

function actualizarTodoDashboardConDatos(payload) {
    datosActuales = construirDatosDesdePayload(payload);
    totalSinFiltroActual = Number(payload.total_sin_filtro ?? payload.total_casos ?? 0);
    ultimaVersionDatos = String(payload.data_version || '');

    if (payload.municipios_disponibles) {
        municipiosDisponibles = payload.municipios_disponibles;
        llenarFiltroMunicipios(municipiosDisponibles);
    }

    actualizarKPIsVisibles();
    actualizarBoletinDinamico();
    llenarTablaSociodemografica();
    llenarTablaTerritorial();
    llenarTablaCalidad();
    llenarTablaClinica();
    graficoSemanas();
    graficoComparativo();
    graficoEdad();
    graficoEdadSocio();
    graficoAfiliacion();
    graficoCausas();
    graficoMomento();
    graficoMapa();
    graficoOportunidad();
    graficoDiasNotificacion();
    actualizarComparacionInteranualSemanal();

    setTimeout(resizeTodosGraficos, 200);
}

/**
 * Sincroniza valores KPI visibles del HTML con datos actuales.
 */
function actualizarKPIsVisibles() {
    const total = datosActuales.totalCasos;
    const variacionRaw = datosActuales.variacionAnual;
    const variacion = (typeof variacionRaw === 'number' && Number.isFinite(variacionRaw)) ? variacionRaw : NaN;
    const casosBases = Number(datosActuales.casosBases);
    const baseComparativaDisponible = Number.isFinite(casosBases) && casosBases > 0;
    const variacionDisponible = baseComparativaDisponible && Number.isFinite(variacion);
    const anioComparacionRaw = datosActuales.anioComparacion;
    const anioComparacion = Number.isFinite(Number(anioComparacionRaw))
        ? Number(anioComparacionRaw)
        : (Number.isFinite(Number(datosActuales.año)) ? Number(datosActuales.año) - 1 : null);
    const calidad = datosActuales.calidad || {};

    const setText = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    };

    // Boletín KPIs
    setText('boletin-casos', total);
    if (variacionDisponible) {
        setText('boletin-variacion', `${variacion >= 0 ? '↑' : '↓'} ${Math.abs(variacion).toFixed(1)}%`);
    } else {
        setText('boletin-variacion', 'N/D');
    }
    setText('boletin-hospitalizados', calidad.hospitalizacion);

    // Resumen ejecutivo
    setText('kpi-total-casos', total);
    setText('kpi-variacion-anual', '...');
    setText('kpi-variacion-subtexto', 'Consultando variación semanal...');
    actualizarClaseVariacionComparacion('kpi-variacion-semanal-neutral');
    setText('kpi-hospitalizacion', `${Number(calidad.porcentajeHospitalizacion).toFixed(1)}%`);

    // Sociodemográfico: edad estadísticas
    const edadStats = datosActuales.edadEstadisticas || {};
    setText('kpi-edad-promedio', edadStats.promedio || '—');
    setText('kpi-edad-min', edadStats.minima || '—');
    setText('kpi-edad-max', edadStats.maxima || '—');
    setText('kpi-edad-moda', edadStats.moda || '—');

    // Clínico
    setText('kpi-clin-hospitalizacion', calidad.hospitalizacion);
    setText('kpi-clin-hospitalizacion-pct', `${Number(calidad.porcentajeHospitalizacion).toFixed(1)}% de casos`);
    setText('kpi-clin-reconsulta', calidad.reconsulta);
    setText('kpi-clin-reconsulta-pct', `${Number(calidad.porcentajeReconsulta).toFixed(1)}% de casos`);
    setText('kpi-clin-control', calidad.controlPrenatal);
    setText('kpi-clin-control-pct', `${Number(calidad.porcentajeControlPrenatal).toFixed(1)}% de casos`);
    setText('kpi-clin-dias', calidad.diasPromedio);

    // Calidad
    setText('kpi-cal-oportuna', calidad.notificacionOportuna);
    setText('kpi-cal-oportuna-pct', `${Number(calidad.porcentajeOportunidad).toFixed(1)}% dentro del plazo`);
    setText('kpi-cal-tardia', calidad.notificacionTardia);
    const pctTardia = (calidad.notificacionOportuna + calidad.notificacionTardia) > 0
        ? (100 - Number(calidad.porcentajeOportunidad)).toFixed(1) : '0.0';
    setText('kpi-cal-tardia-pct', `${pctTardia}% fuera del plazo`);
    setText('kpi-cal-completitud', `${Number(calidad.completitud).toFixed(1)}%`);

    setText('kpi-cal-duplicados', Number(total) || 0);

    // Territorial
    const municipios = Array.isArray(datosActuales.municipios) ? datosActuales.municipios : [];
    if (municipios.length > 0 && total > 0) {
        const ordenados = [...municipios].sort((a, b) => (b.casos || 0) - (a.casos || 0));
        const top = ordenados[0];
        const top3 = ordenados.slice(0, 3).reduce((acc, m) => acc + (Number(m.casos) || 0), 0);
        const prioritarios = ordenados.filter(m => (Number(m.casos) || 0) >= Math.max(1, Math.round(total * 0.1))).length;

        setText('kpi-mayor-carga', top.nombre);
        setText('kpi-mayor-carga-subtexto', `${top.casos} casos (${((top.casos / total) * 100).toFixed(1)}%)`);
        setText('kpi-municipios-afectados', ordenados.filter(m => (Number(m.casos) || 0) > 0).length);
        setText('kpi-top3', top3);
        setText('kpi-top3-subtexto', `${((top3 / total) * 100).toFixed(1)}% de casos`);
        setText('kpi-prioritarios', prioritarios);
    } else {
        setText('kpi-mayor-carga', municipioFiltroActual || '—');
        setText('kpi-mayor-carga-subtexto', '0 casos (0.0%)');
        setText('kpi-municipios-afectados', 0);
        setText('kpi-top3', 0);
        setText('kpi-top3-subtexto', '0.0% de casos');
        setText('kpi-prioritarios', 0);
    }
}

/**
 * Actualizar barra de estado de conexión en tiempo real
 */
function actualizarBarraEstado(archivo, timestamp, exito, mensajePersonalizado = null) {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    const arch = document.getElementById('status-archivo');
    const ts = document.getElementById('status-timestamp');
    if (!dot) return;

    if (exito) {
        dot.className = 'status-dot online';
        const mensaje = mensajePersonalizado || (municipioFiltroActual
            ? `Conectado a base purificada — Municipio: ${municipioFiltroActual}`
            : 'Conectado a base purificada — Total departamental');
        text.textContent = mensaje;
        if (archivo !== null && archivo !== undefined) {
            arch.textContent = archivo ? `Base activa: ${archivo}` : '';
        }
        if (timestamp !== null && timestamp !== undefined) {
            ts.textContent = timestamp ? `Actualizado: ${timestamp}` : '';
            ultimoTimestampDatosMs = parsearTimestampLocal(timestamp);
            actualizarEdadDatosVisual();
        }
    } else {
        dot.className = 'status-dot offline';
        text.textContent = mensajePersonalizado || 'Desconectado — Usando datos de respaldo';
        arch.textContent = '';
        ts.textContent = '';
        ultimoTimestampDatosMs = null;
        actualizarEdadDatosVisual();
    }
}

// ====================================
// COMPARACION INTERANUAL (LOCAL)
// ====================================

function obtenerSemanaEpidemiologicaActual(fecha = new Date()) {
    const hoy = new Date(fecha.getFullYear(), fecha.getMonth(), fecha.getDate());
    const inicio = new Date(hoy.getFullYear(), 0, 1);
    const dias = Math.floor((hoy - inicio) / 86400000) + 1;
    const offsetDomingo = inicio.getDay(); // domingo=0
    return Math.floor((dias + offsetDomingo - 1) / 7) + 1;
}

function obtenerAnioEpidemiologicoActual() {
    const anioDatos = Number(datosActuales?.año);
    if (Number.isFinite(anioDatos) && anioDatos > 1900) {
        return anioDatos;
    }
    return new Date().getFullYear();
}

function actualizarClaseVariacionComparacion(tipo) {
    const valor = document.getElementById('kpi-variacion-anual');
    const subtexto = document.getElementById('kpi-variacion-subtexto');
    const clases = [
        'kpi-variacion-semanal-aumento',
        'kpi-variacion-semanal-disminucion',
        'kpi-variacion-semanal-neutral',
        'kpi-variacion-semanal-error'
    ];
    if (valor) {
        valor.classList.remove(...clases);
        valor.classList.add(tipo);
    }
    if (subtexto) {
        subtexto.classList.remove(...clases);
        subtexto.classList.add(tipo);
    }
}

function renderComparacionInteranualError(semana, anioActual) {
    const anioAnterior = anioActual - 1;
    const setText = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    };

    setText('kpi-variacion-anual', 'N/D');
    setText('kpi-variacion-subtexto', `Sin base comparativa local para SE ${semana} ${anioAnterior}`);
    actualizarClaseVariacionComparacion('kpi-variacion-semanal-error');
}

function renderComparacionInteranual(resultado, semanaSolicitada, anioSolicitado) {
    const setText = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    };

    const semana = Number.isFinite(Number(resultado?.semana)) ? Number(resultado.semana) : semanaSolicitada;
    const anioActual = Number.isFinite(Number(resultado?.anio_actual)) ? Number(resultado.anio_actual) : anioSolicitado;
    const anioAnterior = Number.isFinite(Number(resultado?.anio_anterior)) ? Number(resultado.anio_anterior) : (anioActual - 1);
    const casosActual = Number.isFinite(Number(resultado?.casos_actual)) ? Number(resultado.casos_actual) : null;
    const casosAnterior = Number.isFinite(Number(resultado?.casos_anterior)) ? Number(resultado.casos_anterior) : null;
    const variacion = Number.isFinite(Number(resultado?.variacion_porcentual)) ? Number(resultado.variacion_porcentual) : 0;
    const tendencia = String(resultado?.tendencia || '').toLowerCase();
    const iconoServidor = String(resultado?.icono || '').trim();
    const mensajeServidor = String(resultado?.mensaje || '').trim();

    if (casosAnterior === null || casosAnterior <= 0 || casosActual === null) {
        setText('kpi-variacion-anual', '➡️ N/D');
        setText('kpi-variacion-subtexto', `Sin datos comparativos para SE ${semana} ${anioAnterior}`);
        actualizarClaseVariacionComparacion('kpi-variacion-semanal-neutral');
        return;
    }

    if (tendencia === 'sin_cambio' || Math.abs(variacion) < 0.05) {
        setText('kpi-variacion-anual', '➡️ 0.0%');
        setText('kpi-variacion-subtexto', mensajeServidor || `Sin cambios respecto a SE ${semana} ${anioAnterior}`);
        actualizarClaseVariacionComparacion('kpi-variacion-semanal-neutral');
        return;
    }

    if (tendencia === 'aumento' || variacion > 0) {
        const icono = iconoServidor || '⬆';
        setText('kpi-variacion-anual', `${icono} ${Math.abs(variacion).toFixed(1)}%`);
        setText('kpi-variacion-subtexto', mensajeServidor || `Aumentó comparado con SE ${String(semana).padStart(2, '0')} ${anioAnterior}`);
        actualizarClaseVariacionComparacion('kpi-variacion-semanal-aumento');
        return;
    }

    const icono = iconoServidor || '⬇';
    setText('kpi-variacion-anual', `${icono} ${Math.abs(variacion).toFixed(1)}%`);
    setText('kpi-variacion-subtexto', mensajeServidor || `Disminuyó comparado con SE ${String(semana).padStart(2, '0')} ${anioAnterior}`);
    actualizarClaseVariacionComparacion('kpi-variacion-semanal-disminucion');
}

async function actualizarComparacionInteranualSemanal() {
    const semanaActualCalendario = obtenerSemanaEpidemiologicaActual();
    const anioActual = obtenerAnioEpidemiologicoActual();
    const semanas = Array.isArray(datosActuales?.semanas) ? datosActuales.semanas : [];

    if (semanas.length === 0) {
        renderComparacionInteranualError(semanaActualCalendario, anioActual);
        return;
    }

    const semanasValidas = semanas
        .map(s => Number(s?.semana))
        .filter(n => Number.isFinite(n) && n > 0 && n <= 53)
        .sort((a, b) => a - b);

    if (semanasValidas.length === 0) {
        renderComparacionInteranualError(semanaActualCalendario, anioActual);
        return;
    }

    const semanaObjetivo = semanasValidas.includes(semanaActualCalendario)
        ? semanaActualCalendario
        : semanasValidas[semanasValidas.length - 1];

    const agregados = semanas.reduce((acc, item) => {
        const semana = Number(item?.semana);
        if (semana !== semanaObjetivo) {
            return acc;
        }

        const actual = Number(item?.casos) || 0;
        const previo = Number(item?.['año2025'] ?? item?.anio2025 ?? item?.anio_2025 ?? 0) || 0;

        acc.casosActual += actual;
        acc.casosAnterior += previo;
        return acc;
    }, { casosActual: 0, casosAnterior: 0 });

    const variacion = agregados.casosAnterior > 0
        ? ((agregados.casosActual - agregados.casosAnterior) / agregados.casosAnterior) * 100
        : 0;

    const resultadoLocal = {
        semana: semanaObjetivo,
        anio_actual: anioActual,
        anio_anterior: anioActual - 1,
        casos_actual: agregados.casosActual,
        casos_anterior: agregados.casosAnterior,
        variacion_porcentual: variacion,
        tendencia: variacion > 0 ? 'aumento' : (variacion < 0 ? 'disminucion' : 'sin_cambio'),
        icono: variacion > 0 ? '⬆' : (variacion < 0 ? '⬇' : '➡️'),
        mensaje: `SE ${String(semanaObjetivo).padStart(2, '0')}: ${agregados.casosActual} vs ${agregados.casosAnterior} casos`
    };

    renderComparacionInteranual(resultadoLocal, semanaObjetivo, anioActual);
}

async function sincronizarDashboardTiempoReal() {
    try {
        const payload = await obtenerDatosDepurados549ConRetry(municipioFiltroActual, null, 1);
        const nuevaVersion = String(payload.data_version || '');
        totalSinFiltroActual = Number(payload.total_sin_filtro ?? payload.total_casos ?? 0);

        actualizarBarraEstado(payload.archivo_depurado, payload.archivo_modificado, true);

        if (payload.municipios_disponibles && JSON.stringify(payload.municipios_disponibles) !== JSON.stringify(municipiosDisponibles)) {
            municipiosDisponibles = payload.municipios_disponibles;
            llenarFiltroMunicipios(municipiosDisponibles);
        }

        if (nuevaVersion && nuevaVersion !== ultimaVersionDatos) {
            console.log(`🔄 Datos actualizados en tiempo real: ${payload.archivo_depurado}`);
            actualizarTodoDashboardConDatos(payload);
        }

        fallosRefreshConsecutivos = 0;
    } catch (err) {
        fallosRefreshConsecutivos += 1;
        const msg = mensajeErrorFuenteDatos(err);
        if (fallosRefreshConsecutivos >= 2) {
            actualizarBarraEstado(
                null,
                null,
                false,
                `${msg} (mostrando última lectura)`
            );
        }
    }
}

function detenerSincronizacionAutomatica() {
    if (timerSyncDatos) {
        clearInterval(timerSyncDatos);
        timerSyncDatos = null;
    }
}

async function forzarSincronizacionInmediata() {
    if (eventoActual !== 549) {
        return;
    }
    if (sincronizacionEnCurso) {
        return;
    }

    sincronizacionEnCurso = true;
    try {
        await sincronizarDashboardTiempoReal();
    } finally {
        sincronizacionEnCurso = false;
    }
}

function iniciarSincronizacionAutomatica() {
    detenerSincronizacionAutomatica();

    timerSyncDatos = setInterval(async () => {
        if (document.hidden || eventoActual !== 549 || sincronizacionEnCurso) {
            return;
        }

        sincronizacionEnCurso = true;
        try {
            await sincronizarDashboardTiempoReal();
        } finally {
            sincronizacionEnCurso = false;
        }
    }, REFRESH_TIEMPO_REAL_MS);
}

// ====================================
// FUNCIONES DE FILTRO POR MUNICIPIO
// ====================================

/**
 * Llenar el dropdown de municipios con datos reales del archivo depurado
 */
function llenarFiltroMunicipios(listaMunicipios) {
    const select = document.getElementById('filtro-municipio-select');
    if (!select) return;

    // Guardar selección actual
    const selActual = select.value;

    // Limpiar opciones existentes excepto la primera (Todos)
    while (select.options.length > 1) {
        select.remove(1);
    }

    // Agregar municipios del archivo depurado
    if (Array.isArray(listaMunicipios)) {
        listaMunicipios.forEach(mun => {
            const opt = document.createElement('option');
            opt.value = mun;
            opt.textContent = mun;
            select.appendChild(opt);
        });
    }

    // Restaurar selección si aún existe
    if (selActual && [...select.options].some(o => o.value === selActual)) {
        select.value = selActual;
    }
}

function actualizarBadgeMunicipio(texto = '') {
    const badge = document.getElementById('filtro-municipio-badge');
    if (!badge) return;

    if (texto) {
        badge.textContent = texto;
        badge.classList.remove('filtro-badge-oculto');
    } else {
        badge.textContent = '';
        badge.classList.add('filtro-badge-oculto');
    }
}

/**
 * Aplicar filtro de municipio: re-consulta la API filtrando por municipio
 */
async function aplicarFiltroMunicipio(municipio) {
    const select = document.getElementById('filtro-municipio-select');
    const estadoTexto = document.getElementById('status-text');
    const filtroAnterior = municipioFiltroActual;
    const miSecuencia = ++secuenciaSolicitudFiltro;

    // Cancelar solicitud anterior si el usuario cambió rápido de municipio
    if (controladorFiltroMunicipio) {
        controladorFiltroMunicipio.abort();
    }
    controladorFiltroMunicipio = new AbortController();

    municipioFiltroActual = municipio || '';

    // Estado visual de carga
    if (select) {
        select.disabled = true;
        select.classList.add('cargando');
    }
    if (estadoTexto) {
        estadoTexto.textContent = 'Actualizando filtro...';
    }

    console.log(`📍 Filtro municipio: ${municipioFiltroActual || 'Todos'}`);

    try {
        const payload = await obtenerDatosDepurados549ConRetry(municipioFiltroActual, controladorFiltroMunicipio.signal, 1);

        // Si llegó una respuesta antigua, no sobreescribir el estado actual
        if (miSecuencia !== secuenciaSolicitudFiltro) {
            return;
        }

        actualizarTodoDashboardConDatos(payload);

        // Mantener lista de municipios actualizada desde el archivo depurado
        if (payload.municipios_disponibles) {
            municipiosDisponibles = payload.municipios_disponibles;
            llenarFiltroMunicipios(municipiosDisponibles);
        }

        if (select) {
            select.value = municipioFiltroActual;
        }

        actualizarBarraEstado(payload.archivo_depurado, payload.archivo_modificado, true);

        // Actualizar badge visual con conteo real
        if (municipioFiltroActual) {
            actualizarBadgeMunicipio(`${municipioFiltroActual} · ${payload.total_casos} casos`);
        } else {
            actualizarBadgeMunicipio('');
        }

        console.log(`✅ Dashboard actualizado — ${municipioFiltroActual || 'Todos los municipios'}: ${payload.total_casos} casos`);
    } catch (error) {
        if (error && error.name === 'AbortError') {
            return;
        }

        if (miSecuencia !== secuenciaSolicitudFiltro) {
            return;
        }

        console.error('❌ Error aplicando filtro de municipio:', error);
    const mensajeError = mensajeErrorFuenteDatos(error);

        // Mantener selección del usuario aunque haya fallo temporal
        if (select) {
            select.value = municipioFiltroActual;
        }
        if (municipioFiltroActual) {
            const casosActuales = Number(datosActuales?.totalCasos || 0);
            actualizarBadgeMunicipio(`${municipioFiltroActual} · ${casosActuales} casos (última lectura)`);
        } else {
            actualizarBadgeMunicipio('');
        }
        if (estadoTexto) {
            estadoTexto.textContent = municipioFiltroActual
                ? `${mensajeError} — ${municipioFiltroActual} (última lectura)`
                : `${mensajeError} (última lectura)`;
        }
    } finally {
        if (select && miSecuencia === secuenciaSolicitudFiltro) {
            select.disabled = false;
            select.classList.remove('cargando');
        }
    }
}

// ====================================
// FUNCIONES DE SELECTOR DE EVENTOS
// ====================================

/**
 * Llenar selector de eventos en el header
 */
function llenarSelectorEventos() {
    const selector = document.getElementById('selector-evento');
    
    EVENTOS_DISPONIBLES.forEach(evento => {
        const option = document.createElement('option');
        option.value = evento.codigo;
        option.textContent = `[${evento.codigo}] ${evento.nombre}`;
        if (evento.codigo === 549) {
            option.selected = true;
        }
        selector.appendChild(option);
    });
}

/**
 * Cambiar de evento y cargar datos dinámicamente
 */
async function cambiarEvento(codigoEvento) {
    console.log(`🔄 Cambiando al evento ${codigoEvento}...`);
    eventoActual = parseInt(codigoEvento);
    
    // Obtener info del evento
    const eventoInfo = EVENTOS_DISPONIBLES.find(e => e.codigo === eventoActual);
    
    // Actualizar todos los elementos que muestran el número del evento
    const elementos = [
        document.getElementById('evento-titulo'),
        document.getElementById('portada-evento'),
        document.getElementById('footer-evento')
    ];
    
    // Actualizar título descriptivo en boletín (solo si es 549)
    const eventoBoletin = document.getElementById('evento-titulo-boletin');
    
    elementos.forEach(elem => {
        if (elem) {
            elem.style.opacity = '0.5';
            setTimeout(() => {
                elem.textContent = `Evento ${eventoActual}`;
                elem.style.opacity = '1';
            }, 150);
        }
    });
    
    // Actualizar nombre descriptivo del evento en boletín
    if (eventoBoletin && eventoInfo) {
        eventoBoletin.style.opacity = '0.5';
        setTimeout(() => {
            eventoBoletin.textContent = eventoInfo.nombre;
            eventoBoletin.style.opacity = '1';
        }, 150);
    }
    
    // Si es evento 549, mostrar dashboard con datos
    if (eventoActual === 549) {
        console.log('✅ Cargando datos depurados del evento 549...');
        iniciarSincronizacionAutomatica();
        try {
            const payload = await obtenerDatosDepurados549ConRetry(municipioFiltroActual, null, 1);
            actualizarTodoDashboardConDatos(payload);
            console.log(`📦 Fuente depurada: ${payload.archivo_depurado} | casos: ${payload.total_casos}`);
            actualizarBarraEstado(payload.archivo_depurado, payload.archivo_modificado, true);
            await forzarSincronizacionInmediata();
        } catch (error) {
            console.warn('⚠️ No fue posible cargar API depurada.', error);
            datosActuales = crearDatosVaciosDesdeDepurado();
            totalSinFiltroActual = 0;
            actualizarBarraEstado(null, null, false, mensajeErrorFuenteDatos(error));
        }

        mostrarDashboardConDatos();
    } else {
        // Para otros eventos, mostrar mensaje sin datos
        console.log(`⚠️ Evento ${eventoActual} sin datos disponibles`);
        detenerSincronizacionAutomatica();
        mostrarSinDatos();
    }
    
    // Cambiar a vista boletín y desplazar al inicio
    cambiarVista('boletin');
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

/**
 * Mostrar dashboard con datos (evento 549)
 */
function mostrarDashboardConDatos() {
    console.log('📊 Renderizando dashboard...');
    
    // Mostrar secciones del dashboard
    const boletinSection = document.getElementById('boletin');
    const dashboardSection = document.getElementById('dashboard');
    
    // Restaurar HTML original del boletín si fue reemplazado por "sin datos"
    if (_htmlOriginalBoletin !== null && boletinSection) {
        boletinSection.innerHTML = _htmlOriginalBoletin;
    }

    ensureBoletinTemplate();
    
    // Restaurar visibilidad del dashboard si fue ocultado
    if (dashboardSection && dashboardSection.parentElement) {
        dashboardSection.parentElement.style.display = '';
    }
    
    // Usar setTimeout para permitir que el navegador re-render
    setTimeout(() => {
        // Actualizar boletín y tablas
        actualizarBoletinDinamico();
        llenarTablaSociodemografica();
        llenarTablaTerritorial();
        llenarTablaCalidad();
        llenarTablaClinica();
        
        // Crear todos los gráficos
        graficoSemanas();
        graficoComparativo();
        graficoEdad();
        graficoEdadSocio();
        graficoAfiliacion();
        graficoCausas();
        graficoMomento();
        graficoMapa();
        graficoOportunidad();
        graficoDiasNotificacion();
        renderBoletinEpidemiologico();
        
        // Forzar redimensionado después de render para que Plotly recalcule tamaños
        setTimeout(resizeTodosGraficos, 200);
        
        console.log('✅ Dashboard renderizado completamente');
    }, 100);
}

/**
 * Mostrar mensaje sin datos para otros eventos
 */
function mostrarSinDatos() {
    console.log(`⚠️ Evento ${eventoActual} sin datos disponibles`);
    
    const eventoInfo = EVENTOS_DISPONIBLES.find(e => e.codigo === eventoActual);
    
    const sinDatosHTML = `
        <div class="sin-datos-dinamico">
            <div class="sin-datos-dinamico-icon">📭</div>
            <h3 class="sin-datos-dinamico-title">Sin datos disponibles</h3>
            <p class="sin-datos-dinamico-text">
                El evento <strong>#${eventoActual}</strong> aún no tiene datos procesados en el sistema.
            </p>
            <p class="sin-datos-dinamico-note">
                Los datos se sincronizan automáticamente en tiempo real con el archivo depurado local. Selecciona el evento 
                <strong class="sin-datos-dinamico-highlight">#549 - Morbilidad Materna Extrema</strong> para ver los análisis disponibles.
            </p>
        </div>
    `;
    
    const boletinSection = document.getElementById('boletin');
    const dashboardSection = document.getElementById('dashboard');
    
    // Guardar HTML original SOLO la primera vez
    if (boletinSection && _htmlOriginalBoletin === null) {
        _htmlOriginalBoletin = boletinSection.innerHTML;
    }
    
    if (boletinSection) {
        boletinSection.innerHTML = sinDatosHTML;
    }
    if (dashboardSection && dashboardSection.parentElement) {
        dashboardSection.parentElement.style.display = 'none';
    }
    
    // Actualizar barra de estado
    actualizarBarraEstado(null, null, false);
}

// ====================================
// FUNCIONES DE NAVEGACIÓN
// ====================================

/**
 * Cambiar entre secciones principales (Boletín vs Dashboard)
 */
function cambiarVista(vista) {
    document.querySelectorAll('.section').forEach(section => {
        section.classList.remove('active');
    });
    
    document.getElementById(vista).classList.add('active');
    
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Marcar botón activo basado en índice
    const btns = document.querySelectorAll('.tab-btn');
    if (vista === 'boletin' && btns[0]) btns[0].classList.add('active');
    if (vista === 'dashboard' && btns[1]) btns[1].classList.add('active');

    if (vista === 'boletin') {
        renderBoletinEpidemiologico();
    }
    
    // Redimensionar gráficos al hacerse visible la sección
    setTimeout(resizeTodosGraficos, 150);
    
    window.scrollTo(0, 0);
}

function resizeTodosGraficos() {
    ['grafico-semanas', 'grafico-comparativo', 'grafico-edad', 'grafico-edad-socio',
     'grafico-afiliacion', 'grafico-causas', 'grafico-momento', 'grafico-mapa',
     'grafico-oportunidad', 'grafico-dias-notificacion', 'boletin-grafico-semanas'].forEach(id => {
        const el = document.getElementById(id);
        if (el && el.data) {
            Plotly.Plots.resize(el);
            if (GRAFICOS_PIE_IDS.includes(id)) {
                ajustarLayoutPieResponsivo(id);
            }
        }
    });
}

function obtenerConfigPlotly() {
    return {
        responsive: true,
        displayModeBar: false,
        displaylogo: false
    };
}

function renderGraficoPlotly(graficoId, data, layout, config) {
    const el = document.getElementById(graficoId);
    if (!el) return;

    if (el.data && typeof Plotly.react === 'function') {
        Plotly.react(el, data, layout, config);
        return;
    }

    Plotly.newPlot(graficoId, data, layout, config);
}

function obtenerAnchoUtilGrafico(graficoId) {
    const grafico = document.getElementById(graficoId);
    if (!grafico) return window.innerWidth || 1024;

    const contenedor = grafico.closest('.grafico-box') || grafico.parentElement || grafico;
    const anchoGrafico = Number(grafico.clientWidth) || 0;
    const anchoContenedor = Number(contenedor && contenedor.clientWidth) || 0;
    const anchoVentana = window.innerWidth || 1024;

    return Math.max(anchoGrafico, anchoContenedor, Math.min(640, anchoVentana));
}

function aplicarEstiloBaseLayout(layout, graficoId, opciones = {}) {
    const ancho = obtenerAnchoUtilGrafico(graficoId);
    const compacto = ancho < 560;
    const intermedio = ancho < 820;

    const layoutFinal = Object.assign({
        template: 'plotly_white',
        paper_bgcolor: '#FFFFFF',
        plot_bgcolor: '#FFFFFF',
        font: { family: 'Inter, Arial', size: compacto ? 11 : 12, color: '#2C3E50' },
        hoverlabel: { font: { family: 'Inter, Arial', size: compacto ? 11 : 12 } },
        uniformtext: { mode: 'hide', minsize: compacto ? 9 : 10 }
    }, layout || {});

    const margenBase = opciones.pie
        ? { l: 20, r: 140, t: 24, b: 24 }
        : (opciones.barHorizontal
            ? { l: 110, r: 32, t: 24, b: 42 }
            : { l: 52, r: 24, t: 28, b: 56 });

    layoutFinal.margin = Object.assign(margenBase, (layout && layout.margin) ? layout.margin : {});

    if (layoutFinal.xaxis) {
        layoutFinal.xaxis = Object.assign({
            automargin: true,
            tickfont: { size: compacto ? 10 : 11 },
            titlefont: { size: compacto ? 11 : 12 }
        }, layoutFinal.xaxis);
    }

    if (layoutFinal.yaxis) {
        layoutFinal.yaxis = Object.assign({
            automargin: true,
            tickfont: { size: compacto ? 10 : 11 },
            titlefont: { size: compacto ? 11 : 12 }
        }, layoutFinal.yaxis);
    }

    if (layoutFinal.yaxis2) {
        layoutFinal.yaxis2 = Object.assign({
            automargin: true,
            tickfont: { size: compacto ? 10 : 11 },
            titlefont: { size: compacto ? 11 : 12 }
        }, layoutFinal.yaxis2);
    }

    if (layoutFinal.legend) {
        layoutFinal.legend = Object.assign({
            font: { size: compacto ? 10 : 11, family: 'Inter, Arial' }
        }, layoutFinal.legend);
    }

    if (opciones.pie && intermedio) {
        layoutFinal.legend = Object.assign({}, layoutFinal.legend || {}, {
            orientation: 'h',
            x: 0.5,
            xanchor: 'center',
            y: -0.1,
            yanchor: 'top'
        });
        layoutFinal.margin = Object.assign({}, layoutFinal.margin, { l: 20, r: 20, t: 24, b: 80 });
    }

    return layoutFinal;
}

function ajustarLayoutPieResponsivo(graficoId) {
    const el = document.getElementById(graficoId);
    if (!el || !el.data) return;

    const ancho = obtenerAnchoUtilGrafico(graficoId);
    const intermedio = ancho < 820;

    const relayoutData = intermedio
        ? {
            legend: {
                orientation: 'h',
                x: 0.5,
                xanchor: 'center',
                y: -0.1,
                yanchor: 'top'
            },
            margin: { l: 20, r: 20, t: 24, b: 80 }
        }
        : {
            legend: {
                orientation: 'v',
                x: 1.02,
                xanchor: 'left',
                y: 0.5,
                yanchor: 'middle'
            },
            margin: { l: 20, r: 140, t: 24, b: 24 }
        };

    Plotly.relayout(el, relayoutData);
}

/**
 * Cambiar entre vistas del dashboard
 */
function cambiarDashboard(vista) {
    document.querySelectorAll('.dashboard-view').forEach(view => {
        view.classList.remove('active');
    });
    
    document.getElementById(vista).classList.add('active');
    
    document.querySelectorAll('.dashboard-tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Marcar botón activo por data-dashboard para una activación estable
    const selectorActivo = `.dashboard-tab-btn[data-dashboard="${vista}"]`;
    const botonActivo = document.querySelector(selectorActivo);
    if (botonActivo) {
        botonActivo.classList.add('active');
    }
    
    // Redibujar gráficos
    setTimeout(resizeTodosGraficos, 100);
}

// ====================================
// FUNCIONES DE GRÁFICOS (PLOTLY)
// ====================================

function graficoSemanas() {
    const semanas = datosActuales.semanas.map(s => s.semana);
    const casos2026 = datosActuales.semanas.map(s => s.casos);

    // Calcular porcentaje acumulado
    const totalCasos = casos2026.reduce((a, b) => a + b, 0) || 1;
    let acum = 0;
    const pctAcumulado = casos2026.map(c => {
        acum += c;
        return Math.round((acum / totalCasos) * 1000) / 10;
    });

    const traceBars = {
        x: semanas,
        y: casos2026,
        name: 'Casos 2026',
        type: 'bar',
        marker: {
            color: '#1D4E89',
            line: { color: '#163A66', width: 1 }
        },
        hovertemplate: 'SE %{x}<br><b>%{y} casos</b><extra></extra>'
    };

    const traceLine = {
        x: semanas,
        y: pctAcumulado,
        name: '% Acumulado',
        type: 'scatter',
        mode: 'lines+markers',
        yaxis: 'y2',
        line: { color: '#D9A404', width: 2.5 },
        marker: { color: '#D9A404', size: 6 },
        hovertemplate: 'SE %{x}<br><b>%{y}%</b> acumulado<extra></extra>'
    };

    const layout = {
        title: '',
        xaxis: {
            title: 'Semana Epidemiológica',
            titlefont: { color: '#2C3E50', size: 12, family: 'Inter, Arial' },
            dtick: 1
        },
        yaxis: {
            title: 'Número de Casos',
            titlefont: { color: '#1D4E89', size: 12 },
            side: 'left',
            rangemode: 'tozero'
        },
        yaxis2: {
            title: '% Acumulado',
            titlefont: { color: '#D9A404', size: 12 },
            overlaying: 'y',
            side: 'right',
            range: [0, 105],
            ticksuffix: '%',
            showgrid: false
        },
        hovermode: 'x unified',
        template: 'plotly_white',
        height: 380,
        legend: {
            orientation: 'h',
            x: 0.5,
            xanchor: 'center',
            y: 1.12,
            font: { size: 11 }
        },
        margin: { t: 40, b: 60, l: 50, r: 50 }
    };

    const config = obtenerConfigPlotly();

    if (document.getElementById('grafico-semanas')) {
        const layoutAjustado = aplicarEstiloBaseLayout(layout, 'grafico-semanas');
        renderGraficoPlotly('grafico-semanas', [traceBars, traceLine], layoutAjustado, config);
    }
    if (document.getElementById('boletin-grafico-semanas')) {
        const layoutBoletin = aplicarEstiloBaseLayout(Object.assign({}, layout, { height: 300 }), 'boletin-grafico-semanas');
        renderGraficoPlotly('boletin-grafico-semanas', [traceBars, traceLine], layoutBoletin, config);
    }
}

function graficoComparativo() {
    const anioActual = Number.isFinite(Number(datosActuales.año))
        ? Number(datosActuales.año)
        : new Date().getFullYear();
    const anioBase = Number.isFinite(Number(datosActuales.anioComparacion))
        ? Number(datosActuales.anioComparacion)
        : anioActual - 1;
    const casosBase = Number.isFinite(Number(datosActuales.casosBases))
        ? Number(datosActuales.casosBases)
        : 0;
    const casosActuales = Number.isFinite(Number(datosActuales.casosActuales))
        ? Number(datosActuales.casosActuales)
        : Number(datosActuales.totalCasos || 0);

    const data = [
        {
            x: [String(anioBase), String(anioActual)],
            y: [casosBase, casosActuales],
            type: 'bar',
            marker: { color: ['#95A5A6', '#1F6B45'] },
            text: [casosBase + ' casos', casosActuales + ' casos'],
            textposition: 'outside',
            cliponaxis: false
        }
    ];

    const layout = {
        title: '',
        yaxis: { title: 'Número de Casos' },
        hovermode: 'x unified',
        template: 'plotly_white',
        showlegend: false,
        margin: { t: 20, b: 60, l: 52, r: 20 }
    };

    if (document.getElementById('grafico-comparativo')) {
        const layoutAjustado = aplicarEstiloBaseLayout(layout, 'grafico-comparativo');
        renderGraficoPlotly('grafico-comparativo', data, layoutAjustado, obtenerConfigPlotly());
    }
}

function graficoEdad() {
    const edad = datosActuales.gruposEdad.map(g => g.grupo);
    const casos = datosActuales.gruposEdad.map(g => g.casos);
    const colores = ['#1D4E89', '#D9A404', '#1F6B45', '#2C3E50', '#95A5A6', '#6B7280'];

    const data = [{
        y: edad,
        x: casos,
        type: 'bar',
        orientation: 'h',
        marker: { color: colores },
        text: casos.map((c, i) => `${c} (${datosActuales.gruposEdad[i].porcentaje}%)`),
        textposition: 'outside',
        cliponaxis: false
    }];

    const layout = {
        title: '',
        xaxis: { title: 'Número de Casos' },
        yaxis: { title: 'Grupo de Edad' },
        hovermode: 'y unified',
        template: 'plotly_white',
        showlegend: false,
        margin: { l: 120, r: 24, t: 20, b: 42 }
    };

    if (document.getElementById('grafico-edad')) {
        const layoutAjustado = aplicarEstiloBaseLayout(layout, 'grafico-edad', { barHorizontal: true });
        renderGraficoPlotly('grafico-edad', data, layoutAjustado, obtenerConfigPlotly());
    }
}

function graficoAfiliacion() {
    const tipos = datosActuales.afiliacion.map(a => a.tipo);
    const porcentajes = datosActuales.afiliacion.map(a => a.porcentaje);
    const colores = ['#1D4E89', '#D9A404', '#95A5A6'];

    const data = [{
        labels: tipos,
        values: porcentajes,
        type: 'pie',
        marker: { colors: colores },
        textinfo: 'percent',
        textposition: 'inside',
        textfont: { color: '#fff', size: 12, family: 'Inter, Arial' },
        hovertemplate: '<b>%{label}</b><br>%{value}% (%{percent})<extra></extra>',
        hole: 0
    }];

    const layout = {
        title: '',
        template: 'plotly_white',
        showlegend: true,
        legend: {
            orientation: 'v',
            x: 1.02,
            y: 0.5,
            xanchor: 'left',
            font: { size: 11, family: 'Inter, Arial' }
        },
        margin: { l: 10, r: 140, t: 20, b: 20 }
    };

    if (document.getElementById('grafico-afiliacion')) {
        const layoutAjustado = aplicarEstiloBaseLayout(layout, 'grafico-afiliacion', { pie: true });
        renderGraficoPlotly('grafico-afiliacion', data, layoutAjustado, obtenerConfigPlotly());
    }
}

function graficoCausas() {
    const causas = datosActuales.causas.map(c => c.causa);
    const casos = datosActuales.causas.map(c => c.casos);

    const data = [{
        y: causas,
        x: casos,
        type: 'bar',
        orientation: 'h',
        marker: { color: '#1D4E89' },
        text: casos.map((c, i) => `${c} (${datosActuales.causas[i].porcentaje}%)`),
        textposition: 'outside',
        cliponaxis: false
    }];

    const layout = {
        title: '',
        xaxis: { title: 'Número de Casos' },
        yaxis: { title: 'Causa' },
        hovermode: 'y unified',
        template: 'plotly_white',
        showlegend: false,
        margin: { l: 130, r: 24, t: 20, b: 42 }
    };

    if (document.getElementById('grafico-causas')) {
        const layoutAjustado = aplicarEstiloBaseLayout(layout, 'grafico-causas', { barHorizontal: true });
        renderGraficoPlotly('grafico-causas', data, layoutAjustado, obtenerConfigPlotly());
    }
}

function graficoMomento() {
    const momentos = datosActuales.momentoEvento.map(m => m.momento);
    const porcentajes = datosActuales.momentoEvento.map(m => m.porcentaje);
    const colores = ['#1F6B45', '#1D4E89', '#D9A404'];

    const data = [{
        labels: momentos,
        values: porcentajes,
        type: 'pie',
        marker: { colors: colores },
        textinfo: 'percent',
        textposition: 'inside',
        textfont: { color: '#fff', size: 12, family: 'Inter, Arial' },
        hovertemplate: '<b>%{label}</b><br>%{value}% (%{percent})<extra></extra>',
        hole: 0
    }];

    const layout = {
        title: '',
        template: 'plotly_white',
        showlegend: true,
        legend: {
            orientation: 'v',
            x: 1.02,
            y: 0.5,
            xanchor: 'left',
            font: { size: 11, family: 'Inter, Arial' }
        },
        margin: { l: 10, r: 140, t: 20, b: 20 }
    };

    if (document.getElementById('grafico-momento')) {
        const layoutAjustado = aplicarEstiloBaseLayout(layout, 'grafico-momento', { pie: true });
        renderGraficoPlotly('grafico-momento', data, layoutAjustado, obtenerConfigPlotly());
    }
}

/**
 * GEOJSON DE MUNICIPIOS DE RISARALDA CON COORDENADAS
 */
const risaraldaGeoJSON = {
    type: "FeatureCollection",
    features: [
        {
            type: "Feature",
            properties: { nombre: "Pereira", casos: 14, nv: 217, razon: 64.5, clasificacion: "BAJO" },
            geometry: { type: "Point", coordinates: [-75.70, 4.81] }
        },
        {
            type: "Feature",
            properties: { nombre: "Dosquebradas", casos: 16, nv: 132, razon: 121.2, clasificacion: "MODERADO" },
            geometry: { type: "Point", coordinates: [-75.73, 4.84] }
        },
        {
            type: "Feature",
            properties: { nombre: "Santa Rosa de Cabal", casos: 6, nv: 37, razon: 162.2, clasificacion: "ALTO" },
            geometry: { type: "Point", coordinates: [-75.63, 4.85] }
        },
        {
            type: "Feature",
            properties: { nombre: "La Virginia", casos: 2, nv: 18, razon: 111.1, clasificacion: "MODERADO" },
            geometry: { type: "Point", coordinates: [-75.88, 4.86] }
        },
        {
            type: "Feature",
            properties: { nombre: "Santuario", casos: 3, nv: 6, razon: 500.0, clasificacion: "CRÍTICO" },
            geometry: { type: "Point", coordinates: [-75.74, 5.55] }
        },
        {
            type: "Feature",
            properties: { nombre: "Marsella", casos: 1, nv: 6, razon: 166.7, clasificacion: "ALTO" },
            geometry: { type: "Point", coordinates: [-75.73, 4.95] }
        },
        {
            type: "Feature",
            properties: { nombre: "Belén de Umbría", casos: 1, nv: 7, razon: 142.9, clasificacion: "MODERADO" },
            geometry: { type: "Point", coordinates: [-75.80, 5.27] }
        },
        {
            type: "Feature",
            properties: { nombre: "Quinchía", casos: 2, nv: 18, razon: 111.1, clasificacion: "MODERADO" },
            geometry: { type: "Point", coordinates: [-75.69, 5.03] }
        },
        {
            type: "Feature",
            properties: { nombre: "Apía", casos: 1, nv: 10, razon: 100.0, clasificacion: "MODERADO" },
            geometry: { type: "Point", coordinates: [-75.78, 5.08] }
        },
        {
            type: "Feature",
            properties: { nombre: "Mistrató", casos: 1, nv: 14, razon: 71.4, clasificacion: "BAJO" },
            geometry: { type: "Point", coordinates: [-75.93, 5.18] }
        },
        {
            type: "Feature",
            properties: { nombre: "Pueblo Rico", casos: 1, nv: 24, razon: 41.7, clasificacion: "BAJO" },
            geometry: { type: "Point", coordinates: [-75.64, 5.22] }
        },
        {
            type: "Feature",
            properties: { nombre: "Guática", casos: 0, nv: 5, razon: 0.0, clasificacion: "SIN CASOS" },
            geometry: { type: "Point", coordinates: [-75.59, 5.30] }
        },
        {
            type: "Feature",
            properties: { nombre: "La Celia", casos: 0, nv: 6, razon: 0.0, clasificacion: "SIN CASOS" },
            geometry: { type: "Point", coordinates: [-75.65, 4.98] }
        },
        {
            type: "Feature",
            properties: { nombre: "Balboa", casos: 0, nv: 4, razon: 0.0, clasificacion: "SIN CASOS" },
            geometry: { type: "Point", coordinates: [-75.68, 4.75] }
        }
    ]
};

/**
 * Función para obtener color según razón MME
 */
function getColorByRazon(razon) {
    if (razon >= 400) return '#1D4E89';  // Azul institucional - CRÍTICO
    if (razon >= 300) return '#2B5F9E';  // Azul alto - MUY ALTO
    if (razon >= 200) return '#3C73B1';  // Azul medio - ALTO
    if (razon >= 150) return '#5A8FC5';  // Azul claro - MOD-ALTO
    if (razon >= 100) return '#D9A404';  // Amarillo institucional - MODERADO
    if (razon >= 50) return '#4B8B66';   // Verde medio - BAJO
    if (razon > 0) return '#7DBA97';     // Verde claro - MUY BAJO
    return '#D1D5DB';                    // Gris - SIN CASOS
}

function getBadgeClassByRazon(razon) {
    if (razon >= 400) return 'map-popup-badge-critico';
    if (razon >= 300) return 'map-popup-badge-muy-alto';
    if (razon >= 200) return 'map-popup-badge-alto';
    if (razon >= 150) return 'map-popup-badge-mod-alto';
    if (razon >= 100) return 'map-popup-badge-moderado';
    if (razon >= 50) return 'map-popup-badge-bajo';
    if (razon > 0) return 'map-popup-badge-muy-bajo';
    return 'map-popup-badge-sin-casos';
}

function graficoMapa() {
    // Eliminar mapa anterior si existe
    const mapContainer = document.getElementById('grafico-mapa');
    if (!mapContainer) return;
    
    // Limpiar el contenedor
    mapContainer.innerHTML = '';
    
    // Crear mapa Leaflet
    const map = L.map('grafico-mapa').setView([4.95, -75.73], 9);
    
    // Añadir capa base
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 13,
        minZoom: 8
    }).addTo(map);
    
    // Crear círculos para cada municipio con tamaño proporcional
    const municipiosReales = Array.isArray(datosActuales.municipiosTerritoriales)
        ? datosActuales.municipiosTerritoriales
        : [];

    const municipios = municipiosReales.map(m => ({
            properties: {
                nombre: m.nombre,
                casos: Number(m.casos) || 0,
                nv: Number(m.nv2025) || 0,
                razon: Number(m.razonMME) || 0,
                clasificacion: m.clasificacion || ''
            },
            geometry: {
                type: 'Point',
                coordinates: [Number(m.longitud) || -75.73, Number(m.latitud) || 4.95]
            }
        }));

    if (municipios.length === 0) {
        llenarTablaMapaDetallada([]);
        return;
    }
    
    municipios.forEach(feature => {
        const props = feature.properties;
        const coords = feature.geometry.coordinates;
        
        // Tamaño proporcional a casos
        let radius = 5000; // metros
        if (props.casos === 0) radius = 8000;
        else if (props.casos >= 10) radius = 22000;
        else if (props.casos >= 5) radius = 16000;
        else if (props.casos >= 2) radius = 12000;
        else radius = 8000;
        
        // Crear círculo
        const badgeClass = getBadgeClassByRazon(props.razon);

        L.circle([coords[1], coords[0]], {
            color: getColorByRazon(props.razon),
            fillColor: getColorByRazon(props.razon),
            fillOpacity: 0.75,
            weight: 2,
            opacity: 0.9,
            radius: radius
        }).bindPopup(`
            <div class="map-popup">
                <b class="map-popup-title">${props.nombre}</b><br><br>
                <table class="map-popup-table">
                    <tr class="map-popup-row-alt">
                        <td><b>Casos:</b></td>
                        <td class="map-popup-value"><b>${props.casos}</b></td>
                    </tr>
                    <tr>
                        <td><b>Nacidos Vivos:</b></td>
                        <td class="map-popup-value"><b>${props.nv}</b></td>
                    </tr>
                    <tr class="map-popup-row-alt">
                        <td><b>Razón MME:</b></td>
                        <td class="map-popup-value"><b>${props.razon.toFixed(1)}</b></td>
                    </tr>
                    <tr>
                        <td colspan="2" class="map-popup-badge-cell">
                            <span class="map-popup-badge ${badgeClass}">
                                ${props.clasificacion}
                            </span>
                        </td>
                    </tr>
                </table>
            </div>
        `, {
            maxWidth: 250
        }).addTo(map);
        
        // Añadir etiqueta de municipio
        L.marker([coords[1], coords[0]], {
            icon: L.divIcon({
                html: `<div class="municipio-label-text">${props.nombre}</div>`,
                iconSize: [80, 20],
                className: 'municipio-label'
            })
        }).addTo(map);
    });
    
    // Ajustar mapa al contenedor
    setTimeout(() => {
        map.invalidateSize();
    }, 100);
    
    // Llenar tabla con datos
    llenarTablaMapaDetallada(municipios.map(f => ({
        nombre: f.properties.nombre,
        casos: f.properties.casos,
        nv2025: f.properties.nv,
        razonMME: f.properties.razon
    })));
}

/**
 * Llenar tabla detallada con datos del mapa
 */
function llenarTablaMapaDetallada(municipios) {
    const tbody = document.getElementById('tabla-territorial-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (!Array.isArray(municipios) || municipios.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="territorial-empty-cell">Sin datos depurados para mapa territorial</td>
            </tr>
        `;
        return;
    }

    // Ordenar por razón MME descendente
    const municipiosOrdenados = [...municipios].sort((a, b) => b.razonMME - a.razonMME);

    municipiosOrdenados.forEach((municipio, index) => {
        const row = `
            <tr>
                <td class="territorial-cell-rank"><strong>${index + 1}</strong></td>
                <td class="territorial-cell-name"><strong>${municipio.nombre}</strong></td>
                <td class="territorial-cell-cases"><strong>${municipio.casos}</strong></td>
                <td class="territorial-cell-nv"><strong>${municipio.nv2025}</strong></td>
                <td class="territorial-cell-ratio">
                    <strong class="territorial-ratio-valor">
                        ${municipio.razonMME.toFixed(1)}
                    </strong>
                </td>
            </tr>
        `;
        tbody.innerHTML += row;
    });
}

function graficoOportunidad() {
    const oportunos = datosActuales.calidad.notificacionOportuna;
    const tardios = datosActuales.calidad.notificacionTardia;
    const total = oportunos + tardios;
    
    const porcentajeOportunos = total > 0 ? Number(((oportunos / total) * 100).toFixed(1)) : 0;
    const porcentajeTardios = total > 0 ? Number(((tardios / total) * 100).toFixed(1)) : 0;

    const data = [{
        labels: [
            `Oportunos (≤7 días)<br>${oportunos} casos`,
            `Tardíos (>7 días)<br>${tardios} casos`
        ],
        values: [porcentajeOportunos, porcentajeTardios],
        type: 'pie',
        marker: {
            colors: ['#1F6B45', '#D9A404'],
            line: { width: 2, color: 'white' }
        },
        textinfo: 'label+percent',
        textposition: 'inside',
        textfont: { size: 13, color: 'white', family: 'Arial Black' },
        hovertemplate: '<b>%{label}</b><br>Porcentaje: %{value}%<extra></extra>'
    }];

    const layout = {
        title: {
            text: `Oportunidad en Notificación<br><sub>Meta: 85% (Actual: ${porcentajeOportunos}%)</sub>`,
            font: { size: 14, color: '#2C3E50', family: 'Arial' }
        },
        template: 'plotly_white',
        showlegend: true,
        paper_bgcolor: '#FAFAFA',
        margin: { l: 20, r: 140, t: 54, b: 24 }
    };

    if (document.getElementById('grafico-oportunidad')) {
        const layoutAjustado = aplicarEstiloBaseLayout(layout, 'grafico-oportunidad', { pie: true });
        renderGraficoPlotly('grafico-oportunidad', data, layoutAjustado, obtenerConfigPlotly());
    }
}

function graficoDiasNotificacion() {
    const diasData = datosActuales.diasNotificacion || [];
    const rangos = diasData.map(d => d.rango);
    const casos = diasData.map(d => d.casos);
    const total = datosActuales.totalCasos || 1;
    const colores = ['#1F6B45', '#D9A404', '#1D4E89', '#6B7280'];

    const data = [{
        x: rangos,
        y: casos,
        type: 'bar',
        marker: {
            color: colores.slice(0, rangos.length),
            line: { color: '#2C3E50', width: 1.5 }
        },
        text: casos.map(c => `${c} (${((c / total) * 100).toFixed(1)}%)`),
        textposition: 'outside',
        textfont: { color: '#2C3E50', size: 11, family: 'Inter, Arial' },
        cliponaxis: false
    }];

    const layout = {
        title: '',
        yaxis: { title: 'Número de Casos', titlefont: { color: '#2C3E50', size: 12 } },
        xaxis: { titlefont: { color: '#2C3E50', size: 12 } },
        hovermode: 'x unified',
        template: 'plotly_white',
        showlegend: false,
        margin: { t: 20, b: 60, l: 52, r: 20 }
    };

    if (document.getElementById('grafico-dias-notificacion')) {
        const layoutAjustado = aplicarEstiloBaseLayout(layout, 'grafico-dias-notificacion');
        renderGraficoPlotly('grafico-dias-notificacion', data, layoutAjustado, obtenerConfigPlotly());
    }
}

/**
 * Gráfico de edad duplicado para la vista Sociodemográfica
 */
function graficoEdadSocio() {
    const edad = datosActuales.gruposEdad.map(g => g.grupo);
    const casos = datosActuales.gruposEdad.map(g => g.casos);
    const colores = ['#1D4E89', '#D9A404', '#1F6B45', '#2C3E50', '#95A5A6', '#6B7280'];

    const data = [{
        y: edad,
        x: casos,
        type: 'bar',
        orientation: 'h',
        marker: { color: colores },
        text: casos.map((c, i) => `${c} (${datosActuales.gruposEdad[i].porcentaje}%)`),
        textposition: 'outside',
        cliponaxis: false
    }];

    const layout = {
        title: '',
        xaxis: { title: 'Número de Casos' },
        yaxis: { title: '' },
        hovermode: 'y unified',
        template: 'plotly_white',
        showlegend: false,
        margin: { l: 120, r: 24, t: 20, b: 42 }
    };

    if (document.getElementById('grafico-edad-socio')) {
        const layoutAjustado = aplicarEstiloBaseLayout(layout, 'grafico-edad-socio', { barHorizontal: true });
        renderGraficoPlotly('grafico-edad-socio', data, layoutAjustado, obtenerConfigPlotly());
    }
}

// ====================================
// FUNCIONES DE TABLAS
// ====================================

function llenarTablaSociodemografica() {
    const tbody = document.getElementById('tabla-socio-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    // Agregar grupos de edad
    const seccionEdad = '<tr><td colspan="4" class="tabla-socio-seccion tabla-socio-seccion-edad">DISTRIBUCIÓN POR GRUPO DE EDAD</td></tr>';
    tbody.innerHTML += seccionEdad;

    datosActuales.gruposEdad.forEach(edad => {
        const porcentaje = Number(edad.porcentaje) || 0;
        const row = `
            <tr>
                <td><strong>${edad.grupo}</strong></td>
                <td class="text-center"><strong>${edad.casos}</strong></td>
                <td class="text-center"><strong>${edad.porcentaje}%</strong></td>
                <td>
                    <div class="progress-mini-wrap">
                        <progress class="progress-mini progress-mini-edad" max="100" value="${porcentaje}"></progress>
                        <span class="progress-mini-label">${edad.porcentaje}%</span>
                    </div>
                </td>
            </tr>
        `;
        tbody.innerHTML += row;
    });

    // Agregar sección de afiliación
    const seccionAfiliacion = '<tr><td colspan="4" class="tabla-socio-seccion tabla-socio-seccion-afiliacion">DISTRIBUCIÓN POR TIPO DE AFILIACIÓN</td></tr>';
    tbody.innerHTML += seccionAfiliacion;

    datosActuales.afiliacion.forEach(afiliacion => {
        const porcentaje = Number(afiliacion.porcentaje) || 0;
        const row = `
            <tr>
                <td><strong>${afiliacion.tipo}</strong></td>
                <td class="text-center"><strong>${afiliacion.casos}</strong></td>
                <td class="text-center"><strong>${afiliacion.porcentaje}%</strong></td>
                <td>
                    <div class="progress-mini-wrap">
                        <progress class="progress-mini progress-mini-afiliacion" max="100" value="${porcentaje}"></progress>
                        <span class="progress-mini-label">${afiliacion.porcentaje}%</span>
                    </div>
                </td>
            </tr>
        `;
        tbody.innerHTML += row;
    });
}

function llenarTablaTerritorial() {
    console.log('Tabla territorial actualizada por graficoMapa()');
}

function llenarTablaCalidad() {
    const tbody = document.getElementById('tabla-calidad-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    datosActuales.calidadMunicipios.forEach((mun, index) => {
        const pct = Number(mun.porcentaje) || 0;
        let estado = 'BUENO';
        let estadoClass = 'badge-verde';
        if (pct < 70) { estado = 'DEFICIENTE'; estadoClass = 'badge-rojo'; }
        else if (pct < 85) { estado = 'REGULAR'; estadoClass = 'badge-naranja'; }

        const row = `
            <tr>
                <td><strong>${mun.municipio}</strong></td>
                <td class="text-center">${mun.oportunos}</td>
                <td class="text-center">${mun.tardios}</td>
                <td class="text-center"><strong>${pct}%</strong></td>
                <td class="text-center"><span class="${estadoClass}">${estado}</span></td>
            </tr>
        `;
        tbody.innerHTML += row;
    });
}

function llenarTablaClinica() {
    const tbody = document.getElementById('tabla-clinica-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    const cal = datosActuales.calidad;
    const total = datosActuales.totalCasos;

    const filas = [
        { label: 'Hospitalización', si: cal.hospitalizacion, pct: cal.porcentajeHospitalizacion },
        { label: 'Control Prenatal', si: cal.controlPrenatal, pct: cal.porcentajeControlPrenatal },
        { label: 'Reconsulta', si: cal.reconsulta, pct: cal.porcentajeReconsulta },
        { label: 'Requirió UCI', si: cal.requiereUCI, pct: cal.porcentajeUCI }
    ];

    filas.forEach(f => {
        const no = Math.max(0, total - f.si);
        tbody.innerHTML += `
            <tr>
                <td><strong>${f.label}</strong></td>
                <td class="text-center">${f.si}</td>
                <td class="text-center">${no}</td>
                <td class="text-center"><strong>${Number(f.pct).toFixed(1)}%</strong></td>
            </tr>
        `;
    });
}

// ====================================
// ACTUALIZAR INFORMACIÓN DINÁMICA
// ====================================

function actualizarBoletinDinamico() {
    const hoy = new Date();

    if (document.getElementById('boletin-ano')) {
        document.getElementById('boletin-ano').textContent = `Año ${datosActuales.año}`;
    }
    if (document.getElementById('boletin-fecha')) {
        document.getElementById('boletin-fecha').textContent = datosActuales.fechaActualizacion;
    }
    if (document.getElementById('metodologia-periodo')) {
        document.getElementById('metodologia-periodo').textContent = `Año ${datosActuales.año}`;
    }
    if (document.getElementById('fecha-actualizacion')) {
        document.getElementById('fecha-actualizacion').textContent = datosActuales.fechaActualizacion;
    }

    actualizarKPIsVisibles();
}

// ====================================
// FUNCIONES DE CARGA DINÁMICA
// ====================================

/**
 * Los datos se cargan automáticamente en tiempo real desde el servidor
 * Esta función está reservada para futuras integraciones con el backend
 */
async function cargarDatosDelServidor(codigoEvento) {
    console.log(`📡 Cargando datos del evento ${codigoEvento} desde el servidor...`);
    
    if (codigoEvento === 549) {
        const payload = await obtenerDatosDepurados549ConRetry('', null, 1);
        return construirDatosDesdePayload(payload);
    }
    return null;
}

let chartJsLoadPromise = null;
let chartJsDataLabelsPromise = null;
let geojsonRisaralda = null;
let geojsonRisaraldaPromise = null;
let resumenTerritorialActual = {
    filas: [],
    total: null,
    numVivosDisponible: false
};

const CHARTJS_PALETTE = {
    primary: '#1D4E89',
    secondary: '#1F6B45',
    warning: '#D9A404',
    danger: '#C0392B',
    neutral: '#6B7280',
    lightBlue: '#73A9E6',
    lightGreen: '#7CCBA2',
    lightOrange: '#F0B64D',
    lightRed: '#E5786D',
    violet: '#7D6AE8'
};

const CHART_META = {
    'grafico-semanas': {
        title: 'Curva Epidemiologica - Casos de MME por Semana 2026',
        subtitle: 'Numero de casos por semana epidemiologica y acumulado de casos en el periodo.'
    },
    'grafico-comparativo': {
        title: 'Top 6 Complicaciones Graves Asociadas a MME',
        subtitle: 'Porcentaje de casos con complicaciones clinicas graves sobre el total filtrado.'
    },
    'grafico-edad': {
        title: 'Distribucion de Casos por Grupo de Edad',
        subtitle: 'Conteo absoluto de casos de MME por rangos quinquenales de edad.'
    },
    'grafico-edad-socio': {
        title: 'Perfil Etario de las Mujeres con MME',
        subtitle: 'Frecuencia de casos por grupo de edad en la pestaña sociodemografica.'
    },
    'grafico-afiliacion': {
        title: 'Pertenencia Etnica Reportada en Casos de MME',
        subtitle: 'Participacion porcentual y conteo absoluto por categoria etnica.'
    },
    'grafico-vulnerables': {
        title: 'Grupos Vulnerables Priorizados',
        subtitle: 'Conteo de registros que reportan condicion de vulnerabilidad.'
    },
    'grafico-estrato-area': {
        title: 'Estrato Socioeconomico por Area de Residencia',
        subtitle: 'Distribucion apilada de casos por estrato y area urbana/rural.'
    },
    'grafico-causas': {
        title: 'Top 8 Causas Agrupadas de MME',
        subtitle: 'Principales causas clinicas registradas para los casos filtrados.'
    },
    'grafico-momento': {
        title: 'Dias de Hospitalizacion por Caso',
        subtitle: 'Conteo de casos segun rangos de estancia hospitalaria.'
    },
    'grafico-complicaciones-clinicas': {
        title: 'Complicaciones Graves Asociadas',
        subtitle: 'Numero de casos con hemorragia, eclampsia y otras complicaciones mayores.'
    },
    'grafico-semanas-gestacionales': {
        title: 'Semanas Gestacionales al Momento del Evento',
        subtitle: 'Tendencia de casos por rangos de semanas de gestacion reportadas.'
    },
    'grafico-mapa': {
        title: 'Mapa de Riesgo por Municipio - Razon MME x 1.000 NV',
        subtitle: 'Croquis municipal de la razon MME por 1.000 nacidos vivos.'
    },
    'grafico-area-territorial': {
        title: 'Distribucion de Casos por Area de Residencia',
        subtitle: 'Proporcion de casos segun area urbana, rural y categorias sin dato.'
    },
    'grafico-departamento-territorial': {
        title: 'Casos por Departamento de Residencia',
        subtitle: 'Conteo de casos por departamento; usa municipio cuando no hay departamento.'
    },
    'grafico-oportunidad': {
        title: 'Completitud por Variable Critica',
        subtitle: 'Porcentaje de registros completos para variables clave de vigilancia.'
    },
    'grafico-dias-notificacion': {
        title: 'Tendencia Semanal de Calidad de Registro',
        subtitle: 'Promedio semanal de completitud de variables criticas en los casos notificados.'
    }
};

async function asegurarChartJsListo() {
    if (window.Chart) return;
    if (!chartJsLoadPromise) {
        chartJsLoadPromise = new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js';
            script.async = true;
            script.onload = resolve;
            script.onerror = () => reject(new Error('No fue posible cargar Chart.js'));
            document.head.appendChild(script);
        });
    }
    await chartJsLoadPromise;

    if (!chartJsDataLabelsPromise && !window.ChartDataLabels) {
        chartJsDataLabelsPromise = new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0';
            script.async = true;
            script.onload = resolve;
            script.onerror = () => reject(new Error('No fue posible cargar chartjs-plugin-datalabels'));
            document.head.appendChild(script);
        });
    }
    if (chartJsDataLabelsPromise) {
        await chartJsDataLabelsPromise;
    }
    if (window.ChartDataLabels && !Chart.registry.plugins.get('datalabels')) {
        Chart.register(window.ChartDataLabels);
    }
}

function toNumber(value) {
    if (value === null || value === undefined || value === '') return null;
    const clean = String(value).replace(',', '.').trim();
    const num = Number(clean);
    return Number.isFinite(num) ? num : null;
}

function normalizeText(value) {
    return String(value || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .trim()
        .toUpperCase();
}

function normalizeMunicipioKey(value) {
    return normalizeText(value)
        .replace(/\s+/g, ' ')
        .trim();
}

const RISARALDA_MUNICIPIOS = [
    'Apía',
    'Balboa',
    'Belén de Umbría',
    'Dosquebradas',
    'Guática',
    'La Celia',
    'La Virginia',
    'Marsella',
    'Mistrató',
    'Pereira',
    'Pueblo Rico',
    'Quinchía',
    'Santa Rosa de Cabal',
    'Santuario'
];

const RISARALDA_NV_REFERENCIA_2026 = {
    [normalizeMunicipioKey('Apía')]: 15,
    [normalizeMunicipioKey('Balboa')]: 6,
    [normalizeMunicipioKey('Belén de Umbría')]: 15,
    [normalizeMunicipioKey('Dosquebradas')]: 258,
    [normalizeMunicipioKey('Guática')]: 9,
    [normalizeMunicipioKey('La Celia')]: 11,
    [normalizeMunicipioKey('La Virginia')]: 30,
    [normalizeMunicipioKey('Marsella')]: 13,
    [normalizeMunicipioKey('Mistrató')]: 38,
    [normalizeMunicipioKey('Pereira')]: 485,
    [normalizeMunicipioKey('Pueblo Rico')]: 66,
    [normalizeMunicipioKey('Quinchía')]: 31,
    [normalizeMunicipioKey('Santa Rosa de Cabal')]: 87,
    [normalizeMunicipioKey('Santuario')]: 11
};

function boolLike(value) {
    const txt = normalizeText(value);
    return txt === 'SI' || txt === 'S' || txt === '1' || txt === 'TRUE' || txt === 'VERDADERO' || txt === 'Y' || txt === 'YES' || txt === 'X';
}

function pct(part, total) {
    if (!total || total <= 0) return 0;
    return (Number(part || 0) * 100) / total;
}

function formatPct(part, total, decimals = 1) {
    return `${pct(part, total).toFixed(decimals)}%`;
}

function formatNumber(value, decimals = 0) {
    const num = Number(value || 0);
    if (!Number.isFinite(num)) return '0';
    return num.toLocaleString('es-CO', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}

function buildMapLegendHtml() {
    return '';
}

function riskColorByRatio(razon) {
    if (razon === null || razon === undefined || !Number.isFinite(Number(razon))) return '#D1D5DB';
    const value = Number(razon || 0);
    if (value > 150) return '#8B1A1A';
    if (value >= 70) return '#F4B400';
    return '#A8D5BA';
}

function riskClassByRatio(razon) {
    if (razon === null || razon === undefined || !Number.isFinite(Number(razon))) {
        return 'bg-slate-300 text-slate-700 font-semibold';
    }
    const value = Number(razon || 0);
    if (value > 150) return 'bg-red-800 text-white font-semibold';
    if (value >= 70) return 'bg-amber-400 text-amber-900 font-semibold';
    return 'bg-green-200 text-green-900 font-semibold';
}

function riskLabelByRatio(razon) {
    if (razon === null || razon === undefined || !Number.isFinite(Number(razon))) return 'SIN DATOS DE NV';
    const value = Number(razon || 0);
    if (value > 150) return 'ALTO RIESGO';
    if (value >= 70) return 'RIESGO INTERMEDIO';
    return 'RIESGO BAJO';
}

function toRoman(num) {
    const map = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII', 'XIII'];
    const n = Math.max(1, Math.min(13, Math.trunc(Number(num) || 1)));
    return map[n] || 'I';
}

function buildTerritorialSubtitle(rows) {
    let maxSemana = 8;
    let anio = new Date().getFullYear();

    rows.forEach((row) => {
        const semana = toNumber(row.semana);
        const y = toNumber(row.a_o);
        if (semana !== null && semana > maxSemana) {
            maxSemana = Math.trunc(semana);
        }
        if (y !== null && y > 1900) {
            anio = Math.trunc(y);
        }
    });

    const periodo = Math.ceil(maxSemana / 4);
    return `Risaralda PE ${toRoman(periodo)} SE ${String(maxSemana).padStart(2, '0')}, ${anio}`;
}

function buildTerritorialSource(rows) {
    let anio = new Date().getFullYear();
    rows.forEach((row) => {
        const y = toNumber(row.a_o);
        if (y !== null && y > 1900) {
            anio = Math.trunc(y);
        }
    });
    return `Fuente: SIVIGILA ${anio}`;
}

function ensureChartTitlesAndSubtitles() {
    Object.entries(CHART_META).forEach(([chartId, meta]) => {
        const target = document.getElementById(chartId);
        if (!target) return;

        const box = target.closest('.grafico-box') || target.closest('.mapa-section');
        if (!box) return;

        const title = box.querySelector('h4');
        if (title && meta.title) {
            title.textContent = meta.title;
        }

        const subtitleId = `subtitle-${chartId}`;
        let subtitle = box.querySelector(`#${subtitleId}`);
        if (!subtitle) {
            subtitle = document.createElement('p');
            subtitle.id = subtitleId;
            subtitle.className = 'chart-subtitle';
            if (title) {
                title.insertAdjacentElement('afterend', subtitle);
            } else {
                box.insertAdjacentElement('afterbegin', subtitle);
            }
        }
        subtitle.textContent = meta.subtitle || '';
    });

    const legend = document.getElementById('leyenda-riesgo-mapa');
    if (legend) {
        legend.innerHTML = buildMapLegendHtml();
        legend.style.display = 'none';
    }
}

function clearAndGetCanvas(containerId, heightPx = 320) {
    const container = document.getElementById(containerId);
    if (!container) return null;

    if (chartsEvento549[containerId]) {
        chartsEvento549[containerId].destroy();
        delete chartsEvento549[containerId];
    }

    container.innerHTML = '';
    const canvas = document.createElement('canvas');
    canvas.style.width = '100%';
    canvas.style.height = `${heightPx}px`;
    container.appendChild(canvas);
    return canvas;
}

function maybeShowNoData(containerId, message) {
    const container = document.getElementById(containerId);
    if (!container) return true;
    container.innerHTML = `<div class="territorial-empty-cell">${message}</div>`;
    return false;
}

function chartTooltipCallbacks(chartType) {
    return {
        title(items) {
            if (!items || !items.length) return '';
            return items[0].label || '';
        },
        label(context) {
            const label = context.dataset?.label || 'Valor';
            const value = Number(context.raw || 0);
            return `${label}: ${formatNumber(value, 1)}`;
        },
        afterLabel(context) {
            const value = Number(context.raw || 0);
            if (chartType === 'pie' || chartType === 'doughnut') {
                const all = context.dataset?.data || [];
                const total = all.reduce((acc, n) => acc + Number(n || 0), 0);
                return `Participacion: ${formatPct(value, total, 1)} (${formatNumber(value, 0)} casos)`;
            }
            return `Casos: ${formatNumber(value, 0)}`;
        }
    };
}

function chartDataLabelsConfig(chartType) {
    if (chartType === 'pie' || chartType === 'doughnut') {
        return {
            color: '#1F2937',
            font: { weight: '700', size: 10 },
            formatter(value, ctx) {
                const all = ctx.dataset?.data || [];
                const total = all.reduce((acc, n) => acc + Number(n || 0), 0);
                if (!total) return '0%';
                return `${pct(value, total).toFixed(1)}%\n(${formatNumber(value, 0)})`;
            }
        };
    }

    return {
        color: '#1F2937',
        anchor: 'end',
        align: 'end',
        clamp: true,
        offset: 2,
        font: { weight: '700', size: 10 },
        formatter(value) {
            const num = Number(value || 0);
            return Number.isFinite(num) ? formatNumber(num, 0) : '';
        }
    };
}

function renderChartJs(containerId, config, heightPx = 320) {
    if (!window.Chart) return;
    const canvas = clearAndGetCanvas(containerId, heightPx);
    if (!canvas) return;

    const chartType = config.type || 'bar';

    const baseOptions = {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 180 },
        plugins: {
            legend: {
                display: true,
                position: 'top',
                labels: {
                    boxWidth: 12,
                    usePointStyle: true,
                    color: '#1F2937',
                    font: { size: 11 }
                }
            },
            tooltip: {
                mode: 'index',
                intersect: false,
                callbacks: chartTooltipCallbacks(chartType)
            },
            datalabels: chartDataLabelsConfig(chartType)
        }
    };

    const mergedOptions = {
        ...baseOptions,
        ...(config.options || {}),
        plugins: {
            ...baseOptions.plugins,
            ...((config.options && config.options.plugins) || {})
        }
    };

    chartsEvento549[containerId] = new Chart(canvas.getContext('2d'), {
        ...config,
        options: mergedOptions
    });
}

function ensureExtraDashboardStructure() {
    const resumenGrid = document.querySelector('#resumen .kpi-grid');
    if (resumenGrid && !document.getElementById('kpi-letalidad')) {
        const card = document.createElement('div');
        card.className = 'kpi-card naranja';
        card.innerHTML = [
            '<div class="kpi-icon">⚕️</div>',
            '<div class="kpi-label">% LETALIDAD</div>',
            '<div class="kpi-valor" id="kpi-letalidad">—</div>',
            '<div class="kpi-subtexto" id="kpi-letalidad-subtexto">Defuncion registrada</div>'
        ].join('');
        resumenGrid.appendChild(card);
        resumenGrid.classList.remove('kpi-3col');
        resumenGrid.classList.add('kpi-4col');
    }

    const socioTab = document.getElementById('sociodemografico');
    if (socioTab && !document.getElementById('grafico-vulnerables')) {
        const socioExtra = document.createElement('section');
        socioExtra.className = 'graficos-grid grid-2col';
        socioExtra.id = 'socio-extra-graficos';
        socioExtra.innerHTML = [
            '<div class="grafico-box"><h4>Grupos vulnerables reportados</h4><div id="grafico-vulnerables" class="chart-h-320"></div></div>',
            '<div class="grafico-box"><h4>Estrato socioeconomico por area</h4><div id="grafico-estrato-area" class="chart-h-320"></div></div>'
        ].join('');
        const tabla = socioTab.querySelector('.tabla-section');
        socioTab.insertBefore(socioExtra, tabla || null);
    }

    const clinicoTab = document.getElementById('clinico');
    if (clinicoTab && !document.getElementById('grafico-complicaciones-clinicas')) {
        const clinicoExtra = document.createElement('section');
        clinicoExtra.className = 'graficos-grid grid-2col';
        clinicoExtra.id = 'clinico-extra-graficos';
        clinicoExtra.innerHTML = [
            '<div class="grafico-box"><h4>Complicaciones graves asociadas</h4><div id="grafico-complicaciones-clinicas" class="chart-h-320"></div></div>',
            '<div class="grafico-box"><h4>Semanas gestacionales al evento</h4><div id="grafico-semanas-gestacionales" class="chart-h-320"></div></div>'
        ].join('');
        const tabla = clinicoTab.querySelector('.tabla-section');
        clinicoTab.insertBefore(clinicoExtra, tabla || null);
    }

    // Limpia inyecciones antiguas para priorizar la tabla oficial junto al mapa.
    const territorialExtra = document.getElementById('territorial-extra-graficos');
    if (territorialExtra) {
        territorialExtra.remove();
    }

    ensureChartTitlesAndSubtitles();
}

function countBy(rows, mapper) {
    const map = new Map();
    rows.forEach((row) => {
        const raw = mapper(row);
        const key = (raw === null || raw === undefined || String(raw).trim() === '') ? 'SIN DATO' : String(raw).trim();
        map.set(key, (map.get(key) || 0) + 1);
    });
    return [...map.entries()].map(([label, value]) => ({ label, value }));
}

function buildTerritorialSummary(rows) {
    const summary = new Map();
    let hasNumVivos = false;

    RISARALDA_MUNICIPIOS.forEach((municipio) => {
        const key = normalizeMunicipioKey(municipio);
        summary.set(key, {
            municipio,
            casos: 0,
            nacidosVivos: 0,
            tieneNvFiltrado: false
        });
    });

    rows.forEach((row) => {
        const municipioRaw = String(row.nmun_resi || '').trim();
        const municipio = municipioRaw || '';
        const key = normalizeMunicipioKey(municipio);

        // Solo tabla oficial de 14 municipios del departamento.
        if (!summary.has(key)) {
            return;
        }

        const item = summary.get(key);
        item.casos += 1;

        const numVivos = toNumber(row.num_vivos);
        if (numVivos !== null) {
            item.tieneNvFiltrado = true;
            item.nacidosVivos += numVivos;
        }
    });

    const filas = [...summary.entries()].map(([key, item]) => {
        const nv = item.tieneNvFiltrado
            ? item.nacidosVivos
            : (RISARALDA_NV_REFERENCIA_2026[key] ?? null);
        const razon = (nv === null)
            ? null
            : (nv > 0 ? (item.casos / nv) * 1000 : 0);
        if (nv !== null) {
            hasNumVivos = true;
        }
        return {
            municipio: item.municipio,
            casos: item.casos,
            nacidosVivos: nv,
            razon
        };
    }).sort((a, b) => {
        const ra = Number.isFinite(Number(a.razon)) ? Number(a.razon) : -1;
        const rb = Number.isFinite(Number(b.razon)) ? Number(b.razon) : -1;
        if (rb !== ra) return rb - ra;
        return b.casos - a.casos;
    });

    const totalCasos = filas.reduce((acc, row) => acc + row.casos, 0);
    const totalNv = hasNumVivos
        ? filas.reduce((acc, row) => acc + Number(row.nacidosVivos || 0), 0)
        : null;
    const totalRazon = hasNumVivos && Number(totalNv) > 0 ? (totalCasos / Number(totalNv)) * 1000 : null;

    return {
        filas,
        total: {
            municipio: 'Risaralda',
            casos: totalCasos,
            nacidosVivos: totalNv,
            razon: totalRazon
        },
        numVivosDisponible: hasNumVivos
    };
}

async function cargarGeojsonRisaralda() {
    if (geojsonRisaralda) return geojsonRisaralda;
    if (!geojsonRisaraldaPromise) {
        geojsonRisaraldaPromise = fetch(`/api/geojson-risaralda?ts=${Date.now()}`, {
            method: 'GET',
            cache: 'no-store'
        })
            .then(async (response) => {
                const payload = await response.json().catch(() => null);
                if (!response.ok || !payload || !payload.ok || !payload.geojson) {
                    throw new Error((payload && payload.error) || 'No se pudo cargar el croquis municipal');
                }
                geojsonRisaralda = payload.geojson;
                return geojsonRisaralda;
            })
            .finally(() => {
                geojsonRisaraldaPromise = null;
            });
    }
    return geojsonRisaraldaPromise;
}

function featureMunicipioName(feature) {
    if (!feature || !feature.properties) return 'SIN DATO';
    const p = feature.properties;
    return String(p.MpNombre || p.mpnombre || p.municipio || p.nombre || p.NAME || 'SIN DATO').trim();
}

function flattenCoordinates(geometry) {
    if (!geometry || !geometry.type || !Array.isArray(geometry.coordinates)) return [];
    if (geometry.type === 'Polygon') return [geometry.coordinates];
    if (geometry.type === 'MultiPolygon') return geometry.coordinates;
    return [];
}

function computeGeoBounds(features) {
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;

    features.forEach((feature) => {
        const polygons = flattenCoordinates(feature.geometry);
        polygons.forEach((polygon) => {
            polygon.forEach((ring) => {
                ring.forEach((coord) => {
                    const x = Number(coord[0]);
                    const y = Number(coord[1]);
                    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
                    minX = Math.min(minX, x);
                    minY = Math.min(minY, y);
                    maxX = Math.max(maxX, x);
                    maxY = Math.max(maxY, y);
                });
            });
        });
    });

    return {
        minX,
        minY,
        maxX,
        maxY,
        width: Math.max(0.00001, maxX - minX),
        height: Math.max(0.00001, maxY - minY)
    };
}

function projectCoord(coord, bounds, width, height, pad) {
    const x = pad + ((coord[0] - bounds.minX) / bounds.width) * (width - (pad * 2));
    const y = pad + ((bounds.maxY - coord[1]) / bounds.height) * (height - (pad * 2));
    return [x, y];
}

function polygonToPathD(polygons, bounds, width, height, pad) {
    const parts = [];
    polygons.forEach((polygon) => {
        polygon.forEach((ring) => {
            if (!Array.isArray(ring) || !ring.length) return;
            const projected = ring.map((coord) => projectCoord(coord, bounds, width, height, pad));
            const first = projected[0];
            if (!first) return;
            const cmds = [`M ${first[0].toFixed(2)} ${first[1].toFixed(2)}`];
            for (let i = 1; i < projected.length; i += 1) {
                cmds.push(`L ${projected[i][0].toFixed(2)} ${projected[i][1].toFixed(2)}`);
            }
            cmds.push('Z');
            parts.push(cmds.join(' '));
        });
    });
    return parts.join(' ');
}

function polygonLabelPoint(polygons, bounds, width, height, pad) {
    if (!polygons.length || !polygons[0].length || !polygons[0][0].length) {
        return [width / 2, height / 2];
    }
    const firstRing = polygons[0][0];
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    firstRing.forEach((coord) => {
        minX = Math.min(minX, coord[0]);
        minY = Math.min(minY, coord[1]);
        maxX = Math.max(maxX, coord[0]);
        maxY = Math.max(maxY, coord[1]);
    });
    const center = [(minX + maxX) / 2, (minY + maxY) / 2];
    return projectCoord(center, bounds, width, height, pad);
}

function ensureMapTooltip(containerId = 'grafico-mapa') {
    const container = document.getElementById(containerId);
    if (!container) return null;
    let tooltip = container.querySelector('.map-tooltip');
    if (!tooltip) {
        tooltip = document.createElement('div');
        tooltip.className = 'map-tooltip';
        container.appendChild(tooltip);
    }
    return tooltip;
}

function bindMapTooltipHandlers(pathEl, stats, containerId = 'grafico-mapa') {
    const container = document.getElementById(containerId);
    const tooltip = ensureMapTooltip(containerId);
    if (!container || !tooltip) return;

    const html = [
        `<strong>${stats.municipio}</strong>`,
        `<div>Nº casos: <strong>${formatNumber(stats.casos, 0)}</strong></div>`,
        `<div>Nacidos vivos 2026: <strong>${stats.nacidosVivos === null ? '-' : formatNumber(stats.nacidosVivos, 0)}</strong></div>`,
        `<div>Razon MME: <strong>${stats.razon === null ? '-' : formatNumber(stats.razon, 1)}</strong></div>`,
        `<div>${riskLabelByRatio(stats.razon)}</div>`
    ].join('');

    const show = (ev) => {
        tooltip.innerHTML = html;
        tooltip.classList.add('visible');
        const rect = container.getBoundingClientRect();
        const x = (ev.clientX - rect.left) + 12;
        const y = (ev.clientY - rect.top) + 12;
        tooltip.style.left = `${x}px`;
        tooltip.style.top = `${y}px`;
    };

    const hide = () => tooltip.classList.remove('visible');

    pathEl.addEventListener('mousemove', show);
    pathEl.addEventListener('mouseenter', show);
    pathEl.addEventListener('mouseleave', hide);
    pathEl.addEventListener('focus', (ev) => {
        const bounds = pathEl.getBoundingClientRect();
        const fakeEv = { clientX: bounds.left + (bounds.width / 2), clientY: bounds.top + (bounds.height / 2) };
        show(fakeEv);
    });
    pathEl.addEventListener('blur', hide);
}

function renderSvgRisaraldaMap(summaryRows, containerId = 'grafico-mapa') {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (!geojsonRisaralda || !Array.isArray(geojsonRisaralda.features) || !geojsonRisaralda.features.length) {
        if (containerId === 'grafico-mapa') {
            maybeShowNoData('grafico-mapa', 'Croquis municipal no disponible. Carga el archivo de municipios para activar el mapa.');
        } else {
            container.innerHTML = '<div class="territorial-empty-cell">Croquis municipal no disponible.</div>';
        }
        return;
    }

    const width = 960;
    const height = 620;
    const pad = 18;
    const features = geojsonRisaralda.features;
    const bounds = computeGeoBounds(features);
    const summaryMap = new Map(summaryRows.map((row) => [normalizeMunicipioKey(row.municipio), row]));

    container.innerHTML = '';
    const svgNS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'Mapa de riesgo de Morbilidad Materna Extrema por municipio de Risaralda');

    features.forEach((feature) => {
        const municipio = featureMunicipioName(feature);
        const key = normalizeMunicipioKey(municipio);
        const stats = summaryMap.get(key) || {
            municipio,
            casos: 0,
            nacidosVivos: null,
            razon: null
        };

        const polygons = flattenCoordinates(feature.geometry);
        const d = polygonToPathD(polygons, bounds, width, height, pad);
        if (!d) return;

        const path = document.createElementNS(svgNS, 'path');
        path.setAttribute('d', d);
        path.setAttribute('fill', riskColorByRatio(stats.razon));
        path.setAttribute('class', 'map-svg-region');
        path.setAttribute('tabindex', '0');
        path.setAttribute('aria-label', `${municipio}, ${formatNumber(stats.casos, 0)} casos, razon ${stats.razon === null ? '-' : formatNumber(stats.razon, 1)}`);
        const title = document.createElementNS(svgNS, 'title');
        title.textContent = `${municipio} · Casos ${formatNumber(stats.casos, 0)} · NV ${stats.nacidosVivos === null ? '-' : formatNumber(stats.nacidosVivos, 0)} · Razon ${stats.razon === null ? '-' : formatNumber(stats.razon, 1)}`;
        path.appendChild(title);
        bindMapTooltipHandlers(path, stats, containerId);
        svg.appendChild(path);

        const labelPoint = polygonLabelPoint(polygons, bounds, width, height, pad);
        const text = document.createElementNS(svgNS, 'text');
        text.setAttribute('x', labelPoint[0].toFixed(1));
        text.setAttribute('y', labelPoint[1].toFixed(1));
        text.setAttribute('class', 'map-svg-label');
        text.textContent = municipio.split(' ')[0];
        svg.appendChild(text);
    });

    container.appendChild(svg);
    ensureMapTooltip(containerId);
}

function getRows() {
    return Array.isArray(cleanedData) ? cleanedData : [];
}

function buildAgeStats(rows) {
    const ages = rows.map(r => toNumber(r.edad)).filter(v => v !== null && v >= 0);
    if (!ages.length) {
        return { promedio: 0, minima: 0, maxima: 0, moda: 0 };
    }
    const freq = new Map();
    ages.forEach(a => freq.set(a, (freq.get(a) || 0) + 1));
    const moda = [...freq.entries()].sort((a, b) => b[1] - a[1])[0][0];
    return {
        promedio: (ages.reduce((acc, a) => acc + a, 0) / ages.length).toFixed(1),
        minima: Math.min(...ages),
        maxima: Math.max(...ages),
        moda
    };
}

function buildAgeBins(rows) {
    const bins = [
        { label: '10-14', min: 10, max: 14 },
        { label: '15-19', min: 15, max: 19 },
        { label: '20-24', min: 20, max: 24 },
        { label: '25-29', min: 25, max: 29 },
        { label: '30-34', min: 30, max: 34 },
        { label: '35-39', min: 35, max: 39 },
        { label: '40-44', min: 40, max: 44 },
        { label: '>=45', min: 45, max: 200 }
    ];
    const counts = bins.map(() => 0);
    rows.forEach((row) => {
        const edad = toNumber(row.edad);
        if (edad === null) return;
        const idx = bins.findIndex(b => edad >= b.min && edad <= b.max);
        if (idx >= 0) counts[idx] += 1;
    });
    return bins.map((b, i) => ({ grupo: b.label, casos: counts[i], porcentaje: pct(counts[i], rows.length).toFixed(1) }));
}

function buildSemanas(rows) {
    const sem = new Map();
    rows.forEach((row) => {
        const semanaRaw = toNumber(row.semana);
        if (semanaRaw === null || semanaRaw <= 0) return;
        const semana = Math.trunc(semanaRaw);
        const anioRaw = toNumber(row.a_o);
        const anio = anioRaw !== null && anioRaw > 1900 ? Math.trunc(anioRaw) : new Date().getFullYear();
        const key = `${anio}-S${String(semana).padStart(2, '0')}`;
        sem.set(key, (sem.get(key) || 0) + 1);
    });

    const sorted = [...sem.entries()].sort((a, b) => a[0].localeCompare(b[0]));
    return sorted.map(([semana, casos]) => ({ semana, casos }));
}

function buildCalidad(rows, baseCalidad = {}) {
    const total = rows.length;
    const criticas = ['edad', 'semana', 'a_o', 'pac_hos', 'nmun_resi', 'caus_agrup'];

    const completos = rows.filter((row) => criticas.every((c) => String(row[c] ?? '').trim() !== '')).length;
    const signatures = new Set(rows.map((r) => criticas.map(c => String(r[c] ?? '').trim()).join('|')));

    const diasNotif = rows
        .map(r => toNumber(r.dias_notificacion))
        .filter(v => v !== null && v >= 0);
    const oportuna = diasNotif.filter(v => v <= 7).length;
    const tardia = diasNotif.filter(v => v > 7).length;

    return {
        notificacionOportuna: diasNotif.length ? oportuna : Number(baseCalidad.notificacionOportuna || 0),
        notificacionTardia: diasNotif.length ? tardia : Number(baseCalidad.notificacionTardia || 0),
        porcentajeOportunidad: diasNotif.length ? pct(oportuna, diasNotif.length) : Number(baseCalidad.porcentajeOportunidad || 0),
        completitud: total ? pct(completos, total) : 0,
        porcentajeSinDuplicados: total ? pct(signatures.size, total) : 0,
        diasPromedioNotificacion: diasNotif.length ? (diasNotif.reduce((a, b) => a + b, 0) / diasNotif.length) : null
    };
}

function buildDatosDesdeCleanedData(payload) {
    const base = construirDatosDesdePayload(payload);
    const rows = getRows();
    const total = rows.length || Number(payload.total_casos || base.totalCasos || 0);

    const semanas = buildSemanas(rows);
    const gruposEdad = buildAgeBins(rows);
    const edadEstadisticas = buildAgeStats(rows);

    const hospitalizadas = rows.filter(r => boolLike(r.pac_hos)).length;
    const uci = rows.filter(r => boolLike(r.ingres_uci)).length;
    const defuncion = rows.filter(r => String(r.fec_def || '').trim() !== '').length;

    const calidad = buildCalidad(rows, base.calidad || {});

    return {
        ...base,
        totalCasos: total,
        semanas,
        gruposEdad,
        edadEstadisticas,
        afiliacion: countBy(rows, r => r.per_etn).sort((a, b) => b.value - a.value).slice(0, 8).map(it => ({
            tipo: it.label,
            casos: it.value,
            porcentaje: pct(it.value, total).toFixed(1)
        })),
        causas: countBy(rows, r => r.caus_agrup).sort((a, b) => b.value - a.value).slice(0, 10).map(it => ({
            causa: it.label,
            casos: it.value,
            porcentaje: pct(it.value, total).toFixed(1)
        })),
        municipios: countBy(rows, r => r.nmun_resi).sort((a, b) => b.value - a.value).map((item) => ({
            nombre: item.label,
            casos: item.value,
            porcentaje: pct(item.value, total).toFixed(1)
        })),
        momentoEvento: countBy(rows, r => r.term_gesta).sort((a, b) => b.value - a.value).slice(0, 8).map(it => ({
            momento: it.label,
            casos: it.value,
            porcentaje: pct(it.value, total).toFixed(1)
        })),
        calidad: {
            ...(base.calidad || {}),
            ...calidad,
            hospitalizacion: hospitalizadas,
            porcentajeHospitalizacion: pct(hospitalizadas, total),
            requiereUCI: uci,
            porcentajeUCI: pct(uci, total),
            letalidad: pct(defuncion, total)
        }
    };
}

function boletinTemplateHtml() {
    return `
        <div class="boletin-actions no-print mb-4 flex flex-wrap items-center gap-3">
            <button id="btn-generar-boletin" class="inline-flex items-center justify-center rounded-md bg-[#1D4E89] px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#163A66]">
                Generar / Actualizar Boletin
            </button>
            <button id="btn-descargar-boletin" class="inline-flex items-center justify-center rounded-md bg-[#0F766E] px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#0b5a55]">
                Descargar como PDF
            </button>
            <span class="text-xs text-slate-600">Fuente dinamica: cleanedData (archivo depurado en tiempo real)</span>
        </div>

        <article id="boletin-print-root" class="boletin-pdf-surface rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <header class="boletin-print-section rounded-lg border border-slate-200 bg-slate-50 p-5">
                <p class="mb-1 text-xs font-semibold uppercase tracking-wide text-[#1D4E89]">Secretaria de Salud Departamental - Risaralda</p>
                <h2 id="evento-titulo-boletin" class="text-2xl font-bold text-slate-900">Boletin Epidemiologico - Morbilidad Materna Extrema</h2>
                <p id="boletin-periodo-dinamico" class="mt-1 text-sm text-slate-600">Periodo Epidemiologico II Semana Epidemiologica 08, 2026</p>
                <div class="mt-4 grid gap-3 md:grid-cols-4">
                    <div class="rounded-md border border-slate-200 bg-white p-3 text-center">
                        <p id="boletin-casos" class="text-3xl font-extrabold text-[#1D4E89]">0</p>
                        <p class="text-xs font-medium text-slate-600">Casos reportados</p>
                    </div>
                    <div class="rounded-md border border-slate-200 bg-white p-3 text-center">
                        <p id="boletin-variacion" class="text-xl font-bold text-[#0F766E]">N/D</p>
                        <p class="text-xs font-medium text-slate-600">Variacion vs mismo periodo previo</p>
                    </div>
                    <div class="rounded-md border border-slate-200 bg-white p-3 text-center">
                        <p id="boletin-razon-departamental" class="text-2xl font-bold text-[#B45309]">0.0</p>
                        <p class="text-xs font-medium text-slate-600">Razon MME departamental x 1.000 NV</p>
                    </div>
                    <div class="rounded-md border border-slate-200 bg-white p-3 text-center">
                        <p id="boletin-hospitalizados" class="text-2xl font-bold text-slate-800">0</p>
                        <p class="text-xs font-medium text-slate-600">Hospitalizadas</p>
                    </div>
                </div>
                <p class="mt-2 text-xs text-slate-500">Semana epidemiologica: <span id="boletin-semana">08</span> | <span id="metodologia-periodo">Año 2026</span> | Actualizado: <span id="boletin-fecha">--</span></p>
            </header>

            <section class="boletin-print-section mt-4 rounded-lg border border-slate-200 p-4">
                <h3 class="mb-2 text-base font-bold text-[#1D4E89]">1. Introduccion</h3>
                <textarea id="boletin-introduccion-texto" class="boletin-editor-textarea h-36 w-full rounded-md border border-slate-300 p-3 text-sm leading-relaxed text-slate-700"></textarea>
            </section>

            <section class="boletin-print-section mt-4 rounded-lg border border-slate-200 p-4">
                <h3 class="mb-2 text-base font-bold text-[#1D4E89]">2. Comportamiento en Risaralda</h3>
                <div class="rounded-md border border-slate-200 p-3">
                    <h4 class="mb-2 text-sm font-semibold text-slate-700">Comportamiento de la notificacion por semana epidemiologica</h4>
                    <canvas id="boletin-chart-curva" height="260"></canvas>
                </div>
                <div class="mt-3 grid gap-3 md:grid-cols-3">
                    <div class="rounded-md border border-slate-200 bg-slate-50 p-3 text-center">
                        <div id="boletin-kpi-total" class="text-xl font-bold text-[#1D4E89]">0</div>
                        <div class="text-xs text-slate-600">Total casos</div>
                    </div>
                    <div class="rounded-md border border-slate-200 bg-slate-50 p-3 text-center">
                        <div id="boletin-kpi-variacion" class="text-xl font-bold text-[#0F766E]">N/D</div>
                        <div class="text-xs text-slate-600">Variacion %</div>
                    </div>
                    <div class="rounded-md border border-slate-200 bg-slate-50 p-3 text-center">
                        <div id="boletin-kpi-razon" class="text-xl font-bold text-[#B45309]">0.0</div>
                        <div class="text-xs text-slate-600">Razon departamental</div>
                    </div>
                </div>
            </section>

            <section class="boletin-print-section mt-4 rounded-lg border border-slate-200 p-4">
                <h3 class="mb-2 text-base font-bold text-[#1D4E89]">3. Variables Sociodemograficas</h3>
                <div class="grid gap-3 md:grid-cols-2">
                    <div class="rounded-md border border-slate-200 p-3"><h4 class="mb-2 text-sm font-semibold">Distribucion por edad</h4><canvas id="boletin-chart-edad" height="220"></canvas></div>
                    <div class="rounded-md border border-slate-200 p-3"><h4 class="mb-2 text-sm font-semibold">Distribucion por area de residencia</h4><canvas id="boletin-chart-area" height="220"></canvas></div>
                    <div class="rounded-md border border-slate-200 p-3"><h4 class="mb-2 text-sm font-semibold">Distribucion por estrato</h4><canvas id="boletin-chart-estrato" height="220"></canvas></div>
                    <div class="rounded-md border border-slate-200 p-3"><h4 class="mb-2 text-sm font-semibold">Distribucion por afiliacion</h4><canvas id="boletin-chart-afiliacion" height="220"></canvas></div>
                </div>
                <div class="mt-3 rounded-md border border-slate-200 p-3">
                    <h4 class="mb-2 text-sm font-semibold">Pertenencia etnica</h4>
                    <canvas id="boletin-chart-etnia" height="220"></canvas>
                </div>
                <div class="mt-3 overflow-x-auto rounded-md border border-slate-200">
                    <table class="w-full border-collapse text-sm">
                        <thead class="bg-slate-100">
                            <tr>
                                <th class="border border-slate-300 px-3 py-2 text-left">Grupo de edad</th>
                                <th class="border border-slate-300 px-3 py-2 text-center">N° casos</th>
                                <th class="border border-slate-300 px-3 py-2 text-center">Porcentaje</th>
                            </tr>
                        </thead>
                        <tbody id="boletin-tabla-edad-body"></tbody>
                    </table>
                </div>
            </section>

            <section class="boletin-print-section mt-4 rounded-lg border border-slate-200 p-4">
                <h3 class="mb-2 text-base font-bold text-[#1D4E89]">4. Variables Clinicas</h3>
                <div class="grid gap-3 md:grid-cols-2">
                    <div class="rounded-md border border-slate-200 p-3"><h4 class="mb-2 text-sm font-semibold">Momento del evento</h4><canvas id="boletin-chart-momento" height="220"></canvas></div>
                    <div class="rounded-md border border-slate-200 p-3"><h4 class="mb-2 text-sm font-semibold">Semanas de gestacion</h4><canvas id="boletin-chart-semanas-gest" height="220"></canvas></div>
                    <div class="rounded-md border border-slate-200 p-3"><h4 class="mb-2 text-sm font-semibold">Causas agrupadas</h4><canvas id="boletin-chart-causas" height="220"></canvas></div>
                    <div class="rounded-md border border-slate-200 p-3"><h4 class="mb-2 text-sm font-semibold">Complicaciones especificas</h4><canvas id="boletin-chart-complicaciones" height="220"></canvas></div>
                </div>
                <div class="mt-3 overflow-x-auto rounded-md border border-slate-200">
                    <table class="w-full border-collapse text-sm">
                        <thead class="bg-slate-100">
                            <tr>
                                <th class="border border-slate-300 px-3 py-2 text-left">Causa agrupada</th>
                                <th class="border border-slate-300 px-3 py-2 text-center">Casos</th>
                                <th class="border border-slate-300 px-3 py-2 text-center">%</th>
                            </tr>
                        </thead>
                        <tbody id="boletin-tabla-causas-body"></tbody>
                    </table>
                </div>
            </section>

            <section class="boletin-print-section mt-4 rounded-lg border border-slate-200 p-4">
                <h3 class="mb-2 text-base font-bold text-[#1D4E89]">5. Indicadores de Interes Epidemiologico y Razon por Municipio</h3>
                <p id="boletin-nv-warning" class="mb-2 hidden rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800"></p>
                <div class="grid gap-3 lg:grid-cols-2">
                    <div class="overflow-x-auto rounded-md border border-slate-200">
                        <table class="tabla-territorial w-full border-collapse text-sm">
                            <thead>
                                <tr>
                                    <th class="territorial-col-name">Municipio</th>
                                    <th class="territorial-col-cases">N° casos</th>
                                    <th class="territorial-col-nv">Nacidos vivos 2026</th>
                                    <th class="territorial-col-ratio">Razon MME</th>
                                </tr>
                            </thead>
                            <tbody id="boletin-tabla-municipal-body"></tbody>
                            <tfoot id="boletin-tabla-municipal-total"></tfoot>
                        </table>
                    </div>
                    <div class="rounded-md border border-slate-200 p-3">
                        <h4 class="mb-2 text-sm font-semibold">Mapa de Riesgo por Municipio</h4>
                        <div id="boletin-mapa-risaralda" class="h-[420px] rounded-md border border-slate-200 bg-slate-100"></div>
                        <div class="boletin-map-legend mt-2 grid grid-cols-1 gap-1 text-xs text-slate-700">
                            <div><span class="inline-block h-3 w-4 bg-[#8B1A1A]"></span> Rojo: mayor riesgo (&gt; 150)</div>
                            <div><span class="inline-block h-3 w-4 bg-[#F4B400]"></span> Amarillo: riesgo intermedio (70 a 150)</div>
                            <div><span class="inline-block h-3 w-4 bg-[#A8D5BA]"></span> Verde: menor riesgo (&lt; 70)</div>
                        </div>
                    </div>
                </div>
            </section>

            <section class="boletin-print-section mt-4 rounded-lg border border-slate-200 p-4">
                <h3 class="mb-2 text-base font-bold text-[#1D4E89]">6. Conclusiones</h3>
                <textarea id="boletin-conclusiones-texto" class="boletin-editor-textarea h-28 w-full rounded-md border border-slate-300 p-3 text-sm leading-relaxed text-slate-700"></textarea>
                <h3 class="mb-2 mt-4 text-base font-bold text-[#1D4E89]">7. Observaciones</h3>
                <textarea id="boletin-observaciones-texto" class="boletin-editor-textarea h-24 w-full rounded-md border border-slate-300 p-3 text-sm leading-relaxed text-slate-700"></textarea>
            </section>
        </article>
    `;
}

function boletinGetValue(row, keys) {
    for (const key of keys) {
        const raw = row && Object.prototype.hasOwnProperty.call(row, key) ? row[key] : null;
        const txt = String(raw ?? '').trim();
        if (txt) return txt;
    }
    return 'SIN DATO';
}

function ensureBoletinTemplate() {
    const section = document.getElementById('boletin');
    if (!section) return;

    if (!section.querySelector('#boletin-print-root')) {
        section.innerHTML = boletinTemplateHtml();
    }

    const intro = document.getElementById('boletin-introduccion-texto');
    const conclusiones = document.getElementById('boletin-conclusiones-texto');
    const observaciones = document.getElementById('boletin-observaciones-texto');

    if (intro && !intro.value.trim()) {
        intro.value = BOLETIN_TEXTOS_DEFAULT.introduccion;
    }
    if (conclusiones && !conclusiones.value.trim()) {
        conclusiones.value = BOLETIN_TEXTOS_DEFAULT.conclusiones;
    }
    if (observaciones && !observaciones.value.trim()) {
        observaciones.value = BOLETIN_TEXTOS_DEFAULT.observaciones;
    }

    if (!section.dataset.boletinBound) {
        const btnGenerar = document.getElementById('btn-generar-boletin');
        const btnPdf = document.getElementById('btn-descargar-boletin');
        if (btnGenerar) {
            btnGenerar.addEventListener('click', () => {
                renderBoletinEpidemiologico();
            });
        }
        if (btnPdf) {
            btnPdf.addEventListener('click', () => {
                descargarBoletinComoPdf();
            });
        }
        section.dataset.boletinBound = '1';
    }
}

function buildBoletinTemporalStats(rows) {
    const validRows = Array.isArray(rows) ? rows : [];
    const years = validRows
        .map((row) => toNumber(row.a_o))
        .filter((value) => value !== null && value > 1900)
        .map((value) => Math.trunc(value));

    const anioActual = years.length ? Math.max(...years) : (Number(datosActuales.año) || new Date().getFullYear());

    const weekRows = validRows
        .map((row) => ({
            year: Math.trunc(toNumber(row.a_o) || anioActual),
            week: Math.trunc(toNumber(row.semana) || 0)
        }))
        .filter((item) => item.week > 0 && item.week <= 53 && item.year === anioActual);

    const semanaMax = weekRows.length
        ? Math.max(...weekRows.map((item) => item.week))
        : Math.max(1, ...((datosActuales.semanas || []).map((item) => Math.trunc(Number(item.semana || 0))).filter((v) => v > 0)));

    const anioPrevio = anioActual - 1;
    const casosActualesPeriodo = validRows.filter((row) => {
        const y = Math.trunc(toNumber(row.a_o) || anioActual);
        const w = Math.trunc(toNumber(row.semana) || 0);
        return y === anioActual && w > 0 && w <= semanaMax;
    }).length;

    const casosPrevioPeriodo = validRows.filter((row) => {
        const y = Math.trunc(toNumber(row.a_o) || anioActual);
        const w = Math.trunc(toNumber(row.semana) || 0);
        return y === anioPrevio && w > 0 && w <= semanaMax;
    }).length;

    const variacion = casosPrevioPeriodo > 0
        ? (((casosActualesPeriodo - casosPrevioPeriodo) / casosPrevioPeriodo) * 100)
        : null;

    return {
        anioActual,
        anioPrevio,
        semanaMax,
        periodo: Math.max(1, Math.ceil(semanaMax / 4)),
        casosActualesPeriodo,
        casosPrevioPeriodo,
        variacion
    };
}

function renderBoletinChartJs(chartId, config) {
    const canvas = document.getElementById(chartId);
    if (!canvas || !window.Chart) return;

    if (boletinChartsEvento549[chartId]) {
        boletinChartsEvento549[chartId].destroy();
        delete boletinChartsEvento549[chartId];
    }

    const optionsBase = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                labels: {
                    boxWidth: 12,
                    font: { size: 11 }
                }
            }
        }
    };

    boletinChartsEvento549[chartId] = new Chart(canvas.getContext('2d'), {
        ...config,
        options: {
            ...optionsBase,
            ...(config.options || {}),
            plugins: {
                ...optionsBase.plugins,
                ...((config.options && config.options.plugins) || {})
            }
        }
    });
}

function fillBoletinAgeTable(ageRows, total) {
    const tbody = document.getElementById('boletin-tabla-edad-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    ageRows.forEach((item) => {
        const casos = Number(item.casos || 0);
        const pctTxt = total > 0 ? `${((casos * 100) / total).toFixed(1)}%` : '0.0%';
        tbody.innerHTML += `
            <tr>
                <td class="border border-slate-300 px-3 py-2">${item.grupo}</td>
                <td class="border border-slate-300 px-3 py-2 text-center">${formatNumber(casos, 0)}</td>
                <td class="border border-slate-300 px-3 py-2 text-center">${pctTxt}</td>
            </tr>
        `;
    });

    tbody.innerHTML += `
        <tr class="bg-slate-100 font-semibold">
            <td class="border border-slate-300 px-3 py-2">TOTAL</td>
            <td class="border border-slate-300 px-3 py-2 text-center">${formatNumber(total, 0)}</td>
            <td class="border border-slate-300 px-3 py-2 text-center">100.0%</td>
        </tr>
    `;
}

function fillBoletinCausasTable(causasRows, total) {
    const tbody = document.getElementById('boletin-tabla-causas-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    causasRows.forEach((item) => {
        const pctTxt = total > 0 ? `${((Number(item.value || 0) * 100) / total).toFixed(1)}%` : '0.0%';
        tbody.innerHTML += `
            <tr>
                <td class="border border-slate-300 px-3 py-2">${item.label}</td>
                <td class="border border-slate-300 px-3 py-2 text-center">${formatNumber(item.value, 0)}</td>
                <td class="border border-slate-300 px-3 py-2 text-center">${pctTxt}</td>
            </tr>
        `;
    });
}

function fillBoletinMunicipalTable(filas, total) {
    const tbody = document.getElementById('boletin-tabla-municipal-body');
    const tfoot = document.getElementById('boletin-tabla-municipal-total');
    if (!tbody || !tfoot) return;

    tbody.innerHTML = '';
    tfoot.innerHTML = '';

    filas.forEach((row) => {
        const ratioClass = riskClassByRatio(row.razon);
        const nvTxt = row.nacidosVivos === null ? '-' : formatNumber(row.nacidosVivos, 0);
        const razonTxt = row.razon === null ? '-' : formatNumber(row.razon, 1);

        tbody.innerHTML += `
            <tr>
                <td class="territorial-cell-name">${row.municipio}</td>
                <td class="territorial-cell-cases">${formatNumber(row.casos, 0)}</td>
                <td class="territorial-cell-nv">${nvTxt}</td>
                <td class="territorial-cell-ratio ${ratioClass}">${razonTxt}</td>
            </tr>
        `;
    });

    if (total) {
        const totalClass = riskClassByRatio(total.razon);
        const totalNvTxt = total.nacidosVivos === null ? '-' : formatNumber(total.nacidosVivos, 0);
        const totalRazonTxt = total.razon === null ? '-' : formatNumber(total.razon, 1);
        tfoot.innerHTML = `
            <tr class="territorial-total-row font-semibold">
                <td class="territorial-cell-name">Risaralda</td>
                <td class="territorial-cell-cases">${formatNumber(total.casos, 0)}</td>
                <td class="territorial-cell-nv">${totalNvTxt}</td>
                <td class="territorial-cell-ratio ${totalClass}">${totalRazonTxt}</td>
            </tr>
        `;
    }
}

function renderBoletinEpidemiologico() {
    ensureBoletinTemplate();

    const rows = getRows();
    const total = rows.length;
    const temporal = buildBoletinTemporalStats(rows);
    const resumenMunicipal = buildTerritorialSummary(rows);
    const razonDepto = resumenMunicipal.total && Number.isFinite(Number(resumenMunicipal.total.razon))
        ? Number(resumenMunicipal.total.razon)
        : null;
    const hospitalizadas = rows.filter((row) => boolLike(row.pac_hos)).length;

    const periodoTxt = `Periodo Epidemiologico ${toRoman(temporal.periodo)} Semana Epidemiologica ${String(temporal.semanaMax).padStart(2, '0')}, ${temporal.anioActual}`;
    const variacionTxt = temporal.variacion === null
        ? 'Sin base de comparacion'
        : `${temporal.variacion >= 0 ? 'Aumento' : 'Disminucion'} ${Math.abs(temporal.variacion).toFixed(1)}%`;

    const setText = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    };

    setText('boletin-periodo-dinamico', periodoTxt);
    setText('boletin-semana', String(temporal.semanaMax).padStart(2, '0'));
    setText('boletin-casos', formatNumber(total, 0));
    setText('boletin-hospitalizados', formatNumber(hospitalizadas, 0));
    setText('boletin-variacion', variacionTxt);
    setText('boletin-kpi-total', formatNumber(total, 0));
    setText('boletin-kpi-variacion', variacionTxt);
    setText('boletin-kpi-razon', razonDepto === null ? 'N/D' : formatNumber(razonDepto, 1));
    setText('boletin-razon-departamental', razonDepto === null ? 'N/D' : formatNumber(razonDepto, 1));
    setText('metodologia-periodo', `Año ${temporal.anioActual}`);
    setText('boletin-fecha', datosActuales.fechaActualizacion || new Date().toLocaleString('es-CO'));

    const variacionEl = document.getElementById('boletin-variacion');
    if (variacionEl) {
        if (temporal.variacion === null) {
            variacionEl.style.color = '#475569';
        } else if (temporal.variacion >= 0) {
            variacionEl.style.color = '#C2410C';
        } else {
            variacionEl.style.color = '#0F766E';
        }
    }

    const weekMap = new Map();
    rows.forEach((row) => {
        const y = Math.trunc(toNumber(row.a_o) || temporal.anioActual);
        const w = Math.trunc(toNumber(row.semana) || 0);
        if (y !== temporal.anioActual || w <= 0 || w > temporal.semanaMax) return;
        weekMap.set(w, (weekMap.get(w) || 0) + 1);
    });
    const weeklyRows = weekMap.size
        ? [...weekMap.entries()].sort((a, b) => a[0] - b[0]).map(([week, cases]) => ({ week, cases }))
        : (datosActuales.semanas || []).map((item) => ({ week: Number(item.semana || 0), cases: Number(item.casos || 0) })).filter((item) => item.week > 0);

    const weeklyLabels = weeklyRows.map((item) => `SE ${String(item.week).padStart(2, '0')}`);
    const weeklyCases = weeklyRows.map((item) => item.cases);
    const weeklyAcum = [];
    weeklyCases.reduce((acc, value, index) => {
        const sum = acc + Number(value || 0);
        weeklyAcum[index] = sum;
        return sum;
    }, 0);

    renderBoletinChartJs('boletin-chart-curva', {
        type: 'bar',
        data: {
            labels: weeklyLabels,
            datasets: [
                { label: 'Casos por SE', data: weeklyCases, backgroundColor: CHARTJS_PALETTE.primary },
                { label: 'Acumulado', data: weeklyAcum, type: 'line', borderColor: CHARTJS_PALETTE.warning, backgroundColor: CHARTJS_PALETTE.warning, tension: 0.25, pointRadius: 2, yAxisID: 'y1' }
            ]
        },
        options: {
            scales: {
                y: { beginAtZero: true, title: { display: true, text: 'Casos' } },
                y1: { beginAtZero: true, position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: 'Acumulado' } }
            }
        }
    });

    const ageRows = (datosActuales.gruposEdad && datosActuales.gruposEdad.length)
        ? datosActuales.gruposEdad.map((item) => ({ grupo: item.grupo, casos: Number(item.casos || 0) }))
        : buildAgeBins(rows).map((item) => ({ grupo: item.grupo, casos: Number(item.casos || 0) }));

    renderBoletinChartJs('boletin-chart-edad', {
        type: 'bar',
        data: {
            labels: ageRows.map((item) => item.grupo),
            datasets: [{ label: 'Casos', data: ageRows.map((item) => item.casos), backgroundColor: CHARTJS_PALETTE.lightBlue }]
        },
        options: { scales: { y: { beginAtZero: true } } }
    });
    fillBoletinAgeTable(ageRows, total);

    const areaRows = countBy(rows, (row) => row.area).sort((a, b) => b.value - a.value).slice(0, 6);
    renderBoletinChartJs('boletin-chart-area', {
        type: 'doughnut',
        data: {
            labels: areaRows.map((item) => item.label),
            datasets: [{ label: 'Area residencia', data: areaRows.map((item) => item.value), backgroundColor: [CHARTJS_PALETTE.primary, CHARTJS_PALETTE.secondary, CHARTJS_PALETTE.warning, CHARTJS_PALETTE.lightOrange, CHARTJS_PALETTE.lightGreen, CHARTJS_PALETTE.neutral] }]
        }
    });

    const estratos = ['1', '2', '3', '4', '5', '6', 'SIN DATO'];
    const estratoRows = estratos.map((label) => ({
        label,
        value: rows.filter((row) => (String(row.estrato || '').trim() || 'SIN DATO') === label).length
    }));
    renderBoletinChartJs('boletin-chart-estrato', {
        type: 'bar',
        data: {
            labels: estratoRows.map((item) => item.label),
            datasets: [{ label: 'Casos por estrato', data: estratoRows.map((item) => item.value), backgroundColor: CHARTJS_PALETTE.secondary }]
        },
        options: { scales: { y: { beginAtZero: true } } }
    });

    const afMap = { '1': 'Contributivo', '2': 'Subsidiado', '3': 'Especial', '4': 'Excepcion', '5': 'No asegurado', C: 'Contributivo', S: 'Subsidiado', E: 'Especial' };
    const afiliacionRows = countBy(rows, (row) => {
        const raw = boletinGetValue(row, ['tip_ss_', 'tip_ss', 'afiliacion', 'tipo_afiliacion', 'regimen']);
        const key = normalizeText(raw);
        return afMap[key] || raw;
    }).sort((a, b) => b.value - a.value).slice(0, 6);
    renderBoletinChartJs('boletin-chart-afiliacion', {
        type: 'bar',
        data: {
            labels: afiliacionRows.map((item) => item.label),
            datasets: [{ label: 'Casos por afiliacion', data: afiliacionRows.map((item) => item.value), backgroundColor: CHARTJS_PALETTE.lightOrange }]
        },
        options: { indexAxis: 'y', scales: { x: { beginAtZero: true } } }
    });

    const etniaRows = countBy(rows, (row) => row.per_etn).sort((a, b) => b.value - a.value).slice(0, 8);
    renderBoletinChartJs('boletin-chart-etnia', {
        type: 'bar',
        data: {
            labels: etniaRows.map((item) => item.label),
            datasets: [{ label: 'Casos por pertenencia etnica', data: etniaRows.map((item) => item.value), backgroundColor: CHARTJS_PALETTE.lightGreen }]
        },
        options: { scales: { y: { beginAtZero: true } } }
    });

    const momentoBuckets = { 'Antes del parto': 0, 'Durante el parto': 0, Puerperio: 0, 'Sin dato': 0 };
    rows.forEach((row) => {
        const txt = normalizeText(row.term_gesta || row.momento_evento || 'SIN DATO');
        if (txt.includes('PUERP')) {
            momentoBuckets.Puerperio += 1;
        } else if (txt.includes('PART')) {
            momentoBuckets['Durante el parto'] += 1;
        } else if (txt.includes('EMBAR') || txt.includes('GEST') || txt.includes('ANTE')) {
            momentoBuckets['Antes del parto'] += 1;
        } else {
            momentoBuckets['Sin dato'] += 1;
        }
    });
    renderBoletinChartJs('boletin-chart-momento', {
        type: 'pie',
        data: {
            labels: Object.keys(momentoBuckets),
            datasets: [{ label: 'Momento del evento', data: Object.values(momentoBuckets), backgroundColor: [CHARTJS_PALETTE.primary, CHARTJS_PALETTE.warning, CHARTJS_PALETTE.secondary, CHARTJS_PALETTE.neutral] }]
        }
    });

    const semGestBins = [
        { label: '1-12', min: 1, max: 12 },
        { label: '13-20', min: 13, max: 20 },
        { label: '21-28', min: 21, max: 28 },
        { label: '29-36', min: 29, max: 36 },
        { label: '>=37', min: 37, max: 60 }
    ];
    const semGestData = semGestBins.map((bin) => rows.filter((row) => {
        const value = toNumber(row.sem_ges);
        return value !== null && value >= bin.min && value <= bin.max;
    }).length);
    renderBoletinChartJs('boletin-chart-semanas-gest', {
        type: 'bar',
        data: {
            labels: semGestBins.map((bin) => bin.label),
            datasets: [{ label: 'Casos', data: semGestData, backgroundColor: CHARTJS_PALETTE.violet }]
        },
        options: { scales: { y: { beginAtZero: true } } }
    });

    const causasRows = countBy(rows, (row) => row.caus_agrup).sort((a, b) => b.value - a.value).slice(0, 8);
    renderBoletinChartJs('boletin-chart-causas', {
        type: 'bar',
        data: {
            labels: causasRows.map((item) => item.label),
            datasets: [{ label: 'Casos por causa', data: causasRows.map((item) => item.value), backgroundColor: CHARTJS_PALETTE.primary }]
        },
        options: { indexAxis: 'y', scales: { x: { beginAtZero: true } } }
    });
    fillBoletinCausasTable(causasRows, total);

    const complicaciones = [
        { label: 'Hemorragia obstetrica severa', value: rows.filter((row) => boolLike(row.hemorragia_obst_trica_severa)).length },
        { label: 'Eclampsia', value: rows.filter((row) => boolLike(row.eclampsia)).length },
        { label: 'Preclampsia', value: rows.filter((row) => boolLike(row.preclampsi)).length },
        { label: 'Falla cardiaca', value: rows.filter((row) => boolLike(row.falla_card)).length },
        { label: 'Falla renal', value: rows.filter((row) => boolLike(row.falla_rena)).length },
        { label: 'Ruptura uterina', value: rows.filter((row) => boolLike(row.rupt_uteri)).length }
    ];
    renderBoletinChartJs('boletin-chart-complicaciones', {
        type: 'doughnut',
        data: {
            labels: complicaciones.map((item) => item.label),
            datasets: [{ label: 'Complicaciones', data: complicaciones.map((item) => item.value), backgroundColor: [CHARTJS_PALETTE.lightRed, CHARTJS_PALETTE.warning, CHARTJS_PALETTE.primary, CHARTJS_PALETTE.secondary, CHARTJS_PALETTE.violet, CHARTJS_PALETTE.neutral] }]
        }
    });

    fillBoletinMunicipalTable(resumenMunicipal.filas, resumenMunicipal.total);

    const nvWarning = document.getElementById('boletin-nv-warning');
    const hasRawNv = rows.some((row) => toNumber(row.num_vivos) !== null);
    if (nvWarning) {
        if (hasRawNv) {
            nvWarning.classList.add('hidden');
            nvWarning.textContent = '';
        } else {
            nvWarning.classList.remove('hidden');
            nvWarning.textContent = 'Advertencia: no se encontro num_vivos en cleanedData para el filtro activo. Se usan NV de referencia departamental para mantener la tabla oficial completa.';
        }
    }

    if (!rows.length) {
        const mapContainer = document.getElementById('boletin-mapa-risaralda');
        if (mapContainer) {
            mapContainer.innerHTML = '<div class="territorial-empty-cell">Sin casos para el filtro actual.</div>';
        }
    } else {
        cargarGeojsonRisaralda()
            .then(() => renderSvgRisaraldaMap(resumenMunicipal.filas || [], 'boletin-mapa-risaralda'))
            .catch(() => {
                const mapContainer = document.getElementById('boletin-mapa-risaralda');
                if (mapContainer) {
                    mapContainer.innerHTML = '<div class="territorial-empty-cell">No fue posible cargar el croquis municipal.</div>';
                }
            });
    }
}

async function descargarBoletinComoPdf() {
    ensureBoletinTemplate();
    renderBoletinEpidemiologico();

    if (typeof window.html2pdf !== 'function') {
        alert('No fue posible inicializar html2pdf en este navegador.');
        return;
    }

    const btn = document.getElementById('btn-descargar-boletin');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Generando PDF...';
    }

    try {
        await new Promise((resolve) => setTimeout(resolve, 180));
        const node = document.getElementById('boletin-print-root');
        if (!node) return;

        const semana = String(buildBoletinTemporalStats(getRows()).semanaMax).padStart(2, '0');
        const anio = String(buildBoletinTemporalStats(getRows()).anioActual);
        const options = {
            margin: [6, 6, 6, 6],
            filename: `Boletin_MME_Risaralda_SE${semana}_${anio}.pdf`,
            image: { type: 'jpeg', quality: 0.98 },
            html2canvas: { scale: 2, useCORS: true, backgroundColor: '#ffffff' },
            jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
            pagebreak: { mode: ['css', 'legacy'] }
        };

        await window.html2pdf().set(options).from(node).save();
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Descargar como PDF';
        }
    }
}

function aplicarFiltrosYActualizarGraficos() {
    ensureChartTitlesAndSubtitles();
    actualizarKPIsVisibles();
    llenarTablaSociodemografica();
    llenarTablaTerritorial();
    llenarTablaCalidad();
    llenarTablaClinica();
    graficoSemanas();
    graficoComparativo();
    graficoEdad();
    graficoEdadSocio();
    graficoAfiliacion();
    graficoCausas();
    graficoMomento();
    graficoMapa();
    graficoOportunidad();
    graficoDiasNotificacion();
    renderBoletinEpidemiologico();
    resizeTodosGraficos();
}

function actualizarTodoDashboardConDatos(payload) {
    cleanedData = Array.isArray(payload.cleanedData) ? payload.cleanedData : [];
    datosActuales = buildDatosDesdeCleanedData(payload);
    totalSinFiltroActual = Number(payload.total_sin_filtro ?? payload.total_casos ?? 0);
    ultimaVersionDatos = String(payload.data_version || '');

    if (payload.municipios_disponibles) {
        municipiosDisponibles = payload.municipios_disponibles;
        llenarFiltroMunicipios(municipiosDisponibles);
    }

    ensureExtraDashboardStructure();
    ensureBoletinTemplate();
    actualizarBoletinDinamico();
    aplicarFiltrosYActualizarGraficos();
}

function actualizarKPIsVisibles() {
    const total = Number(datosActuales.totalCasos || 0);
    const calidad = datosActuales.calidad || {};

    const setText = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    };

    const setLabel = (valueId, labelText) => {
        const valueEl = document.getElementById(valueId);
        if (!valueEl) return;
        const card = valueEl.closest('.kpi-card');
        const labelEl = card ? card.querySelector('.kpi-label') : null;
        if (labelEl) labelEl.textContent = labelText;
    };

    setText('boletin-casos', total);
    setText('boletin-hospitalizados', Number(calidad.hospitalizacion || 0));

    setLabel('kpi-variacion-anual', '% UCI');
    setLabel('kpi-hospitalizacion', '% HOSPITALIZADAS');
    setText('kpi-total-casos', total);
    setText('kpi-variacion-anual', `${Number(calidad.porcentajeUCI || 0).toFixed(1)}%`);
    setText('kpi-variacion-subtexto', `${Number(calidad.requiereUCI || 0)} casos en UCI`);
    setText('kpi-hospitalizacion', `${Number(calidad.porcentajeHospitalizacion || 0).toFixed(1)}%`);
    setText('kpi-letalidad', `${Number(calidad.letalidad || 0).toFixed(1)}%`);
    setText('kpi-letalidad-subtexto', `${Math.round((Number(calidad.letalidad || 0) * total) / 100)} defunciones`);

    const edad = datosActuales.edadEstadisticas || {};
    setText('kpi-edad-promedio', edad.promedio || '—');
    setText('kpi-edad-min', edad.minima || '—');
    setText('kpi-edad-max', edad.maxima || '—');
    setText('kpi-edad-moda', edad.moda || '—');

    setText('kpi-clin-hospitalizacion', calidad.hospitalizacion || 0);
    setText('kpi-clin-hospitalizacion-pct', `${Number(calidad.porcentajeHospitalizacion || 0).toFixed(1)}% del total`);
    setText('kpi-clin-reconsulta', calidad.requiereUCI || 0);
    setText('kpi-clin-reconsulta-pct', `${Number(calidad.porcentajeUCI || 0).toFixed(1)}% en UCI`);
    setText('kpi-clin-control', Math.max(0, total - Number(calidad.hospitalizacion || 0)));
    setText('kpi-clin-control-pct', `${formatPct(Math.max(0, total - Number(calidad.hospitalizacion || 0)), total)}`);
    setText('kpi-clin-dias', calidad.diasPromedioNotificacion !== null ? Number(calidad.diasPromedioNotificacion).toFixed(1) : 'N/D');

    setLabel('kpi-cal-oportuna', 'REGISTROS COMPLETOS');
    setLabel('kpi-cal-tardia', 'SIN DUPLICADOS');
    setLabel('kpi-cal-completitud', 'PROM. DIAS NOTIF');
    setLabel('kpi-cal-duplicados', 'CASOS VISUALIZADOS');
    setText('kpi-cal-oportuna', `${Number(calidad.completitud || 0).toFixed(1)}%`);
    setText('kpi-cal-oportuna-pct', 'Variables criticas completas');
    setText('kpi-cal-tardia', `${Number(calidad.porcentajeSinDuplicados || 0).toFixed(1)}%`);
    setText('kpi-cal-tardia-pct', 'Registros unicos');
    setText('kpi-cal-completitud', calidad.diasPromedioNotificacion !== null ? `${Number(calidad.diasPromedioNotificacion).toFixed(1)} d` : 'N/D');
    setText('kpi-cal-duplicados', total);

    const municipios = (datosActuales.municipios || []).sort((a, b) => (b.casos || 0) - (a.casos || 0));
    if (municipios.length) {
        const top = municipios[0];
        const top3 = municipios.slice(0, 3).reduce((acc, m) => acc + Number(m.casos || 0), 0);
        setText('kpi-mayor-carga', top.nombre || top.municipio || '—');
        setText('kpi-mayor-carga-subtexto', `${top.casos || 0} casos (${formatPct(top.casos || 0, total)})`);
        setText('kpi-municipios-afectados', municipios.filter(m => Number(m.casos || 0) > 0).length);
        setText('kpi-top3', top3);
        setText('kpi-top3-subtexto', `${formatPct(top3, total)} del total`);
        setText('kpi-prioritarios', municipios.filter(m => Number(m.casos || 0) >= Math.max(1, Math.round(total * 0.1))).length);
    } else {
        setText('kpi-mayor-carga', '—');
        setText('kpi-mayor-carga-subtexto', '0 casos (0.0%)');
        setText('kpi-municipios-afectados', 0);
        setText('kpi-top3', 0);
        setText('kpi-top3-subtexto', '0.0% del total');
        setText('kpi-prioritarios', 0);
    }
}

function graficoSemanas() {
    const semanas = Array.isArray(datosActuales.semanas) ? datosActuales.semanas : [];
    const labels = semanas.map(s => s.semana);
    const casos = semanas.map(s => Number(s.casos || 0));
    const acumulado = [];
    casos.reduce((acc, val, idx) => {
        const next = acc + val;
        acumulado[idx] = next;
        return next;
    }, 0);

    renderChartJs('grafico-semanas', {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { label: 'Casos por semana', data: casos, backgroundColor: CHARTJS_PALETTE.primary, borderRadius: 4 },
                { label: 'Acumulado de casos', data: acumulado, type: 'line', borderColor: CHARTJS_PALETTE.warning, backgroundColor: CHARTJS_PALETTE.warning, tension: 0.25, pointRadius: 3, yAxisID: 'y1' }
            ]
        },
        options: {
            scales: {
                y: { beginAtZero: true, title: { display: true, text: 'Casos semanales' } },
                y1: { beginAtZero: true, position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: 'Acumulado' } }
            }
        }
    }, 380);
}

function graficoComparativo() {
    const rows = getRows();
    const total = rows.length || 1;
    const fields = [
        { key: 'hemorragia_obst_trica_severa', label: 'Hemorragia obstetrica severa' },
        { key: 'eclampsia', label: 'Eclampsia' },
        { key: 'preclampsi', label: 'Preclampsia severa' },
        { key: 'falla_card', label: 'Falla cardiaca' },
        { key: 'falla_rena', label: 'Falla renal' },
        { key: 'rupt_uteri', label: 'Ruptura uterina' },
        { key: 'ingres_uci', label: 'Ingreso a UCI' }
    ];
    const ranked = fields.map((f) => ({
        label: f.label,
        value: rows.filter(r => boolLike(r[f.key])).length
    })).map((r) => ({ ...r, pct: pct(r.value, total) }))
        .sort((a, b) => b.pct - a.pct)
        .slice(0, 6);

    renderChartJs('grafico-comparativo', {
        type: 'bar',
        data: {
            labels: ranked.map(r => r.label),
            datasets: [{ label: 'Porcentaje de casos con complicacion', data: ranked.map(r => Number(r.pct.toFixed(2))), backgroundColor: CHARTJS_PALETTE.lightOrange }]
        },
        options: {
            indexAxis: 'y',
            scales: { x: { beginAtZero: true, title: { display: true, text: '% sobre total' } } },
            plugins: { legend: { display: true } }
        }
    }, 320);
}

function graficoEdad() {
    const data = Array.isArray(datosActuales.gruposEdad) ? datosActuales.gruposEdad : [];
    renderChartJs('grafico-edad', {
        type: 'bar',
        data: {
            labels: data.map(d => d.grupo),
            datasets: [{ label: 'Numero de casos por grupo', data: data.map(d => Number(d.casos || 0)), backgroundColor: CHARTJS_PALETTE.lightBlue }]
        },
        options: { plugins: { legend: { display: true } }, scales: { y: { beginAtZero: true } } }
    }, 320);
}

function graficoEdadSocio() {
    const data = Array.isArray(datosActuales.gruposEdad) ? datosActuales.gruposEdad : [];
    renderChartJs('grafico-edad-socio', {
        type: 'bar',
        data: {
            labels: data.map(d => d.grupo),
            datasets: [{ label: 'Casos por grupo de edad', data: data.map(d => Number(d.casos || 0)), backgroundColor: CHARTJS_PALETTE.secondary }]
        },
        options: {
            indexAxis: 'y',
            plugins: { legend: { display: true } },
            scales: { x: { beginAtZero: true } }
        }
    }, 350);

    const rows = getRows();
    const vulnerables = [
        { label: 'Discapacidad', count: rows.filter(r => boolLike(r.gp_discapa)).length },
        { label: 'Desplazada', count: rows.filter(r => boolLike(r.gp_desplaz)).length },
        { label: 'Migrante', count: rows.filter(r => boolLike(r.gp_migrant)).length },
        { label: 'Indigena', count: rows.filter(r => boolLike(r.gp_indigen)).length },
        { label: 'Gestante', count: rows.filter(r => boolLike(r.gp_gestan)).length },
        { label: 'Grupo especial', count: rows.filter(r => String(r.nom_grupo || '').trim() !== '').length }
    ].sort((a, b) => b.count - a.count);

    renderChartJs('grafico-vulnerables', {
        type: 'bar',
        data: {
            labels: vulnerables.map(v => v.label),
            datasets: [{ label: 'Casos en grupo vulnerable', data: vulnerables.map(v => v.count), backgroundColor: CHARTJS_PALETTE.lightRed }]
        },
        options: { indexAxis: 'y', plugins: { legend: { display: true } }, scales: { x: { beginAtZero: true } } }
    }, 320);

    const estratos = ['1', '2', '3', '4', '5', '6', 'SIN DATO'];
    const areas = [...new Set(rows.map(r => String(r.area || '').trim() || 'SIN DATO'))];
    const datasets = areas.slice(0, 5).map((area, idx) => ({
        label: area,
        data: estratos.map((e) => rows.filter(r => (String(r.estrato || '').trim() || 'SIN DATO') === e && (String(r.area || '').trim() || 'SIN DATO') === area).length),
        backgroundColor: [CHARTJS_PALETTE.primary, CHARTJS_PALETTE.secondary, CHARTJS_PALETTE.warning, CHARTJS_PALETTE.violet, CHARTJS_PALETTE.neutral][idx]
    }));

    renderChartJs('grafico-estrato-area', {
        type: 'bar',
        data: { labels: estratos, datasets },
        options: {
            scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } },
            plugins: { legend: { display: true, title: { display: true, text: 'Color = Area de residencia' } } }
        }
    }, 320);
}

function graficoAfiliacion() {
    const etnia = countBy(getRows(), r => r.per_etn).sort((a, b) => b.value - a.value).slice(0, 8);
    renderChartJs('grafico-afiliacion', {
        type: 'doughnut',
        data: {
            labels: etnia.map(e => e.label),
            datasets: [{ label: 'Participacion por pertenencia etnica', data: etnia.map(e => e.value), backgroundColor: [CHARTJS_PALETTE.primary, CHARTJS_PALETTE.secondary, CHARTJS_PALETTE.warning, CHARTJS_PALETTE.lightBlue, CHARTJS_PALETTE.lightGreen, CHARTJS_PALETTE.lightOrange, CHARTJS_PALETTE.lightRed, CHARTJS_PALETTE.neutral] }]
        }
    }, 350);
}

function graficoCausas() {
    const causas = countBy(getRows(), r => r.caus_agrup).sort((a, b) => b.value - a.value).slice(0, 8);
    renderChartJs('grafico-causas', {
        type: 'bar',
        data: { labels: causas.map(c => c.label), datasets: [{ label: 'Numero de casos por causa', data: causas.map(c => c.value), backgroundColor: CHARTJS_PALETTE.primary }] },
        options: { plugins: { legend: { display: true } }, scales: { x: { ticks: { maxRotation: 35, minRotation: 35 } }, y: { beginAtZero: true } } }
    }, 350);

    const rows = getRows();
    const comp = [
        { label: 'Hemorragia', value: rows.filter(r => boolLike(r.hemorragia_obst_trica_severa)).length },
        { label: 'Eclampsia', value: rows.filter(r => boolLike(r.eclampsia)).length },
        { label: 'Preclampsia', value: rows.filter(r => boolLike(r.preclampsi)).length },
        { label: 'Falla cardiaca', value: rows.filter(r => boolLike(r.falla_card)).length },
        { label: 'Falla renal', value: rows.filter(r => boolLike(r.falla_rena)).length },
        { label: 'Ruptura uterina', value: rows.filter(r => boolLike(r.rupt_uteri)).length }
    ];
    renderChartJs('grafico-complicaciones-clinicas', {
        type: 'bar',
        data: { labels: comp.map(c => c.label), datasets: [{ label: 'Casos con complicacion grave', data: comp.map(c => c.value), backgroundColor: CHARTJS_PALETTE.lightRed }] },
        options: { indexAxis: 'y', plugins: { legend: { display: true } }, scales: { x: { beginAtZero: true } } }
    }, 320);
}

function graficoMomento() {
    const dias = [
        { label: '0-2 dias', min: 0, max: 2 },
        { label: '3-5 dias', min: 3, max: 5 },
        { label: '6-10 dias', min: 6, max: 10 },
        { label: '>10 dias', min: 11, max: 365 }
    ];
    const rows = getRows();
    const diasHosp = dias.map(b => rows.filter((r) => {
        const v = toNumber(r.dias_hospi);
        return v !== null && v >= b.min && v <= b.max;
    }).length);

    renderChartJs('grafico-momento', {
        type: 'bar',
        data: { labels: dias.map(d => d.label), datasets: [{ label: 'Numero de casos por dias de hospitalizacion', data: diasHosp, backgroundColor: CHARTJS_PALETTE.warning }] },
        options: { plugins: { legend: { display: true } }, scales: { y: { beginAtZero: true } } }
    }, 350);

    const semBins = [
        { label: '1-12', min: 1, max: 12 },
        { label: '13-20', min: 13, max: 20 },
        { label: '21-28', min: 21, max: 28 },
        { label: '29-36', min: 29, max: 36 },
        { label: '>=37', min: 37, max: 50 }
    ];
    const semData = semBins.map(b => rows.filter((r) => {
        const v = toNumber(r.sem_ges);
        return v !== null && v >= b.min && v <= b.max;
    }).length);

    renderChartJs('grafico-semanas-gestacionales', {
        type: 'line',
        data: { labels: semBins.map(s => s.label), datasets: [{ label: 'Casos por rango de semanas gestacionales', data: semData, borderColor: CHARTJS_PALETTE.secondary, backgroundColor: CHARTJS_PALETTE.secondary, tension: 0.25, pointRadius: 3 }] },
        options: { scales: { y: { beginAtZero: true } } }
    }, 320);
}

function graficoMapa() {
    const rows = getRows();
    if (!rows.length) {
        maybeShowNoData('grafico-mapa', 'No hay casos para representar en el mapa con el filtro actual.');
    } else {
        cargarGeojsonRisaralda()
            .then(() => renderSvgRisaraldaMap(resumenTerritorialActual.filas || []))
            .catch((error) => {
                maybeShowNoData('grafico-mapa', `No se pudo cargar el croquis municipal: ${error.message}`);
            });
    }

    const area = countBy(getRows(), r => r.area).sort((a, b) => b.value - a.value);
    renderChartJs('grafico-area-territorial', {
        type: 'pie',
        data: {
            labels: area.map(a => a.label),
            datasets: [{ label: 'Participacion por area', data: area.map(a => a.value), backgroundColor: [CHARTJS_PALETTE.primary, CHARTJS_PALETTE.secondary, CHARTJS_PALETTE.warning, CHARTJS_PALETTE.neutral] }]
        }
    }, 300);

    const depto = countBy(getRows(), r => r.ndep_resi || r.nmun_resi).sort((a, b) => b.value - a.value).slice(0, 8);
    renderChartJs('grafico-departamento-territorial', {
        type: 'bar',
        data: { labels: depto.map(d => d.label), datasets: [{ label: 'Numero de casos por departamento', data: depto.map(d => d.value), backgroundColor: CHARTJS_PALETTE.lightGreen }] },
        options: { plugins: { legend: { display: true } }, scales: { y: { beginAtZero: true } } }
    }, 300);
}

function graficoOportunidad() {
    const rows = getRows();
    const total = rows.length;
    const cols = ['edad', 'semana', 'a_o', 'pac_hos', 'ingres_uci', 'nmun_resi', 'caus_agrup', 'sem_ges'];
    const labels = ['Edad', 'Semana', 'Ano', 'Hospitalizacion', 'UCI', 'Municipio', 'Causa', 'Semanas gestacionales'];
    const values = cols.map((c) => pct(rows.filter(r => String(r[c] ?? '').trim() !== '').length, total));

    renderChartJs('grafico-oportunidad', {
        type: 'bar',
        data: { labels, datasets: [{ label: 'Porcentaje de completitud por variable', data: values.map(v => Number(v.toFixed(2))), backgroundColor: CHARTJS_PALETTE.secondary }] },
        options: { plugins: { legend: { display: true } }, scales: { y: { beginAtZero: true, max: 100 } } }
    }, 350);
}

function graficoDiasNotificacion() {
    const rows = getRows();
    const semMap = new Map();
    rows.forEach((r) => {
        const semanaRaw = toNumber(r.semana);
        if (semanaRaw === null || semanaRaw <= 0) return;
        const semana = Math.trunc(semanaRaw);
        const key = `S${String(semana).padStart(2, '0')}`;
        const cols = ['edad', 'semana', 'a_o', 'pac_hos', 'nmun_resi', 'caus_agrup'];
        const filled = cols.filter(c => String(r[c] ?? '').trim() !== '').length;
        const pctRow = (filled * 100) / cols.length;
        if (!semMap.has(key)) semMap.set(key, []);
        semMap.get(key).push(pctRow);
    });

    const sorted = [...semMap.entries()].sort((a, b) => a[0].localeCompare(b[0]));
    const labels = sorted.map(s => s[0]);
    const series = sorted.map(([, vals]) => (vals.reduce((acc, n) => acc + n, 0) / vals.length));

    renderChartJs('grafico-dias-notificacion', {
        type: 'line',
        data: { labels, datasets: [{ label: 'Completitud semanal (%)', data: series.map(v => Number(v.toFixed(2))), borderColor: CHARTJS_PALETTE.warning, backgroundColor: CHARTJS_PALETTE.warning, tension: 0.25, pointRadius: 3 }] },
        options: { scales: { y: { beginAtZero: true, max: 100 } } }
    }, 350);
}

function llenarTablaSociodemografica() {
    const tbody = document.getElementById('tabla-socio-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    (datosActuales.gruposEdad || []).forEach((item) => {
        tbody.innerHTML += `<tr><td>Grupo de edad</td><td>${item.grupo}</td><td class="text-center">${item.casos}</td><td class="text-center">${item.porcentaje}%</td></tr>`;
    });

    const etnia = countBy(getRows(), r => r.per_etn).sort((a, b) => b.value - a.value).slice(0, 8);
    etnia.forEach((item) => {
        tbody.innerHTML += `<tr><td>Pertenencia etnica</td><td>${item.label}</td><td class="text-center">${item.value}</td><td class="text-center">${formatPct(item.value, getRows().length)}</td></tr>`;
    });
}

function llenarTablaTerritorial() {
    const tbody = document.getElementById('tabla-territorial-body');
    const subtitle = document.getElementById('subtitle-tabla-territorial');
    const fuente = document.getElementById('tabla-territorial-fuente');
    if (!tbody) return;
    tbody.innerHTML = '';

    const rows = getRows();
    if (subtitle) {
        subtitle.textContent = buildTerritorialSubtitle(rows);
    }
    if (fuente) {
        fuente.textContent = buildTerritorialSource(rows);
    }
    resumenTerritorialActual = buildTerritorialSummary(rows);
    const filas = resumenTerritorialActual.filas;
    const total = resumenTerritorialActual.total;

    if (!filas.length) {
        tbody.innerHTML = '<tr><td colspan="4" class="territorial-empty-cell">Sin datos territoriales para el filtro actual.</td></tr>';
        return;
    }

    filas.forEach((row) => {
        const ratioClass = riskClassByRatio(row.razon);
        const nvTxt = row.nacidosVivos === null ? '-' : formatNumber(row.nacidosVivos, 0);
        const razonTxt = row.razon === null ? '-' : formatNumber(row.razon, 1);
        tbody.innerHTML += `
            <tr>
                <td class="territorial-cell-name"><strong>${row.municipio}</strong></td>
                <td class="territorial-cell-cases">${formatNumber(row.casos, 0)}</td>
                <td class="territorial-cell-nv">${nvTxt}</td>
                <td class="territorial-cell-ratio ${ratioClass}">${razonTxt}</td>
            </tr>
        `;
    });

    if (total) {
        const totalClass = riskClassByRatio(total.razon);
        const totalNvTxt = total.nacidosVivos === null ? '-' : formatNumber(total.nacidosVivos, 0);
        const totalRazonTxt = total.razon === null ? '-' : formatNumber(total.razon, 1);
        tbody.innerHTML += `
            <tr class="territorial-total-row">
                <td class="territorial-cell-name"><strong>Risaralda</strong></td>
                <td class="territorial-cell-cases"><strong>${formatNumber(total.casos, 0)}</strong></td>
                <td class="territorial-cell-nv"><strong>${totalNvTxt}</strong></td>
                <td class="territorial-cell-ratio ${totalClass}"><strong>${totalRazonTxt}</strong></td>
            </tr>
        `;
    }
}

function llenarTablaCalidad() {
    const tbody = document.getElementById('tabla-calidad-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    const rows = getRows();
    const weeks = new Map();
    rows.forEach((r) => {
        const weekRaw = toNumber(r.semana);
        if (weekRaw === null || weekRaw <= 0) return;
        const week = Math.trunc(weekRaw);
        const key = `S${String(week).padStart(2, '0')}`;
        if (!weeks.has(key)) weeks.set(key, { total: 0, completos: 0 });
        const entry = weeks.get(key);
        entry.total += 1;
        const ok = ['edad', 'semana', 'a_o', 'pac_hos', 'nmun_resi', 'caus_agrup'].every(c => String(r[c] ?? '').trim() !== '');
        if (ok) entry.completos += 1;
    });

    [...weeks.entries()].sort((a, b) => a[0].localeCompare(b[0])).forEach(([semana, entry]) => {
        const porcentaje = pct(entry.completos, entry.total);
        const estado = porcentaje >= 90 ? 'ALTO' : (porcentaje >= 75 ? 'MEDIO' : 'BAJO');
        const clase = porcentaje >= 90 ? 'badge-verde' : (porcentaje >= 75 ? 'badge-naranja' : 'badge-rojo');
        tbody.innerHTML += `
            <tr>
                <td><strong>${semana}</strong></td>
                <td class="text-center">${entry.completos}</td>
                <td class="text-center">${entry.total - entry.completos}</td>
                <td class="text-center"><strong>${porcentaje.toFixed(1)}%</strong></td>
                <td class="text-center"><span class="${clase}">${estado}</span></td>
            </tr>
        `;
    });
}

function llenarTablaClinica() {
    const tbody = document.getElementById('tabla-clinica-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    const rows = getRows();
    const total = rows.length || 1;
    const items = [
        { label: 'Hospitalizacion', yes: rows.filter(r => boolLike(r.pac_hos)).length },
        { label: 'Ingreso a UCI', yes: rows.filter(r => boolLike(r.ingres_uci)).length },
        { label: 'Hemorragia obstetrica severa', yes: rows.filter(r => boolLike(r.hemorragia_obst_trica_severa)).length },
        { label: 'Eclampsia', yes: rows.filter(r => boolLike(r.eclampsia)).length }
    ];

    items.forEach((item) => {
        const no = Math.max(0, rows.length - item.yes);
        tbody.innerHTML += `
            <tr>
                <td><strong>${item.label}</strong></td>
                <td class="text-center">${item.yes}</td>
                <td class="text-center">${no}</td>
                <td class="text-center"><strong>${formatPct(item.yes, total)}</strong></td>
            </tr>
        `;
    });
}

function resizeTodosGraficos() {
    Object.values(chartsEvento549).forEach((chart) => {
        if (chart && typeof chart.resize === 'function') {
            chart.resize();
        }
    });
    Object.values(boletinChartsEvento549).forEach((chart) => {
        if (chart && typeof chart.resize === 'function') {
            chart.resize();
        }
    });
}

async function actualizarComparacionInteranualSemanal() {
    return;
}

// ====================================
// INICIALIZACIÓN
// ====================================

document.addEventListener('DOMContentLoaded', async function() {
    console.log('🏥 Inicializando Dashboard SIVIGILA...');

    ensureBoletinTemplate();
    await asegurarChartJsListo();
    ensureExtraDashboardStructure();

    // Llenar selector de eventos
    llenarSelectorEventos();
    
    // Inicializar con evento 549
    eventoActual = 549;
    try {
        const payload = await obtenerDatosDepurados549ConRetry('', null, 1);
        actualizarTodoDashboardConDatos(payload);
        console.log(`📦 Inicializado con archivo depurado: ${payload.archivo_depurado} (${payload.total_casos} casos)`);
        actualizarBarraEstado(payload.archivo_depurado, payload.archivo_modificado, true);
    } catch (error) {
        console.warn('⚠️ API depurada no disponible en inicialización.', error);
        datosActuales = crearDatosVaciosDesdeDepurado();
        totalSinFiltroActual = 0;
        actualizarBarraEstado(null, null, false, mensajeErrorFuenteDatos(error));
        ultimaVersionDatos = null;
    }
    
    // Render inicial completo
    actualizarBoletinDinamico();
    llenarTablaSociodemografica();
    llenarTablaTerritorial();
    llenarTablaCalidad();
    llenarTablaClinica();
    graficoSemanas();
    graficoComparativo();
    graficoEdad();
    graficoEdadSocio();
    graficoAfiliacion();
    graficoCausas();
    graficoMomento();
    graficoMapa();
    graficoOportunidad();
    graficoDiasNotificacion();
    renderBoletinEpidemiologico();
    actualizarComparacionInteranualSemanal();
    setTimeout(resizeTodosGraficos, 300);

    console.log('✅ Dashboard inicializado correctamente');

    if (timerEdadDatos) {
        clearInterval(timerEdadDatos);
    }
    timerEdadDatos = setInterval(actualizarEdadDatosVisual, 1000);
    actualizarEdadDatosVisual();

    iniciarSincronizacionAutomatica();
    await forzarSincronizacionInmediata();
});

document.addEventListener('visibilitychange', function () {
    if (!document.hidden && eventoActual === 549) {
        forzarSincronizacionInmediata();
    }
});

window.addEventListener('online', function () {
    if (eventoActual === 549) {
        forzarSincronizacionInmediata();
    }
});

window.addEventListener('beforeunload', function () {
    detenerSincronizacionAutomatica();
    if (timerEdadDatos) {
        clearInterval(timerEdadDatos);
        timerEdadDatos = null;
    }
});
