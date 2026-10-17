import type { BoardingGroup, Station } from './types';

export const sameId = (a: string, b: string | null) => b !== null && a.toLowerCase() === b.toLowerCase();

/** Why the group shown is not the one the link asked for. */
export type BoardingCorrection =
  | { kind: 'unknown-boarding'; value: string }
  | { kind: 'legacy-ambiguous'; value: string }
  | { kind: 'legacy-unknown'; value: string };

export interface BoardingResolution {
  group: BoardingGroup | undefined;
  correction: BoardingCorrection | null;
}

/**
 * The boarding group to show at a station for what a link asked for (docs/boarding_groups.md):
 * - `boarding`, matched case-insensitively;
 * - otherwise an old link's GTFS `direction`, but only when exactly one group at the
 *   station carries it. At Hayward both sides carry both values, so it is never guessed;
 * - otherwise the first group, with a correction to show when the link asked for
 *   something that could not be honoured.
 */
export function resolveBoardingGroup(
  station: Station,
  requested: { boarding: string | null; legacyDirection: string | null },
): BoardingResolution {
  const groups = station.boardingGroups;
  const first = groups[0];
  if (requested.boarding !== null) {
    const match = groups.find((g) => sameId(g.id, requested.boarding));
    return match
      ? { group: match, correction: null }
      : { group: first, correction: { kind: 'unknown-boarding', value: requested.boarding } };
  }
  if (requested.legacyDirection !== null) {
    const value = requested.legacyDirection;
    const carrying = groups.filter((g) => g.gtfsDirectionIds.includes(value));
    const [only] = carrying;
    if (carrying.length === 1 && only) return { group: only, correction: null };
    return {
      group: first,
      correction: { kind: carrying.length > 1 ? 'legacy-ambiguous' : 'legacy-unknown', value },
    };
  }
  return { group: first, correction: null };
}

/** "Toward Daly City and Richmond (platform 2)". */
export function describeGroup(group: BoardingGroup): string {
  return group.platform ? `${group.label} (platform ${group.platform})` : group.label;
}

/** The visible note for a correction, naming what is shown instead. */
export function correctionNote(correction: BoardingCorrection, station: Station, shown: BoardingGroup): string {
  const instead = `trains ${lowerFirst(describeGroup(shown))} are shown instead`;
  switch (correction.kind) {
    case 'unknown-boarding':
      return `“${correction.value}” isn’t a boarding direction at ${station.name}, so ${instead}.`;
    case 'legacy-ambiguous':
      return (
        `This link’s direction “${correction.value}” is from an older version of the page and could mean ` +
        `${station.boardingGroups.length === 2 ? 'either side' : 'more than one side'} of ${station.name}, ` +
        `so ${instead}. Choose the way you’re going below.`
      );
    case 'legacy-unknown':
      return (
        `This link’s direction “${correction.value}” is from an older version of the page and matches no ` +
        `boarding direction at ${station.name}, so ${instead}.`
      );
  }
}

function lowerFirst(text: string): string {
  return text.charAt(0).toLowerCase() + text.slice(1);
}
