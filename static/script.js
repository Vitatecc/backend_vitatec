let intervaloSolicitudes = null;
let mostrarFueraDeHorarioManual = false;
let ultimasSolicitudesJSON = "";
let dnisRegistrados = [];

document.addEventListener("DOMContentLoaded", function () {
    const ahora = new Date();
    const hora = ahora.getHours();
    const dia = ahora.getDay(); // 0=domingo, 6=sábado
    const dentroHorario = true; // ⚠️ FORZAMOS horario laboral

    cargarLogs();
    cargarMensajes();
    cargarAuditoria();
    cargarEstadisticas();

    if (dentroHorario) {
        document.querySelector("#tablaSolicitudes thead").style.display = "table-header-group";
        document.getElementById("avisoHorario").style.display = "none";
        cargarSolicitudes();
        intervaloSolicitudes = setInterval(cargarSolicitudes, 10000);
    } else {
        document.getElementById("avisoHorario").style.display = "block";
        document.getElementById("solicitudesBody").innerHTML = "";
        document.querySelector("#tablaSolicitudes thead").style.display = "none";
    }

    document.querySelectorAll('input[name="tipoEstadistica"]').forEach(radio => {
        radio.addEventListener('change', cargarEstadisticas);
    });
});


fetch("/api/pacientes/dnis")
    .then(res => res.json())
    .then(data => {
        dnisRegistrados = data
            .filter(d => typeof d === "string")  // ✅ Asegura que sea string
            .map(d => d.toLowerCase());
    });

function getApiKey() {
    return fetch("/webhook/get-api-key", {
        method: "GET",
        headers: {
            "Authorization": "Bearer 10987654321CCP"
        }
    })
    .then(res => res.json())
    .then(data => data.api_key);
}

function cargarSolicitudes() {
    fetch('/api/ver-solicitudes')
        .then(res => res.json())
        .then(async data => {
            const nuevoJSON = JSON.stringify(data.archivos || []);
            if (nuevoJSON === ultimasSolicitudesJSON) {
                return; // ✅ No hay cambios, no hacemos nada
            }

            ultimasSolicitudesJSON = nuevoJSON;

            const cuerpo = document.getElementById("solicitudesBody");
            cuerpo.innerHTML = "";

            if (!data.archivos || data.archivos.length === 0) {
                cuerpo.innerHTML = `<tr><td colspan="4">No hay solicitudes pendientes.</td></tr>`;
                return;
            }

            dnisRegistrados = await fetch('/api/pacientes/dnis')
                .then(res => res.json())
                .then(data => data
                    .filter(d => typeof d === "string")
                    .map(d => d.toLowerCase())
                );

            for (const archivo of data.archivos) {
                try {
                    const response = await fetch(`/webhook/solicitud/${archivo}`);
                    const solicitud = await response.json();
                    console.log("🧩 Datos de solicitud recibidos:", solicitud);

                    const fila = document.createElement("tr");
                    const dniPaciente = (solicitud.dni || "").toLowerCase();
                    const dniDuplicado = dnisRegistrados.includes(dniPaciente);

                    fila.innerHTML = `
                        <td>${dniDuplicado ? "⚠️ " : ""}${solicitud.nombre} ${solicitud.apellidos}</td>
                        <td>${solicitud.movil}</td>
                        <td>${solicitud.email}</td>
                        <td>
                            <button class="btn-ver" data-solicitud='${encodeURIComponent(JSON.stringify(solicitud))}'>Ver</button>
                            <button onclick="aprobarPaciente('${solicitud.dni}')">Aprobar</button>
                            <button onclick="rechazarPaciente('${solicitud.dni}')">Rechazar</button>
                        </td>
                    `;

                    if (dniDuplicado) {
                        fila.classList.add("fila-duplicada");
                    }

                    cuerpo.appendChild(fila);
                } catch (err) {
                    console.error("Error procesando solicitud:", err);
                }
            }

            document.querySelectorAll(".btn-ver").forEach(btn => {
                btn.addEventListener("click", () => {
                    const solicitud = JSON.parse(decodeURIComponent(btn.dataset.solicitud));
                    verDetalles(solicitud);
                });
            });
        });
}

function mostrarSolicitudesFueraHorario() {
    document.querySelector("#tablaSolicitudes thead").style.display = "table-header-group";
    document.getElementById("avisoHorario").style.display = "none";

    cargarSolicitudes();
    if (!intervaloSolicitudes) {
        intervaloSolicitudes = setInterval(cargarSolicitudes, 10000);
    }
}


function aprobarPaciente(dni) {
  if (dnisRegistrados.includes(dni.toLowerCase())) {
    alert("⚠️ Este DNI ya existe en la base de datos. No se puede crear el paciente duplicado.");
    return;
  }

  getApiKey().then(apiKey => {
    fetch(`/webhook/aprobar/${dni}`, {
      method: "POST",
      headers: {
        "x-api-key": apiKey
      }
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === "success") {
          alert("Paciente aprobado correctamente.");
          cargarSolicitudes();
          cargarAuditoria();
          cargarLogs();
        } else {
          alert("Error: " + data.message);
        }
      })
      .catch(err => {
        alert("Error al aprobar paciente: " + err);
      });
  });
}

