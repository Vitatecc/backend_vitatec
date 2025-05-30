"""

Proyecto VITATEC - Backend Automatizado para Gestión de Citas
--------------------------------------------------------------
- Desarrollado por: Samuel R. Barker ,Sergi Vique
- Tecnología: Python + Flask + Selenium + WhatsApp Web
- Funcionalidades:
    Webhooks protegidos por API Key
    Panel de administración en tiempo real
    Creación automática de pacientes en ESIClinic
    Notificación de eventos por WhatsApp
    Registro de logs, auditoría y estadísticas

Fecha: Mayo 2025
Versión: 1.0 - Demo TFG

"""
### IMPORTS BASICOS (SISTEMA) ###
 
import os           # SISTEMA
import sys          # SISTEMA
import json         # JSON
import time         # TIEMPO
from collections import defaultdict
import gspread
from google.oauth2.service_account import Credentials
import base64
from io import BytesIO
import requests
 
### IMPORTS DE LIBRERIAS ###
 
import numpy as np  # MATEMATICAS
import pandas as pd # DATAFRAMES
import subprocess   # SUBPROCESOS


### MANEJO DE ARCHIVOS/ENTORNO ###
 
from pathlib import Path       # RUTAS
from dotenv import load_dotenv # ENV

 
### FLASK (WEB) ###
 
from flask import Flask, request, jsonify, send_file, render_template  # API
from flask_cors import CORS                # Importar CORS
from functools import wraps                # API KEY
from flask_cors import cross_origin
from flask import session, redirect, url_for
from werkzeug.security import check_password_hash
 
### DATETIME (FECHAS) ###
 
from datetime import datetime, timedelta, time as dtime  # FECHAS
 
### MANEJO DE ERRORES ###
 
import locale

locale.setlocale(locale.LC_TIME, "C.UTF-8")

# 🔐 Configuración de sesión y funciones de login
# ——————————————————————————————
def cargar_usuarios():
    """Lee el fichero users.json con los usuarios autorizados."""
    if USERS_FILE.exists():
        return json.load(open(USERS_FILE, "r", encoding="utf-8"))
    return {}

def verificar_usuario(email, pwd):
    """Verifica usuario contra users.json usando hash."""
    usuarios = cargar_usuarios()
    hash_guardado = usuarios.get(email)
    if not hash_guardado:
        return False
    return check_password_hash(hash_guardado, pwd)
# ——————————————————————————————
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "clave_super_secreta_123")

CORS(app, resources={r"/webhook/*": {"origins": "*"}})
SECRET_TOKEN = os.getenv("SECRET_TOKEN")

# Directorios y archivos
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DOWNLOAD_DIR = DATA_DIR / "clientes"
USERS_FILE = DATA_DIR / "users.json"
RUTA_AUDIT = DATA_DIR / "audit.json"
RUTA_MESSAGES = DATA_DIR / "messages.json"
RUTA_LOGS = BASE_DIR / "logs.json"
RUTA_SOLICITUDES = DATA_DIR / "solicitudes"
BASE_URL = "https://esiclinic.com/"
API_KEY = os.getenv("ADMIN_API_KEY")

# Crear directorios si no existen
DATA_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR.mkdir(exist_ok=True)

# ==============================================
# API KEY 
# ==============================================

