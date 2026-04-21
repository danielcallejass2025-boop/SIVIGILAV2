/**
 * EPIPROC - Registro de epidemiologos en Google Apps Script
 *
 * Este archivo soporta dos modos:
 * 1) HtmlService con google.script.run -> registrarEpidemiologo(...)
 * 2) API Web App (doPost) con JSON y accion=registrar_epidemiologo
 */

var EPIPROC_SHEET_NAME = "Epidemiologos";
var EPIPROC_MAIL_SENDER_NAME = "EPIPROC - Gobernacion de Risaralda";
var EPIPROC_HEADERS = [
  "nombre",
  "cedula",
  "correo",
  "evento",
  "usuario",
  "password_temporal",
  "estado",
  "fecha_registro"
];

/**
 * Crea un epidemiologo y envia correo de bienvenida.
 *
 * @param {string} nombre
 * @param {string} cedula
 * @param {string} correo
 * @param {string|number} evento
 * @return {{success:boolean, user:string, pass:string, error:(string|null)}}
 */
function registrarEpidemiologo(nombre, cedula, correo, evento) {
  var payload = {
    nombre: String(nombre || "").trim(),
    cedula: String(cedula || "").trim(),
    correo: String(correo || "").trim(),
    evento: String(evento || "").trim()
  };

  var validation = validarRegistro_(payload);
  if (!validation.ok) {
    return { success: false, user: "", pass: "", error: validation.error };
  }

  var passwordTemporal = generarPasswordTemporal_(10);
  var usuario = payload.cedula;
  var eventoDisplay = normalizarEventoDisplay_(payload.evento);

  try {
    var ss = getSpreadsheet_();
    var sheet = getOrCreateSheet_(ss, EPIPROC_SHEET_NAME);

    // Evitar duplicados por cedula
    if (existeCedula_(sheet, payload.cedula)) {
      throw new Error("Ya existe un epidemiologo registrado con esa cedula.");
    }

    sheet.appendRow([
      payload.nombre,
      payload.cedula,
      payload.correo,
      eventoDisplay,
      usuario,
      passwordTemporal,
      "Activo",
      new Date()
    ]);

    var asunto = "Bienvenido a EPIPROC - Tus Credenciales de Acceso";
    var cuerpoHtml =
      '<div style="font-family:Arial,sans-serif;border:1px solid #ddd;padding:20px;">' +
      '<h2 style="color:#007d4c;">Sistema EPIPROC</h2>' +
      '<p>Hola <strong>' + escaparHtml_(payload.nombre) + '</strong>,</p>' +
      '<p>Has sido registrado exitosamente como Epidemiologo en el sistema de la Gobernacion de Risaralda.</p>' +
      '<p>A continuacion, tus datos de acceso:</p>' +
      '<ul>' +
      '<li><strong>Usuario:</strong> ' + escaparHtml_(usuario) + '</li>' +
      '<li><strong>Contrasena Temporal:</strong> ' + escaparHtml_(passwordTemporal) + '</li>' +
      '<li><strong>Evento Asignado:</strong> ' + escaparHtml_(eventoDisplay) + '</li>' +
      '</ul>' +
      '<p>Por favor, ingresa al sistema y cambia tu contrasena en el primer inicio de sesion.</p>' +
      '<br>' +
      '<p style="font-size:0.8em;color:#666;">EPIPROC - Procesamiento Epidemiologico</p>' +
      '</div>';

    enviarCorreoCredenciales_(payload.correo, asunto, cuerpoHtml);

    return { success: true, user: usuario, pass: passwordTemporal, error: null };
  } catch (e) {
    return { success: false, user: "", pass: "", error: String(e) };
  }
}

/**
 * Endpoint de prueba.
 */
function doGet() {
  return jsonOutput_({ success: true, service: "EPIPROC_APPS_SCRIPT", status: "ok" });
}

/**
 * Endpoint API para uso desde EPIPROC (fetch).
 * Espera JSON con accion=registrar_epidemiologo.
 */
