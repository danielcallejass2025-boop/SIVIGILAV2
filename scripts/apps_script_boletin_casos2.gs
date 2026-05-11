/**
 * EPIPROC - Lectura de base historica semanal para boletin epidemiologico.
 *
 * Hoja objetivo por defecto: CASOS 2
 * Spreadsheet ID por defecto: 1t41_VO9SyIy6N2at-Q0kh7DXGpg-iCMZPDpmLLSN-PM
 * Evento por defecto: 549
 *
 * Este Web App es de SOLO LECTURA y esta pensado para que VS Code / Copilot
 * consulte la base historica y pueda generar el boletin semanal con comparacion
 * entre la semana actual y la misma semana del anio anterior.
 *
 * Script Properties soportadas:
 * - EPIPROC_BULLETIN_SPREADSHEET_ID
 * - EPIPROC_BULLETIN_SHEET_NAME
 * - EPIPROC_BULLETIN_API_KEY
 * - EPIPROC_BULLETIN_EVENT_CODE
 * - EPIPROC_BULLETIN_TIMEZONE
 * - EPIPROC_TREAT_TRAILING_ZEROS_AS_MISSING   (true/false)
 *
 * Acciones soportadas:
 * - health / ping
 * - leer_metadata_casos2
 * - leer_base_casos2
 * - leer_semana                (anio, semana)
 * - comparar_semana            (anio, semana)
 * - comparar_ultima_semana     (anio opcional)
 * - boletin_ultima_semana      (alias de comparar_ultima_semana)
 * - validar_canal
 */

var EPIPROC_BULLETIN_DEFAULT_SPREADSHEET_ID = "1t41_VO9SyIy6N2at-Q0kh7DXGpg-iCMZPDpmLLSN-PM";
var EPIPROC_BULLETIN_DEFAULT_SHEET_NAME = "CASOS 2";
var EPIPROC_BULLETIN_DEFAULT_EVENT_CODE = 549;
var EPIPROC_BULLETIN_DEFAULT_TIMEZONE = "America/Bogota";
var EPIPROC_BULLETIN_DEFAULT_API_KEY = "123456";

function doGet(e) {
  return handleBulletinRequest_(e, false);
}

function doPost(e) {
  return handleBulletinRequest_(e, true);
}

function handleBulletinRequest_(e, isPost) {
  try {
    var params = isPost ? parseJsonBody_(e) : ((e && e.parameter) ? e.parameter : {});
    validarApiKey_(params);

    var accion = String(params.accion || params.action || "health").trim().toLowerCase();

    if (accion === "health" || accion === "ping") {
      return jsonOutput_(buildHealthPayload_());
    }

    if (accion === "leer_metadata_casos2") {
      return jsonOutput_(buildMetadataPayload_(params));
    }

    if (accion === "leer_base_casos2") {
      return jsonOutput_(buildBasePayload_(params));
    }

    if (accion === "leer_semana") {
      return jsonOutput_(buildWeekPayload_(params));
    }

    if (accion === "comparar_semana") {
      return jsonOutput_(buildComparisonPayload_(params));
    }

    if (accion === "comparar_ultima_semana" || accion === "boletin_ultima_semana") {
      return jsonOutput_(buildLatestComparisonPayload_(params));
    }

    if (accion === "validar_canal") {
      return jsonOutput_(buildValidationPayload_(params));
    }

    return jsonOutput_({
      success: false,
      error: "Accion no soportada.",
      acciones_soportadas: [
        "health",
        "leer_metadata_casos2",
        "leer_base_casos2",
        "leer_semana",
        "comparar_semana",
        "comparar_ultima_semana",
        "boletin_ultima_semana",
        "validar_canal"
      ]
    });
  } catch (err) {
    return jsonOutput_({ success: false, error: String(err) });
  }
}

function buildHealthPayload_() {
  var config = getBulletinConfig_();
  var sheet = getBulletinSheet_();

  return {
    success: true,
    service: "EPIPROC_BULLETIN_CASOS2_API",
    status: "ok",
    event_code: config.eventCode,
    spreadsheet_id: config.spreadsheetId,
    sheet_name: sheet.getName(),
    timezone: config.timezone,
    generated_at: nowIso_(config.timezone)
  };
}

