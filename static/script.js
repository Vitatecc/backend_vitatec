let intervaloSolicitudes = null;
let ultimasSolicitudesJSON = "";
let ultimaCancelacionMostrada = null;
let historialReagendados = new Set();

let dnisRegistrados = [];
function mostrarModoAutomatico() {
    const tabla = document.querySelector("#tablaSolicitudes thead");
    if (tabla) tabla.style.display = "table-header-group";
    
    const aviso = document.getElementById("avisoHorario");
    if (aviso) aviso.style.display = "none";
    
    const alerta = document.getElementById("alertaFueraHorario");
    if (alerta) alerta.style.display = "none";

    cargarSolicitudes();
    if (!intervaloSolicitudes) {
        intervaloSolicitudes = setInterval(cargarSolicitudes, 10000);
    }
    setInterval(cargarAuditoria, 10000);
}

function mostrarModoFueraHorario() {
    const aviso = document.getElementById("avisoHorario");
    if (aviso) aviso.style.display = "block";
    
    const cuerpo = document.getElementById("solicitudesBody");
    if (cuerpo) cuerpo.innerHTML = "";
    
    const tabla = document.querySelector("#tablaSolicitudes thead");
    if (tabla) tabla.style.display = "none";
    
    const alerta = document.getElementById("alertaFueraHorario");
    if (alerta) alerta.style.display = "none";
    
    clearInterval(intervaloSolicitudes);
    intervaloSolicitudes = null;
}


document.addEventListener("DOMContentLoaded", function () {
    const ahora = new Date();
    const hora = ahora.getHours();
    const dia = ahora.getDay(); // 0 = domingo, 6 = sábado

    const dentroHorario = (dia >= 1 && dia <= 5) && ((hora >= 10 && hora < 14) || (hora >= 16 && hora < 20));
    //const dentroHorario = false;  // ⚠️ SIMULACIÓN: Fuerza fuera de horario
    const modoManual = localStorage.getItem("modoFueraHorario") === "true";

    if (document.getElementById("logsContainer")) {
        cargarLogs();
    }

    if (document.getElementById("messagesContainer")) {
        cargarMensajes();
    }

    if (document.getElementById("auditList")) {
        fetch("/webhook/audit")
          .then(res => res.json())
          .then(data => {
            const contenedor = document.getElementById("auditList");
            contenedor.innerHTML = "";
    
            const lista = Array.isArray(data) ? data : (data.audit || []);
            const ultimos = lista.slice(-5).reverse();  // Últimas 5 entradas
    
            ultimos.forEach(item => {
              if (!item.accion || !item.usuario || !item.dni) return;
    
              const fecha = new Date(item.timestamp).toLocaleString("es-ES");
    
              let clase = "registro";
              if (item.accion === "Rechazada") {
                  clase += " registro-rechazado";
              } else if (item.accion === "Aprobada") {
                  clase += " registro-aprobado";
              } else if (item.accion === "Solicitud recibida") {
                  clase += " registro-pendiente";
              }
    
              const div = document.createElement("div");
              div.className = clase;
              div.innerHTML = `
                  <strong>${item.dni}</strong> – 
                  <span>${item.accion}</span> (${item.usuario})<br>
                  <small>${fecha}</small>
              `;
              contenedor.appendChild(div);
            });
          });
    }


    if (document.getElementById("myChart")) {
        cargarEstadisticas();
    }


    // 🔄 Modo actual al entrar
    if (dentroHorario || modoManual) {
        mostrarModoAutomatico(); // ya activa todo
        if (modoManual) {
            const alerta = document.getElementById("alertaFueraHorario");
            if (modoManual && alerta) {
                alerta.style.display = "block";
            }
        }
    } else {
        mostrarModoFueraHorario();  // muestra aviso y botón
    }

    document.querySelectorAll('input[name="tipoEstadistica"]').forEach(radio => {
        radio.addEventListener('change', cargarEstadisticas);
    });
    if (window.location.pathname.includes("cancelaciones")) {
        cargarCancelaciones();
        setInterval(cargarCancelaciones, 10000);
    }
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
function verReagendar(dni) {
    console.log("🔍 verReagendar invocado con DNI:", dni); 
    fetch(`/api/paciente/info/${dni}`)
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                alert("❌ No se pudo obtener los datos del paciente.");
                return;
            }

            const contenido = `
                <strong>Nombre:</strong> ${data.nombre}<br>
                <strong>Teléfono:</strong> ${data.telefono}<br>
                <strong>DNI:</strong> ${data.dni}
            `;
            document.getElementById("infoReagendar").innerHTML = contenido;
            document.getElementById("modalReagendar").style.display = "flex";
        })
        .catch(err => {
            console.error("Error al obtener datos:", err);
            alert("❌ Error al contactar con el servidor.");
        });
}

function cerrarModalReagendar() {
    document.getElementById("modalReagendar").style.display = "none";
}