def require_api_key(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        key = request.headers.get('x-api-key')
        if not key or key != API_KEY:
            return jsonify({"status": "error", "message": "No autorizado"}), 401
        return func(*args, **kwargs)
    return wrapper

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function
    
@app.route("/api/pacientes/dnis")
@login_required
def obtener_dnis_pacientes():
    try:
        SCOPES = [
            'https://www.googleapis.com/auth/spreadsheets.readonly',
            'https://www.googleapis.com/auth/drive.readonly'
        ]
        cred_base64 = os.getenv("GOOGLE_CREDENTIALS_B64")
        cred_json = base64.b64decode(cred_base64)
        creds = Credentials.from_service_account_info(json.loads(cred_json), scopes=SCOPES)

        client = gspread.authorize(creds)
        sheet = client.open("pacientes.xlsx").sheet1
        datos = sheet.get_all_records()

        dnis = [fila["CIF"] for fila in datos if "CIF" in fila and fila["CIF"]]
        return jsonify(dnis)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==============================================
# CLASE PARA MANEJO DE ESICLINIC
# ==============================================
def dentro_horario_laboral():
    ahora = datetime.now()
    dia_semana = ahora.weekday()  # 0=lunes, 6=domingo
    hora_actual = ahora.time()

    return (
        0 <= dia_semana <= 4 and (
            dtime(10, 0) <= hora_actual <= dtime(14, 0) or
            dtime(16, 0) <= hora_actual <= dtime(20, 0)
        )
    )

@app.route('/api/ver-solicitudes', methods=['GET'])
@login_required
def ver_solicitudes():
    try:
        if not RUTA_SOLICITUDES.exists():
            return jsonify({"status": "ok", "archivos": []})
            
        archivos = [f.name for f in RUTA_SOLICITUDES.glob("*.json")]
        return jsonify({"status": "ok", "archivos": archivos})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
        
@app.route('/api/toggle-fuera-horario', methods=['POST'])
@login_required
def toggle_fuera_horario():
    data = request.get_json()
    mostrar = data.get('mostrar', False)

    try:
        with open(DATA_DIR / "fuera_horario.json", "w", encoding="utf-8") as f:
            json.dump({"mostrar": mostrar}, f)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success", "mostrar": mostrar})


# ==============================================
# WEBHOOKS MEJORADOS
# ==============================================
@app.route('/webhook/solicitud/<nombre_archivo>', methods=['GET'])
@login_required
def obtener_solicitud_individual(nombre_archivo):
    try:
        ruta = RUTA_SOLICITUDES / nombre_archivo
        if not ruta.exists():
            return jsonify({"status": "error", "message": "Archivo no encontrado"}), 404
        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)
        return jsonify(datos)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        usuario = request.form.get("usuario")
        password = request.form.get("password")
        if verificar_usuario(usuario, password):
            session["logged_in"] = True
            session["usuario"] = usuario
            return redirect(url_for("panel"))
        else:
            error = "Credenciales incorrectas"
    return render_template("login.html", error=error)
def obtener_estadisticas_google_sheets(modo="mes"):
    try:
        SCOPES = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        cred_base64 = os.getenv("GOOGLE_CREDENTIALS_B64")
        cred_json = base64.b64decode(cred_base64)
        creds = Credentials.from_service_account_info(json.loads(cred_json), scopes=SCOPES)

        client = gspread.authorize(creds)
        spreadsheet = client.open("pacientes.xlsx")
        sheet = spreadsheet.sheet1

        datos = sheet.get_all_records()
        fechas = []

        for fila in datos:
            fecha_str = str(fila.get("Fecha de alta") or "").strip()
            if fecha_str and fecha_str.lower() not in ["", "nan", "null", "none"]:
                try:
                    fecha = pd.to_datetime(fecha_str, errors='coerce', format='%Y-%m-%d')
                    if pd.notna(fecha):
                        fechas.append(fecha)
                except:
                    continue

        df = pd.DataFrame({"Fecha": fechas})
        if df.empty:
            return {"labels": [], "values": []}

        ahora = datetime.now()

        if modo == "mes":
            df = df[df['Fecha'].dt.year == ahora.year]
            df['MesOrden'] = df['Fecha'].dt.month
            conteo = df.groupby(['MesOrden', df['Fecha'].dt.strftime('%B')]).size()
            conteo = conteo.sort_index()
            labels = [nombre for (_, nombre) in conteo.index]
            values = conteo.values.tolist()
        else:
            df = df[(df['Fecha'].dt.year == ahora.year) & (df['Fecha'].dt.month == ahora.month)]
            df['FechaStr'] = df['Fecha'].dt.strftime('%Y-%m-%d')
            conteo = df.groupby('FechaStr').size()
            conteo = conteo.sort_index()
            labels = conteo.index.tolist()
            values = conteo.values.tolist()

        return {
            "labels": labels,
            "values": values
        }

    except Exception as e:
        return {"error": str(e)}
        
