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
 
### IMPORTS DE LIBRERIAS ###
 
import random       # ALEATORIO
import threading    # HILOS
import numpy as np  # MATEMATICAS
import pandas as pd # DATAFRAMES
import subprocess   # SUBPROCESOS
import urllib.parse # URLS


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
from flask import send_from_directory


### SELENIUM (AUTOMATIZACIoN) ###
 
from selenium import webdriver                        # NAVEGADOR
from selenium.webdriver.common.by import By           # SELECTORES
from selenium.webdriver.common.keys import Keys       # TECLADO
from selenium.webdriver.chrome.options import Options # CONFIG
from selenium.webdriver.chrome.service import Service # DRIVER

 
### DATETIME (FECHAS) ###
 
from datetime import datetime, timedelta, time as dtime  # FECHAS

 
### SELENIUM AVANZADO ###
 
from selenium.webdriver.support.ui import Select                  # DROPDOWNS
from selenium.webdriver.support.ui import WebDriverWait           # ESPERAS
from selenium.webdriver.common.action_chains import ActionChains  # INTERACCIONES
from webdriver_manager.chrome import ChromeDriverManager          # AUTOINSTALADOR
from selenium.webdriver.support import expected_conditions as EC  # CONDICIONES

 
### MANEJO DE ERRORES ###
 
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException  # EXCEPCIONES
import locale
from dateutil.parser import parse  # al inicio del script

locale.setlocale(locale.LC_TIME, "C.UTF-8")

#locale.setlocale(locale.LC_TIME, "es_ES.UTF-8")  # En Linux
#locale.setlocale(locale.LC_TIME, "Spanish_Spain")  # En Windows

def imprimir_banner():
    print("\n" + "=" * 65)
    print("     V I T A T E C   | C L Í N I C A   A U T O M A T I Z A D A")
    print("=" * 65)
    print(r"""
.------.
|J.--. |
| :(): |
| ()() |
| '--'J|
`------'""")
    print()
    print("Desarrollado por: Samuel R. Barker, Sergi G. Vique")
    print("📅 Versión: 1.5 | Mayo 2025")
    print("🌐 URL pública  : https://vitatecpersonal.loca.lt")
    print("🖥️  Consola Admin: http://localhost:8080/")
    print("=" * 65 + "\n")


# Configuracion inicial
load_dotenv("env/.env")

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
RUTA_STATS = DATA_DIR / "stats.json"
RUTA_MESSAGES = DATA_DIR / "messages.json"
RUTA_LOGS = BASE_DIR / "logs.json"
RUTA_SOLICITUDES = DATA_DIR / "solicitudes"
RUTA_EXCEL = DATA_DIR / "clientes" / "pacientes.xlsx"
CITAS_FILE = DATA_DIR / "citas.json"
PACIENTES_FILE = DATA_DIR / "clientes" / "pacientes.xlsx"
FICHERO_FESTIVOS = os.path.join("data", "festivos.json")
BASE_URL = "https://esiclinic.com/"
USER_DATA_DIR = os.path.join(os.getcwd(), "whatsapp_session")
API_KEY = os.getenv("API_KEY")

# Crear directorios si no existen
DATA_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR.mkdir(exist_ok=True)


DOBLE_AGENDA = {
    1: ['manana','tarde'],  # Martes: doble agenda por la mañana
    2: ['manana','tarde'],  # Miercoles: doble agenda por la tarde
    3: ['tarde'],   # Jueves: doble agenda por la tarde
    # Puedes añadir mas dias aqui
}

# Configuracion de horarios
INTERVALO_CITAS = 45  # Duracion de cada cita en minutos

HORARIOS = {
    0: {  # Lunes
        'manana': {'inicio': "10:15", 'fin': "14:00"},
        'tarde': {'inicio': "16:00", 'fin': "20:15"}    },
    1: {  # Martes
        'manana': {'inicio': "10:15", 'fin': "14:00"},
        'tarde': {'inicio': "16:00", 'fin': "20:15"}    },
    2: {  # Miercoles
        'manana': {'inicio': "10:15", 'fin': "14:00"},
        'tarde': {'inicio': "16:00", 'fin': "20:15"}    },
    3: {  # Jueves
        'manana': {'inicio': "10:15", 'fin': "14:00"},
        'tarde': {'inicio': "16:00", 'fin': "20:15"}    },
    4: {  # Viernes
        'manana': {'inicio': "10:15", 'fin': "14:00"},
        'tarde': {'inicio': "16:00", 'fin': "20:15"}
    }
}

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


def check_api_key():
    key = request.headers.get("x-api-key")
    return key == API_KEY

class ESIClinicAutomator:
    def __init__(self, headless=False):
        self.driver = None
        self.wait = None
        self.headless = headless
        self._setup_driver()

    def _setup_driver(self):
        options = webdriver.ChromeOptions()
        if self.headless:
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--start-maximized")
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        self.wait = WebDriverWait(self.driver, CONFIG['WAIT_TIMEOUT'])

    def close(self):
        if self.driver:
            self.driver.quit()

    def login(self):
        try:
            self.driver.get(BASE_URL)
            self.wait.until(EC.presence_of_element_located((By.ID, "esi_user"))).send_keys(os.getenv("USUARIO_ESICLINIC"))
            self.driver.find_element(By.ID, "esi_pass").send_keys(os.getenv("PASSWORD_ESICLINIC"))
            self.driver.find_element(By.ID, "bt_acceder").click()
            self.wait.until(EC.url_contains("agenda.php"))
            return True
        except Exception as e:
            print(f"❌ Error en login: {e}")
            return False

    def create_patient(self, data):
        try:
            self.driver.get("https://app.esiclinic.com/pacientes.php?action=new")
            time.sleep(3)
            campos = {
                'nombre': (By.ID, "Tnombre"),
                'apellidos': (By.ID, "Tapellidos"),
                'dni': (By.ID, "TCIF"),
                'movil': (By.ID, "Tmovil"),
                'email': (By.ID, "Temail"),
                'fecha_nacimiento': (By.ID, "Tfechadenacimiento")
            }
            for campo, selector in campos.items():
                valor = data.get(campo, "").strip()
                if valor:
                    el = self.wait.until(EC.presence_of_element_located(selector))
                    el.clear()
                    el.send_keys(valor)

            self.driver.find_element(By.ID, "guardarRegistro").click()
            time.sleep(2)
            return True
        except Exception as e:
            print(f"❌ Error creando paciente: {e}")
            return False

    def validate_patient_data(self, data):
        errores = []
        for campo in ['nombre', 'apellidos', 'dni', 'movil', 'email']:
            if not data.get(campo):
                errores.append(f"El campo {campo} es obligatorio")
        if data.get('email') and '@' not in data['email']:
            errores.append("Email no válido")
        return errores

    def check_excel_duplicates(self, data):
        if not PACIENTES_FILE.exists():
            return True, None
        try:
            df = pd.read_excel(PACIENTES_FILE)
            dni_repe = not df[df['CIF'].str.lower() == data['dni'].lower()].empty
            mail_repe = not df[df['E-Mail'].str.lower() == data['email'].lower()].empty
            if dni_repe:
                return False, "El DNI ya existe"
            if mail_repe:
                return True, "El correo ya existe"
            return True, None
        except Exception as e:
            print(f"⚠️ Error leyendo Excel: {e}")
            return True, None

# ==============================================
# CLASE PARA MANEJO DE ESICLINIC
# ==============================================
@app.route('/api/ver-solicitudes', methods=['GET'])
def ver_solicitudes():
    solicitudes_dir = os.path.join(BASE_DIR, 'data', 'solicitudes')
    if not os.path.exists(solicitudes_dir):
        return jsonify({"status": "error", "message": "No existe la carpeta 'solicitudes'"}), 404

    archivos = [f for f in os.listdir(solicitudes_dir) if f.endswith(".json")]
    return jsonify({"status": "ok", "archivos": archivos})
