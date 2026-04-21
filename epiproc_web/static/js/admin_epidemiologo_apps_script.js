(function () {
    "use strict";

    const form = document.getElementById("epidemiologoForm");
    if (!form || form.dataset.mode !== "create") {
        return;
    }

    const cfg = window.EPIPROC_APPS_SCRIPT_CONFIG || {};
    const FALLBACK_DEPLOY_URL = "https://script.google.com/macros/s/AKfycbxjY2VrxTqYG_LWR8nhTtR_XRIxiiw962URCh2dFe2BWUl_84Cz3FjGHneTkrdEpeI0/exec";
    const feedback = document.getElementById("epi-feedback");
    const submitBtn = document.getElementById("epi-submit-btn");

    const inputNombre = document.getElementById("epi-nombre");
    const inputCedula = document.getElementById("epi-cedula");
    const inputCorreo = document.getElementById("epi-correo");
    const inputEvento = document.getElementById("epi-evento");

    function setFeedback(type, message, detailsHtml) {
        if (!feedback) {
            return;
        }

        feedback.classList.remove("alert-success", "alert-error", "alert-warning");
        feedback.classList.add("alert", `alert-${type}`);
        feedback.classList.remove("epi-feedback-hidden");

        let html = `<div>${message}</div>`;
        if (detailsHtml) {
            html += `<div class="epi-credentials-box">${detailsHtml}</div>`;
        }
        feedback.innerHTML = html;
    }

    function clearFeedback() {
        if (!feedback) {
            return;
        }
        feedback.classList.add("epi-feedback-hidden");
        feedback.innerHTML = "";
    }

    function lockForm(lock) {
        if (submitBtn) {
            submitBtn.disabled = lock;
            submitBtn.textContent = lock ? "Registrando..." : "Crear usuario";
        }
    }

    function getFormData() {
        const eventoCodigo = (inputEvento && inputEvento.value || "").trim();
        const selectedOption = inputEvento && inputEvento.options
            ? inputEvento.options[inputEvento.selectedIndex]
            : null;
        const eventoTexto = selectedOption
            ? String(selectedOption.textContent || "").trim()
            : "";

        const eventoFinal = eventoTexto && eventoTexto.toLowerCase() !== "sin evento"
            ? eventoTexto
            : eventoCodigo;

        return {
            nombre: (inputNombre && inputNombre.value || "").trim(),
            cedula: (inputCedula && inputCedula.value || "").trim(),
            correo: (inputCorreo && inputCorreo.value || "").trim(),
            evento: eventoFinal,
            eventoCodigo: eventoCodigo
        };
    }

    function validateFormData(data) {
        const errors = [];

        if (!data.nombre) {
            errors.push("El nombre es obligatorio.");
        }
        if (!data.cedula) {
            errors.push("La cedula es obligatoria.");
        }
        if (!data.correo) {
            errors.push("El correo es obligatorio.");
        }
        if (!data.eventoCodigo) {
            errors.push("El evento asignado es obligatorio.");
        }

        return errors;
    }

    function normalizeResult(payload, data) {
        if (!payload || typeof payload !== "object") {
            throw new Error("Respuesta invalida desde Apps Script.");
        }

        if (!payload.success) {
            throw new Error(payload.error || "No fue posible registrar el epidemiologo.");
        }

        const user = payload.user || data.cedula;
        const pass = payload.pass || payload.passwordTemporal || "(no informado)";

        return { user, pass };
    }

    function friendlyAppsScriptError(message) {
        const raw = String(message || "");
        const lower = raw.toLowerCase();

        if (lower.indexOf("getsheetbyname") >= 0 || lower.indexOf("no hay spreadsheet activo") >= 0) {
            return "Apps Script no tiene hoja vinculada. Configura EPIPROC_SPREADSHEET_ID en Script Properties y vuelve a desplegar el Web App.";
        }

        if (lower.indexOf("api key invalida") >= 0) {
            return "La API key de Apps Script no coincide. Revisa APPS_SCRIPT_API_KEY en EPIPROC y en Script Properties.";
        }

        return raw;
    }

    function registerWithGoogleScriptRun(data) {
        return new Promise((resolve, reject) => {
            const gs = window.google && window.google.script && window.google.script.run;
            if (!gs || typeof gs.registrarEpidemiologo !== "function") {
                reject(new Error("google.script.run no esta disponible en este contexto."));
                return;
            }

            gs.withSuccessHandler(resolve)
                .withFailureHandler((err) => {
                    reject(new Error(err && err.message ? err.message : String(err)));
                })
                .registrarEpidemiologo(data.nombre, data.cedula, data.correo, data.evento);
        });
    }

    async function registerWithAppsScriptApi(data, urlOverride) {
        const deployUrl = String(urlOverride || cfg.deployUrl || "").trim();
        if (!deployUrl) {
            throw new Error("No hay APPS_SCRIPT_DEPLOY_URL configurada en el sistema.");
        }

        const body = {
            accion: "registrar_epidemiologo",
            nombre: data.nombre,
            cedula: data.cedula,
            correo: data.correo,
            evento: data.evento,
            evento_codigo: data.eventoCodigo
        };

        const apiKey = String(cfg.apiKey || "").trim();
        if (apiKey) {
            body.key = apiKey;
        }

        // Apps Script Web App no responde bien a preflight OPTIONS (405).
        // Enviamos body JSON como text/plain para mantener una solicitud CORS simple.
        const response = await fetch(deployUrl, {
            method: "POST",
            headers: {
                "Content-Type": "text/plain;charset=utf-8"
            },
            body: JSON.stringify(body)
        });

        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.error || `Error HTTP ${response.status} en Apps Script.`);
        }

        return payload;
    }

    function isSpreadsheetBindingError(message) {
        const raw = String(message || "").toLowerCase();
        return raw.indexOf("getsheetbyname") >= 0 || raw.indexOf("no hay spreadsheet activo") >= 0;
    }

    async function sendToAppsScript(data) {
        try {
            return await registerWithGoogleScriptRun(data);
        } catch (err) {
            const message = String(err && err.message ? err.message : err);
            const googleUnavailable = message.toLowerCase().indexOf("google.script.run") >= 0;
            if (!googleUnavailable) {
                throw err;
            }

            const primaryUrl = String(cfg.deployUrl || "").trim();
            const fallbackUrl = FALLBACK_DEPLOY_URL;

            try {
                return await registerWithAppsScriptApi(data, primaryUrl || fallbackUrl);
            } catch (primaryErr) {
                const pMsg = String(primaryErr && primaryErr.message ? primaryErr.message : primaryErr);
                const shouldRetryWithFallback =
                    fallbackUrl &&
                    fallbackUrl !== primaryUrl &&
                    (isSpreadsheetBindingError(pMsg) || pMsg.toLowerCase().indexOf("error http") >= 0);

                if (!shouldRetryWithFallback) {
                    throw primaryErr;
                }

                return registerWithAppsScriptApi(data, fallbackUrl);
            }
        }
    }

    async function syncWithLocalDatabase(data, credentials) {
        const endpoint = String(cfg.syncEndpoint || "").trim();
        if (!endpoint) {
            throw new Error("No hay endpoint local de sincronizacion configurado.");
        }

        const response = await fetch(endpoint, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                nombre: data.nombre,
                cedula: data.cedula,
                correo: data.correo,
                evento: data.evento,
                evento_codigo: data.eventoCodigo,
                user: credentials.user,
                pass: credentials.pass,
                estado: "Activo"
            })
        });

        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload.success) {
            throw new Error(payload.error || `Error HTTP ${response.status} al sincronizar en EPIPROC.`);
        }

        return payload;
    }

    function resetCreateForm() {
        form.reset();
        if (inputNombre) {
            inputNombre.focus();
        }
    }

    form.addEventListener("submit", async function (event) {
        event.preventDefault();
        clearFeedback();

        const data = getFormData();
        const errors = validateFormData(data);
        if (errors.length > 0) {
            setFeedback("error", errors.join(" "));
            return;
        }

        lockForm(true);
        setFeedback("warning", "Enviando datos al servicio de Apps Script...");

        try {
            const rawResult = await sendToAppsScript(data);
            const result = normalizeResult(rawResult, data);

            await syncWithLocalDatabase(data, result);

            setFeedback(
                "success",
                "Epidemiologo registrado, sincronizado en EPIPROC y correo enviado exitosamente.",
                `<div><strong>Usuario:</strong> ${result.user}</div><div><strong>Contrasena temporal:</strong> ${result.pass}</div>`
            );

            resetCreateForm();
        } catch (err) {
            const msg = friendlyAppsScriptError(err && err.message ? err.message : String(err));
            setFeedback("error", `No se pudo registrar el epidemiologo. ${msg}`);
        } finally {
            lockForm(false);
        }
    });
})();
