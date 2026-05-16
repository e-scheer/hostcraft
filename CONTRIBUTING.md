# Contributing

Thanks for thinking about contributing! Hostcraft is a one-person hobby project that gets better every time someone else pokes at it.

## Dev loop

Everything runs in Docker. You only need Docker (+ Compose v2). No Python, no Node, no venv on your host.

```bash
git clone https://github.com/e-scheer/hostcraft
cd hostcraft
cp .env.example .env       # the dev defaults work as-is
make dev                   # alias for: docker compose -f docker-compose.dev.yml up
```

When containers are up:

- Frontend (Vite, HMR): http://localhost:5173
- Backend (Django, autoreload): http://localhost:8001
- Minecraft (Paper latest): localhost:25565
- Default admin: `admin` / `admin`

Source is bind-mounted in both panel containers — edits on your host hit hot-reload instantly.

### Common commands

```bash
make dev                                  # start
make dev-down                             # stop (cleans up Playit sidecars too)
docker compose -f docker-compose.dev.yml logs -f backend
docker compose -f docker-compose.dev.yml exec backend python manage.py <cmd>
docker compose -f docker-compose.dev.yml exec frontend npx vue-tsc --noEmit
docker compose -f docker-compose.dev.yml exec frontend npm run lint
```

## Code style

- **Backend** — Django conventions, type hints, `dataclass` for value objects. Keep view functions small; business logic lives in `<app>/service.py` or `<app>/<domain>.py` modules. Translatable strings go through `gettext_lazy`.
- **Frontend** — Vue 3 Composition API, TS strict, Tailwind v4 utilities, Reka UI primitives via `@/components/ui/*`. New user-facing strings must go through `useI18n()` with parity in `fr.json` AND `en.json`.
- **i18n parity** — CI fails if `en.json` and `fr.json` don't share the exact same key set. Add to both.
- **No emojis in code** unless the project already uses them for that surface (only the README uses them).

## What's worth working on

Easy wins for a first PR:
- More translations (Spanish / German / etc. — copy `en.json` to `<lang>.json`).
- Better empty states / error messages.
- Backend tests — the scaffolding exists but coverage is thin.
- Engine-specific bug reports with crash logs.

Larger work, please open an issue first:
- CurseForge or Spigot mod source integration.
- Hibernation / wake-on-connect.
- Geyser+Floodgate one-click setup.

## PRs

- Branch off `main`. Small, focused PRs are easier to review than mega-PRs.
- Write a clear PR description: what changed, why, how to test.
- CI must pass (ruff/django checks, eslint, vue-tsc, locale parity, Docker build).
- No CLA. By contributing, you agree your work is MIT-licensed.

## Security

Don't open a public issue for a security bug — file a [private security advisory](https://github.com/e-scheer/hostcraft/security/advisories/new) instead.
