# EPIPROC - Entregables Implementados

## 1. Estructura recomendada del modulo web

```text
SIVIGILA/
  epiproc_web/
    __init__.py
    app.py
    extensions.py
    models.py
    services.py
    dashboard_data.py
    templates/
      base.html
      home.html
      login.html
      change_password.html
      dashboard.html
      bulletins_public.html
      admin_panel.html
      admin_epi_list.html
      admin_epi_form.html
      admin_bulletins.html
      admin_bulletin_form.html
      admin_audit.html
      epi_panel.html
      epi_bulletins.html
      epi_bulletin_form.html
      error.html
    static/
      css/app.css
      js/dashboard.js
  run_epiproc_web.py
  requirements.txt
```

## 2. Modelos de datos (SQLite local)

Archivo: `epiproc_web/models.py`

- `User`
  - Campos: `username`, `password_hash`, `role`, `full_name`, `cedula`, `email`, `assigned_event_code`, `must_change_password`, `is_active`
  - Seguridad: hash de contrasena con Werkzeug (`generate_password_hash`)
- `Event`
  - Campos: `code`, `name`, `active`
- `Bulletin`
  - Campos: `title`, `content`, `status` (`BORRADOR`/`PUBLICADO`), `event_code`, `author_id`, fechas
- `AuditLog`
  - Campos: `user_id`, `action`, `entity`, `entity_id`, `details`, `ip_address`, `created_at`

## 3. Rutas/API principales

Archivo: `epiproc_web/app.py`

- Publico
  - `/` inicio publico
  - `/dashboard` dashboard publico (solo lectura)
  - `/api/dashboard-data` datos para graficas en tiempo real
  - `/boletines` listado publico de boletines publicados
  - `/boletines/<id>/download` descarga de boletin (segun permisos)
- Autenticacion
  - `/login`
  - `/logout`
  - `/cambiar-clave` (forzado en primer ingreso)
  - `/portal` redireccion por rol
- Secretario de Salud (admin)
  - `/admin`
  - `/admin/dashboard`
  - `/admin/epidemiologos`
  - `/admin/epidemiologos/nuevo`
  - `/admin/epidemiologos/<id>/asignar-evento`
  - `/admin/epidemiologos/<id>/eliminar`
  - `/admin/boletines`
  - `/admin/boletines/nuevo`
  - `/admin/boletines/<id>/editar`
  - `/admin/auditoria`
- Epidemiologo
  - `/epi`
  - `/epi/dashboard` (solo evento asignado)
  - `/epi/boletines`
  - `/epi/boletines/nuevo`
  - `/epi/boletines/<id>/editar`

## 4. Middleware/autorizacion

Implementado en `epiproc_web/app.py`:

- `login_required`: exige sesion activa
- `role_required(...)`: control de acceso por rol (RBAC)
- `before_request`: fuerza cambio de contrasena si `must_change_password=True`
- Manejadores globales de error para UI/API: 403, 404 y 500

## 5. Vistas por rol

- Publico: home, dashboard en lectura, boletines publicados
- Secretario de Salud:
  - Panel administrativo
  - CRUD operativo de usuarios epidemiologos
  - Asignacion de evento
  - Gestion de boletines
  - Auditoria
  - Dashboard completo
- Epidemiologo:
  - Panel propio
  - Dashboard restringido a su evento asignado
  - Gestion de sus boletines

## 6. Semilla inicial solicitada

Implementado en `epiproc_web/services.py`:

- Usuario inicial:
  - Usuario: `AndresGob`
  - Contrasena inicial: `Risa2027*`
  - Rol: `SECRETARIO`
- Seguridad adicional:
  - Si el usuario inicial sigue con la clave por defecto, el sistema fuerza cambio de contrasena en el siguiente ingreso.

## 7. Credenciales por correo

Implementado en `epiproc_web/services.py`:

- Funcion `send_credentials_email(...)` usando SMTP por variables de entorno:
  - `SMTP_HOST`
  - `SMTP_PORT`
  - `SMTP_USER`
  - `SMTP_PASSWORD`
  - `SMTP_FROM` (opcional)
- Si SMTP no esta configurado, el sistema crea el usuario y muestra credenciales temporales para entrega controlada.

## 8. Ejecucion local

1. Instalar dependencias:

```bash
pip install -r requirements.txt
```

2. Ejecutar EPIPROC web:

```bash
python servidor_dashboard.py
```

3. Abrir en navegador:

```text
http://localhost:8000
```

## 9. Integracion con dashboard depurado en tiempo real

- `epiproc_web/dashboard_data.py` lee el archivo depurado mas reciente del evento.
- `epiproc_web/static/js/dashboard.js` consulta `/api/dashboard-data` cada 5 segundos.
- Actualizacion por token de version (`data_version`) para refrescar todas las graficas/KPIs/tabla cuando cambian los datos.

## 10. Estado general

- Backend Flask + SQLite + RBAC: implementado
- UI responsive con branding EPIPROC y logo solicitado: implementado
- Auditoria de acciones clave: implementado
- Boletines con estados y filtros: implementado
- Guardas de ruta y manejo global de errores API/UI: implementado