function rechazarPaciente(dni) {
    getApiKey().then(apiKey => {
        fetch(`/webhook/rechazar/${dni}`, {
            method: "POST",
            headers: {
                "x-api-key": apiKey
            }
        })
        .then(res => res.json())
        .then(data => {
            alert(data.message || "Solicitud rechazada");
            cargarSolicitudes();
            cargarAuditoria();
            cargarLogs();
        });
    });
}

function cargarLogs(mostrarTodos = false) {
    fetch("/webhook/logs")
        .then(response => response.json())
        .then(data => {
            const lista = data.logs || [];
            const contenedor = document.getElementById("logsContainer");
            contenedor.innerHTML = "";

            const max = mostrarTodos ? lista.length : 10;
            lista.slice(0, max).forEach(log => {
                const div = document.createElement("div");
                div.className = "log log-" + (log.type || "info");
                div.textContent = `${log.timestamp} - ${log.message}`;
                contenedor.appendChild(div);
            });
        })
        .catch(error => {
            console.error("Error al cargar logs:", error);
        });
}

function cargarMensajes(mostrarTodos = false) {
    fetch("/webhook/messages")
        .then(response => response.json())
        .then(data => {
            const lista = data.messages || [];
            const contenedor = document.getElementById("messagesContainer");
            contenedor.innerHTML = "";

            const max = mostrarTodos ? lista.length : 10;
            lista.slice(0, max).forEach(msg => {
                const div = document.createElement("div");
                div.className = "mensaje";
                div.textContent = `${msg.timestamp} - ${msg.telefono} → ${msg.contenido}`;
                contenedor.appendChild(div);
            });
        })
        .catch(error => {
            console.error("Error al cargar mensajes:", error);
        });
}

function cargarAuditoria() {
    fetch("/webhook/audit")
        .then(res => res.json())
        .then(data => {
            const contenedor = document.getElementById("auditList");
            contenedor.innerHTML = "";

            data.forEach(item => {
                // Ignorar entradas mal formateadas
                if (!item.accion || !item.usuario || !item.dni) return;
            
                const fecha = new Date(item.timestamp).toLocaleString("es-ES");
                const clase = item.accion === "Rechazada" ? "registro-rechazado" : "registro-aprobado";
            
                const div = document.createElement("div");
                div.className = `registro ${clase}`;
                div.innerHTML = `
                    <strong>${item.usuario}</strong> – 
                    <span>${item.accion}</span> (${item.dni})<br>
                    <small>${fecha}</small>
                `;
                div.onclick = () => verAuditoriaDetalles(item);
                contenedor.appendChild(div);
            });
        });
}


function cargarEstadisticas() {
    const tipo = document.querySelector('input[name="tipoEstadistica"]:checked').value;
    const url = tipo === "mes" ? '/webhook/stats-google' : '/webhook/stats-google?modo=dia';
    
    fetch(url)
        .then(res => res.json())
        .then(data => {
            const labels = data.labels || Object.keys(data);
            const values = data.values || labels.map(l => data[l]);

            const ctx = document.getElementById("myChart").getContext("2d");
            if (window.miGrafico) {
                window.miGrafico.destroy();
            }

            window.miGrafico = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: tipo === "mes" ? "Citas por mes" : "Citas por día",
                        data: values,
                        backgroundColor: 'rgba(75, 192, 192, 0.6)'
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });

            const hoy = new Date().toISOString().split("T")[0];
            const totalHoy = tipo === "dia" ? (data[hoy] || 0) : 0;
            document.getElementById("citasHoy").textContent = totalHoy;
        });
}


function verDetalles(p) {
    const existe = dnisRegistrados.includes(p.dni.toLowerCase());
    const contenedor = document.getElementById("contenidoDetalles");

    contenedor.innerHTML = `
        <p><strong>Nombre:</strong> ${p.nombre}</p>
        <p><strong>Apellidos:</strong> ${p.apellidos}</p>
        <p><strong>DNI:</strong> <span style="color:${existe ? 'red' : 'black'}">${p.dni}</span></p>
        <p><strong>Teléfono:</strong> ${p.movil}</p>
        <p><strong>Email:</strong> ${p.email}</p>
        <p><strong>Fecha de nacimiento:</strong> ${p.fecha_nacimiento || "-"}</p>
        <p><strong>Motivo:</strong> ${p.motivo || "-"}</p>
    `;
    document.getElementById("modalDetalles").style.display = "flex";
}

function cerrarModal() {
    document.getElementById("modalDetalles").style.display = "none";
}

function verAuditoriaDetalles(item) {
    const contenedor = document.getElementById("contenidoAuditoria");

    contenedor.innerHTML = `
        <p><strong>DNI:</strong> ${item.dni || "-"}</p>
        <p><strong>Acción:</strong> ${item.accion || "-"}</p>
        <p><strong>Usuario:</strong> ${item.usuario || "Sistema"}</p>
        <p><strong>Fecha:</strong> ${new Date(item.timestamp).toLocaleString("es-ES")}</p>
    `;
    document.getElementById("modalAuditoria").style.display = "flex";
}

function cerrarAuditoriaModal() {
    document.getElementById("modalAuditoria").style.display = "none";
}