class EsiclinicManager:
    def __init__(self, headless=False):
        self.driver = None
        self.wait = None
        self.headless = headless
        self._inicializar_navegador()
    
    def _inicializar_navegador(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_experimental_option("prefs", {
            "download.default_directory": str(DOWNLOAD_DIR),
            "download.prompt_for_download": False,
        })
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        self.wait = WebDriverWait(self.driver, 20)
        
    def login(self, max_intentos=3):
        """Proceso de login con multiples intentos y verificacion de estado"""
        if not self.driver or not self.wait:
            print("❌ Error: Navegador no inicializado")
            return False
            
        for intento in range(1, max_intentos + 1):
            print(f"\n➡️ Intento {intento} de login en esiclinic.com...")
            
            try:
                                
                # Load login page with controlled timeout
                try:
                    self.driver.set_page_load_timeout(30)
                    self.driver.get("https://esiclinic.com/")
                except Exception as load_error:
                    print(f"⚠️ Timeout al cargar pagina: {str(load_error)}")
                    continue  # Skip to next attempt

                # Check if already logged in
                if "agenda.php" in self.driver.current_url:
                    print("✅ Sesion ya activa")
                    return True

                # Fill credentials
                try:
                    usuario = self.wait.until(
                        EC.presence_of_element_located((By.ID, "esi_user")))
                    usuario.clear()
                    usuario.send_keys(os.getenv("USUARIO_ESICLINIC"))

                    password = self.driver.find_element(By.ID, "esi_pass")
                    password.clear()
                    password.send_keys(os.getenv("PASSWORD_ESICLINIC"))

                    btn_login = self.wait.until(
                        EC.element_to_be_clickable((By.ID, "bt_acceder")))
                    btn_login.click()
                except NoSuchElementException as e:
                    print(f"❌ Elemento no encontrado: {str(e)}")
                    self.tomar_captura(f"error_login_elemento_intento_{intento}")
                    continue

                # Wait for login result
                try:
                    # Wait for successful login
                    self.wait.until(lambda d: "agenda.php" in d.current_url)
                    print("✅ Login exitoso")
                    return True
                    
                except TimeoutException:
                    # Check for error message
                    try:
                        error_elements = self.driver.find_elements(By.CSS_SELECTOR, ".alert.alert-danger")
                        if error_elements:
                            error_msg = error_elements[0].text
                            print(f"❌ Error de login: {error_msg}")
                            self.tomar_captura("error_login_visible")
                            continue
                    except:
                        pass
                    
                    print("⚠️ Timeout esperando redireccion")
                    self.tomar_captura("error_login_timeout")

            except Exception as e:
                print(f"❌ Error inesperado: {str(e)}")
                self.tomar_captura(f"error_login_generico_intento_{intento}")

            # Wait before retrying
            if intento < max_intentos:
                time.sleep(3)

        print(f"❌ Fallo el login despues de {max_intentos} intentos")
        return False
    
    def navegar_a_fecha(self, fecha_str):
        """Navega a la semana que contiene la fecha especificada"""
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
            if fecha.weekday() >= 5:  # Fin de semana
                print("⚠️ No se pueden agendar citas los fines de semana")
                return False

            meses_es = {
                'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
                'julio': 7, 'agosto': 8, 'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
            }
            
            max_intentos = 12
            intentos = 0
            
            while intentos < max_intentos:
                try:
                    rango_fechas = self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".fc-center h2"))
                    ).text.strip()
                    
                    # Procesar diferentes formatos de fecha
                    if " — " in rango_fechas:
                        inicio_str, fin_str = rango_fechas.split(" — ")
                        inicio_semana = self.parsear_fecha_es(inicio_str, meses_es)
                        fin_semana = self.parsear_fecha_es(fin_str, meses_es)
                    else:
                        inicio_semana = fin_semana = self.parsear_fecha_es(rango_fechas, meses_es)
                    
                    # Verificar si la fecha esta en este rango
                    if inicio_semana.date() <= fecha.date() <= fin_semana.date():
                        print(f"✅ Semana encontrada: {rango_fechas}")
                        return True
                    
                    # Navegar a la semana correcta
                    if fecha.date() > fin_semana.date():
                        btn_next = self.wait.until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, ".fc-next-button")))
                        btn_next.click()
                        print("⏭️ Avanzando a la proxima semana...")
                    else:
                        btn_prev = self.wait.until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, ".fc-prev-button")))
                        btn_prev.click()
                        print("⏮️ Retrocediendo a la semana anterior...")
                    
                    time.sleep(2)
                    intentos += 1
                    
                except Exception as e:
                    print(f"⚠️ Error al navegar: {str(e)}")
                    intentos += 1
                    continue
            
            print(f"❌ No se encontro la fecha despues de {max_intentos} intentos")
            return False
            
        except Exception as e:
            print(f"❌ Error critico al navegar: {str(e)}")
            self.tomar_captura("error_navegacion_fecha")
            return False

    def parsear_fecha_es(self, fecha_str, meses_es):
        """Convierte fechas en español a objeto datetime"""
        try:
            if "de" in fecha_str:
                partes = fecha_str.split()
                dia = int(partes[0])
                mes = meses_es[partes[2].lower()]
                ano = int(partes[4])
                return datetime(ano, mes, dia)
            else:
                return datetime.strptime(fecha_str, "%d/%m/%Y")
        except Exception as e:
            print(f"❌ Error parseando fecha '{fecha_str}': {str(e)}")
            raise

    def abrir_modal_cita(self, fecha_str):
        """Abre el modal de creacion de cita siempre a las 10:00"""
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
            dia_semana = fecha.weekday()
            horario = HORARIOS.get(dia_semana, HORARIOS[0])  # Horario segun el dia
            
            # Hora fija: siempre probar las 10:00
            slot_a_probar = "10:00"
            
            print(f"🔍 Buscando slot disponible para el {fecha_str} a las {slot_a_probar}...")
            
            # Buscar todas las celdas de hora
            celdas_hora = self.wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "td.fc-axis.fc-time.fc-widget-content")))
            
            # Probar solo el slot de las 10:00
            try:
                print(f"• Probando slot a las {slot_a_probar}...")
                
                # Encontrar la celda que contiene la hora objetivo
                slot_obj = None
                for celda in celdas_hora:
                    if celda.text.strip() == slot_a_probar:
                        slot_obj = celda
                        break
                
                if not slot_obj:
                    print(f"  ✖ Slot {slot_a_probar} no encontrado")
                    return False
                
                # Hacer clic en la celda adyacente
                celda_agenda = slot_obj.find_element(
                    By.XPATH, "./following-sibling::td[contains(@class, 'fc-widget-content')]")
                
                # Scroll suave y click preciso
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", 
                    celda_agenda)
                time.sleep(1)
                
                ActionChains(self.driver).move_to_element_with_offset(
                    celda_agenda, 10, 10).click().perform()
                
                print(f"  ✔ Click en slot {slot_a_probar} realizado")
                
                # Esperar el modal con timeout reducido
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.visibility_of_element_located((By.ID, "citaPaciente")))
                    print("✅ Modal de cita abierto correctamente")
                    return True
                except TimeoutException:
                    print("  ✖ Modal no aparecio despues del click")
                    return False
                
            except Exception as e:
                print(f"  ✖ Error probando slot {slot_a_probar}: {str(e)}")
                return False
            
        except Exception as e:
            print(f"❌ Error critico al abrir modal: {str(e)}")
            self.tomar_captura("error_abrir_modal_critico")
            return False

    def rellenar_modal_cita(self, paciente_data, hora, agenda_num=None):
        # Si no se pasa agenda_num, determinarla automaticamente
        agenda_num = agenda_num or CitaManager.determinar_agenda(hora)
        """Rellena el formulario de cita con la informacion proporcionada"""
        try:
            print("\n📝 Rellenando formulario de cita...")
            
            # 1. Autocompletado de paciente
            input_paciente = self.wait.until(
                EC.presence_of_element_located((By.ID, "citaPaciente")))
            
            # Limpiar y escribir el nombre con pausas naturales
            for _ in range(3):
                input_paciente.clear()
                time.sleep(0.2)
                
            for i, char in enumerate(paciente_data['nombre_completo']):
                input_paciente.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
            
            # Manejar sugerencias de autocompletado
            try:
                sugerencias = self.wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".autocomplete-list li")))
                
                for sugerencia in sugerencias:
                    if paciente_data['nombre_completo'].lower() in sugerencia.text.lower():
                        sugerencia.click()
                        print(f"✅ Autocompletado seleccionado: {sugerencia.text}")
                        break
                else:
                    if sugerencias:
                        sugerencias[0].click()
                        print(f"⚠️ Seleccionada primera sugerencia: {sugerencias[0].text}")
            except:
                print("ℹ️ No se encontraron sugerencias de autocompletado")
            
            # 2. Configurar hora de la cita
            if not self.configurar_hora_cita(hora):
                return False
                
            # 3. Seleccionar facultativo segun horario
            if not self.seleccionar_facultativo(paciente_data['fecha'], hora, agenda_num):
                print("⚠️ No se pudo seleccionar facultativo automaticamente")
                
            # 4. Seleccionar sala segun agenda
            if not self.seleccionar_sala(agenda_num):
                print("⚠️ Fallo al seleccionar sala, reintentando...")
                agenda_num = "1"  # Fallback a agenda principal
                self.seleccionar_sala(agenda_num)
                
            # 5. Rellenar motivo (opcional)
            try:
                motivo = self.driver.find_element(By.ID, "citaMotivo")
                motivo.send_keys(paciente_data.get('motivo', 'Consulta'))
            except:
                pass
            


            print("✅ Formulario completado correctamente")
            return True
            
        except Exception as e:
            print(f"❌ Error al rellenar formulario: {str(e)}")
            self.tomar_captura("error_rellenar_formulario")
            return False

    def configurar_hora_cita(self, hora_deseada):
        """Configura la hora en el timepicker del modal"""
        try:
            print(f"⏰ Configurando hora: {hora_deseada}")
            horas, minutos = map(int, hora_deseada.split(':'))
            minutos = (minutos // 5) * 5  # Redondear a multiplos de 5
            
            # Abrir timepicker
            reloj_icon = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".glyphicon-time")))
            ActionChains(self.driver).move_to_element(reloj_icon).pause(0.3).click().perform()
            time.sleep(0.5)
            
            # Localizar elementos del timepicker
            timepicker = self.wait.until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, ".bootstrap-timepicker-widget")))
            
            input_hora = timepicker.find_element(By.CSS_SELECTOR, "input.bootstrap-timepicker-hour")
            input_minuto = timepicker.find_element(By.CSS_SELECTOR, "input.bootstrap-timepicker-minute")
            
            # Ajustar hora
            hora_actual = int(input_hora.get_attribute("value"))
            diferencia = horas - hora_actual
            
            if diferencia != 0:
                flecha = timepicker.find_element(
                    By.CSS_SELECTOR, 
                    "[data-action='incrementHour']" if diferencia > 0 else "[data-action='decrementHour']"
                )
                for _ in range(abs(diferencia)):
                    flecha.click()
                    time.sleep(0.2)
            
            # Ajustar minutos
            minuto_actual = int(input_minuto.get_attribute("value"))
            dif_minutos = minutos - minuto_actual

            
            if dif_minutos != 0:
                if dif_minutos > 0:
                    flecha = timepicker.find_element(By.CSS_SELECTOR, "[data-action='incrementMinute']")
                else:
                    flecha = timepicker.find_element(By.CSS_SELECTOR, "[data-action='decrementMinute']")
                
                for _ in range(abs(dif_minutos) // 5):
                    flecha.click()
                    time.sleep(0.15)

            # Verificar resultado
            hora_final = f"{input_hora.get_attribute('value')}:{input_minuto.get_attribute('value')}"
            if hora_final == hora_deseada:
                print(f"✅ Hora establecida correctamente: {hora_final}")
                return True
            else:
                print(f"⚠️ Hora resultante: {hora_final} (esperado: {hora_deseada})")
                return False
                
        except Exception as e:
            print(f"❌ Error al configurar hora: {str(e)}")
            self.tomar_captura("error_timepicker")
            return False

    def seleccionar_facultativo(self, fecha_str, hora_str, agenda_num):
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
            dia_semana = fecha.weekday()
            hora = datetime.strptime(hora_str, "%H:%M").time()
            
            # Logica de seleccion basada en dia, hora y agenda
            if dia_semana == 0:  # Lunes
                facultativo = "Arnau Girones" if hora < datetime.strptime("14:00", "%H:%M").time() else "David Ibiza"
                if agenda_num == 2:
                    facultativo = "Jose Cabanes"
            elif dia_semana == 1:  # Martes
                # Asignar diferente facultativo segun agenda
                facultativo = "Arnau Girones" if agenda_num == "1" else "Jose Cabanes"
            elif dia_semana == 2:  # Miercoles
                facultativo = "David Ibiza" if datetime.strptime("10:00", "%H:%M").time() <= hora <= datetime.strptime("12:30", "%H:%M").time() else "Arnau Girones"
            elif dia_semana == 3:  # Jueves
                # Asignar diferente facultativo segun agenda
                facultativo = "Arnau Girones" if agenda_num == "1" else "Jose Cabanes"
            elif dia_semana == 4:  # Viernes
                facultativo = "Arnau Girones"
            else:
                return False
                    
            # Seleccionar en el dropdown
            select = Select(self.wait.until(
                EC.element_to_be_clickable((By.ID, "citaFacultativo"))))
                
            for opcion in select.options:
                if facultativo.lower() in opcion.text.lower():
                    opcion.click()
                    print(f"✅ Facultativo seleccionado: {opcion.text}")
                    return True
                    
            print(f"⚠️ No se encontro el facultativo {facultativo}")
            return False
            
        except Exception as e:
            print(f"⚠️ Error seleccionando facultativo: {str(e)}")
            return False

    def seleccionar_sala(self, agenda_num):
        """Selecciona la sala segun el numero de agenda"""
        try:
            select = Select(self.wait.until(
                EC.element_to_be_clickable((By.ID, "modalRoom"))))
                
            sala = "Box 2" if agenda_num == 2 else "Box 1"
            
            for opcion in select.options:
                if sala in opcion.text:
                    opcion.click()
                    print(f"✅ Sala seleccionada: {sala}")
                    return True
                    
            print(f"⚠️ No se encontro la sala {sala}")
            return False
            
        except Exception as e:
            print(f"⚠️ Error seleccionando sala: {str(e)}")
            return False

    def guardar_cita(self):
        """Guarda la cita en el sistema"""
        try:
            btn_guardar = self.wait.until(
                EC.element_to_be_clickable((By.ID, "guardarCita")))
            self.driver.execute_script("arguments[0].scrollIntoView();", btn_guardar)
            time.sleep(0.5)
            btn_guardar.click()
            
            # Esperar confirmacion
            self.wait.until(EC.invisibility_of_element_located((By.ID, "guardarCita")))
            print("✅ Cita guardada correctamente")
            return True
            
        except Exception as e:
            print(f"❌ Error al guardar cita: {str(e)}")
            self.tomar_captura("error_guardar_cita")
            return False

    def cancelar_cita(self, fecha_str, hora_str, dni=None):
        """Cancela una cita existente"""
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
            fecha_web = fecha.strftime("%d-%m-%Y")
            
            print(f"\n❌ Cancelando cita del {fecha_web} a las {hora_str}...")
            
            # Buscar paciente si hay DNI
            if dni:
                if not self.buscar_paciente_por_dni(dni):
                    print("⚠️ No se pudo encontrar al paciente")
                    return False
            
            # Configurar rango de fechas
            fecha_inicio = (fecha - timedelta(days=7)).strftime("%d-%m-%Y")
            fecha_fin = (fecha + timedelta(days=7)).strftime("%d-%m-%Y")
            
            self.configurar_rango_fechas_manual(fecha_inicio, fecha_fin)
            time.sleep(2)
            
            # Buscar cita en la tabla
            tabla = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.table")))
                
            filas = tabla.find_elements(By.XPATH, ".//tbody/tr[.//td]")
            if not filas:
                print("ℹ️ No hay citas en el rango especificado")
                return False
                
            # Buscar la cita especifica
            for fila in filas:
                celdas = fila.find_elements(By.TAG_NAME, "td")
                if len(celdas) < 3:
                    continue
                    
                if (celdas[0].text.strip() == fecha_web and 
                    celdas[1].text.strip() == hora_str):
                    
                    # Abrir modal de edicion
                    celdas[0].click()
                    time.sleep(2)
                    
                    # Click en Eliminar
                    btn_eliminar = self.wait.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn.btn-danger.lock.bt_eliminar")))
                    btn_eliminar.click()
                    time.sleep(1)
                    
                    # Confirmar eliminacion
                    btn_confirmar = self.wait.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "div.jconfirm-box button.btn-danger")))
                    btn_confirmar.click()
                    time.sleep(3)

                    
                    print("✅ Cita cancelada correctamente")
                    return True
                    
            print("⚠️ No se encontro la cita especificada")
            return False
            
        except Exception as e:
            print(f"❌ Error cancelando cita: {str(e)}")
            self.tomar_captura("error_cancelar_cita")
            return False

    def buscar_paciente_por_dni(self, dni):
        try:
            print(f"\n🔍 Buscando paciente con DNI: {dni}...")

            input_paciente = self.wait.until(
                EC.element_to_be_clickable((By.ID, "TpacienteWidget"))
            )

            # Limpiar input y escribir el DNI
            input_paciente.clear()
            for char in str(dni):
                input_paciente.send_keys(char)
                time.sleep(0.15)

            # Esperar a que se actualice el data-id
            print("⌛ Esperando que cargue paciente...")
            WebDriverWait(self.driver, 10).until(
                lambda d: d.find_element(By.ID, "TpacienteWidget").get_attribute("data-id") not in (None, "", "0")
            )

            print("✅ Paciente detectado en input.")

            # Clic en "Ver citas"
            btn_ver_citas = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.masCitas"))
            )
            btn_ver_citas.click()

            time.sleep(2)

            print("✅ Paciente encontrado y citas abiertas")
    
            # Clic en "Ver citas"
            btn_ver_citas = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.masCitas"))
            )
            btn_ver_citas.click()

            time.sleep(2)

            print("✅ Paciente encontrado")
            return True

        except Exception as e:
            print(f"❌ Error buscando paciente: {str(e)}")
            self.tomar_captura("error_buscar_paciente")
            return False

    def configurar_rango_fechas_manual(self, fecha_inicio, fecha_fin):
        """Configura un rango de fechas manualmente"""
        try:
            # Establecer fecha inicio
            input_fecha = self.wait.until(
                EC.presence_of_element_located((By.ID, "fecha")))
            input_fecha.clear()
            input_fecha.send_keys(fecha_inicio)
            input_fecha.send_keys(Keys.RETURN)
            time.sleep(1)
            
            # Establecer fecha fin
            input_fecha2 = self.wait.until(
                EC.presence_of_element_located((By.ID, "fecha2")))
            input_fecha2.clear()
            input_fecha2.send_keys(fecha_fin)
            input_fecha2.send_keys(Keys.RETURN)
            time.sleep(2)
            
            print(f"✅ Rango de fechas configurado: {fecha_inicio} - {fecha_fin}")
            return True
            
        except Exception as e:
            print(f"❌ Error configurando fechas: {str(e)}")
            self.tomar_captura("error_configurar_fechas")
            return False

    def tomar_captura(self, nombre):
        """Ahora incluye fecha legible en el nombre del archivo"""
        fecha_bonita = datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
        ruta = BASE_DIR / f"errors/{nombre}_{fecha_bonita}.png"
        ruta.parent.mkdir(exist_ok=True)
        self.driver.save_screenshot(str(ruta))
        print(f"📸 Captura guardada en: {ruta}")

    def cerrar(self):
        """Cierra el navegador"""
        if self.driver:
            self.driver.quit()
            print("🛑 Navegador cerrado")

    def cancelar_cita_desde_agenda(self, fecha_str, hora_str, titulo_cita=None):
        """Cancela una cita directamente desde la vista de agenda, opcionalmente filtrando por titulo"""
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
            print(f"\n🗓️ Buscando cita para cancelar: {fecha_str} a las {hora_str}...")

            citas = self.wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.fc-time-grid-event"))
            )

            for cita in citas:
                try:
                    div_hora = cita.find_element(By.CSS_SELECTOR, ".fc-time span")
                    hora_texto = div_hora.text.strip().split(' - ')[0]

                    div_titulo = cita.find_element(By.CSS_SELECTOR, ".fc-title")
                    titulo_texto = div_titulo.text.strip()

                    # Comparar hora (y opcionalmente titulo)
                    if hora_texto == hora_str and (not titulo_cita or titulo_cita.lower() in titulo_texto.lower()):
                        print(f"✅ Cita encontrada: {hora_texto} - {titulo_texto}")

                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cita)
                        ActionChains(self.driver).move_to_element(cita).pause(0.3).click().perform()
                        time.sleep(1)

                        btn_eliminar = self.wait.until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn.btn-danger.lock.bt_eliminar"))
                        )
                        btn_eliminar.click()
                        print("🗑️ Click en eliminar hecho.")

                        btn_confirmar = self.wait.until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "div.jconfirm-box button.btn-danger"))
                        )
                        btn_confirmar.click()
                        print("✅ Cita cancelada exitosamente.")
                        time.sleep(2)

                        return True

                except Exception as e:
                    print(f"⚠️ Error procesando cita individual: {str(e)}")
                    continue

            print("⚠️ No se encontro una cita que coincida con hora y titulo.")
            return False

        except Exception as e:
            print(f"❌ Error critico en cancelar_cita_desde_agenda: {str(e)}")
            self.tomar_captura("error_cancelar_desde_agenda")
            return False

    def crear_paciente(self, data):
        """Automatiza la creación de un nuevo paciente en ESIClinic"""
        try:
            self.driver.get("https://app.esiclinic.com/pacientes.php?autoclose=1&load=")
            time.sleep(3)

            # Intentar abrir el formulario
            try:
                btn = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button#bt_nuevo, #bt_nuevo, [title*="Añadir nuevo"]')))
                self.driver.execute_script("arguments[0].click();", btn)
                time.sleep(2)
            except:
                self.driver.get("https://app.esiclinic.com/pacientes.php?action=new")
                time.sleep(3)

            campos = {
                'nombre': (By.ID, "Tnombre"),
                'apellidos': (By.ID, "Tapellidos"),
                'dni': (By.ID, "TCIF"),
                'movil': (By.ID, "Tmovil"),
                'email': (By.ID, "Temail"),
                'fecha_nacimiento': (By.ID, "Tfechadenacimiento")
            }

            for campo, selector in campos.items():
                valor = data.get(campo, "").strip()
                if valor:
                    el = self.wait.until(EC.presence_of_element_located(selector))
                    el.clear()
                    el.send_keys(valor)

            # Guardar
            btn_guardar = self.wait.until(EC.element_to_be_clickable((By.ID, "guardarRegistro")))
            self.driver.execute_script("arguments[0].click();", btn_guardar)

            # Esperar confirmación
            time.sleep(2)
            try:
                self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".alert-success, .success-message")))
            except:
                pass  # A veces no hay mensaje visible, pero sí se crea

            return True
        except Exception as e:
            print(f"❌ Error al crear paciente: {e}")
            self.tomar_captura("error_crear_paciente")
            return False

