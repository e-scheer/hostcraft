"""Smoke tests for the top-level API surface.

These run on every CI build and act as the canary: if anything in the
Django app, settings, or URL conf is wedged, at least one of these
fails fast. They intentionally don't go near Docker, RCON, the filesystem,
or external HTTP — those are integration-level concerns.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class HealthVersionTests(APITestCase):
    """Public endpoints — no auth required."""

    def test_health_returns_ok(self):
        resp = self.client.get(reverse("api:health"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["status"], "ok")
        self.assertIn("time", resp.json())

    def test_version_returns_payload(self):
        resp = self.client.get(reverse("api:version"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body["name"], "hostcraft")
        self.assertIn("version", body)


class AuthFlowTests(APITestCase):
    """JWT login + /me round-trip."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="tester", password="t0psecret-pw", is_staff=False,
        )

    def test_login_with_bad_credentials_is_rejected(self):
        resp = self.client.post(
            reverse("users:login"),
            {"username": "tester", "password": "wrong"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_returns_token_pair(self):
        resp = self.client.post(
            reverse("users:login"),
            {"username": "tester", "password": "t0psecret-pw"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertIn("access", body)
        self.assertIn("refresh", body)
        self.assertGreater(len(body["access"]), 50)  # JWTs are big-ish

    def test_me_requires_authentication(self):
        resp = self.client.get(reverse("users:me"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_current_user_when_authenticated(self):
        # Grab a token, then attach it to the next request.
        login = self.client.post(
            reverse("users:login"),
            {"username": "tester", "password": "t0psecret-pw"},
            format="json",
        )
        token = login.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = self.client.get(reverse("users:me"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body["username"], "tester")
        self.assertFalse(body["is_staff"])


class SpaFallbackTests(APITestCase):
    """The catch-all route serves the SPA shell for anything outside /api and /admin."""

    def test_unknown_path_falls_through_to_spa(self):
        # SpaView returns 200 with index.html when present; 404 in CI if
        # the SPA hasn't been built. We accept either as proof that the
        # URL routing didn't pattern-match against an API view by mistake.
        resp = self.client.get("/runtime")  # any frontend route
        self.assertIn(resp.status_code, {status.HTTP_200_OK, status.HTTP_404_NOT_FOUND})
