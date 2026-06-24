import { act, cleanup, render } from '@testing-library/react'
import { QueryClient } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useRef } from 'react'

import { textPart, type ChatMessage } from '@/lib/chat-messages'
import { createClientSessionState } from '@/lib/chat-runtime'
import type { RpcEvent } from '@/types/hermes'

import type { ClientSessionState } from '../../types'

import { useMessageStream } from './use-message-stream'

const RUNTIME_SESSION_ID = 'runtime-1'
const STORED_SESSION_ID = 'stored-1'

type HydrateFromStoredSession = (
  attempts?: number,
  storedSessionId?: string | null,
  runtimeSessionId?: string | null
) => Promise<void>
type RefreshSessions = () => Promise<void>

function makeHarness(options: {
  hydrateFromStoredSession?: HydrateFromStoredSession
  refreshSessions?: RefreshSessions
  seed: ClientSessionState
}) {
  const stateMap = new Map<string, ClientSessionState>([[RUNTIME_SESSION_ID, options.seed]])
  const hydrateFromStoredSession = options.hydrateFromStoredSession ?? vi.fn<HydrateFromStoredSession>(async () => undefined)
  const refreshSessions = options.refreshSessions ?? vi.fn<RefreshSessions>(async () => undefined)
  let handleGatewayEvent: ((event: RpcEvent) => void) | null = null

  function Harness() {
    const activeSessionIdRef = useRef<string | null>(RUNTIME_SESSION_ID)
    const sessionStateByRuntimeIdRef = useRef(stateMap)

    const updateSessionState = (
      sessionId: string,
      updater: (state: ClientSessionState) => ClientSessionState,
      storedSessionId?: string | null
    ) => {
      const previous = stateMap.get(sessionId) ?? createClientSessionState(storedSessionId ?? null)
      const next = updater({ ...previous, messages: previous.messages })
      stateMap.set(sessionId, next)

      return next
    }

    ;({ handleGatewayEvent } = useMessageStream({
      activeSessionIdRef,
      hydrateFromStoredSession,
      queryClient: new QueryClient(),
      refreshHermesConfig: async () => undefined,
      refreshSessions,
      sessionStateByRuntimeIdRef,
      updateSessionState
    }))

    return null
  }

  render(<Harness />)

  return {
    getState: () => stateMap.get(RUNTIME_SESSION_ID)!,
    handle: (event: RpcEvent) => handleGatewayEvent?.(event),
    hydrateFromStoredSession,
    refreshSessions
  }
}

function assistantMessage(message: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: 'assistant-stream',
    role: 'assistant',
    parts: [textPart('partial answer')],
    pending: true,
    ...message
  }
}

afterEach(() => {
  cleanup()
})

describe('useMessageStream gateway disconnect recovery', () => {
  it('does not stamp a terminal assistant error on a recoverable gateway disconnect', async () => {
    const seed: ClientSessionState = {
      ...createClientSessionState(STORED_SESSION_ID, [
        { id: 'user-1', role: 'user', parts: [textPart('continue')] },
        assistantMessage()
      ]),
      awaitingResponse: true,
      busy: true,
      sawAssistantPayload: true,
      streamId: 'assistant-stream',
      turnStartedAt: 123
    }

    const harness = makeHarness({ seed })

    await act(async () => {
      harness.handle({
        session_id: RUNTIME_SESSION_ID,
        type: 'gateway.disconnected',
        payload: { message: 'Hermes background process exited' }
      })
    })

    const state = harness.getState()
    const assistant = state.messages.find(message => message.id === 'assistant-stream')

    expect(state.busy).toBe(false)
    expect(state.awaitingResponse).toBe(false)
    expect(state.streamId).toBeNull()
    expect(state.turnStartedAt).toBeNull()
    expect(assistant).toMatchObject({ pending: false })
    expect(assistant?.error).toBeUndefined()
    expect(harness.refreshSessions).toHaveBeenCalledTimes(1)
    expect(harness.hydrateFromStoredSession).toHaveBeenCalledWith(3, STORED_SESSION_ID, RUNTIME_SESSION_ID)
  })

  it('drops an empty pending assistant placeholder instead of preserving a blank orphan bubble', async () => {
    const seed: ClientSessionState = {
      ...createClientSessionState(STORED_SESSION_ID, [
        { id: 'user-1', role: 'user', parts: [textPart('continue')] },
        assistantMessage({ parts: [] })
      ]),
      awaitingResponse: true,
      busy: true,
      streamId: 'assistant-stream'
    }

    const harness = makeHarness({ seed })

    await act(async () => {
      harness.handle({
        session_id: RUNTIME_SESSION_ID,
        type: 'gateway.disconnected',
        payload: { message: 'Hermes background process exited' }
      })
    })

    const state = harness.getState()

    expect(state.messages.map(message => message.id)).toEqual(['user-1'])
    expect(state.busy).toBe(false)
    expect(state.awaitingResponse).toBe(false)
  })
})