@app.route("/webhook/stats-google")
@login_required
def stats_google():
    try:
        modo = request.args.get("modo", "mes")
        datos = obtener_estadisticas_google_sheets(modo=modo)
        return jsonify(datos)
    except Exception as e:
        return jsonify({"labels": [], "values": [], "error": str(e)})



@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
@app.route("/webhook/logs")
@login_required
def get_logs():
    try:
        ruta_logs = os.path.join("data", "logs.json")
        if not os.path.exists(ruta_logs):
            return jsonify({"logs": []})  # devolver vacío sin error

        with open(ruta_logs, "r", encoding="utf-8") as f:
            datos = json.load(f)
        return jsonify({"logs": datos})
    except Exception as e:
        return jsonify({"logs": [], "error": str(e)})


@app.route("/webhook/messages")
@login_required
def get_messages():
    try:
        ruta = os.path.join("data", "messages.json")
        if not os.path.exists(ruta):
            return jsonify({"messages": []})  # Devolver vacío sin error

        with open(ruta, "r", encoding="utf-8") as f:
            mensajes = json.load(f)
        return jsonify({"messages": mensajes})
    except Exception as e:
        return jsonify({"error": str(e), "messages": []})


@app.route("/webhook/audit")
@login_required
def get_audit():
    try:
        ruta = os.path.join("data", "audit.json")
        if not os.path.exists(ruta):
            return jsonify({"audit": []})

        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)
        return jsonify({"audit": datos})
    except Exception as e:
        return jsonify({"audit": [], "error": str(e)})
    
@app.route("/webhook/solicitudes")
@login_required
def get_solicitudes():
    solicitudes = []

    if not RUTA_SOLICITUDES.exists():
        return jsonify(solicitudes)

    for archivo in RUTA_SOLICITUDES.glob("*.json"):
        try:
            with open(archivo, "r", encoding="utf-8") as f:
                data = json.load(f)
                solicitudes.append(data)
        except Exception:
            continue

    return jsonify(solicitudes)

@app.route("/")
@login_required
def panel():
    return render_template('panel.html')
def limpio(valor):
    return str(valor or "").strip()   
def panel_en_modo_manual_fuera_horario():
    try:
        with open(DATA_DIR / "fuera_horario.json", "r", encoding="utf-8") as f:
            estado = json.load(f)
            return estado.get("mostrar", False)
    except:
        return False  # por defecto NO está mostrando

