/**
 * Static catalog of common Minecraft server commands.
 *
 * We don't query the server for tab-completion (it'd cost an RCON round
 * trip per keystroke); we ship the well-known commands here and complete
 * client-side. Coverage: vanilla 1.19+, Paper / Spigot extras. Unknown
 * commands still go through — this is purely additive UX.
 */

export interface CommandHint {
  name: string
  /** Short, fit-on-one-line summary. */
  description: string
  /** Sub-tokens proposed when the user has typed ``<name> ``. */
  subArgs?: string[]
}

export const COMMANDS: CommandHint[] = [
  // Server lifecycle / housekeeping
  { name: 'help', description: 'List all commands or detail one' },
  { name: 'list', description: 'List players currently online' },
  { name: 'save-all', description: 'Save the world to disk', subArgs: ['flush'] },
  { name: 'save-on', description: 'Enable periodic auto-saves' },
  { name: 'save-off', description: 'Disable auto-saves' },
  { name: 'stop', description: 'Gracefully stop the server' },
  { name: 'reload', description: 'Reload datapacks/plugins (lighter than restart)' },
  { name: 'seed', description: 'Print the world seed' },
  { name: 'setworldspawn', description: 'Set the spawn point' },

  // Permissions / access
  { name: 'op', description: 'Grant operator status to a player' },
  { name: 'deop', description: 'Revoke operator status' },
  { name: 'kick', description: 'Kick a player' },
  { name: 'ban', description: 'Ban a player' },
  { name: 'ban-ip', description: 'Ban an IP' },
  { name: 'pardon', description: 'Unban a player' },
  { name: 'pardon-ip', description: 'Unban an IP' },
  {
    name: 'whitelist',
    description: 'Manage the whitelist',
    subArgs: ['add', 'remove', 'list', 'on', 'off', 'reload'],
  },

  // Gameplay state
  {
    name: 'gamemode',
    description: 'Set a player gamemode',
    subArgs: ['survival', 'creative', 'spectator', 'adventure'],
  },
  {
    name: 'defaultgamemode',
    description: 'Default gamemode for new players',
    subArgs: ['survival', 'creative', 'spectator', 'adventure'],
  },
  {
    name: 'difficulty',
    description: 'Set the world difficulty',
    subArgs: ['peaceful', 'easy', 'normal', 'hard'],
  },
  {
    name: 'weather',
    description: 'Set the weather',
    subArgs: ['clear', 'rain', 'thunder'],
  },
  { name: 'time', description: 'Set / add / query the world time', subArgs: ['set', 'add', 'query'] },
  { name: 'gamerule', description: 'Read or set a gamerule' },
  { name: 'worldborder', description: 'Manage the world border', subArgs: ['set', 'center', 'damage', 'warning'] },

  // Player ops
  { name: 'give', description: 'Give items to a player' },
  { name: 'clear', description: 'Clear inventory items' },
  { name: 'kill', description: 'Kill an entity' },
  { name: 'teleport', description: 'Teleport an entity', subArgs: ['@p', '@a', '@s'] },
  { name: 'tp', description: 'Alias for /teleport', subArgs: ['@p', '@a', '@s'] },
  { name: 'spectate', description: 'Spectate a player' },
  { name: 'xp', description: 'Award or query XP', subArgs: ['add', 'set', 'query'] },
  { name: 'experience', description: 'Alias for /xp', subArgs: ['add', 'set', 'query'] },
  { name: 'effect', description: 'Apply / clear status effects', subArgs: ['give', 'clear'] },
  { name: 'enchant', description: 'Enchant the held item' },
  { name: 'spawnpoint', description: 'Set a player spawnpoint' },

  // Communication
  { name: 'msg', description: 'Whisper to a player' },
  { name: 'tell', description: 'Alias for /msg' },
  { name: 'w', description: 'Alias for /msg' },
  { name: 'say', description: 'Broadcast a chat message' },
  { name: 'me', description: 'Emote in the chat' },
  { name: 'tellraw', description: 'Send a JSON-formatted message' },
  { name: 'title', description: 'Show a title to a player', subArgs: ['title', 'subtitle', 'actionbar', 'clear', 'reset'] },

  // World data
  { name: 'fill', description: 'Fill a region with a block' },
  { name: 'setblock', description: 'Place a block' },
  { name: 'clone', description: 'Clone a region' },
  { name: 'summon', description: 'Summon an entity' },
  { name: 'locate', description: 'Locate a structure or biome', subArgs: ['structure', 'biome', 'poi'] },
  { name: 'particle', description: 'Spawn particles' },
  { name: 'playsound', description: 'Play a sound' },
  { name: 'stopsound', description: 'Stop a playing sound' },
  { name: 'forceload', description: 'Force-load chunks', subArgs: ['add', 'remove', 'query'] },

  // Scripting / scoreboards
  { name: 'execute', description: 'Conditional / contextual execution' },
  { name: 'function', description: 'Run a datapack function' },
  { name: 'datapack', description: 'Manage datapacks', subArgs: ['enable', 'disable', 'list'] },
  { name: 'data', description: 'Read / modify NBT', subArgs: ['get', 'merge', 'modify', 'remove'] },
  { name: 'scoreboard', description: 'Manage scoreboards', subArgs: ['objectives', 'players'] },
  { name: 'tag', description: 'Manage entity tags', subArgs: ['add', 'remove', 'list'] },
  { name: 'team', description: 'Manage teams', subArgs: ['add', 'remove', 'list', 'join', 'leave'] },
  { name: 'trigger', description: 'Trigger a scoreboard objective', subArgs: ['add', 'set'] },
  { name: 'bossbar', description: 'Manage boss bars', subArgs: ['add', 'remove', 'list', 'set'] },
  { name: 'attribute', description: 'Read / modify attributes', subArgs: ['get', 'base', 'modifier'] },
  { name: 'advancement', description: 'Grant / revoke advancements', subArgs: ['grant', 'revoke'] },
  { name: 'recipe', description: 'Give / take recipes', subArgs: ['give', 'take'] },
  { name: 'schedule', description: 'Schedule a function', subArgs: ['function', 'clear'] },
  { name: 'item', description: 'Modify items in slots', subArgs: ['replace', 'modify'] },
  { name: 'loot', description: 'Drop loot from a table' },
  { name: 'debug', description: 'Toggle debug profiler', subArgs: ['start', 'stop', 'report'] },
  { name: 'jfr', description: 'JFR profiling', subArgs: ['start', 'stop'] },

  // Paper-specific niceties (no-ops on vanilla)
  { name: 'tps', description: 'Paper — current TPS / MSPT' },
  { name: 'mspt', description: 'Paper — milliseconds per tick' },
  { name: 'version', description: 'Server version + build' },
  { name: 'plugins', description: 'List installed plugins' },
  { name: 'restart', description: 'Paper — restart the server' },
  {
    name: 'paper',
    description: 'Paper-specific subcommands',
    subArgs: ['reload', 'version', 'dumpitem', 'dumpplugins', 'mobcaps', 'syncloadinfo'],
  },
]


