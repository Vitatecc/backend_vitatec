import os
import sys
import time
import json
import logging
import pandas as pd
from datetime import datetime
from typing import Dict, Optional, Tuple, List

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv

# === CONFIGURACIÓN DE RUTAS RELATIVAS === #
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, "env", ".env"))

CONFIG = {
    'BASE_URL': "https://esiclinic.com/",
    'EXCEL_PATH': os.path.join(BASE_DIR, "data", "clientes", "pacientes.xlsx"),
    'SCREENSHOT_DIR': os.path.join(BASE_DIR, "data", "screenshots"),
    'WAIT_TIMEOUT': 15,
    'SHORT_WAIT': 5,
    'IMPLICIT_WAIT': 3,
    'HEADLESS': False
}

os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)
LOG_JSON_PATH = os.path.join(BASE_DIR, "logs.json")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "logs", "esi_clinic_automation.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def registrar_log_json(usuario, mensaje, tipo="info", detalles=""):
    nuevo = {
        "timestamp": datetime.now().isoformat(),
        "usuario": usuario,
        "message": mensaje,
        "type": tipo,
        "detalles": detalles
    }

    if not os.path.exists(LOG_JSON_PATH):
        with open(LOG_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump({"logs": [nuevo]}, f, indent=2)
    else:
        with open(LOG_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["logs"].insert(0, nuevo)
        with open(LOG_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

class EsiclinicManager:
    def __init__(self, headless=False):
        CONFIG['HEADLESS'] = headless
        self.driver = self._setup_driver()
        self.wait = WebDriverWait(self.driver, CONFIG['WAIT_TIMEOUT'])

    def _setup_driver(self):
        options = webdriver.ChromeOptions()
        if CONFIG['HEADLESS']:
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--start-maximized")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.implicitly_wait(CONFIG['IMPLICIT_WAIT'])
        return driver

    def close(self):
        if hasattr(self, 'driver'):
            self.driver.quit()

    def login(self) -> bool:
        try:
            self.driver.get(CONFIG['BASE_URL'])
            self.wait.until(EC.presence_of_element_located((By.ID, "esi_user"))).send_keys(os.getenv("USUARIO_ESICLINIC"))
            self.driver.find_element(By.ID, "esi_pass").send_keys(os.getenv("PASSWORD_ESICLINIC"))
            self.driver.find_element(By.ID, "bt_acceder").click()
            self.wait.until(EC.url_contains("agenda.php"))
            return True
        except Exception as e:
            logger.error(f"Login fallido: {e}")
            return False

    def _handle_modal(self):
        try:
            modal = WebDriverWait(self.driver, CONFIG['SHORT_WAIT']).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, ".jconfirm-scrollpane")))
            try:
                modal.find_element(By.CSS_SELECTOR, ".btn-confirm").click()
            except:
                try:
                    modal.find_element(By.CSS_SELECTOR, ".jconfirm-closeIcon").click()
                except:
                    ActionChains(self.driver).move_by_offset(20, 10).click().perform()
        except:
            pass

    def create_patient(self, data: Dict) -> bool:
        try:
            self.driver.get("https://app.esiclinic.com/pacientes.php?autoclose=1&load=")
            time.sleep(3)

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

            btn_guardar = self.wait.until(EC.element_to_be_clickable((By.ID, "guardarRegistro")))
            self.driver.execute_script("arguments[0].click();", btn_guardar)

            self._handle_modal()
            time.sleep(2)

            try:
                self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".alert-success, .success-message")))
                return True
            except:
                return True

        except Exception as e:
            logger.error(f"Error al crear paciente: {e}")
            return False

    def validate_patient_data(self, data: Dict) -> List[str]:
        errores = []
        for campo in ['nombre', 'apellidos', 'dni', 'movil', 'email']:
            if not data.get(campo):
                errores.append(f"El campo {campo} es obligatorio")
        if data.get('email') and '@' not in data['email']:
            errores.append("Email no válido")
        return errores

    def check_excel_duplicates(self, data: Dict) -> Tuple[bool, Optional[str]]:
        if not os.path.exists(CONFIG['EXCEL_PATH']):
            return True, None
        try:
            df = pd.read_excel(CONFIG['EXCEL_PATH'])
            if not {'CIF', 'E-Mail'}.issubset(df.columns):
                return True, None
            dni_repe = not df[df['CIF'].str.lower() == data['dni'].lower()].empty
            mail_repe = not df[df['E-Mail'].str.lower() == data['email'].lower()].empty
            if dni_repe:
                return False, "El DNI ya existe"
            if mail_repe:
                return True, "El correo ya existe"
            return True, None
        except Exception as e:
            logger.warning(f"Error al leer el Excel: {e}")
            return True, None

def main():
    if len(sys.argv) > 1:
        ruta = sys.argv[1]
        if not os.path.exists(ruta):
            print(f"Archivo JSON no encontrado: {ruta}")
            sys.exit(1)
        with open(ruta, "r", encoding="utf-8") as f:
            paciente = json.load(f)
    else:
        paciente = {
            'nombre': input("Nombre: ").strip(),
            'apellidos': input("Apellidos: ").strip(),
            'dni': input("DNI: ").strip(),
            'movil': input("Móvil: ").strip(),
            'email': input("Email: ").strip(),
            'fecha_nacimiento': input("Fecha nacimiento (dd-mm-yyyy): ").strip(),
        }

    auto = EsiclinicManager()
    try:
        errores = auto.validate_patient_data(paciente)
        if errores:
            print("Errores:")
            for e in errores:
                print("-", e)
            sys.exit(1)

        ok, msg = auto.check_excel_duplicates(paciente)
        if not ok:
            print(msg)
            sys.exit(1)
        elif msg and len(sys.argv) == 1:
            print(msg)
            if input("¿Deseas continuar? (s/n): ").lower() != 's':
                return

        if not auto.login():
            print("Login fallido.")
            sys.exit(1)

        if auto.create_patient(paciente):
            print("Paciente creado correctamente.")
            fecha_actual = datetime.now().strftime("%d/%m/%Y, %H:%M:%S")
            nombre = paciente['nombre']
            apellidos = paciente['apellidos']
            dni = paciente['dni']
            fecha_evento = datetime.now().strftime("%A %d de %B de %Y a las %H:%M")

            logger.info(f"{fecha_actual} - {dni} - Evento: Cita agendada para {nombre} {apellidos} {fecha_evento}")
            registrar_log_json(
                usuario=dni,
                mensaje=f"Evento: Cita agendada para {nombre} {apellidos} {fecha_evento}",
                tipo="info",
                detalles=f"{nombre} {apellidos} ({paciente['email']}) agendado el {fecha_evento}"
            )

        else:
            print("Error durante la creación del paciente.")
            sys.exit(1)

    finally:
        auto.close()

if __name__ == "__main__":
    main()
