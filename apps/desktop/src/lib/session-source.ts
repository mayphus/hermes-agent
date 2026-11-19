import { atom } from 'nanostores'

import { normalize } from '@/lib/text'

const SOURCE_LABELS: Record<string, string> = {
  acp: 'ACP',
  api_server: 'API',
  bluebubbles: 'iMessage',
  cli: 'CLI',
  codex: 'Codex',
  desktop: 'Desktop',
  discord: 'Discord',
  email: 'Email',
  gateway: 'Gateway',
  kanban: 'Kanban',
  local: 'Local',
  matrix: 'Matrix',
  mattermost: 'Mattermost',
  oneshot: 'One-shot',
  photon: 'Photon',
  qqbot: 'QQ',
  signal: 'Signal',
  slack: 'Slack',
  sms: 'SMS',
  telegram: 'Telegram',
  tui: 'TUI',
  webhook: 'Webhook',
  weixin: 'WeChat',
  whatsapp: 'WhatsApp',
  yuanbao: 'Yuanbao'
}

const SOURCE_ALIASES: Record<string, string[]> = {
  bluebubbles: ['apple messages', 'imessage'],
  photon: ['imessage', 'messages'],
  cli: ['terminal'],
  desktop: ['app', 'gui'],
  local: ['machine'],
  qqbot: ['qq'],
  telegram: ['tg'],
  tui: ['terminal'],
  weixin: ['wechat'],
  whatsapp: ['wa']
}

// Sources that run on the local machine rather than an external messaging
// platform. A handoff *from* one of these isn't a platform origin worth a badge.
// Exported so the recents fetch can keep these in the main list while the
// messaging fetch excludes them. `acp` runs as a local stdio process spawned
// by an editor, and its rows must never land in the messaging slice either.
export const LOCAL_SESSION_SOURCE_IDS = [
  'acp',
  'cli',
  'codex',
  'desktop',
  'gateway',
  'kanban',
  'local',
  'oneshot',
  'tui'
]
const LOCAL_SOURCE_IDS = new Set(LOCAL_SESSION_SOURCE_IDS)

// External messaging platforms that each get their own self-managed sidebar
// section (fetched separately from local recents). Mirrors the gateway platform
// adapters; keep in sync with PLATFORM_ICONS in app/messaging/platform-icon.tsx.
export const MESSAGING_SESSION_SOURCE_IDS = [
  'telegram',
  'discord',
  'slack',
  'mattermost',
  'matrix',
  'signal',
  'whatsapp',
  'bluebubbles',
  'photon',
  'homeassistant',
  'email',
  'sms',
  'webhook',
  'api_server',
  'weixin',
  'wecom',
  'qqbot',
  'yuanbao',
  'dingtalk',
  'feishu'
]
const MESSAGING_SOURCE_IDS = new Set(MESSAGING_SESSION_SOURCE_IDS)

// Sources that are never a messaging platform, even if a backend catalog
// lists them: local surfaces plus the cron/subagent/tool bookkeeping sources.
const NEVER_MESSAGING_SOURCE_IDS = new Set([...LOCAL_SESSION_SOURCE_IDS, 'cron', 'subagent', 'tool'])

/** A gateway platform the connected backend reports via
 *  `GET /api/messaging/platforms`: built-in adapters AND plugin-registered
 *  platforms (`ctx.register_platform(...)`, e.g. a OneBot, SimpleX or voice
 *  adapter). The hardcoded list above stays the fallback for an older backend
 *  or before the catalog has loaded. */
export interface RegisteredMessagingPlatform {
  id: string
  name?: null | string
}

const REGISTERED_PLATFORMS_STORAGE_KEY = 'hermes.registeredMessagingPlatforms.v1'

function readCachedRegisteredPlatforms(): Record<string, string> {
  try {
    const raw = globalThis.localStorage?.getItem(REGISTERED_PLATFORMS_STORAGE_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : null

    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return Object.fromEntries(
        Object.entries(parsed as Record<string, unknown>).filter(
          (entry): entry is [string, string] => typeof entry[1] === 'string'
        )
      )
    }
  } catch {
    // Storage unavailable or corrupt: start empty, the catalog fetch refills it.
  }

  return {}
}

/** Registered (non-hardcoded) messaging platforms: normalized id -> display
 *  name. Seeded from the last catalog seen so plugin sections render on the
 *  first paint instead of flashing through local recents. */
export const $registeredMessagingPlatforms = atom<Record<string, string>>(readCachedRegisteredPlatforms())

/** Record the backend's platform catalog. Returns true when the set of
 *  messaging source ids changed (callers re-fetch the sidebar slices then). */
export function setRegisteredMessagingPlatforms(platforms: readonly RegisteredMessagingPlatform[]): boolean {
  const next: Record<string, string> = {}

  for (const platform of platforms) {
    const id = normalizeSessionSource(platform.id)

    if (!id || NEVER_MESSAGING_SOURCE_IDS.has(id) || MESSAGING_SOURCE_IDS.has(id)) {
      continue
    }

    next[id] = platform.name?.trim() || id
  }

  const prev = $registeredMessagingPlatforms.get()
  const prevKeys = Object.keys(prev).sort().join('\u0000')
  const nextKeys = Object.keys(next).sort().join('\u0000')
  const changed = prevKeys !== nextKeys

  if (changed || Object.keys(next).some(id => prev[id] !== next[id])) {
    $registeredMessagingPlatforms.set(next)

    try {
      globalThis.localStorage?.setItem(REGISTERED_PLATFORMS_STORAGE_KEY, JSON.stringify(next))
    } catch {
      // Non-fatal: the cache only speeds up the next launch.
    }
  }

  return changed
}

/** Every source id that gets its own sidebar section: the built-in list plus
 *  whatever the backend registered (plugins included). */
export function messagingSessionSourceIds(): string[] {
  return [...MESSAGING_SESSION_SOURCE_IDS, ...Object.keys($registeredMessagingPlatforms.get())]
}

/** True when a source id is an external messaging platform (gets its own
 *  sidebar section) rather than a local/CLI/desktop session. */
export function isMessagingSource(source: null | string | undefined): boolean {
  const id = normalizeSessionSource(source)

  return id != null && (MESSAGING_SOURCE_IDS.has(id) || id in $registeredMessagingPlatforms.get())
}

export function normalizeSessionSource(source: null | string | undefined): string | null {
  return normalize(source) || null
}

/**
 * Resolve the origin messaging platform for a handed-off session. Returns the
 * normalized platform id (e.g. 'telegram') when the session completed a handoff
 * from a real messaging platform, otherwise null. After a handoff the live
 * source is local, so this is what drives the row's origin-platform badge.
 */
export function handoffOriginSource(
  handoffState: null | string | undefined,
  handoffPlatform: null | string | undefined
): string | null {
  if (handoffState !== 'completed') {
    return null
  }

  const id = normalizeSessionSource(handoffPlatform)

  if (!id || LOCAL_SOURCE_IDS.has(id)) {
    return null
  }

  return id
}

export function sessionSourceLabel(source: null | string | undefined): string | null {
  const id = normalizeSessionSource(source)

  if (!id) {
    return null
  }

  return (
    SOURCE_LABELS[id] ||
    $registeredMessagingPlatforms.get()[id] ||
    id.replace(/[_-]+/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
  )
}

export function sessionSourceSearchTerms(source: null | string | undefined): string[] {
  const id = normalizeSessionSource(source)
  const label = sessionSourceLabel(id)

  if (!id) {
    return []
  }

  return [id, label ?? '', ...(SOURCE_ALIASES[id] ?? [])].filter(Boolean)
}
