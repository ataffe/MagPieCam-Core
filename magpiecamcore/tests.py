from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse


class HealthCheckTests(TestCase):
    """The health check reports each dependency it can reach, and only answers
    200 when every one of them is reachable."""

    def setUp(self):
        self.url = reverse('health_check')

    def healthy_redis(self):
        return mock.patch('magpiecamcore.views.redis.Redis')

    def test_reports_ok_when_database_and_redis_are_reachable(self):
        with self.healthy_redis():
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'database': 'ok', 'redis': 'ok'})

    def test_pings_redis_using_the_configured_host_and_port(self):
        with self.healthy_redis() as redis_class:
            self.client.get(self.url)

        redis_class.assert_called_once_with(
            host=settings.REDIS_HOST, port=settings.REDIS_PORT)
        redis_class.return_value.ping.assert_called_once_with()

    def test_reports_503_when_redis_is_unreachable(self):
        with mock.patch('magpiecamcore.views.redis.Redis') as redis_class:
            redis_class.return_value.ping.side_effect = RuntimeError('connection refused')
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body['database'], 'ok')
        self.assertEqual(body['redis'], 'error: connection refused')

    def test_reports_503_when_the_database_is_unreachable(self):
        with self.healthy_redis(), mock.patch(
            'magpiecamcore.views.connection.cursor',
            side_effect=RuntimeError('could not connect to server'),
        ):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body['database'], 'error: could not connect to server')
        self.assertEqual(body['redis'], 'ok')

    def test_is_reachable_without_authentication(self):
        """Load balancers and container orchestrators probe this endpoint with
        no credentials, so it must not sit behind the JWT auth the API uses."""
        with self.healthy_redis():
            response = self.client.get('/health/')

        self.assertEqual(response.status_code, 200)
