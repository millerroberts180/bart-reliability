import { useEffect, useState } from 'react';

/** Re-reads the clock every `intervalMs` so ages like "34 s old" stay true. */
export function useNow(clock: () => Date, intervalMs = 15_000): Date {
  const [now, setNow] = useState(clock);
  useEffect(() => {
    const id = setInterval(() => setNow(clock()), intervalMs);
    return () => clearInterval(id);
  }, [clock, intervalMs]);
  return now;
}
