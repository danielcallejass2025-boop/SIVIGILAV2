"""
config/settings.py
Gestor centralizado de configuración del sistema SIVIGILA
Carga variables desde .env y proporciona valores por defecto
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import logging

# ========================================
# Cargar variables de entorno desde .env
# ========================================
ENV_PATH = Path(__file__).parent.parent / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    # Si no existe .env, crear a partir de .env.example
    example_path = Path(__file__).parent.parent / ".env.example"
    if example_path.exists():
        logging.warning(f"Archivo .env no encontrado. Usando valores por defecto.")


class Settings:
    """
    Centraliza toda la configuración del sistema SIVIGILA.
    Los valores se cargan desde variables de entorno con fallback a defaults.
    """
    
    # ========================================
    # MODO DE OPERACIÓN Y DIRECTORIOS
    # ========================================
    
    # Modo: LOCAL, DRIVE o HIBRIDO
    APP_MODE = os.getenv("APP_MODE", "LOCAL")
    
    # Directorios locales
    BASE_DIR = Path(__file__).parent.parent
    INPUT_DIR = Path(os.getenv("INPUT_DIR", "data/ENTRADA_SIVIGILA"))
    OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "data/DEPURADO"))
    ERROR_DIR = Path(os.getenv("ERROR_DIR", "data/ERROR"))
    LOG_FILE = Path(os.getenv("LOG_FILE", "logs/sistema.log"))
    RESPALDO_DIR = Path(os.getenv("RESPALDO_DIR", "data/RESPALDOS"))
    
    # Convertir a rutas absolutas si no lo son
    if not INPUT_DIR.is_absolute():
        INPUT_DIR = BASE_DIR / INPUT_DIR
    if not OUTPUT_DIR.is_absolute():
        OUTPUT_DIR = BASE_DIR / OUTPUT_DIR
    if not ERROR_DIR.is_absolute():
        ERROR_DIR = BASE_DIR / ERROR_DIR
    if not LOG_FILE.is_absolute():
        LOG_FILE = BASE_DIR / LOG_FILE
    if not RESPALDO_DIR.is_absolute():
        RESPALDO_DIR = BASE_DIR / RESPALDO_DIR
    
    # Crear directorios si no existen
    for dir_path in [INPUT_DIR, OUTPUT_DIR, ERROR_DIR, LOG_FILE.parent, RESPALDO_DIR]:
        dir_path.mkdir(parents=True, exist_ok=True)
    
    # ========================================
    # CONFIGURACIÓN DE PROCESAMIENTO
    # ========================================
    
    FILTER_ONLY_RISARALDA = os.getenv("FILTER_ONLY_RISARALDA", "False").lower() == "true"
    DELETE_ORIGINAL_AFTER_PROCESS = os.getenv("DELETE_ORIGINAL_AFTER_PROCESS", "False").lower() == "true"
    SPLIT_MIXED_EVENTS = os.getenv("SPLIT_MIXED_EVENTS", "True").lower() == "true"
    PROCESS_ALL_SHEETS = os.getenv("PROCESS_ALL_SHEETS", "False").lower() == "true"
    OUTPUT_FORMAT = os.getenv("OUTPUT_FORMAT", "xlsx")  # xlsx, csv o ambos
    
    # ========================================
    # GOOGLE DRIVE
    # ========================================
    
    GOOGLE_DRIVE_CREDENTIALS_PATH = Path(os.getenv(
        "GOOGLE_DRIVE_CREDENTIALS_PATH",
        "credentials/client_secret.json"
    ))
    
    GOOGLE_DRIVE_TOKEN_PATH = Path(os.getenv(
        "GOOGLE_DRIVE_TOKEN_PATH",
        "credentials/token.json"
    ))
    
    # Convertir a rutas absolutas
    if not GOOGLE_DRIVE_CREDENTIALS_PATH.is_absolute():
        GOOGLE_DRIVE_CREDENTIALS_PATH = BASE_DIR / GOOGLE_DRIVE_CREDENTIALS_PATH
    if not GOOGLE_DRIVE_TOKEN_PATH.is_absolute():
        GOOGLE_DRIVE_TOKEN_PATH = BASE_DIR / GOOGLE_DRIVE_TOKEN_PATH
    
    GOOGLE_DRIVE_INPUT_FOLDER_ID = os.getenv("GOOGLE_DRIVE_INPUT_FOLDER_ID", "")
    GOOGLE_DRIVE_OUTPUT_FOLDER_ID = os.getenv("GOOGLE_DRIVE_OUTPUT_FOLDER_ID", "")
    GOOGLE_DRIVE_ERROR_FOLDER_ID = os.getenv("GOOGLE_DRIVE_ERROR_FOLDER_ID", "")

    # ========================================
    # APPS SCRIPT (HISTORICO INTERANUAL)
    # ========================================

    APPS_SCRIPT_DEPLOY_URL = os.getenv(
        "APPS_SCRIPT_DEPLOY_URL",
        "https://script.google.com/macros/s/AKfycbx6lFYxQtS0sUOIw3713SH5NSwatq-4vYf_eHiedqk3cJgQN_vgzd7rFa1Om-VqLGpd/exec"
    )
    APPS_SCRIPT_API_KEY = os.getenv("APPS_SCRIPT_API_KEY", "123456")
    APPS_SCRIPT_TIMEOUT_SECONDS = int(os.getenv("APPS_SCRIPT_TIMEOUT_SECONDS", "20"))
    
    # ========================================
    # FUNCIONALIDADES OPCIONALES
    # ========================================
    
    ENABLE_BOLETIN = os.getenv("ENABLE_BOLETIN", "False").lower() == "true"
    ENABLE_MAP = os.getenv("ENABLE_MAP", "True").lower() == "true"
    ENABLE_MONITOR = os.getenv("ENABLE_MONITOR", "False").lower() == "true"
    MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL", "30"))
    MONITOR_TIME_WINDOW = int(os.getenv("MONITOR_TIME_WINDOW", "3600"))  # Segundos (1 hora por defecto)
    MONITOR_USE_RECENT_ONLY = os.getenv("MONITOR_USE_RECENT_ONLY", "True").lower() == "true"  # Solo archivos recientes
    
    # ========================================
    # LOGGING
    # ========================================
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # ========================================
    # STREAMLIT
    # ========================================
    
    STREAMLIT_PORT = int(os.getenv("STREAMLIT_PORT", "8501"))
    STREAMLIT_THEME = os.getenv("STREAMLIT_THEME", "light")
    
    # ========================================
    # CONSTANTES DEL SISTEMA
    # ========================================
    
    # Municipios de Risaralda
    MUNICIPIOS_RISARALDA = [
        "PEREIRA",
        "DOSQUEBRADAS",
        "SANTA ROSA DE CABAL",
        "LA VIRGINIA",
        "CARTAGO",
        "QUIMBAYA",
        "FILANDIA",
        "APÍA",
        "GUÁTICA",
        "SANTUARIO",
        "BALBOA",
        "MISTRATO",
        "APIA",
        "PUEBLO RICO",
        "CRIADERO",
        "QUINCHIA"
    ]
    
    # Datos sensibles a eliminar o anonimizar
    DATOS_SENSIBLES = [
        "nombre",
        "primer_nombre",
        "segundo_nombre",
        "pri_nom",
        "seg_nom",
        "apellido",
        "primer_apellido",
        "segundo_apellido",
        "pri_ape",
        "seg_ape",
        "numero_documento",
        "num_ide",
        "identificacion",
        "documento",
        "cedula",
        "telefono",
        "celular",
        "telefonico",
        "email",
        "correo",
        "direccion",
        "domicilio",
        "lugar_residencia",
        "pasaporte",
        "carnet"
    ]
    
    # Columnas críticas (si están ausentes, puede fallar el procesamiento)
    COLUMNAS_CRITICAS = [
        "codigo_evento",
        "fecha_notificacion",
        "departamento",
        "municipio"
    ]
    
    # Tipos de datos por defecto para conversiones
    TIPO_DATO_NUMERICO = ["int", "int64", "float", "float64"]
    TIPO_DATO_DATETIME = ["datetime64[ns]", "object"]


def get_settings():
    """Retorna la instancia de configuración"""
    return Settings


# Para debugging: mostrar configuración actual
if __name__ == "__main__":
    settings = Settings()
    print("=== CONFIGURACIÓN ACTUAL DEL SISTEMA ===")
    print(f"Modo: {settings.APP_MODE}")
    print(f"Directorio entrada: {settings.INPUT_DIR}")
    print(f"Directorio salida: {settings.OUTPUT_DIR}")
    print(f"Directorio errores: {settings.ERROR_DIR}")
    print(f"Archivo log: {settings.LOG_FILE}")
    print(f"Filtrar solo Risaralda: {settings.FILTER_ONLY_RISARALDA}")
    print(f"Formato salida: {settings.OUTPUT_FORMAT}")
