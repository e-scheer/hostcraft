# Screenshots

The repo README embeds six panel captures from this folder. Drop the PNGs here with these exact names:

| File | Route | What to capture |
|---|---|---|
| `dashboard.png` | `/` | The full dashboard — coup d'œil card with status pills, RAM/CPU sparklines, public-access row, recent activity. |
| `console.png` | `/console` | The xterm console with a recent server log; bonus points if you trigger the Tab-completion popover by typing `gam` and capturing the suggestion list. |
| `mods.png` | `/mods` | Browse tab, with a search active (e.g. "create") so the cards have icons, compat badges, install button visible. |
| `runtime.png` | `/runtime` | Engine + version + Java dropdown open showing the ★ recommended badge, plus an amber "newer than recommended" warn if you pick Java 25 on MC 1.20.x. |
| `network.png` | `/network` | Playit "managed" mode with the agent connected, secret-stored badge, tunnel target card, hostname detected. |

The BlueMap worldmap capture is intentionally skipped — its iframe is a WebGL canvas that doesn't render reliably in headless chromium (SwiftShader gives a black tile). Capture it manually on a real browser if you want to add a `worldmap.png` slot back.

## How to capture

1. Get the dev stack running (`make dev`).
2. Open each route in a real browser (Chrome/Firefox) at **1440×900** for consistent framing.
3. Use the OS screenshot tool (macOS: Cmd+Shift+4, Linux: GNOME Screenshot / Flameshot / Spectacle, Windows: Snip & Sketch).
4. Crop to the panel content area (sidebar + content) — drop the browser chrome.
5. Save as PNG, ≤ 1600 px wide; the README sets the column width.

Dark mode is the default and looks better for marketing — leave it as-is. If you want to advertise the light theme, suffix files with `-light.png` and we can add a toggle row to the README.