export interface Suggestion {
  /** What the suggestion replaces the current token with. */
  replace: string
  /** What gets shown to the user — same as ``replace`` for commands,
   *  the sub-arg label for sub-arg completions. */
  label: string
  /** Optional second-line hint. */
  description: string
  /** True when accepting this suggestion should append a trailing space
   *  (commands and most sub-args). */
  trailingSpace: boolean
}


/**
 * Compute completion candidates for the current input.
 *
 * Strategy:
 * - 1st token (the command): prefix-match against COMMANDS.
 * - After 1st token: if the typed command has ``subArgs``, suggest those
 *   that prefix-match the in-progress token.
 *
 * No completion past the second token — beyond that, command grammars
 * diverge too much to be useful without a real parser.
 */
export function suggestionsFor(input: string): Suggestion[] {
  const raw = input.startsWith('/') ? input.slice(1) : input
  const endsWithSpace = raw.length > 0 && raw.endsWith(' ')
  const tokens = raw.split(/\s+/)
  const first = tokens[0] || ''

  // 1st token still being typed.
  if (tokens.length === 1 && !endsWithSpace) {
    if (!first) return []
    const lower = first.toLowerCase()
    return COMMANDS
      .filter((c) => c.name.startsWith(lower))
      .slice(0, 8)
      .map((c) => ({
        replace: c.name,
        label: c.name,
        description: c.description,
        trailingSpace: true,
      }))
  }

  // 2nd token: sub-arg completion if we recognise the command.
  const cmd = COMMANDS.find((c) => c.name === first.toLowerCase())
  if (!cmd?.subArgs) return []
  const current = endsWithSpace ? '' : (tokens[tokens.length - 1] || '')
  const lower = current.toLowerCase()
  const matches = cmd.subArgs.filter((s) => s.toLowerCase().startsWith(lower))
  return matches.slice(0, 8).map((s) => ({
    replace: s,
    label: s,
    description: '',
    trailingSpace: true,
  }))
}


/**
 * Apply a chosen suggestion to the current input, replacing the last
 * (in-progress) token. Returns the new input string.
 */
export function applySuggestion(input: string, sug: Suggestion): string {
  const leading = input.startsWith('/') ? '/' : ''
  const body = leading ? input.slice(1) : input
  const endsWithSpace = body.length > 0 && body.endsWith(' ')

  if (endsWithSpace) {
    // User stopped at a space — append the suggestion.
    return leading + body + sug.replace + (sug.trailingSpace ? ' ' : '')
  }
  const tokens = body.split(/\s+/)
  tokens[tokens.length - 1] = sug.replace
  return leading + tokens.join(' ') + (sug.trailingSpace ? ' ' : '')
}