function doPost(e) {
  try {
    var body = parseJsonBody_(e);
    validarApiKey_(body);

    var accion = String(body.accion || body.action || "").toLowerCase();
    if (accion === "registrar_epidemiologo") {
      var result = registrarEpidemiologo(body.nombre, body.cedula, body.correo, body.evento);
      return jsonOutput_(result);
    }

    if (accion === "listar_epidemiologos") {
      return jsonOutput_({ success: true, items: listarEpidemiologos_() });
    }

    if (accion === "autenticar_epidemiologo") {
      return jsonOutput_(autenticarEpidemiologo_(body.usuario, body.password));
    }

    if (accion === "actualizar_estado_epidemiologo") {
      return jsonOutput_(actualizarEstadoEpidemiologo_(body.usuario, body.cedula, body.estado));
    }

    if (accion === "regenerar_password_epidemiologo") {
      return jsonOutput_(regenerarPasswordEpidemiologo_(body.usuario, body.cedula));
    }

    if (accion === "actualizar_evento_epidemiologo") {
      return jsonOutput_(actualizarEventoEpidemiologo_(body.usuario, body.cedula, body.evento));
    }

    if (accion === "actualizar_epidemiologo") {
      return jsonOutput_(actualizarEpidemiologo_(body));
    }

    if (accion === "eliminar_epidemiologo") {
      return jsonOutput_(eliminarEpidemiologo_(body.usuario, body.cedula));
    }

    return jsonOutput_({ success: false, error: "Accion no soportada." });
  } catch (err) {
    return jsonOutput_({ success: false, error: String(err) });
  }
}

function buscarFilaEpidemiologo_(sheet, usuario, cedula) {
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return null;
  }

  var userTarget = String(usuario || "").trim();
  var cedTarget = String(cedula || "").trim();
  var rows = sheet.getRange(2, 1, lastRow - 1, EPIPROC_HEADERS.length).getValues();

  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    var rowCed = String(row[1] || "").trim();
    var rowUser = String(row[4] || rowCed).trim();

    if (userTarget && rowUser === userTarget) {
      return { rowNumber: i + 2, rowData: row };
    }
    if (cedTarget && rowCed === cedTarget) {
      return { rowNumber: i + 2, rowData: row };
    }
  }

  return null;
}

function existeCedulaEnOtraFila_(sheet, cedula, rowNumberActual) {
  var target = String(cedula || "").trim();
  if (!target) {
    return false;
  }

  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return false;
  }

  var values = sheet.getRange(2, 2, lastRow - 1, 1).getValues();
  for (var i = 0; i < values.length; i++) {
    var rowNumber = i + 2;
    if (rowNumber === rowNumberActual) {
      continue;
    }
    if (String(values[i][0] || "").trim() === target) {
      return true;
    }
  }

  return false;
}

function actualizarEstadoEpidemiologo_(usuario, cedula, estado) {
  var ss = getSpreadsheet_();
  var sheet = getOrCreateSheet_(ss, EPIPROC_SHEET_NAME);
  var found = buscarFilaEpidemiologo_(sheet, usuario, cedula);
  if (!found) {
    return { success: false, error: "No existe epidemiologo para actualizar estado." };
  }

  var estadoTxt = String(estado || "Activo").trim().toLowerCase() === "inactivo" ? "Inactivo" : "Activo";
  sheet.getRange(found.rowNumber, 7).setValue(estadoTxt);

  return { success: true, usuario: String(found.rowData[4] || found.rowData[1]).trim(), estado: estadoTxt };
}

function regenerarPasswordEpidemiologo_(usuario, cedula) {
  var ss = getSpreadsheet_();
  var sheet = getOrCreateSheet_(ss, EPIPROC_SHEET_NAME);
  var found = buscarFilaEpidemiologo_(sheet, usuario, cedula);
  if (!found) {
    return { success: false, error: "No existe epidemiologo para regenerar clave." };
  }

  var newPass = generarPasswordTemporal_(10);
  sheet.getRange(found.rowNumber, 6).setValue(newPass);

  var finalUser = String(found.rowData[4] || found.rowData[1]).trim();
  return { success: true, user: finalUser, pass: newPass, password_temporal: newPass };
}

function actualizarEventoEpidemiologo_(usuario, cedula, evento) {
  var ss = getSpreadsheet_();
  var sheet = getOrCreateSheet_(ss, EPIPROC_SHEET_NAME);
  var found = buscarFilaEpidemiologo_(sheet, usuario, cedula);
  if (!found) {
    return { success: false, error: "No existe epidemiologo para actualizar evento." };
  }

  var eventoDisplay = normalizarEventoDisplay_(evento);
  sheet.getRange(found.rowNumber, 4).setValue(eventoDisplay);

  return { success: true, usuario: String(found.rowData[4] || found.rowData[1]).trim(), evento: eventoDisplay };
}

