import type { ComponentProps } from 'react'
import { useEffect, useMemo, useState } from 'react'

import { cn } from '@/lib/utils'

export type GaladrielAvatarState = 'idle' | 'thinking' | 'tool_use' | 'speaking' | 'error'

interface AnimatedGaladrielAvatarProps extends Omit<ComponentProps<'span'>, 'children'> {
  state?: GaladrielAvatarState
}

const STATE_ROWS: Record<GaladrielAvatarState, number> = {
  idle: 0,
  speaking: 3,
  error: 5,
  tool_use: 7,
  thinking: 8
}

const STATE_DURATIONS_MS: Record<GaladrielAvatarState, number> = {
  idle: 1800,
  speaking: 720,
  error: 1200,
  tool_use: 820,
  thinking: 900
}

const FRAME_COLUMNS = [0, 1, 2, 3, 4, 5, 6, 7] as const

const assetPath = (path: string) => `${import.meta.env.BASE_URL}${path.replace(/^\/+/, '')}`

function frameUrl(row: number, column: number) {
  return assetPath(
    `galadriel-avatar/frames/frame_r${String(row).padStart(2, '0')}_c${String(column).padStart(2, '0')}.png`
  )
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(false)

  useEffect(() => {
    const query = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!query) return

    const update = () => setReduced(query.matches)
    update()
    query.addEventListener?.('change', update)
    return () => query.removeEventListener?.('change', update)
  }, [])

  return reduced
}

export function AnimatedGaladrielAvatar({ className, state = 'idle', title = 'Galadriel', ...props }: AnimatedGaladrielAvatarProps) {
  const reducedMotion = useReducedMotion()
  const frames = useMemo(() => {
    const row = STATE_ROWS[state] ?? STATE_ROWS.idle
    return FRAME_COLUMNS.map(column => frameUrl(row, column))
  }, [state])
  const [frameIndex, setFrameIndex] = useState(0)

  useEffect(() => {
    setFrameIndex(0)
  }, [state])

  useEffect(() => {
    if (reducedMotion || frames.length <= 1) return

    const frameMs = Math.max(80, Math.round((STATE_DURATIONS_MS[state] ?? STATE_DURATIONS_MS.idle) / frames.length))
    const id = window.setInterval(() => {
      setFrameIndex(index => (index + 1) % frames.length)
    }, frameMs)

    return () => window.clearInterval(id)
  }, [frames.length, reducedMotion, state])

  const currentFrame = frames[reducedMotion ? 0 : frameIndex % frames.length]

  return (
    <span
      aria-hidden="true"
      className={cn(
        'relative inline-flex shrink-0 overflow-hidden rounded-md border border-white/10 bg-[#05060b]',
        'shadow-[0_0_18px_rgba(154,132,255,0.18)] ring-1 ring-violet-200/5',
        state !== 'idle' && 'shadow-[0_0_24px_rgba(171,146,255,0.32)] ring-violet-200/15',
        className
      )}
      data-galadriel-avatar-state={state}
      title={title}
      {...props}
    >
      <img alt="" className="size-full object-cover" draggable={false} src={currentFrame} />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_8%,rgba(255,255,255,0.18),transparent_34%),linear-gradient(to_bottom,transparent,rgba(0,0,0,0.16))]"
      />
    </span>
  )
}
