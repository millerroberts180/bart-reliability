import { describe, expect, it } from 'vitest';
import {
  assessFreshness,
  classifyStability,
  describeAwayGlance,
  describeRevision,
  describeRevisionRange,
  describeTimeAway,
  formatClockSince,
  formatDuration,
  formatLongMoment,
  formatMoment,
  formatSignedDuration,
  formatSpokenDuration,
  likelyFinalEtaSeconds,
  STALE_AFTER_SECONDS,
} from './eta';

describe('likelyFinalEtaSeconds', () => {
  it('adds the predicted revision to the current published ETA', () => {
    expect(likelyFinalEtaSeconds(370, 85)).toBe(455);
  });

  it('moves the ETA earlier for a negative revision', () => {
    expect(likelyFinalEtaSeconds(905, -40)).toBe(865);
  });
});

describe('classifyStability', () => {
  it.each([
    [0, 'likely_to_hold'],
    [0.249, 'likely_to_hold'],
    [0.25, 'may_be_revised'],
    [0.499, 'may_be_revised'],
    [0.5, 'likely_to_be_revised'],
    [1, 'likely_to_be_revised'],
  ])('maps probability %s to %s', (p, expected) => {
    expect(classifyStability(p)).toBe(expected);
  });
});

describe('assessFreshness', () => {
  const now = new Date('2026-10-13T17:00:00Z');

  it('treats a snapshot at the freshness limit as current', () => {
    const feed = new Date(now.getTime() - STALE_AFTER_SECONDS * 1000).toISOString();
    expect(assessFreshness(feed, now)).toEqual({ ageSeconds: STALE_AFTER_SECONDS, stale: false });
  });

  it('flags a snapshot older than the limit as stale', () => {
    const feed = new Date(now.getTime() - (STALE_AFTER_SECONDS + 1) * 1000).toISOString();
    expect(assessFreshness(feed, now).stale).toBe(true);
  });
});

describe('duration formatting', () => {
  it('writes minutes and seconds', () => {
    expect(formatDuration(455)).toBe('7 min 35 s');
    expect(formatDuration(45)).toBe('45 s');
    expect(formatDuration(600)).toBe('10 min');
  });

  it('signs revisions with a true minus', () => {
    expect(formatSignedDuration(85)).toBe('+1 min 25 s');
    expect(formatSignedDuration(-40)).toBe('−40 s');
    expect(formatSignedDuration(0)).toBe('0 s');
  });
});

describe('plain-language revision copy', () => {
  it('spells out seconds below a minute and abbreviates longer durations', () => {
    expect(formatSpokenDuration(12)).toBe('12 seconds');
    expect(formatSpokenDuration(1)).toBe('1 second');
    expect(formatSpokenDuration(130)).toBe('2 min 10 sec');
  });

  it('always names the direction of the expected change', () => {
    expect(describeRevision(12)).toBe('about 12 seconds later');
    expect(describeRevision(-40)).toBe('about 40 seconds earlier');
    expect(describeRevision(0)).toBe('no change expected');
  });

  it('words ranges on either side of zero', () => {
    expect(describeRevisionRange(-10, 35)).toBe('10 seconds earlier to 35 seconds later');
    expect(describeRevisionRange(20, 150)).toBe('20 seconds to 2 min 30 sec later');
    expect(describeRevisionRange(-45, -5)).toBe('5 seconds to 45 seconds earlier');
    expect(describeRevisionRange(0, 110)).toBe('no change to 1 min 50 sec later');
  });

  it('describes time remaining, never a negative one', () => {
    expect(describeTimeAway(142)).toBe('2 min 22 sec away');
    expect(describeTimeAway(0)).toBe('due now');
  });
});

describe('describeAwayGlance', () => {
  it('rounds to whole minutes for the glanceable forecast', () => {
    expect(describeAwayGlance(142)).toBe('About 2 min away'); // 2 min 22 sec
    expect(describeAwayGlance(150)).toBe('About 3 min away'); // 2 min 30 sec rounds up
    expect(describeAwayGlance(60)).toBe('About 1 min away');
    expect(describeAwayGlance(89)).toBe('About 1 min away');
    expect(describeAwayGlance(90)).toBe('About 2 min away');
    expect(describeAwayGlance(865)).toBe('About 14 min away');
  });

  it('says less than a minute below one minute, and due at zero', () => {
    expect(describeAwayGlance(59)).toBe('Less than 1 min away');
    expect(describeAwayGlance(1)).toBe('Less than 1 min away');
    expect(describeAwayGlance(0)).toBe('Due now');
  });
});

describe('dated clock times', () => {
  it('names the replay moment with its date in Pacific time', () => {
    expect(formatMoment('2026-10-15T17:00:00Z')).toBe('Thu, Oct 15, 2026, 10:00 AM');
    expect(formatLongMoment('2026-10-20T17:00:00Z')).toBe('Tuesday, October 20, 2026 at 10:00 AM');
    // Pacific, whatever the visitor's time zone: 03:30 UTC is still the previous evening.
    expect(formatLongMoment('2026-10-21T03:30:00Z')).toBe('Tuesday, October 20, 2026 at 8:30 PM');
  });

  it('adds the date only when a time falls on another Pacific day than the reference', () => {
    // 02:56Z on Oct 14 is 7:56 PM on Oct 13 in Pacific time.
    expect(formatClockSince('2026-10-14T02:56:22Z', '2026-10-15T16:59:23Z')).toBe('Oct 13, 7:56:22 PM');
    expect(formatClockSince('2026-10-15T15:10:00Z', '2026-10-15T16:59:23Z')).toBe('8:10:00 AM');
  });
});
