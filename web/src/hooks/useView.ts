import { useSyncExternalStore, type MouseEvent } from 'react';

/**
 * The page has three views, each with a stable address that works on GitHub Pages:
 * ?view=highlights (the default), ?view=map and ?view=explorer. No routing library:
 * moving between views pushes a history entry, so back and forward work, and every view
 * can be loaded directly. A view's own choices (a horizon, a map mode, a selection) are
 * kept current with replaceState, so they are shareable without filling the history.
 */
export type View = 'highlights' | 'map' | 'explorer';
export const VIEWS: readonly View[] = ['highlights', 'map', 'explorer'];
export const VIEW_LABELS: Record<View, string> = {
  highlights: 'Highlights',
  map: 'Network map',
  explorer: 'Train explorer',
};

// Fired after this page changes the address itself (history.pushState and
// replaceState fire no event of their own).
const CHANGED = 'eta-reliability:location';

export function viewFromSearch(search: string): View {
  const value = new URLSearchParams(search).get('view');
  return VIEWS.find((v) => v === value) ?? 'highlights';
}

/** The address of a view, with only the given parameters ("?view=map&mode=published"). */
export function viewHref(view: View, params: Record<string, string | null | undefined> = {}): string {
  const search = new URLSearchParams({ view });
  for (const [key, value] of Object.entries(params)) if (value) search.set(key, value);
  return `?${search.toString()}`;
}

export function navigateTo(href: string): void {
  window.history.pushState(null, '', href);
  window.dispatchEvent(new Event(CHANGED));
}

/** Set or remove one query parameter of the current address, without a history entry. */
export function replaceParam(name: string, value: string | null): void {
  const url = new URL(window.location.href);
  if (value === null) url.searchParams.delete(name);
  else url.searchParams.set(name, value);
  if (url.href === window.location.href) return;
  window.history.replaceState(window.history.state, '', url);
  window.dispatchEvent(new Event(CHANGED));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener('popstate', onChange);
  window.addEventListener(CHANGED, onChange);
  return () => {
    window.removeEventListener('popstate', onChange);
    window.removeEventListener(CHANGED, onChange);
  };
}

export function useLocationSearch(): string {
  return useSyncExternalStore(
    subscribe,
    () => window.location.search,
    () => '',
  );
}

export function useView(): View {
  return viewFromSearch(useLocationSearch());
}

export function useSearchParam(name: string): string | null {
  return new URLSearchParams(useLocationSearch()).get(name);
}

/**
 * Click handler for an in-page link to another view: a plain click navigates in place;
 * a modified or middle click keeps the browser's own behaviour (a new tab, and so on).
 */
export function followViewLink(event: MouseEvent<HTMLAnchorElement>): void {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
    return;
  }
  event.preventDefault();
  navigateTo(event.currentTarget.getAttribute('href') ?? '?');
}