function buildMetadataPayload_(params) {
  var dataset = loadCasos2Dataset_();
  var targetYear = resolveTargetYear_(dataset, params);
  var progress = detectYearProgress_(dataset.rows, targetYear, getTreatTrailingZerosAsMissing_(params));
  var diagnostics = buildDatasetDiagnostics_(dataset, targetYear, getTreatTrailingZerosAsMissing_(params));

  return {
    success: true,
    event_code: dataset.config.eventCode,
    spreadsheet_id: dataset.config.spreadsheetId,
    sheet_name: dataset.config.sheetName,
    generated_at: nowIso_(dataset.config.timezone),
    year_columns: dataset.yearColumns,
    target_year: targetYear,
    latest_year_in_sheet: dataset.latestYear,
    total_weeks: dataset.rows.length,
    last_week_with_observed_data: progress.lastWeekWithObservedData,
    trailing_placeholder_weeks: progress.trailingPlaceholderWeeks,
    diagnostics: diagnostics
  };
}

function buildBasePayload_(params) {
  var dataset = loadCasos2Dataset_();
  var targetYear = resolveTargetYear_(dataset, params);
  var treatTrailingZerosAsMissing = getTreatTrailingZerosAsMissing_(params);
  var progress = detectYearProgress_(dataset.rows, targetYear, treatTrailingZerosAsMissing);
  var includeDiagnostics = getBooleanParam_(params, "include_diagnostics", true);
  var includeRecalculated = getBooleanParam_(params, "include_recalculated_stats", true);
  var onlyUntilLastObserved = getBooleanParam_(params, "only_until_last_observed", false);
  var rows = [];

  for (var i = 0; i < dataset.rows.length; i++) {
    var row = dataset.rows[i];
    if (onlyUntilLastObserved && progress.lastWeekWithObservedData !== null && row.semana > progress.lastWeekWithObservedData) {
      continue;
    }

    var rowPayload = buildWeekRowPayload_(dataset, row, targetYear, treatTrailingZerosAsMissing, includeRecalculated);
    rows.push(rowPayload);
  }

  var response = {
    success: true,
    source: "CASOS 2",
    event_code: dataset.config.eventCode,
    spreadsheet_id: dataset.config.spreadsheetId,
    sheet_name: dataset.config.sheetName,
    target_year: targetYear,
    latest_year_in_sheet: dataset.latestYear,
    last_week_with_observed_data: progress.lastWeekWithObservedData,
    treat_trailing_zeros_as_missing: treatTrailingZerosAsMissing,
    rows: rows
  };

  if (includeDiagnostics) {
    response.diagnostics = buildDatasetDiagnostics_(dataset, targetYear, treatTrailingZerosAsMissing);
  }

  return response;
}

function buildWeekPayload_(params) {
  var dataset = loadCasos2Dataset_();
  var targetYear = resolveTargetYear_(dataset, params);
  var week = requireWeekParam_(params);
  var row = findWeekRow_(dataset.rows, week);
  var treatTrailingZerosAsMissing = getTreatTrailingZerosAsMissing_(params);

  if (!row) {
    throw new Error("La semana solicitada no existe en la hoja.");
  }

  return {
    success: true,
    source: "CASOS 2",
    event_code: dataset.config.eventCode,
    spreadsheet_id: dataset.config.spreadsheetId,
    sheet_name: dataset.config.sheetName,
    generated_at: nowIso_(dataset.config.timezone),
    week: week,
    target_year: targetYear,
    row: buildWeekRowPayload_(dataset, row, targetYear, treatTrailingZerosAsMissing, true)
  };
}

function buildComparisonPayload_(params) {
  var dataset = loadCasos2Dataset_();
  var targetYear = resolveTargetYear_(dataset, params);
  var week = requireWeekParam_(params);
  var row = findWeekRow_(dataset.rows, week);
  var previousYear = resolvePreviousYear_(dataset, targetYear);
  var treatTrailingZerosAsMissing = getTreatTrailingZerosAsMissing_(params);

  if (!row) {
    throw new Error("La semana solicitada no existe en la hoja.");
  }

  return buildComparisonFromRow_(dataset, row, targetYear, previousYear, treatTrailingZerosAsMissing, "semana_solicitada");
}

