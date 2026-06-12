import { AnimatedGaladrielAvatar } from '@/components/galadriel/animated-galadriel-avatar'

// Brand badge: animated Galadriel mark on a nocturne tile, identical in light/dark.
// Fills the tile (softly rounded); size via className (default size-14).
export function BrandMark({ className, ...props }: React.ComponentProps<'span'>) {
  return <AnimatedGaladrielAvatar className={className ?? 'size-14'} state="idle" title="Galadriel" {...props} />
}
