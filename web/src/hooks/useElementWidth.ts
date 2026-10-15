import { useEffect, useRef, useState } from 'react';

/**
 * Tracks an element's content width so SVG text can stay at a readable size
 * instead of scaling down with a viewBox. Falls back to `fallback` where
 * ResizeObserver is unavailable (e.g. jsdom).
 */
export function useElementWidth<T extends HTMLElement>(fallback: number) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.round(entry.contentRect.width));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}