function buildLatestComparisonPayload_(params) {
  var dataset = loadCasos2Dataset_();
  var targetYear = resolveTargetYear_(dataset, params);
  var previousYear = resolvePreviousYear_(dataset, targetYear);
  var treatTrailingZerosAsMissing = getTreatTrailingZerosAsMissing_(params);
  var progress = detectYearProgress_(dataset.rows, targetYear, treatTrailingZerosAsMissing);

  if (progress.lastWeekWithObservedData === null) {
    throw new Error("No se detecto una semana con datos observados para el anio solicitado.");
  }

  var row = findWeekRow_(dataset.rows, progress.lastWeekWithObservedData);
  return buildComparisonFromRow_(dataset, row, targetYear, previousYear, treatTrailingZerosAsMissing, "ultima_semana_disponible");
}

function buildComparisonFromRow_(dataset, row, targetYear, previousYear, treatTrailingZerosAsMissing, basis) {
  var progress = detectYearProgress_(dataset.rows, targetYear, treatTrailingZerosAsMissing);
  var currentValue = getComparableYearValue_(row, targetYear, progress, treatTrailingZerosAsMissing);
  var currentRawValue = getYearValue_(row, targetYear);
  var previousValue = getYearValue_(row, previousYear);
  var historicalStats = computeHistoricalStats_(row, dataset.yearColumns, targetYear);
  var sheetClassification = classifyAgainstLimits_(currentValue, row.sheetStats.upper, row.sheetStats.lower);
  var recalculatedClassification = classifyAgainstLimits_(currentValue, historicalStats.upper, historicalStats.lower);

  var difference = null;
  var percentChange = null;
  var trend = "sin_dato";

  if (currentValue !== null && previousValue !== null) {
    difference = roundNumber_(currentValue - previousValue, 2);
    if (difference > 0) {
      trend = "aumento";
    } else if (difference < 0) {
      trend = "disminucion";
    } else {
      trend = "igual";
    }

    if (previousValue !== 0) {
      percentChange = roundNumber_(((currentValue - previousValue) / previousValue) * 100, 2);
    }
  }

  return {
    success: true,
    source: "CASOS 2",
    comparison_basis: basis,
    event_code: dataset.config.eventCode,
    spreadsheet_id: dataset.config.spreadsheetId,
    sheet_name: dataset.config.sheetName,
    generated_at: nowIso_(dataset.config.timezone),
    week: row.semana,
    target_year: targetYear,
    previous_year: previousYear,
    current_year_cases: currentValue,
    current_year_cases_raw: currentRawValue,
    previous_year_cases: previousValue,
    absolute_change: difference,
    percent_change: percentChange,
    trend: trend,
    last_week_with_observed_data: progress.lastWeekWithObservedData,
    is_current_value_placeholder: currentValue === null && currentRawValue === 0,
    historical_reference: {
      years_used: historicalStats.years,
      values_used: historicalStats.values,
      average: historicalStats.average,
      stddev: historicalStats.stddev,
      upper_limit: historicalStats.upper,
      lower_limit: historicalStats.lower
    },
    sheet_reference: {
      average: row.sheetStats.average,
      upper_limit: row.sheetStats.upper,
      lower_limit: row.sheetStats.lower,
      stddev: row.sheetStats.stddev
    },
    expected_status_sheet: sheetClassification,
    expected_status_recalculated: recalculatedClassification
  };
}

function buildValidationPayload_(params) {
  var dataset = loadCasos2Dataset_();
  var targetYear = resolveTargetYear_(dataset, params);
  var tolerance = getNumericParam_(params, "tolerance", 0.05);
  var mismatches = [];
  var rowsChecked = 0;

  for (var i = 0; i < dataset.rows.length; i++) {
    var row = dataset.rows[i];
    var historicalStats = computeHistoricalStats_(row, dataset.yearColumns, targetYear);

    if (historicalStats.values.length === 0) {
      continue;
    }

    rowsChecked++;
    var avgDiff = absoluteDiff_(row.sheetStats.average, historicalStats.average);
    var upperDiff = absoluteDiff_(row.sheetStats.upper, historicalStats.upper);
    var lowerDiff = absoluteDiff_(row.sheetStats.lower, historicalStats.lower);

    if (avgDiff > tolerance || upperDiff > tolerance || lowerDiff > tolerance) {
      mismatches.push({
        semana: row.semana,
        sheet_average: row.sheetStats.average,
        calc_average: historicalStats.average,
        sheet_upper_limit: row.sheetStats.upper,
        calc_upper_limit: historicalStats.upper,
        sheet_lower_limit: row.sheetStats.lower,
        calc_lower_limit: historicalStats.lower,
        average_diff: avgDiff,
        upper_diff: upperDiff,
        lower_diff: lowerDiff
      });
    }
  }

  return {
    success: true,
    event_code: dataset.config.eventCode,
    spreadsheet_id: dataset.config.spreadsheetId,
    sheet_name: dataset.config.sheetName,
    target_year: targetYear,
    rows_checked: rowsChecked,
    mismatch_count: mismatches.length,
    tolerance: tolerance,
    constant_formula_warning: countUniqueNumericValues_(extractSheetAverages_(dataset.rows)) <= 2,
    mismatches: mismatches
  };
}