@app.route("/formulario", methods=["GET", "POST"])
def formulario_alta():
    if request.method == "GET":
        mensaje = request.args.get("mensaje")
        mostrar_mensaje = mensaje == "ok"
        return render_template('formulario.html', datos={}, errores={}, mensaje=mostrar_mensaje), 200

    # POST → procesamiento de formulario
    datos = request.form.to_dict()
    modo_manual = datos.get("modo_manual") == "true"
    errores = {}

    campos_obligatorios = ['nombre', 'apellidos', 'dni', 'email', 'movil']
    for campo in campos_obligatorios:
        if not datos.get(campo):
            errores[campo] = f"{campo.capitalize()} obligatorio"

    if datos.get("email") and "@" not in datos["email"]:
        errores["email"] = "Email no válido"

    if errores:
        return render_template("formulario.html", datos=datos, errores=errores)
    # Comprobación de DNI duplicado en Google Sheets
    try:
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        cred_base64 = os.getenv("GOOGLE_CREDENTIALS_B64")
        cred_json = base64.b64decode(cred_base64)
        creds = Credentials.from_service_account_info(json.loads(cred_json), scopes=SCOPES)

        client = gspread.authorize(creds)
        sheet = client.open("pacientes.xlsx").sheet1
        datos_hoja = sheet.get_all_records()
        dnis_en_sheets = [fila.get("CIF", "").strip().lower() for fila in datos_hoja]

        if datos["dni"].strip().lower() in dnis_en_sheets:
            errores["dni"] = "Este DNI ya está registrado en el sistema."
            return render_template("formulario.html", datos=datos, errores=errores)
    except Exception as e:
        print(f"❌ Error al comprobar Google Sheets: {e}")

    ahora = datetime.now()
    dia_semana = ahora.weekday()
    hora_actual = ahora.time()
    #dentro_de_horario = False //PARA SIMULAR QUE ESTAMOS FUERA DE HORARIO LABORAL
    dentro_de_horario = (
        dia_semana < 5 and (
            dtime(10, 0) <= hora_actual <= dtime(14, 0) or
            dtime(16, 0) <= hora_actual <= dtime(20, 0)
        )
    )

    solicitudes_dir = os.path.join("data", "solicitudes")
    os.makedirs(solicitudes_dir, exist_ok=True)

    dni = datos["dni"].lower()
    archivo_solicitud = os.path.join(solicitudes_dir, f"{dni}.json")

    with open(archivo_solicitud, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)

    evento = {
        "dni": dni,
        "accion": "Solicitud recibida",
        "usuario": dni,
        "timestamp": ahora.isoformat()
    }

    try:
        with open(RUTA_AUDIT, "r", encoding="utf-8") as f:
            auditoria = json.load(f)
    except:
        auditoria = []

    auditoria.append(evento)
    with open(RUTA_AUDIT, "w", encoding="utf-8") as f:
        json.dump(auditoria, f, indent=2, ensure_ascii=False)

    # Enviar a backend local SOLO si estamos fuera de horario y no están mostrando manualmente
    if not dentro_de_horario and not modo_manual:
        try:
            response = requests.post("https://vitatecpersonal.loca.lt/crear", json=datos)
            if response.status_code == 200:
                print("✅ Enviado a backend local correctamente")
            else:
                print(f"⚠️ Error al enviar a backend local: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"❌ Excepción al conectar con backend local: {e}")

    return redirect(url_for("formulario_alta", mensaje="ok"))
@app.route("/cancelacion", methods=["GET", "POST"])
def formulario_cancelacion():
    ruta_cancelaciones = DATA_DIR / "cancelaciones.json"

    if request.method == "GET":
        mensaje = request.args.get("mensaje") == "ok"
        return render_template("cancelacion.html", mensaje=mensaje)

    # Recoger datos del formulario
    datos = request.form.to_dict()
    datos["timestamp"] = datetime.now().isoformat()
    datos["Ayuda reagendar"] = "Sí" if datos.get("ayuda_reagendar") else "No"

    # Guardar en JSON local (backup)
    try:
        with open(ruta_cancelaciones, "r", encoding="utf-8") as f:
            cancelaciones = json.load(f)
    except:
        cancelaciones = []

    cancelaciones.append(datos)
    with open(ruta_cancelaciones, "w", encoding="utf-8") as f:
        json.dump(cancelaciones, f, indent=2, ensure_ascii=False)

    # Guardar en Google Sheets
    try:
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        cred_base64 = os.getenv("GOOGLE_CREDENTIALS_B64")
        cred_json = base64.b64decode(cred_base64)
        creds = Credentials.from_service_account_info(json.loads(cred_json), scopes=SCOPES)

        client = gspread.authorize(creds)
        sheet = client.open("cancelaciones.xlsx").sheet1
        fila = [
            datos.get("dni", ""),
            datos.get("motivo", ""),
            datos.get("comentario", ""),
            datos.get("mejora", ""),
            datos.get("Ayuda reagendar", ""),
            datos["timestamp"]
        ]
        sheet.append_row(fila)
    except Exception as e:
        print(f"❌ Error al enviar a Google Sheets: {e}")

    # Auditoría
    evento = {
        "dni": datos["dni"],
        "accion": "Cancelación registrada",
        "usuario": datos["dni"],
        "timestamp": datos["timestamp"]
    }

    if datos["Ayuda reagendar"] == "Sí":
        evento_extra = {
            "dni": datos["dni"],
            "accion": "Solicitó ayuda para reagendar",
            "usuario": datos["dni"],
            "timestamp": datos["timestamp"]
        }

    try:
        with open(RUTA_AUDIT, "r", encoding="utf-8") as f:
            auditoria = json.load(f)
    except:
        auditoria = []

    auditoria.append(evento)
    if datos["Ayuda reagendar"] == "Sí":
        auditoria.append(evento_extra)

    with open(RUTA_AUDIT, "w", encoding="utf-8") as f:
        json.dump(auditoria, f, indent=2, ensure_ascii=False)

    return redirect(url_for("formulario_cancelacion", mensaje="ok"))

@app.route("/webhook/eliminar-cancelacion", methods=["POST"])
@login_required
def eliminar_cancelacion():
    datos = request.get_json()
    dni = datos.get("dni")
    timestamp = datos.get("timestamp")

    if not dni or not timestamp:
        return jsonify({"error": "Faltan datos"}), 400

    # === 1. ELIMINAR DEL JSON LOCAL ===
    ruta_cancelaciones = DATA_DIR / "cancelaciones.json"
    try:
        with open(ruta_cancelaciones, "r", encoding="utf-8") as f:
            cancelaciones = json.load(f)
        nuevas = [c for c in cancelaciones if not (c.get("dni") == dni and c.get("timestamp") == timestamp)]
        with open(ruta_cancelaciones, "w", encoding="utf-8") as f:
            json.dump(nuevas, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"❌ Error al eliminar del JSON local: {e}")

    # === 2. ELIMINAR DE GOOGLE SHEETS ===
    try:
        SCOPES = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        cred_base64 = os.getenv("GOOGLE_CREDENTIALS_B64")
        cred_json = base64.b64decode(cred_base64)
        creds = Credentials.from_service_account_info(json.loads(cred_json), scopes=SCOPES)

        client = gspread.authorize(creds)
        sheet = client.open("cancelaciones.xlsx").sheet1

        celda_dni = sheet.find(dni)
        if celda_dni:
            fila = celda_dni.row
            valores = sheet.row_values(fila)
            if timestamp in valores:
                sheet.delete_rows(fila)
    except Exception as e:
        print(f"❌ Error al eliminar en Google Sheets: {e}")

    # === 3. REGISTRAR EN AUDITORÍA ===
    usuario = session.get("usuario", "Desconocido")
    evento = {
        "dni": dni,
        "accion": "Cancelación eliminada",
        "usuario": "usuario",
        "timestamp": datetime.now().isoformat()
    }

    try:
        with open(RUTA_AUDIT, "r", encoding="utf-8") as f:
            auditoria = json.load(f)
    except:
        auditoria = []

    auditoria.append(evento)
    with open(RUTA_AUDIT, "w", encoding="utf-8") as f:
        json.dump(auditoria, f, indent=2, ensure_ascii=False)

    return jsonify({"status": "success", "message": "Cancelación eliminada correctamente"})



@app.route("/cancelaciones")
@login_required
def ver_cancelaciones():
    try:
        SCOPES = [
            'https://www.googleapis.com/auth/spreadsheets.readonly',
            'https://www.googleapis.com/auth/drive.readonly'
        ]
        cred_base64 = os.getenv("GOOGLE_CREDENTIALS_B64")
        cred_json = base64.b64decode(cred_base64)
        creds = Credentials.from_service_account_info(json.loads(cred_json), scopes=SCOPES)

        client = gspread.authorize(creds)
        sheet = client.open("cancelaciones.xlsx").sheet1
        filas = sheet.get_all_records()

        conteo_cancelaciones = {}
        total_reagendar = 0
        lista_final = []

        for fila in filas:
            dni = limpio(fila.get("DNI"))
            motivo = limpio(fila.get("Motivo"))
            comentario = limpio(fila.get("Comentario"))
            mejora = limpio(fila.get("Mejora"))
            reagendar_valor = str(fila.get("Ayuda reagendar", "")).strip().lower()
            timestamp = limpio(fila.get("Timestamp"))

            conteo_cancelaciones[dni] = conteo_cancelaciones.get(dni, 0) + 1
            reagendar_si = reagendar_valor in ["sí", "si", "yes"]

            if reagendar_si:
                total_reagendar += 1

            lista_final.append({
                "dni": dni,
                "motivo": motivo,
                "comentario": comentario,
                "mejora": mejora,
                "reagendar": "Sí" if reagendar_si else "No",
                "timestamp": timestamp,
                "cancelaciones": conteo_cancelaciones[dni]
            })

        total = len(lista_final)
        pacientes_mas_de_3 = sum(1 for v in conteo_cancelaciones.values() if v >= 3)
        porcentaje_reagendar = round((total_reagendar / total) * 100, 1) if total > 0 else 0

        return render_template(
            "cancelaciones.html",
            cancelaciones=lista_final,
            total_cancelaciones=total,
            pacientes_mas_de_3=pacientes_mas_de_3,
            porcentaje_reagendar=porcentaje_reagendar,
            API_KEY=os.getenv("ADMIN_API_KEY")
        )

    except Exception as e:
        return f"❌ Error al cargar cancelaciones: {e}", 500


        
@app.route("/api/cancelaciones/dni", methods=["GET"])
@login_required
def contar_cancelaciones_dni():
    dni = request.args.get("dni", "").strip()
    if not dni:
        return jsonify({"error": "DNI no proporcionado"}), 400

    try:
        SCOPES = [
            'https://www.googleapis.com/auth/spreadsheets.readonly',
            'https://www.googleapis.com/auth/drive.readonly'
        ]
        cred_base64 = os.getenv("GOOGLE_CREDENTIALS_B64")
        cred_json = base64.b64decode(cred_base64)
        creds = Credentials.from_service_account_info(json.loads(cred_json), scopes=SCOPES)

        client = gspread.authorize(creds)
        sheet = client.open("cancelaciones.xlsx").sheet1
        datos = sheet.get_all_records()

        total = sum(1 for fila in datos if fila.get("DNI", "").strip().lower() == dni.lower())
        return jsonify({"dni": dni, "cancelaciones": total})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
@app.route("/auditoria")
@login_required
def ver_auditoria():
    try:
        # Cargar datos auditoría
        if not RUTA_AUDIT.exists():
            with open(RUTA_AUDIT, "w", encoding="utf-8") as f:
                json.dump([], f)
        with open(RUTA_AUDIT, "r", encoding="utf-8") as f:
            registros = json.load(f)
        
        # O también puedes leer desde Sheets si ya lo tienes integrado
        return render_template("auditoria.html", auditoria=registros)
    except Exception as e:
        return f"Error al cargar auditoría: {e}", 500

    
@app.route('/api/cancelaciones/ultima-reagendar', methods=["GET"])
@login_required
def ultima_cancelacion_reagendar():
    try:
        SCOPES = [
            'https://www.googleapis.com/auth/spreadsheets.readonly',
            'https://www.googleapis.com/auth/drive.readonly'
        ]
        cred_base64 = os.getenv("GOOGLE_CREDENTIALS_B64")
        cred_json = base64.b64decode(cred_base64)
        creds = Credentials.from_service_account_info(json.loads(cred_json), scopes=SCOPES)

        client = gspread.authorize(creds)
        sheet = client.open("cancelaciones.xlsx").sheet1
        filas = sheet.get_all_records()

        # Filtrar por "Sí"
        con_reagendar = [fila for fila in filas if str(fila.get("Ayuda reagendar", "")).strip().lower() in ["sí", "si", "yes"]]
        if not con_reagendar:
            return jsonify({"status": "ok", "hay": False})

        # Tomar la última
        ultima = sorted(con_reagendar, key=lambda x: x.get("Timestamp", ""), reverse=True)[0]
        return jsonify({"status": "ok", "hay": True, "dni": ultima.get("DNI"), "timestamp": ultima.get("Timestamp")})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
@app.route("/api/cancelaciones", methods=["GET"])
def obtener_cancelaciones():
    try:
        # Conexión a Google Sheets
        scope = [     
            "https://www.googleapis.com/auth/spreadsheets",     
            "https://www.googleapis.com/auth/drive" 
        ]
        creds = Credentials.from_service_account_info(
            json.loads(base64.b64decode(os.getenv("GOOGLE_CREDENTIALS_B64")).decode("utf-8")),
            scopes=scope
        )
        client = gspread.authorize(creds)
        sheet = client.open("cancelaciones.xlsx").sheet1

        # Leemos los registros
        registros = sheet.get_all_records()
        dnis_cancelaciones = {}

        for r in registros:
            dni = r.get("DNI", "").strip().upper()
            if dni:
                dnis_cancelaciones[dni] = dnis_cancelaciones.get(dni, 0) + 1

        resultado = []
        for r in registros:
            dni = r.get("DNI", "").strip().upper()
            r["cancelaciones"] = dnis_cancelaciones.get(dni, 1)
            r["reagendar"] = r.get("Ayuda reagendar", "")
            resultado.append({
                "dni": r.get("DNI", ""),
                "motivo": r.get("Motivo", ""),
                "comentario": r.get("Comentario", ""),
                "mejora": r.get("Mejora", ""),
                "reagendar": r.get("Ayuda reagendar", ""),
                "timestamp": r.get("Timestamp", ""),
                "cancelaciones": dnis_cancelaciones.get(dni, 1)
            })

        return jsonify(resultado)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/webhook/aprobar/<dni>', methods=['POST'])
@require_api_key
def aprobar_solicitud(dni):
    try:
        archivo_individual = RUTA_SOLICITUDES / f"{dni.lower()}.json"
        if not archivo_individual.exists():
            return jsonify({"status": "error", "message": "Solicitud no encontrada"}), 404

        # Leer datos del paciente
        with open(archivo_individual, "r", encoding="utf-8") as f:
            aprobado = json.load(f)

        # Registrar evento en audit.json
        evento = {
            "dni": aprobado["dni"],
            "accion": "Aprobada",
            "usuario": session.get("usuario", "Sistema"),
            "timestamp": datetime.now().isoformat()
        }

        try:
            with open(RUTA_AUDIT, "r", encoding="utf-8") as f:
                auditoria = json.load(f)
        except:
            auditoria = []

        auditoria.append(evento)
        with open(RUTA_AUDIT, "w", encoding="utf-8") as f:
            json.dump(auditoria, f, indent=2, ensure_ascii=False)

        # Enviar a Make
        webhook_url = "https://hook.eu2.make.com/dct31mtpwqb5ibzfm2f29wvzciomqivv"  # tu webhook
        response = requests.post(webhook_url, json=aprobado)

        if response.status_code != 200:
            return jsonify({"status": "error", "message": f"Make respondió con {response.status_code}: {response.text}"}), 500

        # Eliminar la solicitud original SOLO si todo fue bien
        archivo_individual.unlink()

        return jsonify({"status": "success", "message": "Solicitud aprobada y enviada a Make"})

    except Exception as e:
        return jsonify({"status": "error", "message": f"Excepción interna: {str(e)}"}), 500


@app.route('/webhook/rechazar/<dni>', methods=["POST"])
@login_required
def rechazar_solicitud(dni):
    ruta = RUTA_SOLICITUDES / f"{dni.lower()}.json"
    if ruta.exists():
        os.remove(ruta)

        # 🛠 Registrar en audit.json directamente
        evento = {
            "dni": dni,
            "accion": "Rechazada",
            "usuario": session.get("usuario", "Sistema"),
            "timestamp": datetime.now().isoformat()
        }
        try:
            with open(RUTA_AUDIT, "r", encoding="utf-8") as f:
                auditoria = json.load(f)
        except:
            auditoria = []

        auditoria.append(evento)
        with open(RUTA_AUDIT, "w", encoding="utf-8") as f:
            json.dump(auditoria, f, indent=2, ensure_ascii=False)

        return jsonify({"status": "ok", "mensaje": "Solicitud rechazada"})
    return jsonify({"status": "error", "mensaje": "Solicitud no encontrada"}), 404
@app.route("/api/paciente/info/<dni>", methods=["GET"])
@login_required
def obtener_info_paciente(dni):
    try:
        SCOPES = [
            'https://www.googleapis.com/auth/spreadsheets.readonly',
            'https://www.googleapis.com/auth/drive.readonly'
        ]
        cred_base64 = os.getenv("GOOGLE_CREDENTIALS_B64")
        cred_json = base64.b64decode(cred_base64)
        creds = Credentials.from_service_account_info(json.loads(cred_json), scopes=SCOPES)

        client = gspread.authorize(creds)
        sheet = client.open("pacientes.xlsx").sheet1
        datos = sheet.get_all_records()

        print(f"🔍 Buscando paciente con DNI: {dni}")
        for fila in datos:
            print(f"➡️ Revisando fila: {fila.get('CIF', '')}")
            if str(fila.get("CIF", "")).strip().lower() == dni.lower():
                print("✅ Paciente encontrado")
                return jsonify({
                    "nombre": fila.get("Nombre", ""),
                    "telefono": fila.get("Telefono2", ""),
                    "dni": fila.get("CIF", "")
                })
        print("❌ Paciente no encontrado")
        return jsonify({"error": "Paciente no encontrado"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/webhook/solicitudes', methods=['GET'])
@require_api_key
def listar_solicitudes():
    solicitudes_file = os.path.join("data", "solicitudes.json")
    try:
        with open(solicitudes_file, "r", encoding="utf-8") as f:
            datos = json.load(f)
    except:
        datos = []
    return jsonify(datos)

@app.route('/webhook/messages', methods=['GET'])
@require_api_key
def obtener_mensajes():
    try:
        with open("messages.json", "r", encoding="utf-8") as f:
            mensajes = json.load(f)
    except:
        mensajes = {"messages": []}
    return jsonify(mensajes)

@app.route('/webhook/audit', methods=['GET'])
@require_api_key
def obtener_auditoria():
    try:
        with open("logs.json", "r", encoding="utf-8") as f:
            logs = json.load(f)
            auditoria = [l for l in logs.get("logs", []) if "Evento" in l.get("message", "")]
    except:
        auditoria = []
    return jsonify(auditoria)
    
@app.route('/webhook/get-api-key', methods=['GET', 'OPTIONS'])
@cross_origin(origins="http://localhost:5500")
def get_api_key():
    if request.method == 'OPTIONS':
        return '', 204  # Responde a preflight sin más

    token = request.headers.get('Authorization')
    if token != f"Bearer {SECRET_TOKEN}":
        return jsonify({"status": "error", "message": "Token no autorizado"}), 403

    return jsonify({"status": "success", "api_key": API_KEY}), 200

# ==============================================
# INICIO DE LA APLICACIoN
# ==============================================

if __name__ == '__main__':
    # Crear directorios necesarios
    (BASE_DIR / "errors").mkdir(exist_ok=True)
    
    # Iniciar servidor Flask
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
