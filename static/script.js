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
    const dia = ahora.getDay(); // 0=domingo, 1=lunes, ..., 6=sábado

    const dentroHorario = (dia >= 1 && dia <= 5) && ((hora >= 10 && hora < 14) || (hora >= 16 && hora < 20));

    if (!dentroHorario) {
        document.getElementById("avisoHorario").style.display = "block";
        // No activamos intervalo aquí
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

function cargarSolicitudes() {
    fetch('https://formulario-vitatec.onrender.com/api/ver-solicitudes')
        .then(res => res.json())
        .then(async data => {
            const cuerpo = document.getElementById("solicitudesBody");
            cuerpo.innerHTML = "";

            if (!data.archivos || !data.archivos.length) {
                const fila = document.createElement("tr");
                const celda = document.createElement("td");
                celda.colSpan = 4;
                celda.textContent = "No hay solicitudes pendientes.";
                fila.appendChild(celda);
                cuerpo.appendChild(fila);
                return;
            }

            let algunaVisible = false;

            for (const archivo of data.archivos) {
                try {
                    const response = await fetch(`/webhook/solicitud/${archivo}`);
                    const p = await response.json();

                    const fila = document.createElement("tr");

                    // Marcar si se debe mostrar en horario laboral
                    fila.setAttribute("data-visible", p.visible_en_panel ? "true" : "false");

                    // Si está fuera de horario y no se ha activado "ver también fuera de horario", ocultar
                    if (!p.visible_en_panel && !mostrarFueraHorario) {
                        fila.style.display = "none";
                    }

                    if (p.visible_en_panel) {
                        algunaVisible = true;
                    }

                    const dniDuplicado = dnisRegistrados.includes(p.dni.toLowerCase());

                    if (dniDuplicado) {
                        fila.classList.add("fila-duplicada");
                        fila.title = "⚠️ El DNI ya está registrado en pacientes.";
                    }

                    fila.innerHTML = `
                        <td>${dniDuplicado ? "⚠️ " : ""}${p.nombre} ${p.apellidos}</td>
                        <td>${p.movil}</td>
                        <td>${p.email}</td>
                        <td>
                            <button onclick='verDetalles(${JSON.stringify(p).replace(/"/g, "&quot;")})'>Ver</button>
                            <button onclick="aprobarPaciente('${p.dni}')">Aprobar</button>
                            <button onclick="rechazarPaciente('${p.dni}')">Rechazar</button>
                        </td>
                    `;
                    cuerpo.appendChild(fila);
                } catch (err) {
                    console.error("Error leyendo solicitud:", archivo, err);
                }
            }

            // Mostrar aviso solo si no hay solicitudes visibles
            const aviso = document.getElementById("avisoHorario");
            if (!algunaVisible && aviso) {
                aviso.style.display = "block";
            } else if (aviso) {
                aviso.style.display = "none";
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

    const filas = document.querySelectorAll("#solicitudesBody tr");
    filas.forEach(fila => {
        const visible = fila.getAttribute("data-visible") === "true";
        if (!visible) {
            fila.style.display = mostrarFueraHorario ? "table-row" : "none";
        }
    });

    const boton = document.querySelector("#avisoHorario button");
    const avisoManual = document.getElementById("avisoManual");

    if (mostrarFueraHorario) {
        // Activado el modo fuera de horario manual
        boton.textContent = "Ocultar fuera de horario";
        boton.style.backgroundColor = "#dc3545"; // rojo
        avisoManual.style.display = "block";
        document.getElementById("avisoHorario").style.display = "none";

        if (!intervaloSolicitudes) {
            cargarSolicitudes();
            intervaloSolicitudes = setInterval(cargarSolicitudes, 10000);
        }
    } else {
        // Modo automático restablecido
        boton.textContent = "Ver también fuera de horario";
        boton.style.backgroundColor = "#008CBA"; // azul
        avisoManual.style.display = "none";

        if (intervaloSolicitudes) {
            clearInterval(intervaloSolicitudes);
            intervaloSolicitudes = null;
        }

        document.getElementById("avisoHorario").style.display = "block";
        cargarSolicitudes();
    }
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
