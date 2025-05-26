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
from Crear_usuario import EsiclinicManager


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

@app.route('/webhook/crear-paciente-automatico/<dni>', methods=['POST'])
@require_api_key
def crear_paciente_automatico(dni):
    ruta_json = RUTA_SOLICITUDES / f"{dni.lower()}.json"

    if not ruta_json.exists():
        return jsonify({"status": "error", "message": "Archivo de solicitud no encontrado"}), 404

    try:
        # Leer datos actuales
        with open(ruta_json, "r", encoding="utf-8") as f:
            datos = json.load(f)

        if datos.get("procesado") is True:
            return jsonify({"status": "ok", "message": "Ya procesado anteriormente"})

        # Ejecutar el script
        result = subprocess.run(
            ["python", "Crear_usuario.py", str(ruta_json)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )

        # Marcar como procesado
        datos["procesado"] = True
        with open(ruta_json, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=2, ensure_ascii=False)

        return jsonify({
            "status": "success",
            "message": "Paciente creado automáticamente",
            "output": result.stdout
        })

    except subprocess.CalledProcessError as e:
        return jsonify({
            "status": "error",
            "message": "Error al crear paciente",
            "output": e.stderr
        }), 500
    except Exception as ex:
        return jsonify({"status": "error", "message": str(ex)}), 500


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
        
@app.route('/webhook/stats-google')
@login_required
def stats_google():
    modo = request.args.get("modo", "mes")
    resultado = obtener_estadisticas_google_sheets(modo)
    return jsonify(resultado)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
@app.route("/webhook/logs")
@login_required
def get_logs():
    try:
        with open(RUTA_LOGS, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"logs": [], "error": str(e)})

@app.route("/webhook/messages")
@login_required
def get_messages():
    try:
        with open(RUTA_MESSAGES, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"messages": [], "error": str(e)})

@app.route("/webhook/audit")
@login_required
def get_audit():
    try:
        with open(RUTA_AUDIT, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
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