function buildWeekRowPayload_(dataset, row, targetYear, treatTrailingZerosAsMissing, includeRecalculated) {
  var progress = detectYearProgress_(dataset.rows, targetYear, treatTrailingZerosAsMissing);
  var comparableCurrentValue = getComparableYearValue_(row, targetYear, progress, treatTrailingZerosAsMissing);
  var payload = {
    semana: row.semana,
    source_row_number: row.sourceRowNumber,
    cases_by_year: copyObject_(row.casesByYear),
    current_year_value_adjusted: comparableCurrentValue,
    current_year_value_raw: getYearValue_(row, targetYear),
    is_current_year_placeholder: comparableCurrentValue === null && getYearValue_(row, targetYear) === 0,
    stats_sheet: copyObject_(row.sheetStats)
  };

  if (includeRecalculated) {
    payload.stats_recalculated = computeHistoricalStats_(row, dataset.yearColumns, targetYear);
  }

  return payload;
}

function loadCasos2Dataset_() {
  var config = getBulletinConfig_();
  var sheet = getBulletinSheet_();
  var lastRow = sheet.getLastRow();
  var lastColumn = sheet.getLastColumn();

  if (lastRow < 2 || lastColumn < 2) {
    throw new Error("La hoja CASOS 2 no tiene datos suficientes para analisis.");
  }

  var values = sheet.getRange(1, 1, lastRow, lastColumn).getValues();
  var headers = values[0];
  var headerInfo = analyzeHeaders_(headers);
  var rows = [];

  for (var r = 1; r < values.length; r++) {
    var rawWeek = values[r][headerInfo.weekIndex];
    var week = toIntOrNull_(rawWeek);
    if (week === null) {
      continue;
    }

    var row = {
      semana: week,
      sourceRowNumber: r + 1,
      casesByYear: {},
      sheetStats: {
        average: null,
        upper: null,
        lower: null,
        stddev: null
      }
    };

    for (var y = 0; y < headerInfo.yearColumns.length; y++) {
      var yearColumn = headerInfo.yearColumns[y];
      row.casesByYear[yearColumn.year] = toNumberOrNull_(values[r][yearColumn.index]);
    }

    if (headerInfo.averageIndex !== null) {
      row.sheetStats.average = toNumberOrNull_(values[r][headerInfo.averageIndex]);
    }
    if (headerInfo.upperIndex !== null) {
      row.sheetStats.upper = toNumberOrNull_(values[r][headerInfo.upperIndex]);
    }
    if (headerInfo.lowerIndex !== null) {
      row.sheetStats.lower = toNumberOrNull_(values[r][headerInfo.lowerIndex]);
    }
    if (headerInfo.stddevIndex !== null) {
      row.sheetStats.stddev = toNumberOrNull_(values[r][headerInfo.stddevIndex]);
    }

    rows.push(row);
  }

  rows.sort(function(a, b) {
    return a.semana - b.semana;
  });

  return {
    config: config,
    headers: headers,
    yearColumns: headerInfo.yearColumns.map(function(item) { return item.year; }),
    latestYear: headerInfo.yearColumns.length ? headerInfo.yearColumns[headerInfo.yearColumns.length - 1].year : null,
    rows: rows
  };
}

