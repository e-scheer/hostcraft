"""Schema and (de)serialization helpers for server.properties.

Exposed to the frontend as `{ values, schema, unknown_keys }` so the UI can
render typed inputs (boolean toggle, enum dropdown, int with bounds, etc.)
instead of forcing the user to remember Java properties syntax.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

# Type values: "string" | "integer" | "boolean" | "enum"
# Section keys map to i18n labels in the frontend (settings.properties.sections.*).
SCHEMA: dict[str, dict] = {
    # ---- Identity --------------------------------------------------------
    "motd": {"type": "string", "section": "identity", "default": "A Minecraft Server", "max_length": 60},
    "server-port": {"type": "integer", "section": "identity", "default": 25565, "min": 1, "max": 65535},
    "server-ip": {"type": "string", "section": "identity", "default": ""},

    # ---- Gameplay -------------------------------------------------------
    "gamemode": {
        "type": "enum", "section": "gameplay",
        "options": ["survival", "creative", "adventure", "spectator"], "default": "survival",
    },
    "difficulty": {
        "type": "enum", "section": "gameplay",
        "options": ["peaceful", "easy", "normal", "hard"], "default": "easy",
    },
    "hardcore": {"type": "boolean", "section": "gameplay", "default": False},
    "pvp": {"type": "boolean", "section": "gameplay", "default": True},
    "allow-flight": {"type": "boolean", "section": "gameplay", "default": False},
    "allow-nether": {"type": "boolean", "section": "gameplay", "default": True},
    "force-gamemode": {"type": "boolean", "section": "gameplay", "default": False},

    # ---- World ----------------------------------------------------------
    "level-name": {"type": "string", "section": "world", "default": "world"},
    "level-seed": {"type": "string", "section": "world", "default": ""},
    "level-type": {
        "type": "enum", "section": "world",
        "options": [
            "minecraft:normal", "minecraft:flat", "minecraft:large_biomes",
            "minecraft:amplified", "minecraft:single_biome_surface",
        ],
        "default": "minecraft:normal",
    },
    "spawn-protection": {"type": "integer", "section": "world", "default": 16, "min": 0, "max": 1024},
    "max-world-size": {"type": "integer", "section": "world", "default": 29999984, "min": 1},
    "generate-structures": {"type": "boolean", "section": "world", "default": True},

    # ---- Players --------------------------------------------------------
    "max-players": {"type": "integer", "section": "players", "default": 20, "min": 1, "max": 10000},
    "online-mode": {"type": "boolean", "section": "players", "default": True},
    "white-list": {"type": "boolean", "section": "players", "default": False},
    "enforce-whitelist": {"type": "boolean", "section": "players", "default": False},
    "player-idle-timeout": {"type": "integer", "section": "players", "default": 0, "min": 0, "max": 1440},

    # ---- Performance ----------------------------------------------------
    "view-distance": {"type": "integer", "section": "performance", "default": 10, "min": 3, "max": 32},
    "simulation-distance": {"type": "integer", "section": "performance", "default": 10, "min": 3, "max": 32},
    "network-compression-threshold": {"type": "integer", "section": "performance", "default": 256, "min": -1},
    "entity-broadcast-range-percentage": {"type": "integer", "section": "performance", "default": 100, "min": 1, "max": 500},

    # ---- Spawning -------------------------------------------------------
    "spawn-monsters": {"type": "boolean", "section": "spawning", "default": True},
    "spawn-animals": {"type": "boolean", "section": "spawning", "default": True},
    "spawn-npcs": {"type": "boolean", "section": "spawning", "default": True},

    # ---- Permissions ----------------------------------------------------
    "op-permission-level": {"type": "integer", "section": "permissions", "default": 4, "min": 1, "max": 4},
    "function-permission-level": {"type": "integer", "section": "permissions", "default": 2, "min": 1, "max": 4},
    "enable-command-block": {"type": "boolean", "section": "permissions", "default": False},

    # ---- Security -------------------------------------------------------
    "enforce-secure-profile": {"type": "boolean", "section": "security", "default": True},
    "prevent-proxy-connections": {"type": "boolean", "section": "security", "default": False},
    "hide-online-players": {"type": "boolean", "section": "security", "default": False},

    # ---- Resource pack --------------------------------------------------
    "resource-pack": {"type": "string", "section": "resource_pack", "default": ""},
    "resource-pack-sha1": {"type": "string", "section": "resource_pack", "default": ""},
    "require-resource-pack": {"type": "boolean", "section": "resource_pack", "default": False},
}


# Order of sections in the UI.
SECTIONS = [
    "identity",
    "gameplay",
    "world",
    "players",
    "performance",
    "spawning",
    "permissions",
    "security",
    "resource_pack",
]


def properties_path() -> Path:
    return Path(settings.MC_DATA_PATH) / "server.properties"


def parse(text: str) -> dict[str, str]:
    """Parse a Java .properties text into a flat str→str dict.

    Comments (`#…` / `!…`) are dropped. Lines without `=` are skipped.
    """
    out: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line[0] in "#!":
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value
    return out


def serialize(values: dict[str, str]) -> str:
    """Serialize a flat dict back to Java .properties format."""
    lines = ["#Minecraft server properties — managed by hostcraft"]
    for key in sorted(values):
        lines.append(f"{key}={values[key]}")
    return "\n".join(lines) + "\n"


def deserialize_typed(raw: dict[str, str]) -> dict[str, object]:
    """Coerce stored string values to schema-aware Python types for the UI."""
    out: dict[str, object] = {}
    for key, spec in SCHEMA.items():
        if key in raw:
            value = raw[key]
        else:
            out[key] = spec.get("default")
            continue

        match spec["type"]:
            case "boolean":
                out[key] = value.lower() == "true"
            case "integer":
                try:
                    out[key] = int(value)
                except (TypeError, ValueError):
                    out[key] = spec.get("default", 0)
            case "enum":
                out[key] = value if value in spec.get("options", []) else spec.get("default")
            case _:  # "string"
                out[key] = value
    return out


def coerce(key: str, raw_value: object) -> str | None:
    """Coerce a frontend value back to the .properties string form. None = drop."""
    spec = SCHEMA.get(key)
    if not spec:
        return None  # never write keys we don't own

    match spec["type"]:
        case "boolean":
            return "true" if bool(raw_value) else "false"
        case "integer":
            try:
                n = int(raw_value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                n = int(spec.get("default", 0))
            if "min" in spec:
                n = max(spec["min"], n)
            if "max" in spec:
                n = min(spec["max"], n)
            return str(n)
        case "enum":
            value = str(raw_value)
            if value in spec.get("options", []):
                return value
            return str(spec.get("default", ""))
        case _:  # string
            value = str(raw_value)
            if "max_length" in spec:
                value = value[: spec["max_length"]]
            return value
