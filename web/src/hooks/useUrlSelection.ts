import { useEffect, useRef } from 'react';

/**
 * The selected station and boarding group live in the query string
 * (?station=HAYW&boarding=to-SHAY) so a selection can be bookmarked or shared. No routing
 * library: the page reads the values on load and again on back/forward (popstate), and
 * keeps them current with history.replaceState, which updates the address without adding
 * a history entry for every choice. Other parameters and the hash are kept.
 *
 * Links from before boarding groups carry ?direction=0|1, a GTFS direction_id. It is read
 * only so it can be translated where that is unambiguous (domain/boardingSelection.ts).
 */
export interface UrlSelection {
  station: string | null;
  boarding: string | null;
  /** An old link's ?direction= value. */
  legacyDirection: string | null;
}

export function readUrlSelection(): UrlSelection {
  const params = new URLSearchParams(window.location.search);
  return { station: params.get('station'), boarding: params.get('boarding'), legacyDirection: params.get('direction') };
}

export function writeUrlSelection({ station, boarding }: { station: string; boarding: string }): void {
  const url = new URL(window.location.href);
  url.searchParams.set('station', station);
  url.searchParams.set('boarding', boarding);
  url.searchParams.delete('direction'); // translated or corrected; never written again
  if (url.href !== window.location.href) window.history.replaceState(window.history.state, '', url);
}

/** Calls `onNavigate` with the URL's selection whenever back or forward changes the address. */
export function useUrlNavigation(onNavigate: (selection: UrlSelection) => void): void {
  const latest = useRef(onNavigate);
  useEffect(() => {
    latest.current = onNavigate;
  });
  useEffect(() => {
    const onPopState = () => latest.current(readUrlSelection());
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);
}
