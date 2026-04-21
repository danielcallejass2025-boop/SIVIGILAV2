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
let ultimoTimestampDatosMs = null;
const GRAFICOS_PIE_IDS = ['grafico-afiliacion', 'grafico-momento', 'grafico-oportunidad'];

// Respaldo del HTML original para restaurar al volver al evento 549
let _htmlOriginalBoletin = null;
let _htmlOriginalDashboardParent = null;

// Nota: el dashboard consume exclusivamente datos reales del archivo depurado vía API.

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

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }

    return response.json();
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
            ? `Conectado — Municipio: ${municipioFiltroActual}`
            : 'Conectado — Total departamental');
        text.textContent = mensaje;
        if (archivo !== null && archivo !== undefined) {
            arch.textContent = archivo || '';
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
        if (fallosRefreshConsecutivos >= 2) {
            actualizarBarraEstado(
                null,
                null,
                false,
                'Sincronización temporalmente interrumpida (mostrando última lectura)'
            );
        }
    }
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
                ? `Conectado — Municipio: ${municipioFiltroActual} (última lectura)`
                : 'Conectado — Total departamental (última lectura)';
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
        try {
            const payload = await obtenerDatosDepurados549ConRetry(municipioFiltroActual, null, 1);
            actualizarTodoDashboardConDatos(payload);
            console.log(`📦 Fuente depurada: ${payload.archivo_depurado} | casos: ${payload.total_casos}`);
            actualizarBarraEstado(payload.archivo_depurado, payload.archivo_modificado, true);
        } catch (error) {
            console.warn('⚠️ No fue posible cargar API depurada.', error);
            datosActuales = crearDatosVaciosDesdeDepurado();
            totalSinFiltroActual = 0;
            actualizarBarraEstado(null, null, false);
        }

        mostrarDashboardConDatos();
    } else {
        // Para otros eventos, mostrar mensaje sin datos
        console.log(`⚠️ Evento ${eventoActual} sin datos disponibles`);
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
                Los datos se actualizarán automáticamente cada semana. Selecciona el evento 
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
        Plotly.newPlot('grafico-semanas', [traceBars, traceLine], layoutAjustado, config);
    }
    if (document.getElementById('boletin-grafico-semanas')) {
        const layoutBoletin = aplicarEstiloBaseLayout(Object.assign({}, layout, { height: 300 }), 'boletin-grafico-semanas');
        Plotly.newPlot('boletin-grafico-semanas', [traceBars, traceLine], layoutBoletin, config);
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
        Plotly.newPlot('grafico-comparativo', data, layoutAjustado, obtenerConfigPlotly());
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
        Plotly.newPlot('grafico-edad', data, layoutAjustado, obtenerConfigPlotly());
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
        Plotly.newPlot('grafico-afiliacion', data, layoutAjustado, obtenerConfigPlotly());
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
        Plotly.newPlot('grafico-causas', data, layoutAjustado, obtenerConfigPlotly());
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
        Plotly.newPlot('grafico-momento', data, layoutAjustado, obtenerConfigPlotly());
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
        Plotly.newPlot('grafico-oportunidad', data, layoutAjustado, obtenerConfigPlotly());
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
        Plotly.newPlot('grafico-dias-notificacion', data, layoutAjustado, obtenerConfigPlotly());
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
        Plotly.newPlot('grafico-edad-socio', data, layoutAjustado, obtenerConfigPlotly());
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
 * Los datos se cargan automáticamente cada semana desde el servidor
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

// ====================================
// INICIALIZACIÓN
// ====================================

document.addEventListener('DOMContentLoaded', async function() {
    console.log('🏥 Inicializando Dashboard SIVIGILA...');

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
        actualizarBarraEstado(null, null, false);
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
    actualizarComparacionInteranualSemanal();
    setTimeout(resizeTodosGraficos, 300);

    console.log('✅ Dashboard inicializado correctamente');

    if (timerEdadDatos) {
        clearInterval(timerEdadDatos);
    }
    timerEdadDatos = setInterval(actualizarEdadDatosVisual, 1000);
    actualizarEdadDatosVisual();
});
