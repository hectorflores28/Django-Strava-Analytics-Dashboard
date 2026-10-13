# Panel de Análisis de Strava

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Django](https://img.shields.io/badge/Django-5.0+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

Una aplicación web local completa para rastrear y analizar tus datos de actividad de Strava con actualizaciones automáticas diarias.

![Home](public/screenshot.png)
![Logged-In-Dashboard](public/screenshot_dashboard.png)
![Activities](public/screenshot_activities.png)
![Activity-Detail](public/screenshot_activity_details.png)
![Weekly](public/screenshot_weekly.png)
![Monthly](public/screenshot_monthly.png)

## Funcionalidades

![Dashboard](public/dashboard.jpeg)

### Vistas del Panel
- Resúmenes de actividad **Diarios, Semanales, Mensuales**
- **Seguimiento de progreso** con conteo de actividades, distancia, desnivel acumulado y tiempo
- **Seguimiento de rachas** que muestra días consecutivos y días activos totales
- **Seguimiento de objetivos** para metas de distancia semanal
- **Gráficos interactivos** con capacidades de comparación semanal/mensual
- **Vista de calendario mensual** que muestra el estado de actividad diaria
- **Análisis de Esfuerzo Relativo**
- **Informes de resumen mensual**

### Gestión de Actividades
- Lista de actividades filtrable
- Registros de actividad individual que muestran:
  - Nombre de la actividad
  - Hora de finalización
  - Distancia y desnivel
  - Mapas de ruta
  - Comparaciones interanuales

## Implementación Técnica

### Flujo de Datos
- Script de Python que utiliza la API de Strava v3
- Tarea programada diaria (cron job) para actualizaciones automáticas de datos
- Esquema de base de datos con tablas para:
  - Activities (Actividades)
  - Athlete (Atleta)
  - Club (Club)
  - Equipment (Equipamiento)
  - Routes (Rutas)
  - Segment (Segmento)
  - Stream (Streams)
  - Load (Carga)

### Instrucciones de Configuración

### Desplegar en Render

1. Crea un servicio **Web Service** conectado al repositorio y selecciona **Docker** como runtime.
2. En **Environment**, añade `SECRET_KEY` (genera una clave nueva y privada), `DJANGO_DEBUG=False`, `STRAVA_CLIENT_ID` y `STRAVA_CLIENT_SECRET`. `PORT` lo proporciona Render.
3. Si quieres conservar actividades y tokens entre despliegues, añade un Persistent Disk (requiere una instancia compatible de pago) montado en `/var/data` y configura `DATABASE_PATH=/var/data/strava.db`. Sin un disco persistente, SQLite se perderá al recrear el servicio.
4. En [Strava API Settings](https://www.strava.com/settings/api), establece **Authorization Callback Domain** a `django-strava-analytics-dashboard.onrender.com` (sin `https://` ni `/`). El campo **Website** puede ser `https://django-strava-analytics-dashboard.onrender.com/`.
5. Cuando Strava solicite la URL completa de callback, usa `https://django-strava-analytics-dashboard.onrender.com/callback/`. La aplicación la genera automáticamente desde la petición HTTPS de Render.
6. `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` incluyen este dominio en la configuración. Si usas un dominio personalizado, añade su hostname a `ALLOWED_HOSTS` y su origen HTTPS a `CSRF_TRUSTED_ORIGINS` en las variables de Render.

### Ejecutar con Docker Compose

- Configura las credenciales en el archivo `.env`.
- Desde la raíz del proyecto, construye e inicia la aplicación:
  ```bash
  docker compose up --build
  ```
  Al iniciar, el contenedor aplica las migraciones de Django antes de ejecutar el servidor.
- Abre http://localhost:8000.

Si el contenedor ya estaba iniciado, vuelve a ejecutar `docker compose up --build` para recrearlo con el comando actualizado.

1. **Clonar el repositorio**
   ```bash
   git clone https://github.com/hectorflores28/django-strava-analytics-dashboard
   cd django-strava-analytics-dashboard
   ```

2. **Instalar dependencias**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configurar credenciales de la API de Strava**
   - Registra una aplicación en [Strava API Settings](https://www.strava.com/settings/api)
   - Actualiza `config.py` con tu ID de cliente y secreto

4. **Inicializar la base de datos**
   ```bash
   python init_db.py
   ```

5. **Configurar la tarea programada (cron job) para actualizaciones diarias**
   ```bash
   # Añadir al crontab (crontab -e)
   0 2 * * * cd /path/to/django-strava-analytics-dashboard && python sync_data_strava.py
   0 3 * * * cd /path/to/django-strava-analytics-dashboard && python sync_maps.py
   ```

6. **Ejecutar la aplicación web**
   ```bash
   python app.py
   ```

### Variables de entorno (.env)
```
STRAVA_CLIENT_ID=tu_strava_client_id
STRAVA_CLIENT_SECRET=tu_strava_client_secret
SECRET_KEY=tu_secret_key
```

### Estructura del Proyecto
```
django-strava-analytics-dashboard/
├── StravaAPIv3.md          # Documentación de referencia de la API
├── config.py               # Configuración
├── daily_update.py         # Script de actualización diaria de datos
├── init_db.py              # Inicialización de la base de datos
├── app.py                  # Aplicación web
├── models.py               # Modelos de base de datos
├── requirements.txt        # Dependencias de Python
└── templates/              # Plantillas web
    ├── index.html          # Panel principal
    ├── activities.html     # Lista de actividades
    └── monthly.html        # Vista mensual
```

## Referencia de la API
Consulta la [Documentación StravaAPIv3](public/strava_api_v3_documentation.md) en el directorio raíz para obtener la documentación completa de la API de Strava v3 y detalles de los endpoints.

## Desarrollo
Este proyecto utiliza:
- Python 3.8+
- Framework web django
- Base de datos SQLite (puede configurarse para otras bases de datos)
- API de Strava v3 con autenticación OAuth2

## Soporte
Para problemas y preguntas, consulta:
- Documentación de la API de Strava: https://developers.strava.com/docs/reference/
- Página de issues del proyecto

---

*Este proyecto no está afiliado con Strava, Inc. pero utiliza su API de acuerdo con sus términos de servicio.*
