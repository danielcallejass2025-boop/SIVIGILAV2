import os
import json
from google.oauth2 import service_account

# Lee la variable de entorno que pusiste en Railway
google_creds_raw = os.environ.get('GOOGLE_CREDENTIALS')

if google_creds_raw:
    creds_dict = json.loads(google_creds_raw)
    credentials = service_account.Credentials.from_service_account_info(creds_dict)
    # Ahora usa 'credentials' para conectar a Drive o Gmail