from django.test import TestCase, Client, override_settings
from django.urls import reverse

@override_settings(SECURE_SSL_REDIRECT=False)
class BasicHealthCheck(TestCase):
    def test_homepage(self):
        client = Client()
        # Assuming there is a home page. Let's check urls.py to be sure.
        # But usually '/' works.
        response = client.get('/')
        self.assertEqual(response.status_code, 200)
