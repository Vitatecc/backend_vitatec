document.addEventListener("DOMContentLoaded", function () {
    cargarLogs();
    cargarMensajes();
    cargarAuditoria();
    cargarEstadisticas();

    document.querySelectorAll('input[name="tipoEstadistica"]').forEach(radio => {
        radio.addEventListener('change', cargarEstadisticas);
    });

    const ahora = new Date();
    const hora = ahora.getHours();
    const dia = ahora.getDay();
    const dentroHorario = (dia >= 1 && dia <= 5) && ((hora >= 10 && hora < 14) || (hora >= 16 && hora < 20));

    // Recuperar estado desde localStorage
    mostrarFueraHorario = localStorage.getItem("mostrarFueraHorario") === "true";

    if (mostrarFueraHorario) {
        document.querySelector("#avisoHorario button").textContent = "Ocultar fuera de horario";
        document.getElementById("avisoRecordatorio").style.display = "block";
        cargarSolicitudes();
        intervaloSolicitudes = setInterval(cargarSolicitudes, 10000);
    } else if (!dentroHorario) {
        document.getElementById("avisoHorario").style.display = "block";
    } else {
        cargarSolicitudes();
        intervaloSolicitudes = setInterval(cargarSolicitudes, 10000);
    }
});


let intervaloSolicitudes = null;
let mostrarFueraHorario = false;
let dnisRegistrados = [];

fetch("/api/pacientes/dnis")
    .then(res => res.json())
    .then(data => {
        dnisRegistrados = data.map(d => d.toLowerCase());
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
function mostrarAvisos(algunaVisible) {
    const aviso = document.getElementById("avisoHorario");
    const recordatorio = document.getElementById("avisoRecordatorio");

    if (mostrarFueraHorario) {
        if (aviso) aviso.style.display = "none";
        if (recordatorio) recordatorio.style.display = "block";
    } else {
        if (recordatorio) recordatorio.style.display = "none";
        if (aviso) aviso.style.display = algunaVisible ? "none" : "block";
    }
}

function cargarSolicitudes() {
    fetch('/api/ver-solicitudes')
        .then(res => res.json())
        .then(async data => {
            const cuerpo = document.getElementById("solicitudesBody");
            cuerpo.innerHTML = "";

            if (!data.archivos || data.archivos.length === 0) {
                cuerpo.innerHTML = `<tr><td colspan="4">No hay solicitudes pendientes.</td></tr>`;
                return;
            }

            // Obtener DNIs registrados primero
            const dnisRegistrados = await fetch('/api/pacientes/dnis')
                .then(res => res.json())
                .then(data => data.map(d => d.toLowerCase()));

            for (const archivo of data.archivos) {
                try {
                    const response = await fetch(`/webhook/solicitud/${archivo}`);
                    const solicitud = await response.json();

                    const fila = document.createElement("tr");
                    const visible = solicitud.visible_en_panel || false;
                    
                    // Mostrar según configuración
                    if (mostrarFueraHorario || visible) {
                        const dniDuplicado = dnisRegistrados.includes(solicitud.dni.toLowerCase());
                        
                        fila.innerHTML = `
                            <td>${dniDuplicado ? "⚠️ " : ""}${solicitud.nombre} ${solicitud.apellidos}</td>
                            <td>${solicitud.movil}</td>
                            <td>${solicitud.email}</td>
                            <td>
                                <button onclick='verDetalles(${JSON.stringify(solicitud)})'>Ver</button>
                                <button onclick="aprobarPaciente('${solicitud.dni}')">Aprobar</button>
                                <button onclick="rechazarPaciente('${solicitud.dni}')">Rechazar</button>
                            </td>
                        `;
                        
                        if (dniDuplicado) {
                            fila.classList.add("fila-duplicada");
                        }
                        
                        cuerpo.appendChild(fila);
                    }
                } catch (err) {
                    console.error("Error procesando solicitud:", err);
                }
            }
        });
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

function toggleFueraDeHorario() {
    mostrarFueraHorario = !mostrarFueraHorario;
    localStorage.setItem('mostrarFueraHorario', mostrarFueraHorario);

    const boton = document.querySelector("#avisoHorario button");
    const avisoHorario = document.getElementById("avisoHorario");
    const avisoManual = document.getElementById("avisoRecordatorio");

    if (mostrarFueraHorario) {
        boton.textContent = "Ocultar fuera de horario";
        avisoHorario.style.display = "none";
        avisoManual.style.display = "block";

        // ⚠️ Activar el intervalo de actualización si no está activo
        if (!intervaloSolicitudes) {
            cargarSolicitudes();
            intervaloSolicitudes = setInterval(cargarSolicitudes, 10000);
        }

    } else {
        boton.textContent = "Ver también fuera de horario";
        avisoManual.style.display = "none";

        // Solo mostrar aviso si realmente estamos fuera del horario
        const ahora = new Date();
        const hora = ahora.getHours();
        const dia = ahora.getDay();
        const fueraHorario = !(dia >= 1 && dia <= 5 && ((hora >= 10 && hora < 14) || (hora >= 16 && hora < 20)));
        if (fueraHorario) {
            avisoHorario.style.display = "block";
        }

        // Detener intervalo
        if (intervaloSolicitudes) {
            clearInterval(intervaloSolicitudes);
            intervaloSolicitudes = null;
        }
    }

    cargarSolicitudes();
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
