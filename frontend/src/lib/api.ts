import ky, { HTTPError } from 'ky'
import { toast } from 'vue-sonner'
import { i18n } from '@/i18n'

const t = (key: string, params?: Record<string, unknown>) =>
  i18n.global.t(key, params ?? {}) as string

export const api = ky.create({
  prefixUrl: '/api/',
  timeout: 30_000,
  retry: { limit: 2, methods: ['get'] },
  hooks: {
    beforeRequest: [
      (request) => {
        const token = localStorage.getItem('hostcraft.token')
        if (token) {
          request.headers.set('Authorization', `Bearer ${token}`)
        }
        // Tell Django which locale to use for gettext() messages.
        request.headers.set('Accept-Language', i18n.global.locale.value)
      },
    ],
    afterResponse: [
      async (_request, _options, response) => {
        // Auth store handles 401 redirects centrally — see stores/auth.ts.
        return response
      },
    ],
  },
})

// ---------------------------------------------------------------------------
// Public endpoints
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: string
  time: string
}

export interface VersionResponse {
  name: string
  version: string
}

export const apiClient = {
  health: () => api.get('health/').json<HealthResponse>(),
  version: () => api.get('version/').json<VersionResponse>(),
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface LoginPayload {
  username: string
  password: string
}

export interface TokenPair {
  access: string
  refresh: string
}

export interface CurrentUser {
  id: number
  username: string
  is_staff: boolean
  date_joined: string
}

export const authApi = {
  login: (creds: LoginPayload) =>
    api.post('auth/login/', { json: creds }).json<TokenPair>(),
  refresh: (refresh: string) =>
    api.post('auth/refresh/', { json: { refresh } }).json<{ access: string }>(),
  me: () => api.get('auth/me/').json<CurrentUser>(),
}

// ---------------------------------------------------------------------------
// Server lifecycle
// ---------------------------------------------------------------------------

export type ServerState =
  | 'running'
  | 'exited'
  | 'created'
  | 'restarting'
  | 'paused'
  | 'absent'
  | 'error'
  | 'unknown'

export interface ServerStatus {
  state: ServerState
  started_at: string | null
  image: string
  health: 'healthy' | 'unhealthy' | 'starting' | 'none' | null
  uptime_seconds: number | null
  error: string | null
  restart_count: number
  crash_looping: boolean
  last_exit_code: number | null
}

export const serverApi = {
  status: () => api.get('server/status/').json<ServerStatus>(),
  start: () => api.post('server/start/').json<ServerStatus>(),
  stop: (timeout = 60) =>
    api.post('server/stop/', { json: { timeout }, timeout: (timeout + 10) * 1000 }).json<ServerStatus>(),
  restart: (timeout = 60) =>
    api
      .post('server/restart/', { json: { timeout }, timeout: (timeout + 15) * 1000 })
      .json<ServerStatus>(),
}

// ---------------------------------------------------------------------------
// File manager
// ---------------------------------------------------------------------------

export interface FileEntry {
  name: string
  is_dir: boolean
  size: number
  modified: number  // unix timestamp seconds
}

export interface FilesListing {
  path: string
  entries: FileEntry[]
}

export interface FileContent {
  path: string
  content: string
  encoding: string
  size: number
}

// ---------------------------------------------------------------------------
// server.properties (visual editor)
// ---------------------------------------------------------------------------

export type PropertyType = 'string' | 'integer' | 'boolean' | 'enum'

export interface PropertySpec {
  type: PropertyType
  section: string
  default: string | number | boolean
  options?: string[]
  min?: number
  max?: number
  max_length?: number
}

export interface PropertiesPayload {
  values: Record<string, string | number | boolean>
  schema: Record<string, PropertySpec>
  sections: string[]
  unknown_keys: string[]
}

export const propertiesApi = {
  get: () => api.get('server/properties/').json<PropertiesPayload>(),
  save: (values: Record<string, unknown>) =>
    api.put('server/properties/', { json: { values } }).json<PropertiesPayload>(),
}

// ---------------------------------------------------------------------------
// Players (whitelist + ops)
// ---------------------------------------------------------------------------

export interface WhitelistEntry {
  uuid: string
  name: string
}

export interface OpEntry {
  uuid: string
  name: string
  level: number
  bypassesPlayerLimit: boolean
}

export const whitelistApi = {
  list: () => api.get('server/whitelist/').json<{ entries: WhitelistEntry[] }>(),
  add: (name: string) =>
    api
      .post('server/whitelist/', { json: { name } })
      .json<{ entry: WhitelistEntry; entries: WhitelistEntry[] }>(),
  remove: (uuid: string) =>
    api
      .delete('server/whitelist/', { searchParams: { uuid } })
      .json<{ entries: WhitelistEntry[] }>(),
}

// ---------------------------------------------------------------------------
// Backups
// ---------------------------------------------------------------------------

export type BackupKind = 'world' | 'full'
export type BackupStatus = 'pending' | 'running' | 'ready' | 'failed'

export type RemoteStatus = 'none' | 'pending' | 'uploading' | 'uploaded' | 'failed'
export type RestoreStatus = 'idle' | 'running' | 'done' | 'failed'

export interface BackupEntry {
  id: number
  name: string
  size_bytes: number
  kind: BackupKind
  status: BackupStatus
  error: string
  created_at: string
  completed_at: string | null
  remote_status: RemoteStatus
  remote_destination: number | null
  remote_destination_name: string
  remote_key: string
  remote_error: string
  restore_status: RestoreStatus
  restore_error: string
  restored_at: string | null
}

export const backupsApi = {
  list: () => api.get('backups/').json<{ entries: BackupEntry[] }>(),
  sizes: () => api.get('backups/sizes/').json<Record<BackupKind, number>>(),
  create: (kind: BackupKind = 'world', name?: string) =>
    api.post('backups/', { json: { kind, name } }).json<BackupEntry>(),
  uploadTo: (id: number, destinationId: number) =>
    api
      .post(`backups/${id}/upload/`, { searchParams: { destination: destinationId } })
      .json<BackupEntry>(),
  restore: (id: number) =>
    api.post(`backups/${id}/restore/`, { timeout: 30_000 }).json<BackupEntry>(),
  remove: (id: number) => api.delete(`backups/${id}/`).then(() => undefined),
  downloadUrl: (id: number) => `/api/backups/${id}/download/`,
}

// ---------------------------------------------------------------------------
// Runtime tuning (Java memory, Aikar flags, JVM args)
// ---------------------------------------------------------------------------

export interface RuntimeSnapshot {
  image: string
  image_tag: string
  state: string
  error: string | null
  values: {
    TYPE: string
    VERSION: string
    MEMORY: string
    USE_AIKAR_FLAGS: string
    JVM_OPTS: string
    JVM_XX_OPTS: string
  }
  editable_keys: string[]
  risky_keys: string[]
}

export interface JavaTag {
  tag: string         // 'latest' | 'java25' | …
  label: string
  java: number        // 0 = auto (latest)
  lts: boolean
}

export interface RuntimeOptions {
  types: { value: string; label: string; loader: string }[]
  version_presets: string[]
  java_tags: JavaTag[]
  current_image_tag: string
  min_java_for_current_mc: number | null
  recommended_java_for_current_mc: number | null
  resolved_mc_version: string
}

export const runtimeApi = {
  get: () => api.get('server/runtime/').json<RuntimeSnapshot>(),
  options: () => api.get('server/runtime/options/').json<RuntimeOptions>(),
  apply: (
    values: Record<string, string | boolean>,
    opts: { image_tag?: string; engine_reset?: boolean } = {},
  ) => {
    const body: Record<string, unknown> = { values }
    if (opts.image_tag != null) body.image_tag = opts.image_tag
    if (opts.engine_reset) body.engine_reset = true
    return api
      .put('server/runtime/', { json: body, timeout: 120_000 })
      .json<RuntimeSnapshot>()
  },
}

export const opsApi = {
  list: () => api.get('server/ops/').json<{ entries: OpEntry[] }>(),
  add: (name: string, level = 4, bypassesPlayerLimit = false) =>
    api
      .post('server/ops/', { json: { name, level, bypassesPlayerLimit } })
      .json<{ entry: OpEntry; entries: OpEntry[] }>(),
  update: (uuid: string, payload: { level?: number; bypassesPlayerLimit?: boolean }) =>
    api
      .patch('server/ops/', { searchParams: { uuid }, json: payload })
      .json<{ entry: OpEntry; entries: OpEntry[] }>(),
  remove: (uuid: string) =>
    api.delete('server/ops/', { searchParams: { uuid } }).json<{ entries: OpEntry[] }>(),
}

// ---------------------------------------------------------------------------
// File manager
// ---------------------------------------------------------------------------

export const filesApi = {
  list: (path: string = '') =>
    api.get('files/', { searchParams: { path } }).json<FilesListing>(),
  read: (path: string) =>
    api.get('files/read/', { searchParams: { path } }).json<FileContent>(),
  write: (path: string, content: string) =>
    api.put('files/write/', { searchParams: { path }, json: { content } }).json<FileEntry>(),
  upload: (path: string, files: File[]) => {
    const fd = new FormData()
    for (const f of files) fd.append(f.name, f)
    return api
      .post('files/upload/', { searchParams: { path }, body: fd, timeout: false })
      .json<{ uploaded: FileEntry[] }>()
  },
  mkdir: (path: string) =>
    api.post('files/mkdir/', { searchParams: { path } }).json<FileEntry>(),
  delete: (path: string) =>
    api.delete('files/delete/', { searchParams: { path } }).then(() => undefined),
  move: (from: string, to: string) =>
    api.post('files/move/', { json: { from, to } }).json<FileEntry>(),
  downloadUrl: (path: string) => `/api/files/download/?path=${encodeURIComponent(path)}`,
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Authenticated download: fetch via ky (Bearer token attached by hooks),
 * then trigger a real browser download with a programmatic <a download>.
 *
 * Why not `window.open(url)`? Because the new tab/window has no Authorization
 * header, so the backend would reject it with 401.
 */
export async function downloadAuthenticated(path: string, filename: string): Promise<void> {
  const toastId = toast.loading(t('common.downloading'))
  try {
    const blob = await api.get(path, { timeout: false }).blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
    toast.success(t('common.downloadStarted'), { id: toastId, duration: 2000 })
  } catch (err) {
    toast.error(t('common.downloadFailed'), {
      id: toastId,
      description: await extractErrorMessage(err),
    })
  }
}

export async function extractErrorMessage(err: unknown): Promise<string> {
  if (err instanceof HTTPError) {
    try {
      const body = (await err.response.clone().json()) as Record<string, unknown>
      if (typeof body.detail === 'string') return body.detail
      const firstKey = Object.keys(body)[0]
      if (firstKey && Array.isArray(body[firstKey])) return String((body[firstKey] as string[])[0])
    } catch {
      /* fall through */
    }
    return err.message
  }
  if (err instanceof Error) return err.message
  return 'Unknown error'
}

// ---------------------------------------------------------------------------
// Activity / audit log
// ---------------------------------------------------------------------------

export interface AuditEntry {
  id: number
  user: string | null
  action: string
  method: string
  target: string
  status: 'success' | 'failed'
  status_code: number
  duration_ms: number | null
  created_at: string
}

export interface AuditQuery {
  limit?: number
  since?: string  // ISO-8601
  until?: string  // ISO-8601
  status?: 'success' | 'failed'
  action?: string  // substring match
}

export const auditApi = {
  list: (q: AuditQuery = {}) => {
    const params: Record<string, string | number> = {}
    if (q.limit) params.limit = q.limit
    if (q.since) params.since = q.since
    if (q.until) params.until = q.until
    if (q.status) params.status = q.status
    if (q.action) params.action = q.action
    return api
      .get('audit/', { searchParams: params })
      .json<{ entries: AuditEntry[]; count: number; limit: number }>()
  },
}

// ---------------------------------------------------------------------------
// Realtime stats (Dashboard)
// ---------------------------------------------------------------------------

export interface RealtimeStats {
  cpu_percent: number | null
  memory_used: number | null
  memory_limit: number | null
  players_online: number | null
  players_max: number | null
  tps: [number, number, number] | null
}

export interface PerfSample {
  t: string
  cpu_percent: number | null
  memory_used: number | null
  memory_limit: number | null
  players_online: number | null
  players_max: number | null
  tps_1m: number | null
}

export type PerfWindow = '1h' | '6h' | '24h' | '7d'

export const realtimeApi = {
  get: () => api.get('server/realtime/').json<RealtimeStats>(),
  history: (window: PerfWindow = '1h') =>
    api
      .get('server/realtime/history/', { searchParams: { window } })
      .json<{ window: PerfWindow; samples: PerfSample[] }>(),
}

// ---------------------------------------------------------------------------
// Schedules
// ---------------------------------------------------------------------------

export type ScheduleKind = 'restart' | 'backup_world' | 'backup_full' | 'rcon'
export type ScheduleStatus = 'never_run' | 'running' | 'success' | 'failed'

export interface Schedule {
  id: number
  name: string
  kind: ScheduleKind
  cron: string
  payload: Record<string, unknown>
  enabled: boolean
  last_run_at: string | null
  last_status: ScheduleStatus
  last_error: string
  next_run_at: string | null
  created_at: string
  updated_at: string
}

export type SchedulePayload = Pick<Schedule, 'name' | 'kind' | 'cron' | 'enabled'> & {
  payload?: Record<string, unknown>
}

export const schedulesApi = {
  list: () => api.get('schedules/').json<{ entries: Schedule[] }>(),
  create: (data: SchedulePayload) => api.post('schedules/', { json: data }).json<Schedule>(),
  update: (id: number, data: Partial<SchedulePayload>) =>
    api.patch(`schedules/${id}/`, { json: data }).json<Schedule>(),
  remove: (id: number) => api.delete(`schedules/${id}/`).then(() => undefined),
  runNow: (id: number) => api.post(`schedules/${id}/run/`).json<{ queued: boolean }>(),
}

// ---------------------------------------------------------------------------
// Network — public access mode, custom domain, allocations
// ---------------------------------------------------------------------------

export type NetworkMode = 'direct' | 'playit_guided' | 'playit_managed'

export interface NetworkProfile {
  mode: NetworkMode
  custom_domain: string
  playit_hostname: string
  has_playit_agent_key: boolean
  public_ip_override: string
  updated_at: string
}

export type NetworkProfilePatch = Partial<
  Pick<
    NetworkProfile,
    'mode' | 'custom_domain' | 'playit_hostname' | 'public_ip_override'
  >
> & { playit_agent_key?: string }

export type AllocationProtocol = 'tcp' | 'udp'

export interface Allocation {
  id: number
  label: string
  host_port: number
  container_port: number
  protocol: AllocationProtocol
  notes: string
  created_at: string
}

export type AllocationPayload = Pick<
  Allocation,
  'label' | 'host_port' | 'container_port' | 'protocol'
> & { notes?: string }

export interface DnsRecord {
  type: 'A' | 'CNAME' | 'SRV' | 'TXT'
  name: string
  value: string
  ttl: number
  note?: string
}

export interface NetworkPayload {
  profile: NetworkProfile
  public_ip: string | null
  primary_port: number
  allocations: Allocation[]
  dns_records: DnsRecord[]
}

export interface PlayitAgentStatus {
  state: 'absent' | 'created' | 'running' | 'restarting' | 'exited' | 'error' | 'unknown'
  image: string
  started_at: string | null
  error: string | null
  has_secret: boolean
  hostname: string             // mirror of profile.playit_hostname (what the panel uses for DNS)
  detected_hostname: string    // sniffed from agent logs / playit API — empty until the tunnel is up
  /** ready = tunnel configured · no_tunnel = valid secret but nothing
   *  set up on playit.gg yet · unknown = API unreachable / no secret. */
  playit_setup: 'ready' | 'no_tunnel' | 'unknown'
  /** Current Docker-network IP of the MC container — what the user pastes
   *  into playit.gg's "Local IP" field. Empty if container isn't up. */
  mc_container_ip: string
}

export const networkApi = {
  get: () => api.get('network/').json<NetworkPayload>(),
  update: (data: NetworkProfilePatch) =>
    api.patch('network/', { json: data }).json<NetworkPayload>(),
  refreshIp: () =>
    api.post('network/refresh-ip/').json<{ public_ip: string | null }>(),
  createAllocation: (data: AllocationPayload) =>
    api.post('network/allocations/', { json: data }).json<Allocation>(),
  updateAllocation: (id: number, data: Partial<AllocationPayload>) =>
    api.patch(`network/allocations/${id}/`, { json: data }).json<Allocation>(),
  removeAllocation: (id: number) =>
    api.delete(`network/allocations/${id}/`).then(() => undefined),
  playitAgent: () => api.get('network/playit/agent/').json<PlayitAgentStatus>(),
  playitAgentStart: (secret?: string) =>
    api
      .post('network/playit/agent/', {
        json: secret ? { secret } : {},
        timeout: 60_000,
      })
      .json<PlayitAgentStatus>(),
  playitAgentStop: () =>
    api.delete('network/playit/agent/').json<PlayitAgentStatus>(),
  playitAgentLogs: (tail = 200) =>
    api
      .get('network/playit/agent/logs/', { searchParams: { tail: String(tail) } })
      .json<{ logs: string }>(),
  playitAgentRefresh: () =>
    api.post('network/playit/agent/refresh/').json<PlayitAgentStatus>(),
}

// ---------------------------------------------------------------------------
// Watchdog — auto-restart on unhealthy
// ---------------------------------------------------------------------------

export interface WatchdogConfig {
  enabled: boolean
  threshold_seconds: number
  max_restarts_per_hour: number
  last_restart_at: string | null
  total_restarts: number
}

export const watchdogApi = {
  get: () => api.get('server/watchdog/').json<WatchdogConfig>(),
  update: (data: Partial<WatchdogConfig>) =>
    api.patch('server/watchdog/', { json: data }).json<WatchdogConfig>(),
}

// ---------------------------------------------------------------------------
// Server icon
// ---------------------------------------------------------------------------

export interface IconState {
  present: boolean
  size: number
  etag: string | null
}

export interface IconPreset {
  id: string
  name: string
}

export interface IconPayload {
  current: IconState
  presets: IconPreset[]
  max_upload_bytes: number
  size: number
}

export const iconApi = {
  get: () => api.get('server/icon/').json<IconPayload>(),
  remove: () => api.delete('server/icon/').json<IconPayload>(),
  applyPreset: (id: string) =>
    api.post('server/icon/preset/', { json: { id } }).json<IconPayload>(),
  upload: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.put('server/icon/upload/', { body: fd }).json<IconPayload>()
  },
  rawUrl: (etag: string | null) =>
    `/api/server/icon/raw/${etag ? `?v=${etag}` : ''}`,
  presetUrl: (id: string) => `/api/server/icon/presets/${id}/raw/`,
}

// ---------------------------------------------------------------------------
// World map (BlueMap)
// ---------------------------------------------------------------------------

export type WorldmapState = 'unsupported' | 'not_installed' | 'installed'

export interface WorldmapStatus {
  state: WorldmapState
  filename: string
  web_port: number
  target_kind: 'mod' | 'plugin' | 'none' | ''
  target_loader: string
}

export const worldmapApi = {
  status: () => api.get('worldmap/').json<WorldmapStatus>(),
  install: () =>
    api
      .post('worldmap/install/', { timeout: 120_000 })
      .json<{ status: WorldmapStatus; result: Record<string, unknown> }>(),
}

// ---------------------------------------------------------------------------
// Mods marketplace
// ---------------------------------------------------------------------------

export type ModProvider = 'modrinth' | 'hangar'
export type ModKind = 'mod' | 'plugin' | 'none'

export interface ModTarget {
  kind: ModKind
  folder: string
  loaders: string[]
  loader_label: string
  mc_version: string         // resolved (e.g. '1.21.4')
  mc_version_alias: string   // raw alias when different from resolved (e.g. 'LATEST'), '' otherwise
}

export type ModProjectType = 'mod' | 'plugin' | 'modpack' | 'datapack' | 'shader' | 'resourcepack'
export type ModSideSupport = 'required' | 'optional' | 'unsupported' | 'unknown'

export interface ModSearchHit {
  provider: ModProvider
  project_id: string
  slug: string
  title: string
  summary: string
  icon_url: string
  project_url: string
  downloads: number
  follows: number
  project_type: ModProjectType
  server_side: ModSideSupport
  client_side: ModSideSupport
  categories: string[]
  loaders: string[]
  mc_versions: string[]
  /** True when at least one version of the project supports the user's
   * (loader, mc) combo. Null when we couldn't fetch versions. */
  installable_for_target: boolean | null
  /** MC versions the project actually ships for the user's loader, sorted
   * ascending. Empty when the loader filter excludes everything. */
  compat_mc_versions_for_loader: string[]
}

export interface ModProviderError {
  provider: string
  error: string
}

export interface ModSearchPayload {
  hits: ModSearchHit[]
  total: number
  providers_errored: ModProviderError[]
  target: ModTarget
}

export interface ModDependency {
  project_id: string
  version_id: string | null
  kind: 'required' | 'optional' | 'incompatible' | 'embedded'
  name: string
}

export interface ModVersion {
  provider: ModProvider
  project_id: string
  version_id: string
  name: string
  version_number: string
  file_url: string
  filename: string
  file_size: number
  file_hash: string
  hash_algo: 'sha512' | 'sha256' | ''
  mc_versions: string[]
  loaders: string[]
  dependencies: ModDependency[]
  published_at: string
}

export interface InstalledMod {
  id: number
  provider: ModProvider
  project_id: string
  project_slug: string
  title: string
  icon_url: string
  project_url: string
  version_id: string
  version_number: string
  filename: string
  file_size: number
  kind: 'mod' | 'plugin'
  loader: string
  mc_version: string
  installed_at: string | null
  present_on_disk: boolean
}

export interface UntrackedJar {
  folder: string
  filename: string
  size: number
}

export interface InstalledPayload {
  tracked: InstalledMod[]
  untracked: UntrackedJar[]
  target: ModTarget
}

export interface InstallResult {
  id: number
  filename: string
  verified: boolean
  bytes_written: number
}

export interface ManualMeta {
  kind: 'mod' | 'plugin' | 'modpack' | 'unknown'
  loaders: string[]
  name: string
  version: string
  mc_version_range: string
  declared_minecraft: string[]
  can_install: boolean
  install_reason: string
}

export interface ManualVerdict {
  loader: 'ok' | 'mismatch' | 'unknown'
  mc: 'ok' | 'mismatch' | 'unknown'
  overall: 'ok' | 'warn' | 'block'
}

export interface ManualInspectPayload {
  meta: ManualMeta
  verdict: ManualVerdict
  filename: string
  size: number
  target: {
    kind: ModKind
    loaders: string[]
    loader_label: string
    mc_version: string
  }
}

export const modsApi = {
  target: () => api.get('mods/target/').json<ModTarget>(),
  search: (
    q: string,
    opts: { limit?: number; offset?: number; strictVersion?: boolean } = {},
  ) =>
    api
      .get('mods/search/', {
        searchParams: {
          q,
          limit: String(opts.limit ?? 24),
          offset: String(opts.offset ?? 0),
          strict_version: opts.strictVersion === false ? '0' : '1',
        },
      })
      .json<ModSearchPayload>(),
  versions: (provider: ModProvider, project_id: string) =>
    api
      .get('mods/versions/', { searchParams: { provider, project_id } })
      .json<{ versions: ModVersion[] }>(),
  installed: () => api.get('mods/installed/').json<InstalledPayload>(),
  install: (provider: ModProvider, project_id: string, version_id?: string) =>
    api
      .post('mods/install/', {
        json: { provider, project_id, version_id: version_id ?? null },
      })
      .json<InstallResult>(),
  uninstall: (id: number) =>
    api.delete(`mods/${id}/`).json<{ removed: string }>(),
  inspectUpload: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    // Inspect only reads the zip directory — fast even on big files, but
    // give it room for the upload itself on slow links.
    return api.post('mods/upload/inspect/', { body: fd, timeout: 5 * 60_000 })
      .json<ManualInspectPayload>()
  },
  uploadInstall: (file: File, force_kind?: 'mod' | 'plugin') => {
    const fd = new FormData()
    fd.append('file', file)
    if (force_kind) fd.append('force_kind', force_kind)
    // 10 min for a 1 GB modpack on a slow uplink.
    return api.post('mods/upload/', { body: fd, timeout: 10 * 60_000 })
      .json<{ id: number; filename: string; kind: string; size: number; meta: ManualMeta }>()
  },
}
