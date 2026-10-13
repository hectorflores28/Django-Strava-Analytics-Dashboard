import requests
import os
from datetime import datetime, timedelta, timezone as datetime_timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.conf import settings
from django.contrib import messages
import json 
from .models import Athlete, Activity
from django.db.models import Sum, Count, F, Max
from django.db.models.functions import ExtractYear, ExtractWeek, ExtractDay
from django.core.paginator import Paginator
from collections import defaultdict
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.utils import timezone # Usamos timezone de Django

# --- Vistas de Dashboard ---

def index(request):
    """Vista principal del Dashboard."""
    athlete, access_token = get_athlete_and_token(request)

    if not athlete:
        return render(request, 'index.html', {'is_authenticated': False})

    # 1. Calcular Fechas Clave
    today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)
    
    # 2. Agregación Base
    def get_summary(start_date, end_date=today + timedelta(days=1)):
        summary = Activity.objects.filter(
            athlete=athlete,
            start_date_local__gte=start_date,
            start_date_local__lt=end_date
        ).aggregate(
            count=Count('id'),
            distance=Sum('distance') / 1000.0,
            elevation=Sum('total_elevation_gain'),
            time=Sum('moving_time') / 3600.0,
        )
        return {k: round(v, 2) if v is not None else 0 for k, v in summary.items()}

    # 3. Lógica para Actividades Recientes (movida desde el template)
    recent_activities = Activity.objects.filter(athlete=athlete).order_by('-start_date_local')[:5]

    # 4. Lógica para Gráfico de Distribución por Tipo de Actividad
    activity_distribution = Activity.objects.filter(
        athlete=athlete
    ).values('type').annotate(
        count=Count('id')
    ).order_by('-count')

    chart_labels = [item['type'] for item in activity_distribution]
    chart_data = [item['count'] for item in activity_distribution]

    # 5. Construir el Contexto Final
    today_stats = get_summary(today)
    this_week_stats = get_summary(start_of_week)
    this_month_stats = get_summary(start_of_month)

    # Goal Logic (Default 150km)
    monthly_goal = 150.0
    current_distance = this_month_stats.get('distance', 0)
    goal_percentage = min(100, (current_distance / monthly_goal * 100)) if monthly_goal > 0 else 0

    context = {
        'today': today_stats,
        'this_week': this_week_stats,
        'this_month': this_month_stats,
        'athlete': athlete,
        'is_authenticated': True,
        'recent_activities': recent_activities,
        # Goal Data
        'meta_mensual': monthly_goal,
        'avance_mensual': current_distance,
        'avance_porcentaje': goal_percentage,
        # Pasamos los datos del gráfico como JSON para ser usados en JavaScript
        'chart_labels': chart_labels,
        'chart_data': chart_data,
    }

    return render(request, 'index.html', context)

def weekly_view(request):
    """
    Muestra el progreso semanal agregado de las actividades del atleta durante el último año.
    """
    athlete, _ = get_athlete_and_token(request)

    if not athlete:
        messages.warning(request, "Please log in to see your weekly progress.")
        return redirect('login')

    # 1. Definir el rango de tiempo (ej: último año)
    one_year_ago = datetime.now() - timedelta(days=365)

    # 2. Agregación Semanal Avanzada
    # Usamos ExtractIsoWeek para obtener el número de semana (1-52/53) y ExtractYear para agrupar
    weekly_summary = Activity.objects.filter(
        athlete=athlete,
        start_date_local__gte=one_year_ago
    ).annotate(
        # Creamos campos temporales para agrupar por Año y Semana ISO
        year=ExtractYear('start_date_local'),
        week=ExtractWeek('start_date_local')
    ).values(
        'year', 'week'
    ).annotate(
        # Calculamos las métricas agregadas
        count=Count('id'),
        distance=Sum(F('distance') / 1000.0), # Convertir a km en la DB
        elevation=Sum('total_elevation_gain'),
        time=Sum(F('moving_time') / 3600.0)    # Convertir a horas en la DB
    ).order_by('-year', '-week') # Ordenar de la semana más reciente a la más antigua

    # 3. Formatear los datos para la plantilla
    weekly_data = []
    for entry in weekly_summary:
        # Formatear la clave de la semana como "YYYY - Week W"
        week_label = f"{entry['year']} - Week {entry['week']}"
        
        weekly_data.append({
            'week': week_label,
            'data': {
                'count': entry['count'],
                'distance': entry['distance'] or 0.0,
                'elevation': entry['elevation'] or 0.0,
                'time': entry['time'] or 0.0,
            }
        })
        
    context = {
        'athlete': athlete,
        'weekly_data': weekly_data,
    }

    return render(request, 'weekly.html', context)

