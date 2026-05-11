"""
scripts/lector_drive.py
Módulo de integración con Google Drive
Descarga, carga y monitorea archivos en Google Drive.
Soporta tanto OAuth 2.0 de usuario como credenciales de service account.
"""

import os
import json
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from config.settings import Settings
from scripts.google_auth import load_google_credentials
from scripts.utils import Logger

# Importes condicionales de Google API
try:
    from google.auth.transport.requests import Request
    from google.oauth2.service_account import Credentials as ServiceCredentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials as UserCredentials
    from google_auth_httplib2 import AuthorizedHttp
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
    
    GOOGLE_API_DISPONIBLE = True
except ImportError:
    GOOGLE_API_DISPONIBLE = False


class LectorDrive:
    """
    Lector de Google Drive con soporte OAuth 2.0
    Descarga, carga y monitorea archivos epidemiológicos
    """
    
    # Scope necesario para acceso a Drive
    SCOPES = ['https://www.googleapis.com/auth/drive']
    
    def __init__(self):
        self.logger = Logger()
        self.settings = Settings()
        self.service = None
        self._credentials = None
        self._credential_mode = "desconocido"
        
        if not GOOGLE_API_DISPONIBLE:
            self.logger.warning("Google API no disponible. Instalar: pip install google-auth-oauthlib")
            return
        
        # Intentar autenticarse
        self._autenticar()
    
    def _autenticar(self) -> bool:
        """
        Autentica con Google Drive usando service account u OAuth 2.0.
        Si el archivo de credenciales es de tipo service_account, evita por completo
        el flujo interactivo y el manejo de token.json.
        
        Flujo:
        1. Intenta cargar token JSON (formato nuevo) o pickle (formato legacy)
        2. Si el token existe y tiene refresh_token, lo refresca proactivamente
        3. Si no hay token válido, inicia flujo OAuth con access_type=offline
        4. Guarda siempre en formato JSON para mejor compatibilidad
        
        Returns:
            True si la autenticación fue exitosa
        """
        try:
            # Verificar que el archivo de credenciales exista
            if not self.settings.GOOGLE_DRIVE_CREDENTIALS_PATH.exists():
                self.logger.error(
                    f"Archivo de credenciales no encontrado: "
                    f"{self.settings.GOOGLE_DRIVE_CREDENTIALS_PATH}"
                )
                return False

            credentials, credential_mode = load_google_credentials(
                credentials_path=self.settings.GOOGLE_DRIVE_CREDENTIALS_PATH,
                scopes=self.SCOPES,
                token_path=self.settings.GOOGLE_DRIVE_TOKEN_PATH,
                logger=self.logger,
            )
            
            # ---- 3. Construir servicio ----
            self.service = build('drive', 'v3', credentials=credentials)
            self._credentials = credentials  # Guardar referencia para refresco proactivo
            self._credential_mode = credential_mode
            if credential_mode == "service_account":
                self.logger.info("Autenticación con Google Drive exitosa usando service account")
            else:
                self.logger.info("Autenticación con Google Drive exitosa usando OAuth")
            
            return True
            
        except Exception as e:
            msg = str(e)
            self.logger.error(f"Error en autenticación con Google Drive: {msg}")
            if 'getaddrinfo failed' in msg or 'NameResolutionError' in msg:
                self.logger.error(
                    "Fallo de resolución DNS hacia Google. Verificar Internet, DNS o proxy corporativo."
                )
            return False

    def _cargar_service_account_credentials(self, credentials_path: Path) -> Optional['ServiceCredentials']:
        """
        Carga credenciales de service account si el JSON corresponde a ese tipo.
        Retorna None cuando el archivo es de OAuth de usuario para mantener compatibilidad.
        """
        try:
            with open(credentials_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except Exception as e:
            self.logger.warning(f"No se pudo inspeccionar archivo de credenciales: {e}")
            return None

        if str(payload.get('type') or '').strip().lower() != 'service_account':
            return None

        try:
            return ServiceCredentials.from_service_account_file(
                str(credentials_path),
                scopes=self.SCOPES,
            )
        except Exception as e:
            self.logger.error(f"Error cargando service account de Google Drive: {e}")
            return None

    def _cargar_token(self, token_path: Path) -> Optional['UserCredentials']:
        """
        Carga token desde JSON (formato nuevo) o pickle (formato legacy).
        Si encuentra pickle, lo migra automáticamente a JSON.
        """
        if not token_path.exists():
            return None
            
        try:
            # Intentar formato JSON primero
            with open(token_path, 'r', encoding='utf-8') as f:
                token_data = json.load(f)
            
            credentials = UserCredentials(
                token=token_data.get('token'),
                refresh_token=token_data.get('refresh_token'),
                token_uri=token_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
                client_id=token_data.get('client_id'),
                client_secret=token_data.get('client_secret'),
                scopes=token_data.get('scopes', self.SCOPES)
            )
            self.logger.info("Token cargado desde formato JSON")
            return credentials
            
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            pass
        
        try:
            # Fallback: formato pickle (legacy)
            with open(token_path, 'rb') as f:
                credentials = pickle.load(f)
            
            self.logger.info("Token cargado desde formato pickle (legacy)")
            
            # Migrar a JSON automáticamente
            if credentials and hasattr(credentials, 'refresh_token'):
                self._guardar_token_json(credentials, token_path)
                self.logger.info("Token migrado de pickle a JSON exitosamente")
            
            return credentials
            
        except Exception as e:
            self.logger.warning(f"No se pudo cargar token existente: {e}")
            return None

    def _guardar_token_json(self, credentials, token_path: Path):
        """
        Guarda las credenciales en formato JSON (más robusto que pickle).
        Incluye el refresh_token para renovación automática.
        """
        try:
            token_path.parent.mkdir(parents=True, exist_ok=True)
            
            token_data = {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': list(credentials.scopes) if credentials.scopes else self.SCOPES,
                'saved_at': datetime.now(timezone.utc).isoformat()
            }
            
            with open(token_path, 'w', encoding='utf-8') as f:
                json.dump(token_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Token guardado en formato JSON: {token_path}")
            
        except Exception as e:
            self.logger.error(f"Error guardando token: {e}")

    def _iniciar_flujo_oauth(self, token_path: Path) -> Optional['UserCredentials']:
        """
        Inicia flujo OAuth 2.0 completo asegurando obtener refresh_token.
        
        Claves:
        - access_type='offline' → Google entrega refresh_token
        - prompt='consent' → Fuerza pantalla de consentimiento para garantizar refresh_token
        """
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.settings.GOOGLE_DRIVE_CREDENTIALS_PATH),
                self.SCOPES
            )
            
            credentials = flow.run_local_server(
                port=0,
                access_type='offline',
                prompt='consent'
            )
            
            if not credentials.refresh_token:
                self.logger.warning(
                    "Google no entregó refresh_token. "
                    "Verificar que la app en Google Cloud Console NO esté en modo 'Testing'."
                )
            else:
                self.logger.info("Refresh token obtenido correctamente")
            
            # Guardar en formato JSON
            self._guardar_token_json(credentials, token_path)
            
            return credentials
            
        except Exception as e:
            self.logger.error(f"Error en flujo OAuth: {e}")
            return None

    def _refrescar_proactivo(self, credentials) -> 'UserCredentials':
        """
        Refresca el token proactivamente si le quedan menos de 5 minutos.
        Esto evita que expire durante una operación larga.
        """
        try:
            if (credentials.expiry and credentials.refresh_token and
                    credentials.expiry.replace(tzinfo=timezone.utc) - 
                    datetime.now(timezone.utc)).total_seconds() < 300:
                self.logger.info("Token próximo a expirar, refrescando proactivamente...")
                credentials.refresh(Request())
                self._guardar_token_json(credentials, self.settings.GOOGLE_DRIVE_TOKEN_PATH)
                self.logger.info("Token refrescado proactivamente")
        except Exception as e:
            self.logger.warning(f"Refresco proactivo falló (no crítico): {e}")
        
        return credentials

    def reconectar(self) -> bool:
        """Reintenta autenticación con Google Drive."""
        self.service = None
        self._credentials = None
        if not GOOGLE_API_DISPONIBLE:
            return False
        return self._autenticar()
    
    def verificar_salud_token(self) -> Dict[str, Any]:
        """
        Verifica el estado actual del token OAuth.
        Útil para diagnóstico.
        
        Returns:
            Dict con información del estado del token
        """
        info = {
            'conectado': self.esta_conectado(),
            'tiene_credentials': hasattr(self, '_credentials') and self._credentials is not None,
            'modo_credencial': getattr(self, '_credential_mode', 'desconocido'),
            'token_valido': False,
            'tiene_refresh_token': False,
            'expira_en_segundos': None,
            'necesita_reauth': False
        }
        
        if hasattr(self, '_credentials') and self._credentials:
            creds = self._credentials
            if info['modo_credencial'] == 'service_account':
                info['token_valido'] = info['conectado']
                info['necesita_reauth'] = not info['conectado']
                return info

            info['token_valido'] = getattr(creds, 'valid', False)
            info['tiene_refresh_token'] = getattr(creds, 'refresh_token', None) is not None
            
            if getattr(creds, 'expiry', None):
                try:
                    expiry_utc = creds.expiry.replace(tzinfo=timezone.utc)
                    delta = (expiry_utc - datetime.now(timezone.utc)).total_seconds()
                    info['expira_en_segundos'] = round(delta)
                except Exception:
                    pass
            
            info['necesita_reauth'] = not getattr(creds, 'valid', False) and not getattr(creds, 'refresh_token', None)
        
        return info

    def forzar_nueva_autorizacion(self) -> bool:
        """
        Elimina el token actual y fuerza una nueva autorización OAuth.
        Usar cuando el refresh_token ya no funciona.
        
        Returns:
            True si la re-autorización fue exitosa
        """
        if getattr(self, '_credential_mode', '') == 'service_account':
            self.service = None
            self._credentials = None
            return self._autenticar()

        token_path = self.settings.GOOGLE_DRIVE_TOKEN_PATH
        try:
            if token_path.exists():
                token_path.unlink()
                self.logger.info(f"Token eliminado: {token_path}")
        except Exception as e:
            self.logger.error(f"Error eliminando token: {e}")
        
        self.service = None
        self._credentials = None
        return self._autenticar()
    
    def esta_conectado(self) -> bool:
        """Verifica si está conectado a Google Drive"""
        return self.service is not None
    
    def listar_archivos(self, folder_id: str, tipos_archivo: List[str] = None) -> List[Dict[str, Any]]:
        """
        Lista archivos en una carpeta de Google Drive
        
        Args:
            folder_id: ID de la carpeta
            tipos_archivo: Extensiones a buscar (xlsx, csv, ods)
            
        Returns:
            Lista de diccionarios con información de archivos
        """
        if not self.esta_conectado():
            self.logger.error("No hay conexión con Google Drive")
            return []
        
        try:
            archivos = []
            
            # Construir query
            query = f"'{folder_id}' in parents and trashed=false"
            
            # Filtrar por tipo si se especifica
            if tipos_archivo:
                type_filters = " or ".join(
                    [f"name contains '{ext}'" for ext in tipos_archivo]
                )
                query += f" and ({type_filters})"
            
            # Ejecutar búsqueda
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, mimeType, createdTime, modifiedTime, size)',
                pageSize=100
            ).execute()
            
            archivos = results.get('files', [])
            
            self.logger.info(f"Archivos encontrados en Drive: {len(archivos)}")
            
            return archivos
            
        except HttpError as e:
            self.logger.error(f"Error listando archivos de Drive: {e}")
            return []
    
    def descargar_archivo(self, file_id: str, ruta_destino: str) -> Tuple[bool, str]:
        """
        Descarga un archivo de Google Drive
        
        Args:
            file_id: ID del archivo en Drive
            ruta_destino: Ruta local (carpeta o archivo completo) donde guardar
                         - Si es carpeta: agregará el nombre del archivo automáticamente
                         - Si es archivo: usará esa ruta directamente
            
        Returns:
            Tupla (exitoso, ruta_completa_o_mensaje)
        """
        if not self.esta_conectado():
            return False, "No hay conexión con Google Drive"
        
        try:
            # Obtener información del archivo
            file_metadata = self.service.files().get(
                fileId=file_id,
                fields='name'
            ).execute()
            
            file_name = file_metadata.get('name', 'archivo_descargado')
            ruta_path = Path(ruta_destino)
            
            # Determinar si ruta_destino es una carpeta o un archivo completo
            # Si tiene extensión y no existe como carpeta, es un archivo completo
            es_archivo_completo = (ruta_path.suffix != '' and not ruta_path.is_dir())
            
            if es_archivo_completo:
                # Usar la ruta tal cual (ya incluye el nombre del archivo)
                ruta_completa = ruta_path
            else:
                # Crear dentro de la carpeta
                ruta_completa = ruta_path / file_name
            
            # Asegurar que la carpeta padre existe
            ruta_completa.parent.mkdir(parents=True, exist_ok=True)
            
            # Descargar contenido
            request = self.service.files().get_media(fileId=file_id)
            
            with open(ruta_completa, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                
                while done is False:
                    status, done = downloader.next_chunk()
            
            self.logger.info(f"Archivo descargado: {ruta_completa}")
            return True, str(ruta_completa)
            
        except HttpError as e:
            self.logger.error(f"Error descargando archivo de Drive: {e}")
            return False, f"Error: {e}"
    
    def subir_archivo(self, ruta_local: str, folder_id: str, nombre_remoto: Optional[str] = None) -> Tuple[bool, str]:
        """
        Sube un archivo a Google Drive
        
        Args:
            ruta_local: Ruta del archivo local
            folder_id: ID de la carpeta destino en Drive
            nombre_remoto: Nombre con el que guardar (None = mismo nombre)
            
        Returns:
            Tupla (exitoso, file_id_o_error)
        """
        if not self.esta_conectado():
            return False, "No hay conexión con Google Drive"
        
        try:
            archivo = Path(ruta_local)
            
            if not archivo.exists():
                return False, f"Archivo no existe: {ruta_local}"
            
            nombre_remoto = nombre_remoto or archivo.name
            
            # Crear metadata del archivo
            file_metadata = {
                'name': nombre_remoto,
                'parents': [folder_id]
            }
            
            # Crear media upload
            media = MediaFileUpload(
                ruta_local,
                resumable=True
            )
            
            # Subir
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            file_id = file.get('id')
            self.logger.info(f"Archivo subido a Drive: {nombre_remoto} (ID: {file_id})")
            
            return True, file_id
            
        except HttpError as e:
            raw_error = str(e)
            if self._credential_mode == "service_account" and "storageQuotaExceeded" in raw_error:
                message = (
                    "La service account puede leer Drive, pero no crear archivos en una carpeta compartida de My Drive "
                    "porque no tiene cuota propia. Mueve la carpeta de salida a un Shared Drive o usa OAuth/delegación "
                    "de un usuario con cuota."
                )
                self.logger.error(message)
                return False, message

            self.logger.error(f"Error subiendo archivo a Drive: {e}")
            return False, f"Error: {e}"
    
    def encontrar_carpeta(self, nombre_carpeta: str) -> Optional[str]:
        """
        Busca una carpeta por nombre en Google Drive
        
        Args:
            nombre_carpeta: Nombre de la carpeta
            
        Returns:
            ID de la carpeta o None
        """
        if not self.esta_conectado():
            return None
        
        try:
            query = f"name='{nombre_carpeta}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)',
                pageSize=10
            ).execute()
            
            carpetas = results.get('files', [])
            
            if carpetas:
                self.logger.info(f"Carpeta encontrada: {nombre_carpeta} (ID: {carpetas[0]['id']})")
                return carpetas[0]['id']
            
            self.logger.warning(f"Carpeta no encontrada: {nombre_carpeta}")
            return None
            
        except HttpError as e:
            self.logger.error(f"Error buscando carpeta: {e}")
            return None
    
    def sincronizar_carpeta(self, folder_id_drive: str, carpeta_local: str,
                           tipos_archivo: List[str] = None) -> Tuple[int, List[str]]:
        """
        Descarga todos los archivos de una carpeta de Drive
        
        Args:
            folder_id_drive: ID de la carpeta en Drive
            carpeta_local: Ruta de carpeta local destino
            tipos_archivo: Tipos de archivo a descargar
            
        Returns:
            Tupla (cantidad_descargada, lista_rutas)
        """
        archivos_descargados = []
        
        # Crear carpeta local si no existe
        Path(carpeta_local).mkdir(parents=True, exist_ok=True)
        
        # Listar archivos
        archivos = self.listar_archivos(folder_id_drive, tipos_archivo)
        
        for archivo in archivos:
            exitoso, ruta = self.descargar_archivo(archivo['id'], carpeta_local)
            if exitoso:
                archivos_descargados.append(ruta)
        
        self.logger.info(f"Sincronización completada: {len(archivos_descargados)} archivos")
        
        return len(archivos_descargados), archivos_descargados


def obtener_lector_drive() -> Optional[LectorDrive]:
    """Obtiene instancia del lector de Drive si está disponible"""
    if not GOOGLE_API_DISPONIBLE:
        return None
    return LectorDrive()


if __name__ == "__main__":
    print("=== PRUEBA DEL MÓDULO LECTOR_DRIVE ===")
    
    lector = obtener_lector_drive()
    if lector:
        print(f"Conectado a Drive: {lector.esta_conectado()}")
    else:
        print("Google API no disponible")
