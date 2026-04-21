(function () {
    const cfg = window.EPIPROC_DASHBOARD_CONFIG;
    if (!cfg) {
        return;
    }

    const state = {
        dataVersion: null,
        charts: {
            municipio: null,
            sexo: null,
            edad: null,
            semana: null,
        },
    };

    const el = {
        eventoSelect: document.getElementById("eventoSelect"),
        municipioSelect: document.getElementById("municipioSelect"),
        reloadBtn: document.getElementById("reloadBtn"),
        status: document.getElementById("syncStatus"),
        kpiTotal: document.getElementById("kpiTotal"),
        kpiMunicipios: document.getElementById("kpiMunicipios"),
        kpiEdad: document.getElementById("kpiEdad"),
        kpiSemana: document.getElementById("kpiSemana"),
        tableRows: document.getElementById("tableRows"),
        chartMunicipio: document.getElementById("chartMunicipio"),
        chartSexo: document.getElementById("chartSexo"),
        chartEdad: document.getElementById("chartEdad"),
        chartSemana: document.getElementById("chartSemana"),
    };

    function getCurrentEvent() {
        if (cfg.assignedEvent) {
            return Number(cfg.assignedEvent);
        }
        return Number(el.eventoSelect.value || cfg.selectedEvent || 549);
    }

    function setStatus(text, isError) {
        el.status.textContent = text;
        el.status.style.color = isError ? "#b42318" : "#0f766e";
    }

    function buildUrl() {
        const params = new URLSearchParams();
        params.set("evento", String(getCurrentEvent()));
        if (el.municipioSelect.value) {
            params.set("municipio", el.municipioSelect.value);
        }
        return `${cfg.endpoint}?${params.toString()}`;
    }

    async function fetchData() {
        const resp = await fetch(buildUrl(), { cache: "no-store" });
        if (!resp.ok) {
            let message = "No se pudo consultar el dashboard.";
            try {
                const payload = await resp.json();
                message = payload.error || message;
            } catch (e) {
                /* empty */
            }
            throw new Error(message);
        }
        return resp.json();
    }

    function toLabelsValues(mapObj) {
        const labels = Object.keys(mapObj || {});
        const values = labels.map((k) => Number(mapObj[k] || 0));
        return { labels, values };
    }

    function destroyChart(chart) {
        if (chart && typeof chart.destroy === "function") {
            chart.destroy();
        }
    }

    function updateKpis(payload) {
        el.kpiTotal.textContent = payload.total_casos ?? 0;
        el.kpiMunicipios.textContent = payload.total_municipios ?? 0;
        el.kpiEdad.textContent = payload.edad_promedio ?? 0;
        el.kpiSemana.textContent = payload.ultima_semana ?? "N/A";
    }

    function renderCharts(payload) {
        const municipios = toLabelsValues(payload.casos_por_municipio);
        const sexo = toLabelsValues(payload.casos_por_sexo);
        const edad = payload.hist_edad || { labels: [], values: [] };
        const semanal = toLabelsValues(payload.casos_por_semana);

        destroyChart(state.charts.municipio);
        destroyChart(state.charts.sexo);
        destroyChart(state.charts.edad);
        destroyChart(state.charts.semana);

        state.charts.municipio = new Chart(el.chartMunicipio, {
            type: "bar",
            data: {
                labels: municipios.labels,
                datasets: [{
                    label: "Casos",
                    data: municipios.values,
                    backgroundColor: "rgba(15, 118, 110, 0.75)",
                }],
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
            },
        });

        state.charts.sexo = new Chart(el.chartSexo, {
            type: "doughnut",
            data: {
                labels: sexo.labels,
                datasets: [{
                    data: sexo.values,
                    backgroundColor: ["#0f766e", "#22c55e", "#f59e0b", "#ef4444"],
                }],
            },
            options: { responsive: true },
        });

        state.charts.edad = new Chart(el.chartEdad, {
            type: "line",
            data: {
                labels: edad.labels || [],
                datasets: [{
                    label: "Casos",
                    data: edad.values || [],
                    borderColor: "#0f766e",
                    backgroundColor: "rgba(15, 118, 110, 0.25)",
                    tension: 0.25,
                    fill: true,
                }],
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
            },
        });

        state.charts.semana = new Chart(el.chartSemana, {
            type: "bar",
            data: {
                labels: semanal.labels,
                datasets: [{
                    label: "Casos",
                    data: semanal.values,
                    backgroundColor: "rgba(6, 95, 70, 0.75)",
                }],
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
            },
        });
    }

    function updateTable(payload) {
        const rows = (payload.muestra || []).slice(0, 25);
        el.tableRows.innerHTML = "";

        if (!rows.length) {
            const tr = document.createElement("tr");
            tr.innerHTML = "<td colspan='5'>Sin registros para mostrar.</td>";
            el.tableRows.appendChild(tr);
            return;
        }

        rows.forEach((item) => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${item.municipio || "N/A"}</td>
                <td>${item.edad ?? "N/A"}</td>
                <td>${item.sexo || "N/A"}</td>
                <td>${item.semana || "N/A"}</td>
                <td>${item.fecha_notificacion || "N/A"}</td>
            `;
            el.tableRows.appendChild(tr);
        });
    }

    function updateMunicipios(payload) {
        const actual = el.municipioSelect.value;
        const options = payload.municipios || [];

        el.municipioSelect.innerHTML = "<option value=''>Todos</option>";
        options.forEach((m) => {
            const opt = document.createElement("option");
            opt.value = m;
            opt.textContent = m;
            el.municipioSelect.appendChild(opt);
        });

        if (actual && options.includes(actual)) {
            el.municipioSelect.value = actual;
        }
    }

    function applyPayload(payload, force) {
        if (!payload) {
            return;
        }

        const changed = force || state.dataVersion !== payload.data_version;
        if (!changed) {
            setStatus(`Sin cambios (${new Date().toLocaleTimeString()})`, false);
            return;
        }

        state.dataVersion = payload.data_version;
        updateKpis(payload);
        updateMunicipios(payload);
        renderCharts(payload);
        updateTable(payload);
        setStatus(`Actualizado ${new Date().toLocaleTimeString()}`, false);
    }

    async function refresh(force) {
        try {
            setStatus("Sincronizando...", false);
            const payload = await fetchData();
            applyPayload(payload, Boolean(force));
        } catch (error) {
            console.error(error);
            setStatus(String(error.message || error), true);
        }
    }

    el.reloadBtn.addEventListener("click", function () {
        refresh(true);
    });

    el.eventoSelect.addEventListener("change", function () {
        state.dataVersion = null;
        refresh(true);
    });

    el.municipioSelect.addEventListener("change", function () {
        state.dataVersion = null;
        refresh(true);
    });

    refresh(true);
    window.setInterval(function () {
        refresh(false);
    }, Number(cfg.refreshMs || 5000));
})();
