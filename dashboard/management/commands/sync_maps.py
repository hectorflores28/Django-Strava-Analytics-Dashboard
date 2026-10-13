"""
CronJobs:

# Ejemplo de entrada en crontab -e (se ejecuta a las 3:00 AM todos los días)
# Asegúrate de usar la ruta completa al entorno y manage.py
0 3 * * * /path/to/venv/bin/python /path/to/project/manage.py sync_maps >> /path/to/project/logs/sync_maps.log 2>&1

"""
from django.core.management.base import BaseCommand
from dashboard.models import Activity, Athlete
from dashboard.views import get_session, refresh_strava_token
from django.conf import settings
from datetime import datetime
import json
from django.utils import timezone

class Command(BaseCommand):
    help = 'Syncs map data (polyline) for all existing activities'

    def handle(self, *args, **options):
        athletes = Athlete.objects.all()
        for athlete in athletes:
            if athlete.is_token_expired():
                athlete = refresh_strava_token(athlete)
            
            self.stdout.write(f"Syncing activities for {athlete.firstname}...")
            
            access_token = athlete.access_token
            activities_url = f"{settings.STRAVA_API_URL}/athlete/activities"
            page = 1
            updated_count = 0

            with get_session() as s:
                while True:
                    params = {
                        'page': page,
                        'per_page': 50,
                    }
                    headers = {'Authorization': 'Bearer ' + access_token}
                    response = s.get(activities_url, headers=headers, params=params)
                    
                    if response.status_code != 200:
                        self.stderr.write(f"Error fetching page {page}: {response.text}")
                        break
                        
                    strava_activities = response.json()
                    if not strava_activities:
                        break

                    for item in strava_activities:
                        activity_id = item['id']
                        try:
                            activity = Activity.objects.get(id=activity_id)
                            
                            # Extraer datos de mapa
                            map_data = item.get('map', {})
                            summary_polyline = map_data.get('summary_polyline')
                            start_latlng = item.get('start_latlng')
                            end_latlng = item.get('end_latlng')
                            
                            activity.summary_polyline = summary_polyline
                            activity.start_latlng = json.dumps(start_latlng) if start_latlng else None
                            activity.end_latlng = json.dumps(end_latlng) if end_latlng else None
                            activity.save()
                            updated_count += 1
                        except Activity.DoesNotExist:
                            # Si no existe, la creamos (opcional, pero fetch_and_sync_activities ya lo hace)
                            continue
                    
                    page += 1
                    if len(strava_activities) < 50:
                        break
            
            self.stdout.write(self.style.SUCCESS(f"Successfully updated {updated_count} activities for {athlete.firstname}"))