function analyzeHeaders_(headers) {
  var weekIndex = null;
  var averageIndex = null;
  var upperIndex = null;
  var lowerIndex = null;
  var stddevIndex = null;
  var yearColumns = [];

  for (var i = 0; i < headers.length; i++) {
    var rawHeader = String(headers[i] || "").trim();
    var normalized = normalizeHeader_(rawHeader);

    if (normalized === "semana") {
      weekIndex = i;
      continue;
    }

    if (/^\d{4}$/.test(rawHeader)) {
      yearColumns.push({ year: parseInt(rawHeader, 10), index: i });
      continue;
    }

    if (normalized === "promedio" || normalized === "promediohistorico") {
      averageIndex = i;
      continue;
    }

    if (normalized === "limitesuperior") {
      upperIndex = i;
      continue;
    }

    if (normalized === "limiteinferior") {
      lowerIndex = i;
      continue;
    }

    if (normalized === "desv" || normalized === "desviacion" || normalized === "desviacionestandar") {
      stddevIndex = i;
      continue;
    }
  }

  if (weekIndex === null) {
    throw new Error("No se encontro la columna SEMANA en la hoja.");
  }

  if (yearColumns.length < 2) {
    throw new Error("No se detectaron suficientes columnas de anio en la hoja.");
  }

  yearColumns.sort(function(a, b) {
    return a.year - b.year;
  });

  return {
    weekIndex: weekIndex,
    averageIndex: averageIndex,
    upperIndex: upperIndex,
    lowerIndex: lowerIndex,
    stddevIndex: stddevIndex,
    yearColumns: yearColumns
  };
}

function detectYearProgress_(rows, targetYear, treatTrailingZerosAsMissing) {
  var result = {
    lastWeekWithObservedData: null,
    trailingPlaceholderWeeks: []
  };

  for (var i = 0; i < rows.length; i++) {
    var value = getYearValue_(rows[i], targetYear);
    if (value !== null && (!treatTrailingZerosAsMissing || value > 0)) {
      result.lastWeekWithObservedData = rows[i].semana;
    }
  }

  if (!treatTrailingZerosAsMissing || result.lastWeekWithObservedData === null) {
    return result;
  }

  for (var j = 0; j < rows.length; j++) {
    var row = rows[j];
    var rowValue = getYearValue_(row, targetYear);
    if (row.semana > result.lastWeekWithObservedData && (rowValue === 0 || rowValue === null)) {
      result.trailingPlaceholderWeeks.push(row.semana);
    }
  }

  return result;
}

function buildDatasetDiagnostics_(dataset, targetYear, treatTrailingZerosAsMissing) {
  var progress = detectYearProgress_(dataset.rows, targetYear, treatTrailingZerosAsMissing);
  var averages = extractSheetAverages_(dataset.rows);
  var diagnostics = {
    target_year: targetYear,
    last_week_with_observed_data: progress.lastWeekWithObservedData,
    trailing_placeholder_weeks: progress.trailingPlaceholderWeeks,
    unique_sheet_average_count: countUniqueNumericValues_(averages),
    warnings: []
  };

  if (diagnostics.unique_sheet_average_count <= 2 && dataset.rows.length >= 20) {
    diagnostics.warnings.push(
      "Los valores de promedio historico en la hoja parecen casi constantes. Verifica formulas o referencias del canal."
    );
  }

  if (progress.trailingPlaceholderWeeks.length > 0) {
    diagnostics.warnings.push(
      "Se detectaron semanas finales con cero en el anio objetivo que pueden representar semanas futuras no cargadas."
    );
  }

  return diagnostics;
}

function computeHistoricalStats_(row, yearColumns, targetYear) {
  var yearsUsed = [];
  var values = [];

  for (var i = 0; i < yearColumns.length; i++) {
    var year = yearColumns[i];
    if (year >= targetYear) {
      continue;
    }

    var value = getYearValue_(row, year);
    if (value === null) {
      continue;
    }

    yearsUsed.push(year);
    values.push(value);
  }

  if (values.length === 0) {
    return {
      years: yearsUsed,
      values: values,
      average: null,
      stddev: null,
      upper: null,
      lower: null
    };
  }

  var average = values.reduce(function(acc, item) {
    return acc + item;
  }, 0) / values.length;

  var variance = 0;
  if (values.length > 1) {
    for (var j = 0; j < values.length; j++) {
      variance += Math.pow(values[j] - average, 2);
    }
    variance = variance / (values.length - 1);
  }

  var stddev = Math.sqrt(variance);
  var upper = average + stddev;
  var lower = Math.max(0, average - stddev);

  return {
    years: yearsUsed,
    values: values,
    average: roundNumber_(average, 2),
    stddev: roundNumber_(stddev, 2),
    upper: roundNumber_(upper, 2),
    lower: roundNumber_(lower, 2)
  };
}