# ==============================================
# MoDULO DE PACIENTES 
# ==============================================

class PacienteManager:
    @staticmethod
    def verificar_paciente(identificador):
        """Verifica si el paciente existe por DNI o email"""
        try:
            if not PACIENTES_FILE.exists():
                return {"existe": False, "error": "Archivo de pacientes no encontrado"}
            
            df = pd.read_excel(PACIENTES_FILE, engine='openpyxl')
            
            # Verificar columnas necesarias
            columnas_requeridas = ['CIF', 'E-Mail', 'Nombre', 'Apellidos']
            for col in columnas_requeridas:
                if col not in df.columns:
                    return {"existe": False, "error": f"Columna '{col}' no encontrada en el archivo"}
            
            # Normalizar datos
            df['CIF'] = df['CIF'].astype(str).str.strip()
            df['E-Mail'] = df['E-Mail'].astype(str).str.strip().str.lower()
            
            
            # Buscar por DNI o email
            pacientes = df[(df['CIF'] == identificador) | 
                          (df['E-Mail'] == identificador.lower())]
            
            if pacientes.empty:
                return {"existe": False, "error": "Paciente no encontrado"}
                
            # Manejar multiples coincidencias (mismo email)
            if len(pacientes) > 1:
                return {
                    "existe": True,
                    "multiples": True,
                    "pacientes": pacientes.to_dict('records')
                }
                
            # Un solo paciente encontrado
            paciente = pacientes.iloc[0]
            return {
                "existe": True,
                "multiples": False,
                "paciente": {
                    "nombre_completo": f"{paciente['Nombre']} {paciente['Apellidos']}",
                    "dni": paciente['CIF'],
                    "email": paciente['E-Mail'],
                    "telefono": int(np.int64(paciente.get('Telefono2', '')))
                }
            }
            
        except Exception as e:
            return {"existe": False, "error": str(e)}

