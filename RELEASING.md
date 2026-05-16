# Releasing

Every release is gated through a single signal — an annotated git tag of the form `vX.Y.Z`. Nothing gets published to GHCR or the Releases page without one, and **the CI guarantees both happen together**: the docker image and the GitHub Release are created in the same pipeline run, so the two views can never drift.

## How to cut a release

From an up-to-date `main` with a clean working tree:

```bash
git pull --ff-only
git tag -a v0.2.0 -m "$(cat <<'EOF'
v0.2.0 — short summary

- bullet of what changed
- another bullet
- one-line breaking change call-out if any
EOF
)"
git push origin v0.2.0
```

That single push triggers `ci.yml`:

1. **backend** + **frontend** jobs run (lint, typecheck, tests, i18n parity).
2. If both pass, **docker** builds and pushes the multi-arch image to GHCR with three tags:
   - `ghcr.io/e-scheer/hostcraft:v0.2.0` — exact, immutable
   - `ghcr.io/e-scheer/hostcraft:0.2` — latest patch on the minor line, picks up `v0.2.1`, `v0.2.2`, …
   - `ghcr.io/e-scheer/hostcraft:latest` — always points at the newest tag
3. If the image push succeeds, **release** creates the GitHub Release using the tag annotation as the body (falling back to GitHub's auto-generated notes if the tag is lightweight). The release body also embeds the pull command for the image.

Stop here. There's no manual "Publish release" step — the moment the tag is on the remote, everything else is automatic.

## Version policy

Hostcraft follows [SemVer](https://semver.org/). For an early project this mostly means:

- `0.X.0` — anything goes, breaking changes are allowed but should be called out in the tag annotation.
- `0.X.Y` — bug-fix only, no breaking changes to the panel API, env vars, or persisted data shape.
- `1.0.0` — when the panel is stable enough to recommend for non-tinkerers (probably a long way off).

Pre-releases use `vX.Y.Z-rc.N` style suffixes — `metadata-action` recognises them and tags `:vX.Y.Z-rc.N` only, not `:latest`.

## What's NOT published

- Pushes to `main` — CI runs lint/typecheck/tests for fast feedback, but no image is built. The registry stays clean of mid-merge builds.
- PR builds — same deal. No registry credentials needed for PRs, no token pollution.

If you want a one-off pre-release image to share with a tester, just push a `v0.X.Y-test.N` tag and delete it (and the resulting image) afterwards.

## Hot fixes

1. Branch off the tag: `git switch -c hotfix/0.2.1 v0.2.0`.
2. Apply the fix, PR into `main`, get it green, merge.
3. Pull `main`, tag `v0.2.1`, push — pipeline handles the rest.

## Yanking a bad release

GitHub doesn't allow re-tagging the same version safely. If something escapes:

1. Mark the GitHub Release as a pre-release (or delete it).
2. Delete the GHCR tag at `https://github.com/users/e-scheer/packages/container/hostcraft/versions` (keeps the underlying digest layers for anyone who pinned by digest).
3. Cut `vX.Y.Z+1` with the actual fix.

Don't force-push the tag — clients that already pulled the bad version won't notice the change, and clients pulling later would get the silent swap.