def monthly_view(request):
    """Vista de resumen mensual."""
    athlete, access_token = get_athlete_and_token(request)

    if not athlete:
        messages.warning(request, "Please log in to see the monthly view.")
        return redirect('login')

    # Usamos F() expressions y anotaciones para agrupar y agregar en la DB
    monthly_data_raw = Activity.objects.filter(
        athlete=athlete,
        start_date_local__gte=timezone.now() - timedelta(days=365)
    ).extra(
        select={'month_key': "strftime('%%Y-%%m', start_date_local)"} # SQLite formatting
    ).values('month_key').annotate(
        count=Count('id'),
        distance=Sum(F('distance') / 1000.0),
        elevation=Sum('total_elevation_gain'),
        time=Sum(F('moving_time') / 3600.0)
    ).order_by('-month_key')

    monthly_data = [{
        'month': item['month_key'],
        'data': {k: item[k] for k in ['count', 'distance', 'elevation', 'time']}
    } for item in monthly_data_raw]

    return render(request, 'monthly.html', {'monthly_data': monthly_data, 'athlete': athlete})

# --- Funciones Auxiliares de API (Mejor práctica: Mover a un módulo `strava_api.py`) ---

def get_session():
    """Usa requests.Session para conexiones persistentes."""
    return requests.Session()

def refresh_strava_token(athlete):
    """Refresca el token de acceso de Strava."""
    url = f"{settings.STRAVA_OAUTH_URL}/token"
    payload = {
        'client_id': settings.STRAVA_CLIENT_ID,
        'client_secret': settings.STRAVA_CLIENT_SECRET,
        'grant_type': 'refresh_token',
        'refresh_token': athlete.refresh_token
    }
    
    with get_session() as s:
        response = s.post(url, data=payload)
    
    response.raise_for_status()
    data = response.json()
    
    # Actualizar el objeto Athlete en la DB
    athlete.access_token = data['access_token']
    athlete.refresh_token = data.get('refresh_token', athlete.refresh_token) # A veces no cambia
    athlete.expires_at = data['expires_at']
    athlete.save()
    
    return athlete

# --- Vistas de Autenticación ---

def login_strava(request):
    """Redirige al usuario a Strava para la autenticación OAuth."""
    client_id = settings.STRAVA_CLIENT_ID
    redirect_uri = request.build_absolute_uri(reverse('strava_callback'))
    scope = "read,activity:read_all" # read_all es esencial para el dashboard

    auth_url = (
        f"{settings.STRAVA_OAUTH_URL}/authorize?"
        f"client_id={client_id}&"
        f"response_type=code&"
        f"redirect_uri={redirect_uri}&"
        f"approval_prompt=force&" # Forzar al usuario a revisar los permisos
        f"scope={scope}"
    )
    return redirect(auth_url)

@require_http_methods(["GET"])
def strava_callback(request):
    """Maneja el callback de Strava y el intercambio de código por tokens."""
    code = request.GET.get('code')
    error = request.GET.get('error')

    if error:
        messages.error(request, f"Strava authentication failed: {error}")
        return redirect('index')

    if not code:
        messages.error(request, "Authorization code missing.")
        return redirect('index')

    token_url = f"{settings.STRAVA_OAUTH_URL}/token"
    payload = {
        'client_id': settings.STRAVA_CLIENT_ID,
        'client_secret': settings.STRAVA_CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code',
    }

    try:
        with get_session() as s:
            response = s.post(token_url, data=payload)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        messages.error(request, f"Error exchanging code for token: {e}")
        return redirect('index')

    # Guardar o actualizar el Athlete
    athlete_data = data['athlete']
    athlete_id = athlete_data['id']
    
    # Usamos transaction.atomic para asegurar la consistencia
    with transaction.atomic():
        athlete, created = Athlete.objects.update_or_create(
            id=athlete_id,
            defaults={
                'access_token': data['access_token'],
                'refresh_token': data['refresh_token'],
                'expires_at': data['expires_at'],
                'firstname': athlete_data.get('firstname'),
                'lastname': athlete_data.get('lastname'),
                'username': athlete_data.get('username'),
                'profile': athlete_data.get('profile'),
                'profile_medium': athlete_data.get('profile_medium'),
                # ... otros campos ...
            }
        )
    
    # Iniciar sesión de Django (guardar el ID del atleta en la sesión)
    request.session['athlete_id'] = athlete_id
    messages.success(request, f"Welcome back, {athlete.firstname}!")
    
    # Iniciar la primera sincronización de datos
    return redirect(reverse('refresh_activities'))