function classifyAgainstLimits_(value, upper, lower) {
  if (value === null || upper === null || lower === null) {
    return "sin_dato";
  }

  if (value > upper) {
    return "sobre_lo_esperado";
  }

  if (value < lower) {
    return "por_debajo_de_lo_esperado";
  }

  return "dentro_de_lo_esperado";
}

function resolveTargetYear_(dataset, params) {
  var requested = toIntOrNull_(params.anio || params.year);
  if (requested !== null) {
    for (var i = 0; i < dataset.yearColumns.length; i++) {
      if (dataset.yearColumns[i] === requested) {
        return requested;
      }
    }
    throw new Error("El anio solicitado no existe como columna en la hoja.");
  }
  return dataset.latestYear;
}

function resolvePreviousYear_(dataset, targetYear) {
  var previous = null;
  for (var i = 0; i < dataset.yearColumns.length; i++) {
    if (dataset.yearColumns[i] < targetYear) {
      previous = dataset.yearColumns[i];
    }
  }

  if (previous === null) {
    throw new Error("No existe un anio historico previo para comparar.");
  }

  return previous;
}

function requireWeekParam_(params) {
  var week = toIntOrNull_(params.semana || params.week);
  if (week === null || week < 1 || week > 53) {
    throw new Error("Debes enviar una semana valida entre 1 y 53.");
  }
  return week;
}

function findWeekRow_(rows, week) {
  for (var i = 0; i < rows.length; i++) {
    if (rows[i].semana === week) {
      return rows[i];
    }
  }
  return null;
}

function getComparableYearValue_(row, year, progress, treatTrailingZerosAsMissing) {
  var value = getYearValue_(row, year);
  if (!treatTrailingZerosAsMissing) {
    return value;
  }

  if (progress.lastWeekWithObservedData !== null && row.semana > progress.lastWeekWithObservedData && value === 0) {
    return null;
  }

  return value;
}

function getYearValue_(row, year) {
  var key = String(year);
  if (!row || !row.casesByYear || !row.casesByYear.hasOwnProperty(key)) {
    return null;
  }

  return row.casesByYear[key];
}

function getBulletinConfig_() {
  var props = PropertiesService.getScriptProperties();
  return {
    spreadsheetId: String(props.getProperty("EPIPROC_BULLETIN_SPREADSHEET_ID") || EPIPROC_BULLETIN_DEFAULT_SPREADSHEET_ID).trim(),
    sheetName: String(props.getProperty("EPIPROC_BULLETIN_SHEET_NAME") || EPIPROC_BULLETIN_DEFAULT_SHEET_NAME).trim(),
    eventCode: toIntOrNull_(props.getProperty("EPIPROC_BULLETIN_EVENT_CODE")) || EPIPROC_BULLETIN_DEFAULT_EVENT_CODE,
    timezone: String(props.getProperty("EPIPROC_BULLETIN_TIMEZONE") || EPIPROC_BULLETIN_DEFAULT_TIMEZONE).trim()
  };
}

function getBulletinSheet_() {
  var config = getBulletinConfig_();
  var ss = SpreadsheetApp.openById(config.spreadsheetId);
  var sheet = ss.getSheetByName(config.sheetName);

  if (!sheet && config.sheetName !== EPIPROC_BULLETIN_DEFAULT_SHEET_NAME) {
    sheet = ss.getSheetByName(EPIPROC_BULLETIN_DEFAULT_SHEET_NAME);
  }

  if (!sheet) {
    sheet = ss.getSheetByName("Hoja 1");
  }

  if (!sheet) {
    var sheets = ss.getSheets();
    if (sheets && sheets.length === 1) {
      sheet = sheets[0];
    }
  }

  if (!sheet) {
    throw new Error(
      "No se encontro la hoja configurada para CASOS 2. Define EPIPROC_BULLETIN_SHEET_NAME o renombra la pestaña del Google Sheets."
    );
  }

  return sheet;
}