# ==============================================
# MoDULO DE LOGS 
# ==============================================

class LogManager:
    
    @staticmethod
    def agregar_log(mensaje, tipo="info", usuario=None, detalles=None):
        log = {
            "timestamp": datetime.now().isoformat(),
            "message": mensaje,
            "type": tipo,
            "usuario": usuario if usuario else "Sistema",  # Si no hay usuario, se registra "Sistema"
            "detalles": detalles if detalles else ""
        }

        try:
            # Intenta cargar los logs del archivo
            with open('logs.json', 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except FileNotFoundError:
            # Si el archivo no existe, inicializamos con una lista vacía en 'logs'
            logs = {"logs": []}
        except json.JSONDecodeError:
            # Si el archivo no está bien formado, lo inicializamos con una lista vacía en 'logs'
            logs = {"logs": []}

        # Verifica si la clave 'logs' existe, si no, la inicializa
        if "logs" not in logs:
            logs["logs"] = []

        # Añade el nuevo log
        logs["logs"].append(log)

        # Guarda los logs de nuevo en el archivo
        with open('logs.json', 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=4, ensure_ascii=False)

    @staticmethod
    def agregar_mensaje(telefono, contenido, estado="enviado"):
        """
        Agregar un mensaje enviado al registro.
        
        - telefono: El número de teléfono del destinatario.
        - contenido: El contenido del mensaje.
        - estado: Puede ser 'enviado', 'fallido' o 'pendiente'.
        """
        
        mensaje = {
            "timestamp": datetime.now().isoformat(),
            "telefono": telefono,
            "contenido": contenido,
            "estado": estado
        }

        try:
            with open('messages.json', 'r', encoding='utf-8') as f:
                messages = json.load(f)
        except FileNotFoundError:
            messages = {"messages": []}

        messages["messages"].append(mensaje)

        with open('messages.json', 'w', encoding='utf-8') as f:
            json.dump(messages, f, indent=4, ensure_ascii=False)

    @staticmethod
    def agregar_evento_auditoria(evento, usuario=None):
        entrada = {
            "timestamp": datetime.now().isoformat(),
        }
    
        if isinstance(evento, dict):
            entrada.update(evento)
        else:
            # Caso antiguo, lo mantienes si quieres logs de texto genéricos
            entrada["message"] = f"{evento}"
            entrada["usuario"] = usuario or "Sistema"
    
        try:
            if RUTA_AUDIT.exists():
                with open(RUTA_AUDIT, "r", encoding="utf-8") as f:
                    auditoria = json.load(f)
            else:
                auditoria = []
    
            auditoria.append(entrada)
    
            with open(RUTA_AUDIT, "w", encoding="utf-8") as f:
                json.dump(auditoria, f, indent=4, ensure_ascii=False)
    
        except Exception as e:
            print(f"❌ Error al guardar auditoría: {e}")


# ==============================================
# MoDULO DE WHATSAPP 
# ==============================================

class WhatsAppManager:

    @staticmethod
    def initialize_whatsapp_session():
        """Inicia sesion en WhatsApp Web usando Selenium"""
        try:
            options = webdriver.ChromeOptions()
            
            # Configuracion del perfil de usuario
            options.add_argument(f"--user-data-dir={USER_DATA_DIR}")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            
            # No usar headless para poder escanear el QR
            # options.add_argument("--headless=new")  # Descomentar solo despues de la primera configuracion
            
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=options
            )
            
            driver.get("https://web.whatsapp.com")
            
            print("⌛ Por favor escanea el codigo QR de WhatsApp Web...")
            input("Presiona Enter despues de haber escaneado el codigo QR y WhatsApp este listo...")
            
            driver.quit()
            print("✅ Sesion de WhatsApp iniciada correctamente")
            return True
            
        except Exception as e:
            print(f"⚠️ Error iniciando sesion en WhatsApp: {str(e)}")
            return False


    @staticmethod
    def enviar_notificacion_whatsapp(telefono, cita):
        """Envia notificacion por WhatsApp usando sesion guardada"""
        try:
            fecha_bonita = CitaManager.formatear_fecha_bonita(cita['dia'], cita['hora_inicio'])

            mensaje = (
                f"✅ Confirmacion de Cita\n\n"
                f"📅 Fecha: {fecha_bonita}\n"  # Cambiado aqui
                f"👤 Paciente: {cita['paciente']}\n\n"
                f"Gracias por confiar en Vitatec."
)

            options = webdriver.ChromeOptions()
            options.add_argument(f"--user-data-dir={USER_DATA_DIR}")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            
            # Descomenta esto despues de la primera configuracion
            # options.add_argument("--headless=new")  

            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=options
            )

            url = f"https://web.whatsapp.com/send?phone={telefono}&text={urllib.parse.quote(mensaje)}"
            driver.get(url)

            print("⌛ Esperando que cargue WhatsApp Web...")
            
            # Espera hasta que el boton de enviar este disponible (maximo 30 segundos)
            try:
                wait = WebDriverWait(driver, 30)
                send_button = wait.until(EC.presence_of_element_located(
                    (By.XPATH, '//button[@aria-label="Enviar"]')
                ))
                
                # Hacer clic en el boton de enviar
                send_button.click()
                print("⌛ Mensaje enviado, esperando confirmacion...")
                time.sleep(5)  # Esperar a que se complete el envio
                LogManager.agregar_mensaje(telefono, mensaje, estado="enviado")
                print(f"✅ Mensaje enviado a {telefono}")
                
            except Exception as e:
                print(f"⚠️ No se pudo enviar el mensaje: {str(e)}")
                LogManager.agregar_log("Faltan datos requeridos para enviar mensaje.", tipo="error")
                # Tomar screenshot para diagnostico
                driver.save_screenshot('error_whatsapp.png')
                print("📸 Se guardo captura de pantalla: error_whatsapp.png")
                
            finally:
                driver.quit()

        except Exception as e:
            print(f"⚠️ Error enviando WhatsApp: {str(e)}")
            if 'driver' in locals():
                driver.quit()