def logout_view(request):
    """Cierra la sesión de Django."""
    if 'athlete_id' in request.session:
        del request.session['athlete_id']
    messages.info(request, "Successfully logged out.")
    return redirect('index')

def get_athlete_and_token(request):
    """Obtiene el atleta de la sesión y refresca el token si es necesario."""
    athlete_id = request.session.get('athlete_id')
    if not athlete_id:
        return None, None
        
    athlete = get_object_or_404(Athlete, id=athlete_id)
    
    if athlete.is_token_expired():
        try:
            athlete = refresh_strava_token(athlete)
        except requests.exceptions.RequestException as e:
            messages.error(request, f"Token refresh failed. Please re-login: {e}")
            return None, None
            
    return athlete, athlete.access_token


def fetch_and_sync_activities(athlete, access_token):
    """
    Obtiene las actividades nuevas del atleta desde Strava y las sincroniza con la DB.
    Esta lógica DEBE ser reutilizada en el cron job (`daily_update.py`).
    """
    # 1. Determinar el punto de partida (after parameter de la API)
    # Buscamos la fecha de inicio más reciente en nuestra DB para este atleta
    last_activity = Activity.objects.filter(athlete=athlete).aggregate(Max('start_date'))
    # Si hay actividades, establecemos el timestamp de inicio para buscar SOLO nuevas
    after_timestamp = 0
    if last_activity['start_date__max']:
        # Convertir a timestamp UNIX, restamos un día por seguridad
        last_date = last_activity['start_date__max'] - timedelta(days=1)
        after_timestamp = int(last_date.timestamp())

    # 2. Bucle de paginación para obtener actividades
    activities_url = f"{settings.STRAVA_API_URL}/athlete/activities"
    page = 1
    new_activities_count = 0

    with get_session() as s:
        # Usamos requests.Session() para conexiones persistentes (Mejor Práctica)
        while True:
            params = {
                'page': page,
                'per_page': 50,
                'after': after_timestamp # Solo actividades después de este timestamp
            }
            headers = {'Authorization': 'Bearer ' + access_token}

            response = s.get(activities_url, headers=headers, params=params)
            response.raise_for_status()
            strava_activities = response.json()
            
            if not strava_activities:
                break # No hay más actividades

            # 3. Sincronizar con la DB
            for item in strava_activities:
                # Convertir la fecha UTC (string) a objeto datetime
                start_date_utc = datetime.strptime(
                    item['start_date'], '%Y-%m-%dT%H:%M:%SZ'
                ).replace(tzinfo=datetime_timezone.utc)
                start_date_local = datetime.strptime(
                    item['start_date_local'], '%Y-%m-%dT%H:%M:%SZ'
                ).replace(tzinfo=datetime_timezone.utc)

                # Extraer datos de mapa si existen
                map_data = item.get('map', {})
                summary_polyline = map_data.get('summary_polyline')
                start_latlng = item.get('start_latlng')
                end_latlng = item.get('end_latlng')

                # Crear o actualizar la actividad
                _, created = Activity.objects.update_or_create(
                    id=item['id'],
                    defaults={
                        'athlete': athlete,
                        'name': item['name'],
                        'distance': item['distance'],
                        'moving_time': item['moving_time'],
                        'elapsed_time': item['elapsed_time'],
                        'total_elevation_gain': item['total_elevation_gain'],
                        'type': item['type'],
                        'sport_type': item['sport_type'],
                        'average_speed': item['average_speed'],
                        'max_speed': item['max_speed'],
                        'has_heartrate': item.get('has_heartrate', False),
                        'average_heartrate': item.get('average_heartrate'),
                        'max_heartrate': item.get('max_heartrate'),
                        'start_date': start_date_utc,
                        'start_date_local': start_date_local,
                        'timezone': item['timezone'],
                        'summary_polyline': summary_polyline,
                        'start_latlng': json.dumps(start_latlng) if start_latlng else None,
                        'end_latlng': json.dumps(end_latlng) if end_latlng else None,
                    }
                )
                if created:
                    new_activities_count += 1
                
            page += 1
            # Strava tiene un límite de 200 por página, pero 50 es más seguro.
            if len(strava_activities) < 50:
                break # Menos del límite significa que es la última página

    return new_activities_count

# --- Vista para la Sincronización Manual ---