function parseJsonBody_(e) {
  if (!e || !e.postData || !e.postData.contents) {
    return {};
  }

  try {
    return JSON.parse(e.postData.contents);
  } catch (err) {
    throw new Error("JSON invalido en la solicitud.");
  }
}

function validarApiKey_(params) {
  var expected = PropertiesService.getScriptProperties().getProperty("EPIPROC_BULLETIN_API_KEY");
  if (!expected) {
    expected = EPIPROC_BULLETIN_DEFAULT_API_KEY;
  }

  if (!expected) {
    return;
  }

  var provided = String(params.key || params.api_key || "").trim();
  if (!provided || provided !== expected) {
    throw new Error("API key invalida.");
  }
}

function jsonOutput_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function normalizeHeader_(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[áàäâ]/g, "a")
    .replace(/[éèëê]/g, "e")
    .replace(/[íìïî]/g, "i")
    .replace(/[óòöô]/g, "o")
    .replace(/[úùüû]/g, "u")
    .replace(/ñ/g, "n")
    .replace(/[^a-z0-9]+/g, "")
    .trim();
}

function toNumberOrNull_(value) {
  if (value === null || value === "") {
    return null;
  }

  if (typeof value === "number") {
    if (isNaN(value)) {
      return null;
    }
    return value;
  }

  var txt = String(value).trim();
  if (!txt) {
    return null;
  }

  txt = txt.replace(/\./g, "").replace(/,/g, ".");
  var parsed = Number(txt);
  if (isNaN(parsed)) {
    return null;
  }
  return parsed;
}

function toIntOrNull_(value) {
  var num = toNumberOrNull_(value);
  if (num === null) {
    return null;
  }
  return parseInt(num, 10);
}

function getBooleanParam_(params, key, defaultValue) {
  if (!params || !params.hasOwnProperty(key)) {
    return defaultValue;
  }

  var raw = String(params[key]).trim().toLowerCase();
  if (!raw) {
    return defaultValue;
  }

  return raw === "1" || raw === "true" || raw === "si" || raw === "yes";
}

function getNumericParam_(params, key, defaultValue) {
  if (!params || !params.hasOwnProperty(key)) {
    return defaultValue;
  }

  var num = toNumberOrNull_(params[key]);
  return num === null ? defaultValue : num;
}

function getTreatTrailingZerosAsMissing_(params) {
  var props = PropertiesService.getScriptProperties();
  var configured = props.getProperty("EPIPROC_TREAT_TRAILING_ZEROS_AS_MISSING");
  var defaultValue = configured === null ? true : getBooleanText_(configured);

  if (params && (params.hasOwnProperty("treat_trailing_zeros_as_missing") || params.hasOwnProperty("placeholder_zeros"))) {
    return getBooleanParam_(params, params.hasOwnProperty("treat_trailing_zeros_as_missing") ? "treat_trailing_zeros_as_missing" : "placeholder_zeros", defaultValue);
  }

  return defaultValue;
}

function getBooleanText_(value) {
  var raw = String(value || "").trim().toLowerCase();
  return raw === "1" || raw === "true" || raw === "si" || raw === "yes";
}

function extractSheetAverages_(rows) {
  var items = [];
  for (var i = 0; i < rows.length; i++) {
    if (rows[i].sheetStats.average !== null) {
      items.push(rows[i].sheetStats.average);
    }
  }
  return items;
}

function countUniqueNumericValues_(items) {
  var seen = {};
  for (var i = 0; i < items.length; i++) {
    var value = items[i];
    if (value === null) {
      continue;
    }
    seen[String(roundNumber_(value, 2))] = true;
  }
  return Object.keys(seen).length;
}

function copyObject_(obj) {
  return JSON.parse(JSON.stringify(obj));
}

function absoluteDiff_(a, b) {
  if (a === null || b === null) {
    return null;
  }
  return roundNumber_(Math.abs(a - b), 2);
}

function roundNumber_(value, digits) {
  if (value === null || typeof value === "undefined") {
    return null;
  }
  var factor = Math.pow(10, digits || 0);
  return Math.round(value * factor) / factor;
}

function nowIso_(timezone) {
  return Utilities.formatDate(new Date(), timezone || EPIPROC_BULLETIN_DEFAULT_TIMEZONE, "yyyy-MM-dd'T'HH:mm:ssXXX");
}