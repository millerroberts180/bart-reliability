import { useCallback, useState } from 'react';

/** Only station IDs are stored, in this browser, and never sent anywhere. */
const STORAGE_KEY = 'eta-reliability.recent-stations';
export const RECENT_STATION_LIMIT = 3;

function read(): string[] {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '[]');
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string').slice(0, RECENT_STATION_LIMIT) : [];
  } catch {
    return []; // storage blocked or corrupted: carry on without recents
  }
}

function write(ids: string[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  } catch {
    // Private mode or quota: recents are a convenience, so ignore the failure.
  }
}

/** Up to three recently chosen station IDs, most recent first. */
export function useRecentStations(): { recentIds: string[]; remember: (id: string) => void } {
  const [recentIds, setRecentIds] = useState(read);
  const remember = useCallback((id: string) => {
    setRecentIds((current) => {
      const next = [id, ...current.filter((existing) => existing !== id)].slice(0, RECENT_STATION_LIMIT);
      write(next);
      return next;
    });
  }, []);
  return { recentIds, remember };
}