def refresh_activities_view(request):
    """Endpoint de Django para la sincronización manual de datos."""
    athlete, access_token = get_athlete_and_token(request)

    if not athlete:
        return redirect('login') # Si no hay atleta o falla el refresh, redirigir al login

    try:
        count = fetch_and_sync_activities(athlete, access_token)
        messages.success(request, f"Data synchronization complete. {count} new activities added.")
    except requests.exceptions.HTTPError as e:
        # Manejar errores de la API (ej: 401 Unauthorized, 404 Not Found)
        messages.error(request, f"Strava API Error during sync. Status: {e.response.status_code}. Message: {e.response.text}")
    except Exception as e:
        messages.error(request, f"An unexpected error occurred during sync: {e}")
        
    return redirect('index')

def activities_list(request):
    """
    Lista de actividades con paginación y filtrado por tipo.
    Miga la lógica de la función 'activities()' de app.py
    """
    athlete, access_token = get_athlete_and_token(request)

    if not athlete:
        messages.warning(request, "Please log in to see your activities.")
        return redirect('login')

    # 1. Obtener los filtros (Query Parameters)
    selected_type = request.GET.get('type')
    search_query = request.GET.get('q', '').strip()

    # 2. Construir el QuerySet base
    activities_queryset = Activity.objects.filter(athlete=athlete)

    # 3. Aplicar filtro
    if selected_type:
        activities_queryset = activities_queryset.filter(type=selected_type)
    if search_query:
        activities_queryset = activities_queryset.filter(name__icontains=search_query)

    # Obtener todos los tipos únicos para el dropdown de filtrado
    activity_types = Activity.objects.filter(athlete=athlete).values_list('type', flat=True).distinct().order_by('type')

    PAGINATOR_SIZE = 20
    paginator = Paginator(activities_queryset, PAGINATOR_SIZE)
    
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    query_parameters = request.GET.copy()
    query_parameters.pop('page', None)
    
    # activities.items -> page_obj.object_list
    # activities.has_next -> page_obj.has_next
    # activities.next_num -> page_obj.next_page_number
    # activities.iter_pages() -> Lo simularemos con un loop
    
    # 5. Generar un rango de páginas para la plantilla (opcional, pero mejora la UX)
    def get_page_range(current_page, num_pages):
        """Genera un rango de números de página para mostrar en el paginador."""
        if num_pages <= 10:
            return range(1, num_pages + 1)
        
        # Muestra 3 páginas alrededor de la actual + el inicio y el fin.
        start = max(1, current_page - 2)
        end = min(num_pages, current_page + 2)
        
        pages = list(range(start, end + 1))
        
        if 1 not in pages:
            pages.insert(0, 1)
            if 2 not in pages and 1 < start - 1:
                pages.insert(1, None) # Placeholder para "..."

        if num_pages not in pages:
            if num_pages - 1 not in pages and num_pages > end + 1:
                pages.append(None) # Placeholder para "..."
            pages.append(num_pages)
            
        return pages

    context = {
        # Renombramos para usar un nombre de variable más claro en la plantilla
        'page_obj': page_obj, 
        'activities': page_obj.object_list,
        'activity_types': activity_types,
        'selected_type': selected_type,
        'search_query': search_query,
        'query_string': query_parameters.urlencode(),
        'page_range': get_page_range(page_obj.number, paginator.num_pages),
        'athlete': athlete,
    }

    return render(request, 'activities.html', context)

def activity_detail(request, activity_id):
    """
    Muestra los detalles de una actividad específica y sus actividades similares para comparación.
    """
    athlete, _ = get_athlete_and_token(request)

    if not athlete:
        messages.warning(request, "Please log in to see activity details.")
        return redirect('login')

    # Obtener la actividad por ID, asegurando que pertenezca al atleta actual
    # get_object_or_404 dispara un 404 si no existe o no pertenece al atleta
    activity = get_object_or_404(
        Activity, 
        id=activity_id, 
        athlete=athlete
    )

    # Lógica para actividades similares (mismo tipo, anteriores a la fecha actual)
    similar_activities = Activity.objects.filter(
        athlete=athlete,
        type=activity.type,
        start_date_local__lt=activity.start_date_local # Actividades con fecha anterior
    ).exclude(
        id=activity.id
    ).order_by(
        '-start_date_local' # Las más recientes primero
    )[:5] # Limitar a las 5 más recientes para la comparación en la tabla

    context = {
        'athlete': athlete,
        'activity': activity,
        'similar_activities': similar_activities,
    }
    
    return render(request, 'activity_detail.html', context)