function actualizarEpidemiologo_(body) {
  var oldUsuario = String(body.old_usuario || "").trim();
  var oldCedula = String(body.old_cedula || "").trim();

  var nombre = String(body.nombre || "").trim();
  var cedula = String(body.cedula || "").trim();
  var correo = String(body.correo || "").trim();
  var evento = normalizarEventoDisplay_(body.evento);
  var usuario = String(body.usuario || cedula).trim();
  var estado = String(body.estado || "Activo").trim().toLowerCase() === "inactivo" ? "Inactivo" : "Activo";
  var newPass = String(body.password_temporal || "").trim();

  var validation = validarRegistro_({ nombre: nombre, cedula: cedula, correo: correo, evento: evento });
  if (!validation.ok) {
    return { success: false, error: validation.error };
  }

  var ss = getSpreadsheet_();
  var sheet = getOrCreateSheet_(ss, EPIPROC_SHEET_NAME);
  var found = buscarFilaEpidemiologo_(sheet, oldUsuario || usuario, oldCedula || cedula);
  if (!found) {
    return { success: false, error: "No existe epidemiologo para actualizar." };
  }

  if (existeCedulaEnOtraFila_(sheet, cedula, found.rowNumber)) {
    return { success: false, error: "Ya existe otra fila con la cedula indicada." };
  }

  var rowData = found.rowData;
  var finalPass = newPass || String(rowData[5] || "").trim();

  sheet.getRange(found.rowNumber, 1, 1, EPIPROC_HEADERS.length).setValues([[
    nombre,
    cedula,
    correo,
    evento,
    usuario || cedula,
    finalPass,
    estado,
    rowData[7] || new Date()
  ]]);

  return {
    success: true,
    usuario: usuario || cedula,
    cedula: cedula,
    correo: correo,
    evento: evento,
    estado: estado,
    password_temporal: finalPass
  };
}

function eliminarEpidemiologo_(usuario, cedula) {
  var ss = getSpreadsheet_();
  var sheet = getOrCreateSheet_(ss, EPIPROC_SHEET_NAME);
  var found = buscarFilaEpidemiologo_(sheet, usuario, cedula);
  if (!found) {
    return { success: false, error: "No existe epidemiologo para eliminar." };
  }

  sheet.deleteRow(found.rowNumber);
  return { success: true, usuario: String(found.rowData[4] || found.rowData[1]).trim() };
}

function listarEpidemiologos_() {
  var ss = getSpreadsheet_();
  var sheet = getOrCreateSheet_(ss, EPIPROC_SHEET_NAME);
  var lastRow = sheet.getLastRow();

  if (lastRow < 2) {
    return [];
  }

  var rows = sheet.getRange(2, 1, lastRow - 1, EPIPROC_HEADERS.length).getValues();
  var items = [];

  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    var cedula = String(row[1] || "").trim();
    if (!cedula) {
      continue;
    }

    items.push({
      nombre: String(row[0] || "").trim(),
      cedula: cedula,
      correo: String(row[2] || "").trim(),
      evento: String(row[3] || "").trim(),
      usuario: String(row[4] || cedula).trim(),
      password_temporal: String(row[5] || "").trim(),
      estado: String(row[6] || "Activo").trim(),
      fecha_registro: row[7] || ""
    });
  }

  return items;
}

function autenticarEpidemiologo_(usuario, password) {
  var userTxt = String(usuario || "").trim();
  var passTxt = String(password || "");

  if (!userTxt || !passTxt) {
    return { success: false, error: "Usuario y contrasena obligatorios." };
  }

  var items = listarEpidemiologos_();
  for (var i = 0; i < items.length; i++) {
    var item = items[i];
    var sameUser = String(item.usuario || "").trim() === userTxt;
    var samePass = String(item.password_temporal || "") === passTxt;
    var isInactive = String(item.estado || "").toLowerCase() === "inactivo";

    if (sameUser && samePass && !isInactive) {
      return {
        success: true,
        nombre: item.nombre,
        cedula: item.cedula,
        correo: item.correo,
        evento: item.evento,
        usuario: item.usuario,
        password_temporal: item.password_temporal,
        estado: item.estado
      };
    }
  }

  return { success: false, error: "Credenciales invalidas en Apps Script." };
}

