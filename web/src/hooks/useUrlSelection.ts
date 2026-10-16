/**
 * The selected station and direction live in the query string (?station=EMBR&direction=0)
 * so a selection can be bookmarked or shared. No routing library: the page reads the
 * values once on load and keeps them current with history.replaceState, which updates
 * the address without adding a history entry for every choice.
 */
export interface UrlSelection {
  station: string | null;
  direction: string | null;
}

export function readUrlSelection(): UrlSelection {
  const params = new URLSearchParams(window.location.search);
  return { station: params.get('station'), direction: params.get('direction') };
}

export function writeUrlSelection({ station, direction }: UrlSelection): void {
  const url = new URL(window.location.href);
  const set = (key: string, value: string | null) =>
    value === null ? url.searchParams.delete(key) : url.searchParams.set(key, value);
  set('station', station);
  set('direction', direction);
  if (url.href !== window.location.href) window.history.replaceState(window.history.state, '', url);
}