# ==============================================
# MoDULO DE CITAS 
# ==============================================

class CitaManager:
    
    @staticmethod
    def cargar_citas():
        try:
            if not os.path.exists(CITAS_FILE) or os.path.getsize(CITAS_FILE) == 0:
                return []
            with open(CITAS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Error cargando citas: {e}")
            return []
        
    @staticmethod
    def guardar_citas(citas):
        """Guarda las citas en el archivo JSON"""
        try:
            with open(CITAS_FILE, 'w', encoding='utf-8') as f:
                json.dump(citas, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"❌ Error guardando citas: {str(e)}")
            return False
    
    @staticmethod
    def agregar_cita(nueva_cita):
        """Agrega una nueva cita al sistema"""
        citas = CitaManager.cargar_citas()
        
        # Verificar conflicto
        for cita in citas:
            if (cita['dia'] == nueva_cita['dia'] and
                cita['hora_inicio'] == nueva_cita['hora_inicio'] and
                cita['agenda'] == nueva_cita['agenda']):
                return {
                    "status": "error",
                    "message": "El horario ya esta ocupado",
                    "cita_existente": cita
                }
        
        citas.append(nueva_cita)
        if CitaManager.guardar_citas(citas):
            return {"status": "success", "cita": nueva_cita}
        return {"status": "error", "message": "No se pudo guardar la cita"}

    @staticmethod
    def cancelar_cita(fecha, hora, identificador=None):
        """Cancela una cita existente"""
        citas = CitaManager.cargar_citas()
        
        for i, cita in enumerate(citas):
            if (cita['dia'] == fecha and 
                cita['hora_inicio'] == hora and
                (identificador is None or cita.get('identificador') == identificador)):
                
                cita_cancelada = citas.pop(i)
                if CitaManager.guardar_citas(citas):
                    return {
                        "status": "success",
                        "cita_cancelada": cita_cancelada
                    }
                return {"status": "error", "message": "Error al guardar cambios"}
        
        return {"status": "error", "message": "Cita no encontrada"}

    @staticmethod
    def consultar_disponibilidad(fecha):
        try:
            fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")
            dia_semana = fecha_dt.weekday()

            if fecha in CitaManager.cargar_festivos():
                return jsonify({
                    "status": "no_disponible",
                    "message": f"La clínica estará cerrada el {fecha} por festivo o vacaciones."
                }), 206

            if dia_semana >= 5:
                return {
                    "status": "error",
                    "message": "No hay disponibilidad los fines de semana"
                }, 209

            slots = CitaManager.generar_slots_para_fecha(fecha)
            citas = CitaManager.cargar_citas()
            citas_dia = [c for c in citas if c.get('dia') == fecha]

            doble_turno = DOBLE_AGENDA.get(dia_semana, [])
            disponibilidad = {
                "agenda_1": [],
                "agenda_2": [],
                "doble_agenda": {
                    "manana": 'manana' in doble_turno,
                    "tarde": 'tarde' in doble_turno
                }
            }

            hora_actual = datetime.now().time()
            es_hoy = fecha_dt.date() == datetime.now().date()

            for slot in slots:
                # Si es hoy, ignorar slots pasados
                if es_hoy and datetime.strptime(slot, "%H:%M").time() <= hora_actual:
                    continue

                agenda = CitaManager.determinar_agenda(slot, fecha)
                ocupado = any(
                    c['hora_inicio'] == slot and c['agenda'] == agenda
                    for c in citas_dia
                )
                if not ocupado:
                    if agenda == "1":
                        disponibilidad["agenda_1"].append(slot)
                    elif agenda == "2":
                        disponibilidad["agenda_2"].append(slot)

            return jsonify({
                "status": "success",
                "dias": {
                    "disponibilidad": disponibilidad
                }
            }), 200

        except Exception as e:
            return jsonify({
                "status": "error",
                "message": f"Error interno: {str(e)}"
            }), 500

    @staticmethod
    def es_hora_valida(hora_str, fecha_str):
        try:
            fecha_dt = datetime.strptime(fecha_str, "%Y-%m-%d")
            hora_dt = datetime.strptime(hora_str, "%H:%M").time()
            dia_semana = fecha_dt.weekday()
            horarios = HORARIOS.get(dia_semana, HORARIOS[0])

            if dia_semana >= 5:
                print(f"Hora recibida: {hora_str}")
                print(f"Fecha recibida: {fecha_str}")
                print(f"Comparando contra horario:")
                print(f"  Mañana: {horarios['manana']}")
                print(f"  Tarde:  {horarios['tarde']}")
                print(f"  Hora valida mañana hasta: {(datetime.combine(fecha_dt, datetime.strptime(horarios['manana']['fin'], '%H:%M')) - timedelta(minutes=INTERVALO_CITAS)).time()}")
                print(f"  Hora valida tarde hasta:  {(datetime.combine(fecha_dt, datetime.strptime(horarios['tarde']['fin'], '%H:%M')) - timedelta(minutes=INTERVALO_CITAS)).time()}")
                print(f"Hora convertida: {hora_dt}")
                return False


            for periodo in ['manana', 'tarde']:
                inicio = datetime.strptime(horarios[periodo]['inicio'], "%H:%M").time()
                fin = datetime.strptime(horarios[periodo]['fin'], "%H:%M").time()
                fin_valido = (datetime.combine(fecha_dt, fin) - timedelta(minutes=INTERVALO_CITAS)).time()

                if inicio <= hora_dt <= fin_valido:
                    return True
            print(f"Hora recibida: {hora_str}")
            print(f"Fecha recibida: {fecha_str}")
            print(f"Comparando contra horario:")
            print(f"  Mañana: {horarios['manana']}")
            print(f"  Tarde:  {horarios['tarde']}")
            print(f"  Hora valida mañana hasta: {(datetime.combine(fecha_dt, datetime.strptime(horarios['manana']['fin'], '%H:%M')) - timedelta(minutes=INTERVALO_CITAS)).time()}")
            print(f"  Hora valida tarde hasta:  {(datetime.combine(fecha_dt, datetime.strptime(horarios['tarde']['fin'], '%H:%M')) - timedelta(minutes=INTERVALO_CITAS)).time()}")
            print(f"Hora convertida: {hora_dt}")
            return False
        except Exception as e:
            print(f"Error validando hora: {e}")
            return False

    @staticmethod
    def cargar_festivos():
        try:
            with open(FICHERO_FESTIVOS, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []
        except Exception as e:
            print(f"⚠️ Error cargando festivos: {e}")
            return []

    @staticmethod
    def generar_slots_para_fecha(fecha):
        fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")
        dia_semana = fecha_dt.weekday()

        if dia_semana >= 5:
            return []

        horarios = HORARIOS.get(dia_semana, HORARIOS[0])
        slots = []

        for periodo in ['manana', 'tarde']:
            inicio = datetime.strptime(horarios[periodo]['inicio'], "%H:%M")
            fin = datetime.strptime(horarios[periodo]['fin'], "%H:%M")
            current = inicio
            ultimo_slot_valido = fin - timedelta(minutes=INTERVALO_CITAS)

            while current <= ultimo_slot_valido:
                slots.append(current.strftime("%H:%M"))
                current += timedelta(minutes=INTERVALO_CITAS)

        return slots
    
    @staticmethod
    def formatear_fecha_bonita(fecha_str, hora_str=None):
        """
        Formatea fechas en español de manera consistente
        Ejemplos:
        - CitaManager.formatear_fecha_bonita("2023-12-25") → "Lunes 25 de diciembre de 2023"
        - CitaManager.formatear_fecha_bonita("2023-12-25", "10:00") → "Lunes 25 de diciembre de 2023 a las 10:00"
        """
        try:
            # Si la fecha no tiene formato adecuado, usar la fecha original
            if not fecha_str:
                return f"{fecha_str}" + (f" a las {hora_str}" if hora_str else "")
            
            # Intentar convertir la fecha con parse (esto se puede ajustar según el formato)
            fecha_dt = parse(fecha_str, fuzzy=True)  # fuzzy=True permite algunas variaciones en la fecha
            
            # Comprobamos si parse devolvió algo correcto
            if not fecha_dt:
                return f"{fecha_str}" + (f" a las {hora_str}" if hora_str else "")

            # Extraemos los elementos de la fecha
            dia_semana = fecha_dt.weekday()
            dia = fecha_dt.day
            mes = fecha_dt.month
            anio = fecha_dt.year

            # Mapeo manual para días de la semana y meses
            DIA_SEMANA = {
                0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves", 4: "viernes", 5: "sábado", 6: "domingo"
            }
            MES = {
                1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
                7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
            }

            # Construir la fecha en formato bonito
            fecha_bonita = f"{DIA_SEMANA[dia_semana]} {dia} de {MES[mes]} de {anio}"

            if hora_str:
                fecha_bonita += f" a las {hora_str}"

            return fecha_bonita.capitalize()

        except Exception as e:
            print(f"⚠️ Error al formatear fecha ({fecha_str}, {hora_str}): {str(e)}")
            return f"{fecha_str}" + (f" a las {hora_str}" if hora_str else "")

    @staticmethod
    def determinar_agenda(hora_inicio_str, fecha_str=None):
        """
        Determina a qué agenda pertenece una hora, sin aplicar lógica de prioridad.
        """
        hora = datetime.strptime(hora_inicio_str, "%H:%M").time()
        minutos = hora.hour * 60 + hora.minute

        AGENDA_1 = [
            range(615, 841, INTERVALO_CITAS),    # 10:15–14:00
            range(960, 1141, INTERVALO_CITAS)    # 16:00–19:00
        ]
        AGENDA_2 = [
            range(630, 826, INTERVALO_CITAS),    # 10:30–13:45
            range(975, 1141, INTERVALO_CITAS)  # 1141 incluye 1140 (19:00)
        ]

        if any(minutos in r for r in AGENDA_1):
            return "1"
        if any(minutos in r for r in AGENDA_2):
            return "2"

        return "1"  # Por defecto

    @staticmethod
    def obtener_alternativas(fecha):
        """Devuelve slots disponibles en ambas agendas"""
        return {
            "agenda_1": CitaManager.consultar_disponibilidad_por_agenda(fecha, "1"),
            "agenda_2": CitaManager.consultar_disponibilidad_por_agenda(fecha, "2")
        }

    @staticmethod
    def consultar_disponibilidad_por_agenda(fecha, agenda_num):
        """Devuelve slots REALMENTE disponibles para una agenda especifica"""
        # Primero genera todos los slots posibles para la fecha
        todos_slots = CitaManager.generar_slots_para_fecha(fecha)
        
        # Filtra solo los slots que pertenecen a esta agenda
        slots_agenda = [
            s for s in todos_slots 
            if CitaManager.determinar_agenda(s, fecha) == str(agenda_num)
        ]
        
        # Obtiene citas existentes para esta agenda
        citas_ocupadas = [
            c['hora_inicio'] for c in CitaManager.cargar_citas()
            if c['dia'] == fecha and c.get('agenda') == str(agenda_num)
        ]
        
        return [s for s in slots_agenda if s not in citas_ocupadas]
    
    @staticmethod
    def consultar_disponibilidad_real(fecha, hora_str=None):
        """Devuelve slots disponibles verificando ambas agendas"""
        slots = CitaManager.generar_slots_para_fecha(fecha)
        citas = CitaManager.cargar_citas()
        
        disponibles = []
        for slot in slots:
            # Verificar conflicto en CUALQUIER agenda
            conflicto = any(
                c['dia'] == fecha and 
                c['hora_inicio'] == slot 
                for c in citas
            )
            if not conflicto:
                disponibles.append(slot)
        
        return disponibles

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
            'https://www.googleapis.com/auth/drive
        ]
        cred_base64 = os.getenv("GOOGLE_CREDENTIALS_B64")
        cred_json = base64.b64decode(cred_base64)
        creds = Credentials.from_service_account_info(json.loads(cred_json), scopes=SCOPES)

        client = gspread.authorize(creds)
        spreadsheet = client.open("pacientes.xlsx")  # Asegúrate de que el nombre coincida
        sheet = spreadsheet.sheet1  # O usa .worksheet("Nombre") si no es la primera hoja

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

        if modo == "mes":
            conteo = df.groupby(df['Fecha'].dt.strftime('%B')).size()
        else:
            conteo = df.groupby(df['Fecha'].dt.strftime('%Y-%m-%d')).size()

        return {
            "labels": conteo.index.tolist(),
            "values": conteo.values.tolist()
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

@app.route('/webhook/stats')
@login_required
def get_stats():
    modo = request.args.get("modo", "mes")
    excel_path = "C:\\Users\\PC\\Documents\\VITATEC_AUTO\\proyecto_citas\\data\\clientes\\pacientes.xlsx"

    if not os.path.exists(excel_path):
        return jsonify({})

    try:
        df = pd.read_excel(excel_path)
        df['Fecha'] = pd.to_datetime(df['Fecha de alta'], errors='coerce')
        df = df.dropna(subset=['Fecha'])

        if modo == "mes":
            conteo = df.groupby(df['Fecha'].dt.strftime('%B')).size()
            return jsonify({
                "labels": conteo.index.tolist(),
                "values": conteo.values.tolist()
            })
        else:
            conteo = df.groupby(df['Fecha'].dt.strftime('%Y-%m-%d')).size().to_dict()
            return jsonify(conteo)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    
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


@app.route('/webhook/cita', methods=['POST'])
@require_api_key
def agendar_cita():
    print("\U0001F4E9 Recibida solicitud para agendar cita")

    if not request.is_json:
        return jsonify({"status": "error", "message": "Se esperaba JSON"}), 400

    try:
        data = request.get_json()
    except:
        return jsonify({"status": "error", "message": "JSON invalido"}), 400

    required = ['identificador', 'fecha', 'hora']
    if missing := [field for field in required if field not in data]:
        LogManager.agregar_log("Faltan datos requeridos para agendar la cita.", tipo="error")
        return jsonify({"status": "error", "message": f"Faltan campos: {', '.join(missing)}"}), 400

    paciente_result = PacienteManager.verificar_paciente(data['identificador'])
    if not paciente_result.get('existe'):
        return jsonify({"status": "no_encontrado", "message": "Paciente no encontrado"}), 207

    if paciente_result.get('multiples'):
        return jsonify({"status": "error", "message": "Multiples pacientes encontrados", "pacientes": paciente_result.get('pacientes', [])}), 409

    paciente_info = paciente_result['paciente']
    fecha = data['fecha']
    hora_str = data['hora']

    try:
        fecha_hora = datetime.strptime(f"{fecha} {hora_str}", "%Y-%m-%d %H:%M")
        hora = fecha_hora.time()

        if fecha in CitaManager.cargar_festivos():
            return jsonify({"status": "no_disponible", "message": f"No se pueden agendar citas el {fecha}, la clinica esta cerrada."}), 202

        if fecha_hora < datetime.now():
            return jsonify({"status": "error", "message": "No se permiten fechas pasadas"}), 400

        if not dtime(9, 0) <= hora <= dtime(20, 0):
            return jsonify({"status": "error", "message": "Horario fuera del rango laboral (09:00-20:00)"}), 400

        if not CitaManager.es_hora_valida(hora_str, fecha):
            return jsonify({"status": "error", "message": f"La hora {hora_str} esta fuera del horario de atencion"}), 400

    except ValueError as e:
        return jsonify({"status": "error", "message": "Formato de fecha/hora invalido", "detalle": str(e)}), 400

    respuesta_obj, codigo = CitaManager.consultar_disponibilidad(fecha)
    if codigo != 200:
        return respuesta_obj, codigo

    disponibilidad = respuesta_obj.get_json()
    disponibilidad_dia = disponibilidad.get("dias", {}).get(fecha, {})
    doble_agenda_dia = disponibilidad_dia.get("doble_agenda", {})

    turno = "manana" if hora < dtime(14, 0) else "tarde"
    doble_turno = doble_agenda_dia.get(turno, False)

    print(f"🕵️ Determinada agenda para {hora_str}: {CitaManager.determinar_agenda(hora_str, fecha)}")

    # Intenta meter la cita en agenda 1 primero
    disponibles_ag1 = CitaManager.consultar_disponibilidad_por_agenda(fecha, "1")
    disponibles_ag2 = CitaManager.consultar_disponibilidad_por_agenda(fecha, "2")

    agenda_original = "1"  # siempre intentamos empezar por la 1
    agenda_final = None

    # Primero intentamos en agenda 1
    if hora_str in CitaManager.consultar_disponibilidad_por_agenda(fecha, "1"):
        agenda_final = "1"
    # Si no está, y hay doble turno activo, intentamos agenda 2
    elif doble_turno and hora_str in CitaManager.consultar_disponibilidad_por_agenda(fecha, "2"):
        agenda_final = "2"
    else:
        return jsonify({
            "status": "error",
            "message": f"No hay disponibilidad para {hora_str}",
            "alternativas": CitaManager.obtener_alternativas(fecha)
        }), 209
    
    agenda_alternativa = "2" if agenda_original == "1" else "1"
    disponibles_ag1 = CitaManager.consultar_disponibilidad_por_agenda(fecha, "1")
    print(f"🧪 Verificando hora {hora_str} en disponibles agenda 1: {disponibles_ag1}")

    if not doble_turno:
        agenda_final = CitaManager.determinar_agenda(hora_str, fecha)
        disponibles = CitaManager.consultar_disponibilidad_por_agenda(fecha, agenda_final)
        
        if hora_str not in disponibles:
            return jsonify({
                "status": "error",
                "message": f"Agenda {agenda_final} llena. No hay doble turno disponible en este turno."
            }), 209


    else:
        disponibles_original = CitaManager.consultar_disponibilidad_por_agenda(fecha, agenda_original)
        disponibles_alternativa = CitaManager.consultar_disponibilidad_por_agenda(fecha, agenda_alternativa)

        if hora_str in disponibles_original:
            agenda_final = agenda_original
        elif hora_str in disponibles_alternativa:
            agenda_final = agenda_alternativa
        else:
            return jsonify({
                "status": "error",
                "message": f"El horario {hora_str} ya no esta disponible ni en agenda 1 ni 2",
                "alternativas": CitaManager.obtener_alternativas(fecha)
            }), 409
    print(f"🕵️ Determinada agenda para {hora_str}: {CitaManager.determinar_agenda(hora_str, fecha)}")

    hora_fin = fecha_hora + timedelta(minutes=INTERVALO_CITAS)
    cita = {
        "dia": fecha,
        "hora_inicio": hora_str,
        "hora_fin": hora_fin.strftime("%H:%M"),
        "paciente": paciente_info['nombre_completo'],
        "identificador": data['identificador'],
        "telefono": paciente_info.get('telefono', ''),
        "fecha_creacion": datetime.now().isoformat(),
        "agenda": agenda_final,
        "agenda_original": agenda_original
    }

    if not (resultado := CitaManager.agregar_cita(cita))['status'] == 'success':
        return jsonify(resultado), 409

    esiclinic = None
    max_reintentos = 3
    exito = False

    for intento in range(1, max_reintentos + 1):
        try:
            print(f"\n🔄 Intento {intento} de {max_reintentos}")
            esiclinic = EsiclinicManager(headless=True)
            if not esiclinic.login(): raise Exception("Error de login")
            if not esiclinic.navegar_a_fecha(fecha): raise Exception("Error de navegacion")
            if not esiclinic.abrir_modal_cita(fecha): raise Exception("Error al abrir modal")
            if not esiclinic.rellenar_modal_cita({
                'nombre_completo': paciente_info['nombre_completo'],
                'fecha': fecha,
                'motivo': data.get('motivo', 'Consulta')
            }, hora_str, agenda_final): raise Exception("Error en formulario")
            if not esiclinic.guardar_cita(): raise Exception("Error al guardar")
            exito = True
            break
        except Exception as e:
            print(f"❌ Error en intento {intento}: {str(e)}")
            if esiclinic:
                esiclinic.tomar_captura(f"error_intento_{intento}")
                esiclinic.cerrar()
            time.sleep(3)
        finally:
            if esiclinic and not exito:
                esiclinic.cerrar()

    if not exito:
        CitaManager.cancelar_cita(fecha, hora_str, data['identificador'])
        return jsonify({"status": "error", "message": "No se pudo crear la cita en ESICLINIC", "intentos": intento}), 500

    if paciente_info.get('telefono'):
        threading.Thread(target=WhatsAppManager.enviar_notificacion_whatsapp, args=(paciente_info['telefono'], cita)).start()

    fecha_bonita = CitaManager.formatear_fecha_bonita(fecha, hora_str)
    LogManager.agregar_evento_auditoria(f"Cita agendada para {paciente_info['nombre_completo']} {fecha_bonita}", usuario=data['identificador'])
    return jsonify({"status": "success", "message": f"Cita confirmada para el {fecha_bonita}.", "cita": cita}), 200

@app.route('/webhook/cancelacion', methods=['POST'])
@require_api_key
def cancelar_cita():
    if not check_api_key():
       return jsonify({"error": "No autorizado"}), 401
    
    if not request.is_json:
        return jsonify({"status": "error", "message": "El contenido debe ser JSON"}), 400

    data = request.get_json()

    required_fields = ['fecha', 'hora']
    missing = [field for field in required_fields if field not in data]
    if missing:
        LogManager.agregar_log("Faltan datos requeridos para cancelar la cita.", tipo="error")
        return jsonify({
            "status": "error",
            "message": f"Faltan campos requeridos: {', '.join(missing)}"
        }), 400

    fecha = data['fecha']
    hora = data['hora']
    identificador = data.get('identificador')

    # 1. Verificar que existe en JSON
    citas = CitaManager.cargar_citas()
    cita_obj = None
    for c in citas:
        if c['dia'] == fecha and c['hora_inicio'] == hora and (not identificador or c.get('identificador') == identificador):
            cita_obj = c
            break

    if not cita_obj:
        return jsonify({
            "status": "error",
            "message": "No se encontro la cita en el sistema local."
        }), 209

    # 2. Cancelar en ESICLINIC
    esiclinic = EsiclinicManager(headless=True)
    exito_esiclinic = False

    try:
        if esiclinic.login():
            if esiclinic.navegar_a_fecha(fecha):
                exito_esiclinic = esiclinic.cancelar_cita_desde_agenda(fecha, hora)
    except Exception as e:
        print(f"❌ Error durante cancelacion en esiclinic: {str(e)}")
    finally:
        esiclinic.cerrar()

    # 3. Cancelar en JSON
    resultado_json = CitaManager.cancelar_cita(fecha, hora, identificador)
    fecha_bonita = CitaManager.formatear_fecha_bonita(fecha, hora)
    if exito_esiclinic and resultado_json['status'] == 'success':
        LogManager.agregar_evento_auditoria(f"Cita cancelada para {data['identificador']} el {data['fecha']} a las {data['hora']}", usuario=data['identificador'])
        return jsonify({
            "status": "success",
            "message": f"Cita cancelada correctamente para el {fecha_bonita}",
            "cita_cancelada": resultado_json['cita_cancelada']
        }), 200
    
    elif exito_esiclinic:
        return jsonify({
            "status": "partial_success",
            "message": "Cita cancelada en ESICLINIC, pero no en sistema local",
        }), 207
    elif resultado_json['status'] == 'success':
        return jsonify({
            "status": "partial_success",
            "message": "Cita cancelada en sistema local, pero no en ESICLINIC",
        }), 207
    else:
        return jsonify({
            "status": "error",
            "message": "No se pudo cancelar la cita",
        }), 500

@require_api_key
@app.route('/webhook/disponibilidad', methods=['GET'])
def consultar_disponibilidad():
    if not check_api_key():
       return jsonify({"error": "No autorizado"}), 401
    fecha = request.args.get('fecha')
    if not fecha:
        return jsonify({
            "status": "error",
            "message": "El parametro 'fecha' es requerido (YYYY-MM-DD)"
        }), 400
    
    return CitaManager.consultar_disponibilidad(fecha)

@require_api_key
@app.route('/webhook/paciente', methods=['GET'])
def consultar_paciente():
    if not check_api_key():
       return jsonify({"error": "No autorizado"}), 401
    
    identificador = request.args.get('identificador')
    if not identificador:
        return jsonify({
            "status": "error",
            "message": "El parametro 'identificador' (DNI o email) es requerido"
        }), 400
    
    return jsonify(PacienteManager.verificar_paciente(identificador))

@app.route('/webhook/reagendar', methods=['POST'])
@require_api_key
def reagendar_cita():
    if not check_api_key():
        return jsonify({"error": "No autorizado"}), 401
    
    if not request.is_json:
        return jsonify({"status": "error", "message": "El contenido debe ser JSON"}), 400

    data = request.get_json()

    # Validar campos requeridos
    required_fields = ['fecha_original', 'hora_original', 'nueva_fecha', 'nueva_hora']
    missing = [field for field in required_fields if field not in data]
    if missing:
        return jsonify({
            "status": "error",
            "message": f"Faltan campos requeridos: {', '.join(missing)}"
        }), 400

    fecha_original = data['fecha_original']
    hora_original = data['hora_original']
    nueva_fecha = data['nueva_fecha']
    nueva_hora = data['nueva_hora']
    identificador = data.get('identificador')

    # 1. Verificar que la cita existe en el sistema local
    citas = CitaManager.cargar_citas()
    cita_obj = None
    for c in citas:
        if c['dia'] == fecha_original and c['hora_inicio'] == hora_original and (not identificador or c.get('identificador') == identificador):
            cita_obj = c
            break

    if not cita_obj:
        return jsonify({
            "status": "error",
            "message": "No se encontró la cita en el sistema local."
        }), 209

    # 2. Cancelar la cita en ESICLINIC
    esiclinic = EsiclinicManager(headless=True)
    exito_esiclinic = False

    try:
        if esiclinic.login():
            if esiclinic.navegar_a_fecha(fecha_original):
                exito_esiclinic = esiclinic.cancelar_cita_desde_agenda(fecha_original, hora_original)
    except Exception as e:
        print(f"❌ Error durante cancelación en ESICLINIC: {str(e)}")
    finally:
        esiclinic.cerrar()

    # 3. Cancelar la cita en el sistema local
    resultado_json = CitaManager.cancelar_cita(fecha_original, hora_original, identificador)
    fecha_bonita = CitaManager.formatear_fecha_bonita(fecha_original, hora_original)
    
    if exito_esiclinic and resultado_json['status'] == 'success':
        print(f"✅ Cita cancelada correctamente para el {fecha_bonita}")
    elif exito_esiclinic:
        print(f"⚠️ Cita cancelada en ESICLINIC, pero no en el sistema local.")
    elif resultado_json['status'] == 'success':
        print(f"⚠️ Cita cancelada en el sistema local, pero no en ESICLINIC.")

    # 4. Verificar disponibilidad para la nueva cita
    disponibilidad_nueva = CitaManager.consultar_disponibilidad_real(nueva_fecha, nueva_hora)
    if nueva_hora not in disponibilidad_nueva:
        return jsonify({
            "status": "error",
            "message": f"El horario {nueva_hora} no está disponible en la nueva fecha",
            "alternativas": disponibilidad_nueva
        }), 409

    # 5. Agendar la nueva cita en ESICLINIC usando Selenium
    esiclinic = EsiclinicManager(headless=True)
    try:
        if esiclinic.login():
            if esiclinic.navegar_a_fecha(nueva_fecha):
                if not esiclinic.abrir_modal_cita(nueva_fecha):
                    raise Exception("No se pudo abrir el modal para agendar la nueva cita.")
                if not esiclinic.rellenar_modal_cita({
                    'nombre_completo': cita_obj['paciente'],
                    'fecha': nueva_fecha,
                    'motivo': data.get('motivo', 'Consulta')
                }, nueva_hora):
                    raise Exception("No se pudo rellenar el formulario de la nueva cita.")
                if not esiclinic.guardar_cita():
                    raise Exception("No se pudo guardar la nueva cita en ESICLINIC.")
                print(f"✅ Nueva cita agendada correctamente para el {nueva_fecha} a las {nueva_hora}")
    except Exception as e:
        print(f"❌ Error durante el agendamiento en ESICLINIC: {str(e)}")
    finally:
        esiclinic.cerrar()

    # 6. Registrar la nueva cita en el sistema local
    fecha_hora = datetime.strptime(f"{nueva_fecha} {nueva_hora}", "%Y-%m-%d %H:%M")
    nueva_cita = {
        "dia": nueva_fecha,
        "hora_inicio": nueva_hora,
        "hora_fin": (fecha_hora + timedelta(minutes=INTERVALO_CITAS)).strftime("%H:%M"),
        "paciente": cita_obj['paciente'],
        "identificador": identificador,
        "telefono": cita_obj.get('telefono', ''),
        "fecha_creacion": datetime.now().isoformat(),
        "agenda": CitaManager.determinar_agenda(nueva_hora, nueva_fecha)
    }

    if not (resultado := CitaManager.agregar_cita(nueva_cita))['status'] == 'success':
        return jsonify(resultado), 409

    # Respuesta exitosa
    nueva_fecha_bonita = CitaManager.formatear_fecha_bonita(nueva_fecha, nueva_hora)
    return jsonify({
        "status": "success",
        "message": f"Cita reagendada correctamente para el {nueva_fecha_bonita}.",
        "nueva_cita": nueva_cita
    }), 200

@app.route('/webhook/crear_paciente', methods=['POST'])
@require_api_key
def webhook_crear_paciente():
    print("📥 Solicitud de creación de paciente recibida")

    if not request.is_json:
        return jsonify({"status": "error", "message": "Se esperaba JSON"}), 400

    data = request.get_json()
    campos_requeridos = ['nombre', 'apellidos', 'dni', 'email', 'movil']
    faltan = [campo for campo in campos_requeridos if not data.get(campo)]
    if faltan:
        return jsonify({"status": "error", "message": f"Faltan campos: {', '.join(faltan)}"}), 400

    # Comprobación de duplicados
    duplicado = PacienteManager.verificar_paciente(data['dni'])
    if duplicado['existe']:
        return jsonify({"status": "duplicado", "message": "El paciente ya existe"}), 409

    # Crear paciente en ESIClinic
    esiclinic = EsiclinicManager(headless=True)
    try:
        if not esiclinic.login():
            return jsonify({"status": "error", "message": "Login fallido en ESIClinic"}), 500
        if not esiclinic.crear_paciente(data):
            return jsonify({"status": "error", "message": "Error al crear paciente"}), 500
    finally:
        esiclinic.cerrar()

    # Registrar en logs
    nombre_completo = f"{data['nombre']} {data['apellidos']}"
    LogManager.agregar_evento_auditoria(f"Paciente creado: {nombre_completo}", usuario=data['dni'])

    return jsonify({"status": "success", "message": f"Paciente creado correctamente: {nombre_completo}"}), 200

@require_api_key
@app.route('/webhook/whatsapp-login', methods=['GET'])
def whatsapp_login():
    if not check_api_key():
       return jsonify({"error": "No autorizado"}), 401
    
    """Endpoint para iniciar sesion en WhatsApp"""
    success = WhatsAppManager.initialize_whatsapp_session()
    if success:
        return jsonify({"status": "success", "message": "WhatsApp session initialized successfully"})
    else:
        return jsonify({"status": "error", "message": "Failed to initialize WhatsApp session"}), 500

@app.route('/webhook/sincronizar', methods=['POST'])
@require_api_key
def sincronizar_citas():
    try:
        path_local = Path("data/citas.json")
        path_esiclinic = Path("data/citas_2_semanas.json")

        if not path_local.exists() or not path_esiclinic.exists():
            return jsonify({
                "status": "error",
                "message": "Uno o ambos archivos de citas no existen."
            }), 400

        with open(path_local, "r", encoding="utf-8") as f:
            citas_local = json.load(f)

        with open(path_esiclinic, "r", encoding="utf-8") as f:
            citas_esiclinic = json.load(f)

        def clave(c):
            return f"{c['dia']}|{c['hora_inicio']}"

        dict_local = {clave(c): c for c in citas_local}
        dict_esiclinic = {clave(c): c for c in citas_esiclinic}

        solo_en_esiclinic = [c for k, c in dict_esiclinic.items() if k not in dict_local]
        solo_en_local = [c for k, c in dict_local.items() if k not in dict_esiclinic]

        diferencias = []
        for k in dict_local.keys() & dict_esiclinic.keys():
            c1 = dict_local[k]
            c2 = dict_esiclinic[k]
            if c1['paciente'].strip().lower() != c2['paciente'].strip().lower():
                diferencias.append({
                    "clave": k,
                    "paciente_local": c1['paciente'],
                    "paciente_esiclinic": c2['paciente']
                })

        # Opción de actualizar el sistema local
        if request.args.get("actualizar") == "1":
            citas_local.extend(solo_en_esiclinic)
            with open(path_local, "w", encoding="utf-8") as f:
                json.dump(citas_local, f, indent=2, ensure_ascii=False)

        return jsonify({
            "status": "success",
            "solo_en_esiclinic": solo_en_esiclinic,
            "solo_en_local": solo_en_local,
            "diferencias": diferencias,
            "actualizado": bool(request.args.get("actualizar") == "1")
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Error interno durante la sincronización: {str(e)}"
        }), 500

@app.route("/")
@login_required
def panel():
    return render_template('panel.html')

@app.route('/formulario')
def formulario_alta():
    return render_template('formulario.html', datos={}, errores={})

@app.route('/api/solicitud-alta', methods=['POST'])
def solicitud_alta():
    datos = request.form.to_dict()
    errores = {}

    # Validación de campos obligatorios
    campos_obligatorios = ['nombre', 'apellidos', 'dni', 'email', 'movil']
    for campo in campos_obligatorios:
        if not datos.get(campo):
            errores[campo] = f"{campo.capitalize()} obligatorio"

    # Validación básica de email
    if datos.get("email") and "@" not in datos["email"]:
        errores["email"] = "Email no válido"

    # Leer los DNI ya existentes desde archivos individuales
    solicitudes_dir = os.path.join("data", "solicitudes")
    if os.path.exists(solicitudes_dir):
        if not os.path.isdir(solicitudes_dir):
            os.remove(solicitudes_dir)  # elimina el archivo para poder crear la carpeta
            os.makedirs(solicitudes_dir)
    else:
        os.makedirs(solicitudes_dir)

    dnis_existentes = [
        os.path.splitext(f)[0].lower()
        for f in os.listdir(solicitudes_dir) if f.endswith(".json")
    ]

    if datos.get("dni") and datos["dni"].lower() in dnis_existentes:
        errores["dni"] = "Ya hay una solicitud con ese DNI"

    # Si hay errores, re-renderiza con los datos y errores
    if errores:
        return render_template("formulario.html", datos=datos, errores=errores)

    # Guardar solicitud como archivo individual
    dni = datos["dni"].lower()
    archivo_solicitud = os.path.join(solicitudes_dir, f"{dni}.json")
    with open(archivo_solicitud, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)

    # Registro en auditoría
    evento = {
        "dni": dni,
        "accion": "Solicitud recibida",
        "usuario": dni,
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


    return render_template('formulario.html', datos={}, errores={}, mensaje="Solicitud recibida. Nos pondremos en contacto contigo.")
@app.route('/webhook/aprobar/<dni>', methods=['POST'])
@require_api_key
def aprobar_solicitud(dni):
    archivo_individual = RUTA_SOLICITUDES / f"{dni.lower()}.json"
    if not archivo_individual.exists():
        return jsonify({"status": "error", "message": "Solicitud no encontrada"}), 404

    # Leer los datos del paciente
    with open(archivo_individual, "r", encoding="utf-8") as f:
        aprobado = json.load(f)

    # Eliminar la solicitud original
    archivo_individual.unlink()

    # Añadir al Excel
    if os.path.exists(PACIENTES_FILE):
        df = pd.read_excel(PACIENTES_FILE)
    else:
        df = pd.DataFrame(columns=['CIF','Nombre','Apellidos','E-Mail','Telefono2','Fecha_nacimiento'])

    nuevo = {
        "CIF": aprobado['dni'],
        "Nombre": aprobado['nombre'],
        "Apellidos": aprobado['apellidos'],
        "E-Mail": aprobado['email'],
        "Telefono2": aprobado['movil'],
        "Fecha_nacimiento": aprobado.get('fecha_nacimiento', '')
    }
    df = pd.concat([df, pd.DataFrame([nuevo])], ignore_index=True)
    df.to_excel(PACIENTES_FILE, index=False)

    # Crear paciente en Esiclinic
    esiclinic = EsiclinicManager(headless=True)
    try:
        if esiclinic.login():
            esiclinic.crear_paciente(aprobado)
    finally:
        esiclinic.cerrar()

    # ✅ Registrar evento en audit.json
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

    return jsonify({"status": "success", "message": "Paciente aprobado y guardado"})


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


@app.route('/webhook/logs', methods=['GET'])
@require_api_key
def obtener_logs():
    try:
        with open("logs.json", "r", encoding="utf-8") as f:
            logs = json.load(f)
    except:
        logs = {"logs": []}
    return jsonify(logs)

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

@app.route('/webhook/stats', methods=['GET'])
@require_api_key
def obtener_estadisticas():
    modo = request.args.get("modo", "mes")
    citas = CitaManager.cargar_citas()
    if not citas:
        return jsonify({})

    agrupadas = defaultdict(int)

    for cita in citas:
        fecha = cita.get("dia")
        if not fecha:
            continue

        try:
            fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")
        except:
            continue

        clave = fecha_dt.strftime("%Y-%m") if modo == "mes" else fecha_dt.strftime("%Y-%m-%d")
        agrupadas[clave] += 1

    if modo == "mes":
        return jsonify({"labels": list(agrupadas.keys()), "values": list(agrupadas.values())})
    else:
        return jsonify(agrupadas)
    
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
    imprimir_banner()
    # Crear directorios necesarios
    (BASE_DIR / "errors").mkdir(exist_ok=True)
    
    # Iniciar servidor Flask
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
