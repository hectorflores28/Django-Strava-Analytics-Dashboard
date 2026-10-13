from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import Activity, Athlete
from .views import fetch_and_sync_activities


class FetchAndSyncActivitiesTests(SimpleTestCase):
    def test_sync_uses_bearer_token_parses_utc_and_counts_only_created_activities(self):
        first_activity = {
            'id': 101,
            'name': 'Morning Run',
            'distance': 5000,
            'moving_time': 1800,
            'elapsed_time': 1900,
            'total_elevation_gain': 25,
            'type': 'Run',
            'sport_type': 'Run',
            'average_speed': 2.7,
            'max_speed': 3.5,
            'start_date': '2026-10-13T14:00:00Z',
            'start_date_local': '2026-10-13T07:00:00Z',
            'timezone': '(GMT-07:00) America/Los_Angeles',
        }
        second_activity = {**first_activity, 'id': 102}
        response = MagicMock()
        response.json.return_value = [first_activity, second_activity]
        session = MagicMock()
        session.__enter__.return_value.get.return_value = response
        athlete = SimpleNamespace(id=1)

        with patch('dashboard.views.Activity.objects.filter') as filter_activities, \
                patch('dashboard.views.Activity.objects.update_or_create') as save_activity, \
                patch('dashboard.views.get_session', return_value=session):
            filter_activities.return_value.aggregate.return_value = {
                'start_date__max': None,
            }
            save_activity.side_effect = [
                (SimpleNamespace(), True),
                (SimpleNamespace(), False),
            ]

            synced_count = fetch_and_sync_activities(athlete, 'test-access-token')

        self.assertEqual(synced_count, 1)
        self.assertEqual(
            session.__enter__.return_value.get.call_args.kwargs['headers'],
            {'Authorization': 'Bearer test-access-token'},
        )
        saved_fields = save_activity.call_args_list[0].kwargs['defaults']
        self.assertEqual(
            saved_fields['start_date'],
            datetime(2026, 10, 13, 14, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            saved_fields['start_date_local'],
            datetime(2026, 10, 13, 7, 0, tzinfo=timezone.utc),
        )


class ActivitySearchTests(TestCase):
    def setUp(self):
        self.athlete = Athlete.objects.create(
            id=9001,
            firstname='Test',
            lastname='Athlete',
            access_token='access-token',
            refresh_token='refresh-token',
            expires_at=2_000_000_000,
        )
        activity_defaults = {
            'athlete': self.athlete,
            'distance': 5000,
            'moving_time': 1800,
            'elapsed_time': 1900,
            'total_elevation_gain': 25,
            'sport_type': 'Run',
            'average_speed': 2.7,
            'max_speed': 3.5,
            'start_date': datetime(2026, 10, 13, 14, tzinfo=timezone.utc),
            'start_date_local': datetime(2026, 10, 13, 7, tzinfo=timezone.utc),
            'timezone': '(GMT-07:00) America/Los_Angeles',
        }
        Activity.objects.create(
            id=1001,
            name='Morning Run',
            type='Run',
            **activity_defaults,
        )
        Activity.objects.create(
            id=1002,
            name='Evening Ride',
            type='Ride',
            **activity_defaults,
        )

    def test_search_matches_activity_name_and_links_name_after_date_column(self):
        with patch(
            'dashboard.views.get_athlete_and_token',
            return_value=(self.athlete, 'access-token'),
        ):
            response = self.client.get(
                reverse('activities'),
                {'q': 'mOrNiNg'},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].paginator.count, 1)
        self.assertContains(response, 'Morning Run')
        self.assertNotContains(response, 'Evening Ride')
        rendered = response.content.decode()
        self.assertLess(
            rendered.index('<th scope="col">Date</th>'),
            rendered.index('<th scope="col">Name</th>'),
        )
        self.assertContains(response, 'href="/activities/1001/"')
