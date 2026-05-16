"""WebSocket JWT auth middleware.

Browser WebSockets can't send custom Authorization headers, so we accept the
access token in a `?token=...` query string and validate it against SimpleJWT.
"""

from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken


@database_sync_to_async
def _user_from_token(token: str):
    try:
        access = AccessToken(token)
        user_id = access["user_id"]
    except (TokenError, InvalidToken, KeyError):
        return AnonymousUser()
    user_model = get_user_model()
    try:
        return user_model.objects.get(id=user_id)
    except user_model.DoesNotExist:
        return AnonymousUser()


class JwtAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token = (query.get("token") or [None])[0]
        scope["user"] = await _user_from_token(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)