function cargarSolicitudes() {
    fetch('/api/ver-solicitudes')
        .then(res => res.json())
        .then(async data => {
            const nuevoJSON = JSON.stringify(data.archivos || []);
            if (nuevoJSON === ultimasSolicitudesJSON) return;

            ultimasSolicitudesJSON = nuevoJSON;

            const cuerpo = document.getElementById("solicitudesBody");
            if (!cuerpo) return;
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

                    if (dniDuplicado) fila.classList.add("fila-duplicada");
                    cuerpo.appendChild(fila);

                    // 🧠 CREACIÓN AUTOMÁTICA SI AÚN NO SE HA PULSADO "MOSTRAR"
                    const modoManual = localStorage.getItem("modoFueraHorario") === "true";
                    if (!modoManual && !solicitud.procesado) {
                        getApiKey().then(apiKey => {
                            fetch(`/webhook/crear-paciente-automatico/${solicitud.dni}`, {
                                method: "POST",
                                headers: {
                                    "x-api-key": apiKey
                                }
                            })
                            .then(res => res.json())
                            .then(data => {
                                console.log("⏩ Auto-creación:", data.message || data.status);
                                cargarSolicitudes();  // Actualiza después de marcar como procesado
                            })
                            .catch(err => console.error("❌ Error creando automáticamente:", err));
                        });
                    }

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
    const tabla = document.querySelector("#tablaSolicitudes thead");
    if (tabla) tabla.style.display = "table-header-group";
    
    const aviso = document.getElementById("avisoHorario");
    if (aviso) aviso.style.display = "none";
    
    const alerta = document.getElementById("alertaFueraHorario");
    if (alerta) alerta.style.display = "block";


    ultimasSolicitudesJSON = "";  // 🔁 Fuerza recarga total

    cargarSolicitudes();

    if (!intervaloSolicitudes) {
        intervaloSolicitudes = setInterval(cargarSolicitudes, 10000);
    }

    localStorage.setItem("modoFueraHorario", "true");
}


function ocultarFueraHorario() {
    const alerta = document.getElementById("alertaFueraHorario");
    if (alerta) alerta.style.display = "none";

    // Simulamos "volver al modo automático" (detecta si estamos en horario)
    const ahora = new Date();
    const hora = ahora.getHours();
    const dia = ahora.getDay();
    const dentroHorario = (dia >= 1 && dia <= 5) && ((hora >= 10 && hora < 14) || (hora >= 16 && hora < 20));

    if (dentroHorario) {
        if (!intervaloSolicitudes) {
            cargarSolicitudes();
            intervaloSolicitudes = setInterval(cargarSolicitudes, 10000);
        }
        const aviso = document.getElementById("avisoHorario");
        if (dentroHorario && aviso) aviso.style.display = "none";
    } else {
        clearInterval(intervaloSolicitudes);
        intervaloSolicitudes = null;
        if (!dentroHorario) {
            const aviso = document.getElementById("avisoHorario");
            if (aviso) aviso.style.display = "block";
            const tabla = document.querySelector("#tablaSolicitudes thead");
            if (tabla) tabla.style.display = "none";
        
            const cuerpo = document.getElementById("solicitudesBody");
            if (cuerpo) cuerpo.innerHTML = "";
        }
    }

    // Eliminar el modo manual
    localStorage.removeItem("modoFueraHorario");
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
        .then(async res => {
            const contentType = res.headers.get("content-type");
            const texto = await res.text();

            if (!res.ok) {
                throw new Error(`Error HTTP ${res.status}: ${texto}`);
            }

            if (contentType && contentType.includes("application/json")) {
                return JSON.parse(texto);
            } else {
                throw new Error("Respuesta inesperada del servidor: " + texto);
            }
        })
        .then(data => {
            if (data.status === "success") {
                alert("✅ Paciente aprobado correctamente. El proceso continuará en tu sistema local mediante Make y Desktop Agent.");

                // No llamamos a /webhook/crear-paciente porque Make ya ejecuta el proceso en local
                cargarSolicitudes();
                cargarAuditoria();
                cargarLogs();
            } else {
                alert("Error: " + data.message);
            }
        })
        .catch(err => {
            alert("❌ Error al aprobar paciente: " + err.message);
            console.error(err);
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
        .then(response => {
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return response.json();
        })
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
            if (error.message.includes("HTTP 401") || error.message.includes("HTTP 302")) {
                alert("⚠️ Tu sesión ha expirado. Vuelve a iniciar sesión.");
                window.location.href = "/login";
            }
        });
}


function cargarAuditoria() {
    fetch("/webhook/audit")
        .then(res => res.json())
        .then(data => {
            const contenedor = document.getElementById("auditList");
            if (!contenedor) return;
            contenedor.innerHTML = "";

            const lista = Array.isArray(data) ? data : (data.audit || []);
            lista.forEach(item => {
                if (!item.accion || !item.usuario || !item.dni) return;

                const fecha = new Date(item.timestamp).toLocaleString("es-ES");

                let clase = "registro";
                if (item.accion === "Rechazada") {
                    clase += " registro-rechazado";
                } else if (item.accion === "Aprobada") {
                    clase += " registro-aprobado";
                } else if (item.accion === "Solicitud recibida") {
                    clase += " registro-pendiente";
                }

                const div = document.createElement("div");
                div.className = clase;
                div.innerHTML = `
                    <strong>${item.dni}</strong> – 
                    <span>${item.accion}</span> (${item.usuario})<br>
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

            const canvas = document.getElementById("myChart");
            if (!canvas) return;
            const ctx = canvas.getContext("2d");
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

function cargarCancelaciones() {
  fetch("/api/cancelaciones")
    .then(res => res.json())
    .then(data => {
      // 🔍 VERIFICACIÓN de que la respuesta es un array
      if (!Array.isArray(data)) {
        console.error("❌ Error al cargar cancelaciones:", data);
        return;
      }
      actualizarResumenCancelaciones(data);
      const tablaBody = document.querySelector("#tablaCancelaciones tbody");
      if (!tablaBody) return;

      tablaBody.innerHTML = "";

      // 🧠 Agrupar cancelaciones por DNI y ordenar por timestamp
      const cancelacionesPorDni = {};
      data.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

      data.forEach(c => {
        const dni = c.dni;

        if (!cancelacionesPorDni[dni]) {
          cancelacionesPorDni[dni] = [];
        }

        cancelacionesPorDni[dni].push(c);
      });

      // 🧾 Construcción de filas
      data.forEach(c => {
        const dni = c.dni;
        const timestamp = c.timestamp;
        const historial = cancelacionesPorDni[dni] || [];
        const index = historial.findIndex(item => item.timestamp === timestamp);
        const contador = index + 1;

        const fila = document.createElement("tr");

        if (contador >= 3) {
          fila.style.backgroundColor = "#f8d7da";
        }

        const reagendarTexto = (c.reagendar || "").trim().toLowerCase();
        if (reagendarTexto === "sí" || reagendarTexto === "si") {
          if (contador >= 3) {
              fila.style.animation = "parpadeo 1s infinite";
          } else {
              fila.style.backgroundColor = "#d4edda";  // verde claro
          }
        }

        fila.innerHTML = `
          <td>${dni}</td>
          <td>${c.motivo}</td>
          <td>${c.comentario}</td>
          <td>${c.mejora}</td>
          <td>${c.reagendar}</td>
          <td>${timestamp}</td>
          <td>${contador}</td>
        `;
        
        const celdaAcciones = document.createElement("td");
        
        const btnEliminar = document.createElement("button");
        btnEliminar.textContent = "Eliminar";
        btnEliminar.className = "btn-eliminar";
        btnEliminar.addEventListener("click", () => eliminarCancelacion(dni, timestamp));
        celdaAcciones.appendChild(btnEliminar);
        
        if (reagendarTexto === "sí" || reagendarTexto === "si") {
          const btnReagendar = document.createElement("button");
          btnReagendar.className = "btn-reagendar";
          btnReagendar.innerHTML = "📞 Reagendar";
          btnReagendar.addEventListener("click", () => verReagendar(dni));
          celdaAcciones.appendChild(btnReagendar);
        }
        
        fila.appendChild(celdaAcciones);


        tablaBody.appendChild(fila);
      });
    })
    .catch(err => {
      console.error("❌ Error al cargar cancelaciones:", err);
    });
}
function actualizarResumenCancelaciones(data) {
  const total = data.length;

  const pacientesCon3OMas = {};
  let totalReagendar = 0;

  data.forEach(c => {
    const dni = c.dni;
    pacientesCon3OMas[dni] = (pacientesCon3OMas[dni] || 0) + 1;

    const reagendar = (c.reagendar || "").toLowerCase().trim();
    if (reagendar === "sí" || reagendar === "si") {
      totalReagendar++;
    }
  });

  const con3OMas = Object.values(pacientesCon3OMas).filter(count => count >= 3).length;
  const porcentajeReagendar = total > 0 ? ((totalReagendar / total) * 100).toFixed(1) : "0";

  document.getElementById("resumenTotalCancelaciones").textContent = total;
  document.getElementById("resumenCon3OMas").textContent = con3OMas;
  document.getElementById("resumenPorcentajeReagendar").textContent = `${porcentajeReagendar}%`;
}

function eliminarCancelacion(dni, timestamp) {
  if (!confirm("¿Estás seguro de eliminar esta cancelación?")) return;

  fetch("/webhook/eliminar-cancelacion", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": "clave_vitatec_super_segura" // o tu variable segura
    },
    body: JSON.stringify({ dni, timestamp })
  })
  .then(res => res.json())
  .then(data => {
    if (data.status === "success") {
      console.log("✅ Cancelación eliminada");
      if (document.getElementById("tablaCancelaciones")) {
          cargarCancelaciones();
      }

      // 🔴 Eliminar alerta si existe
      const alerta = document.getElementById(`alerta-${timestamp}`);
      if (alerta) alerta.remove();
    } else {
      alert("❌ Error al eliminar: " + data.message);
    }
  })
  .catch(err => {
    console.error("❌ Error al eliminar:", err);
    alert("❌ Error de red al eliminar.");
  });
}


