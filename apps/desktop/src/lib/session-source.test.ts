import { describe, expect, it } from 'vitest'

import {
  $registeredMessagingPlatforms,
  isMessagingSource,
  messagingSessionSourceIds,
  sessionSourceLabel,
  sessionSourceSearchTerms,
  setRegisteredMessagingPlatforms
} from './session-source'

// Regression guard for #46761 / PR #47395: Photon (iMessage) must keep its own
// sidebar section. refreshMessagingSessions() filters rows through
// isMessagingSource(), so this entry is the sole condition that keeps Photon
// sessions out of generic recents. A silent removal would regress the feature
// with no test failure — these asserts pin the contract.
describe('photon messaging source registration', () => {
  it('treats photon as a messaging source (own sidebar section)', () => {
    expect(isMessagingSource('photon')).toBe(true)
  })

  it('is case/space insensitive on the source id', () => {
    expect(isMessagingSource('PHOTON')).toBe(true)
    expect(isMessagingSource('  photon ')).toBe(true)
  })

  it('exposes the iMessage/messages search aliases so Photon sessions are findable', () => {
    const terms = sessionSourceSearchTerms('photon')
    expect(terms).toContain('imessage')
    expect(terms).toContain('messages')
  })

  it('does not flag local/CLI-ish sources as messaging (guard sanity)', () => {
    expect(isMessagingSource('cli')).toBe(false)
    expect(isMessagingSource(null)).toBe(false)
    expect(isMessagingSource(undefined)).toBe(false)
  })
})

// Plugin-registered gateway platforms (ctx.register_platform) are not in the
// hardcoded list; the backend's /api/messaging/platforms catalog teaches the
// sidebar about them so each still gets its own section (#79836).
describe('registered (plugin) messaging platforms', () => {
  it('is not a messaging source until the backend registers it', () => {
    setRegisteredMessagingPlatforms([])
    expect(isMessagingSource('voice')).toBe(false)
  })

  it('treats a registered plugin platform as a messaging source with its catalog label', () => {
    expect(
      setRegisteredMessagingPlatforms([
        { id: 'voice', name: 'Voice' },
        { id: 'telegram', name: 'Telegram' }
      ])
    ).toBe(true)
    expect(isMessagingSource('voice')).toBe(true)
    expect(isMessagingSource(' VOICE ')).toBe(true)
    expect(sessionSourceLabel('voice')).toBe('Voice')
    expect(messagingSessionSourceIds()).toContain('voice')
    expect(messagingSessionSourceIds()).toContain('telegram')
  })

  it('reports no change for the same id set', () => {
    expect(setRegisteredMessagingPlatforms([{ id: 'voice', name: 'Voice' }])).toBe(false)
  })

  it('never promotes local or bookkeeping sources to messaging', () => {
    setRegisteredMessagingPlatforms([{ id: 'cli' }, { id: 'desktop' }, { id: 'cron' }, { id: 'acp' }])
    expect(isMessagingSource('cli')).toBe(false)
    expect(isMessagingSource('cron')).toBe(false)
    expect($registeredMessagingPlatforms.get()).toEqual({})
  })

  it('keeps the hardcoded built-ins as a fallback with an empty catalog', () => {
    setRegisteredMessagingPlatforms([])
    expect(isMessagingSource('telegram')).toBe(true)
  })
})
