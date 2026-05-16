import { onUnmounted, ref, shallowRef, watch } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import { useAuthStore } from '@/stores/auth'
import { i18n } from '@/i18n'

const t = (key: string, params?: Record<string, unknown>) =>
  i18n.global.t(key, params ?? {}) as string

interface OutMsg {
  type: 'cmd'
  id: string
  text: string
}

interface InMsg {
  type: 'log' | 'reply' | 'info' | 'error'
  id?: string
  text: string
}

const COLORS = {
  reset: '\x1b[0m',
  dim: '\x1b[90m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  green: '\x1b[32m',
  cyan: '\x1b[36m',
  brand: '\x1b[38;5;78m', // emerald-ish
}

function classifyLog(line: string): string {
  if (/\bERROR\b|\bSEVERE\b/.test(line)) return COLORS.red
  if (/\bWARN(ING)?\b/.test(line)) return COLORS.yellow
  return ''
}

export interface UseConsoleOptions {
  historyKey?: string
  maxHistory?: number
}

export function useConsole(opts: UseConsoleOptions = {}) {
  const auth = useAuthStore()
  const term = shallowRef<Terminal | null>(null)
  const fit = new FitAddon()
  const ws = ref<WebSocket | null>(null)
  const connected = ref(false)
  const lastError = ref<string | null>(null)

  const historyKey = opts.historyKey ?? 'hostcraft.console.history'
  const maxHistory = opts.maxHistory ?? 100
  const history = ref<string[]>(loadHistory(historyKey))
  let historyIdx = -1

  function loadHistory(key: string): string[] {
    try {
      const raw = localStorage.getItem(key)
      return raw ? JSON.parse(raw) : []
    } catch {
      return []
    }
  }
  function persistHistory() {
    try {
      localStorage.setItem(historyKey, JSON.stringify(history.value.slice(0, maxHistory)))
    } catch { /* quota etc. */ }
  }

  function mount(el: HTMLElement) {
    const t = new Terminal({
      convertEol: true,
      cursorBlink: false,
      cursorStyle: 'bar',
      disableStdin: true,
      scrollback: 5000,
      fontFamily: '"JetBrains Mono", ui-monospace, monospace',
      fontSize: 12.5,
      lineHeight: 1.35,
      letterSpacing: 0,
      theme: {
        background: '#0a0a0a',
        foreground: '#e4e4e7',
        cursor: '#34d399',
        selectionBackground: 'rgba(52, 211, 153, 0.18)',
      },
    })
    t.loadAddon(fit)
    t.loadAddon(new WebLinksAddon())
    t.open(el)
    term.value = t
    queueMicrotask(() => fit.fit())
    open()
  }

  function fitNow() {
    try { fit.fit() } catch { /* element detached */ }
  }

  function writeLine(line: string, color = '') {
    term.value?.writeln(`${color}${line}${color ? COLORS.reset : ''}`)
  }

  function open() {
    const token = auth.token
    if (!token) {
      writeLine(t('console.notAuthenticated'), COLORS.red)
      return
    }
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${proto}//${location.host}/ws/console/?token=${encodeURIComponent(token)}`
    const sock = new WebSocket(url)
    ws.value = sock
    sock.onopen = () => {
      connected.value = true
      lastError.value = null
    }
    sock.onclose = (ev) => {
      connected.value = false
      const msg =
        ev.code === 4401
          ? t('console.disconnectedAuthFailed')
          : ev.reason
            ? t('console.disconnectedReason', { reason: ev.reason })
            : t('console.disconnectedGeneric')
      writeLine(msg, COLORS.dim)
    }
    sock.onerror = () => {
      lastError.value = t('console.wsError')
    }
    sock.onmessage = (ev) => {
      let msg: InMsg
      try { msg = JSON.parse(ev.data as string) } catch { return }
      if (msg.type === 'log') writeLine(msg.text, classifyLog(msg.text))
      else if (msg.type === 'reply') writeLine(`> ${msg.text}`, COLORS.cyan)
      else if (msg.type === 'info') writeLine(msg.text, COLORS.dim)
      else if (msg.type === 'error') writeLine(`[ERROR] ${msg.text}`, COLORS.red)
    }
  }

  function send(cmd: string) {
    const sock = ws.value
    if (!sock || sock.readyState !== WebSocket.OPEN) return
    const id = (crypto.randomUUID?.() ?? String(Date.now()))
    const text = cmd.trim()
    if (!text) return
    sock.send(JSON.stringify({ type: 'cmd', id, text } satisfies OutMsg))
    writeLine(`$ ${text}`, COLORS.brand)
    history.value = [text, ...history.value.filter((c) => c !== text)].slice(0, maxHistory)
    historyIdx = -1
    persistHistory()
  }

  function historyPrev(current: string): string {
    if (history.value.length === 0) return current
    historyIdx = Math.min(historyIdx + 1, history.value.length - 1)
    return history.value[historyIdx]
  }
  function historyNext(): string {
    if (historyIdx <= 0) {
      historyIdx = -1
      return ''
    }
    historyIdx -= 1
    return history.value[historyIdx]
  }

  function clear() {
    term.value?.clear()
  }

  /** Jump the terminal viewport to the most recent line. */
  function scrollToBottom() {
    term.value?.scrollToBottom()
  }

  /** Dump the entire scrollback (visible + buffered) to a plain string.
   *
   * Strips trailing whitespace on each line and drops empty trailing
   * lines so the clipboard payload doesn't include hundreds of empty
   * rows from a freshly-cleared buffer. */
  function bufferText(): string {
    const t = term.value
    if (!t) return ''
    const buf = t.buffer.active
    const lines: string[] = []
    for (let i = 0; i < buf.length; i++) {
      const line = buf.getLine(i)
      if (!line) continue
      lines.push(line.translateToString(true).replace(/\s+$/, ''))
    }
    while (lines.length && lines[lines.length - 1] === '') lines.pop()
    return lines.join('\n')
  }

  function close() {
    ws.value?.close()
    ws.value = null
    term.value?.dispose()
    term.value = null
  }

  // Refit on container resize. Caller can also call fitNow() manually.
  let observer: ResizeObserver | null = null
  function observe(el: HTMLElement) {
    observer = new ResizeObserver(() => fitNow())
    observer.observe(el)
  }

  onUnmounted(() => {
    observer?.disconnect()
    close()
  })

  watch(connected, (v) => {
    if (!v && term.value) {
      // already wrote disconnect line in onclose
    }
  })

  return {
    term,
    connected,
    lastError,
    history,
    mount,
    observe,
    fit: fitNow,
    send,
    historyPrev,
    historyNext,
    clear,
    scrollToBottom,
    bufferText,
  }
}