function validarRegistro_(payload) {
  if (!payload.nombre) {
    return { ok: false, error: "El nombre es obligatorio." };
  }
  if (!payload.cedula) {
    return { ok: false, error: "La cedula es obligatoria." };
  }
  if (!payload.correo) {
    return { ok: false, error: "El correo es obligatorio." };
  }
  if (!payload.evento) {
    return { ok: false, error: "El evento es obligatorio." };
  }

  var emailRegex = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
  if (!emailRegex.test(payload.correo)) {
    return { ok: false, error: "El correo no tiene un formato valido." };
  }

  return { ok: true, error: null };
}

function generarPasswordTemporal_(length) {
  var chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789@#$%*";
  var output = [];
  for (var i = 0; i < length; i++) {
    var idx = Math.floor(Math.random() * chars.length);
    output.push(chars.charAt(idx));
  }
  return output.join("");
}

function existeCedula_(sheet, cedula) {
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return false;
  }

  // Columna B: cedula
  var values = sheet.getRange(2, 2, lastRow - 1, 1).getValues();
  var target = String(cedula).trim();

  for (var i = 0; i < values.length; i++) {
    if (String(values[i][0]).trim() === target) {
      return true;
    }
  }
  return false;
}

function parseJsonBody_(e) {
  if (!e || !e.postData || !e.postData.contents) {
    throw new Error("Solicitud sin cuerpo JSON.");
  }

  try {
    return JSON.parse(e.postData.contents);
  } catch (err) {
    throw new Error("JSON invalido en la solicitud.");
  }
}

/**
 * Valida API key opcional desde Script Properties.
 * Si APPS_SCRIPT_API_KEY no esta configurada, no exige validacion.
 */
function validarApiKey_(body) {
  var expected = PropertiesService.getScriptProperties().getProperty("APPS_SCRIPT_API_KEY");
  if (!expected) {
    return;
  }

  var provided = String(body.key || "").trim();
  if (!provided || provided !== expected) {
    throw new Error("API key invalida.");
  }
}

function normalizarEventoDisplay_(eventoRaw) {
  var evento = String(eventoRaw || "").trim();
  if (!evento) {
    return "No especificado";
  }

  if (evento.indexOf(" - ") >= 0) {
    return evento;
  }

  var mapa = {
    "549": "549 - Morbilidad materna extrema"
  };

  if (mapa[evento]) {
    return mapa[evento];
  }

  return evento;
}

function enviarCorreoCredenciales_(to, subject, htmlBody) {
  var props = PropertiesService.getScriptProperties();
  var fromAlias = String(props.getProperty("EPIPROC_FROM_ALIAS") || "").trim();

  // Si hay alias configurado (y autorizado en Gmail), usarlo para no exponer correo personal.
  if (fromAlias) {
    try {
      GmailApp.sendEmail(
        to,
        subject,
        "EPIPROC: correo en formato HTML. Si no ves el contenido, habilita HTML.",
        {
          htmlBody: htmlBody,
          name: EPIPROC_MAIL_SENDER_NAME,
          from: fromAlias,
          replyTo: fromAlias
        }
      );
      return;
    } catch (aliasErr) {
      // Fallback a MailApp si el alias no esta autorizado.
    }
  }

  var mailOptions = {
    to: to,
    subject: subject,
    htmlBody: htmlBody,
    name: EPIPROC_MAIL_SENDER_NAME
  };

  MailApp.sendEmail(mailOptions);
}

function getSpreadsheet_() {
  var spreadsheetId = PropertiesService.getScriptProperties().getProperty("EPIPROC_SPREADSHEET_ID");

  if (spreadsheetId) {
    return SpreadsheetApp.openById(String(spreadsheetId).trim());
  }

  var active = SpreadsheetApp.getActiveSpreadsheet();
  if (active) {
    return active;
  }

  throw new Error(
    "No hay spreadsheet activo para este Web App. Configura Script Property EPIPROC_SPREADSHEET_ID con el ID del Google Sheet destino."
  );
}

function getOrCreateSheet_(ss, sheetName) {
  var sheet = ss.getSheetByName(sheetName);

  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
    sheet.getRange(1, 1, 1, EPIPROC_HEADERS.length).setValues([EPIPROC_HEADERS]);
  } else if (sheet.getLastRow() === 0) {
    sheet.getRange(1, 1, 1, EPIPROC_HEADERS.length).setValues([EPIPROC_HEADERS]);
  }

  return sheet;
}

function jsonOutput_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function escaparHtml_(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
