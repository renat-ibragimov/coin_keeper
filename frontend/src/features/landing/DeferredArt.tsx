import { useNearViewport } from './useNearViewport';

/** Keep offscreen CSS backgrounds out of the initial download. */
export function DeferredArt({ className }: { className: string }) {
  const { ref, visible } = useNearViewport();

  return <div ref={ref} className={className} data-visible={visible} aria-hidden="true" />;
}
