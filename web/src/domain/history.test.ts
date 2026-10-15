import { describe, expect, it } from 'vitest';
import { addSeconds } from './eta';
import {
  analyzeHistory,
  describeChart,
  describeObservation,
  HISTORY_GAP_SECONDS,
  REVISION_THRESHOLD_SECONDS,
  summarizeHistory,
} from './history';
import type { PredictionHistoryPoint } from './types';

const LATEST = '2026-10-13T16:59:26.000Z'; // 9:59:26 AM Pacific

/** Snapshots `minutesAgo` before LATEST with the given published ETA offsets (seconds after LATEST). */
function history(points: [minutesAgo: number, etaAfterLatest: number][]): PredictionHistoryPoint[] {
  return points.map(([m, eta]) => {
    const feedTimestamp = addSeconds(LATEST, -m * 60);
    const publishedEtaAt = addSeconds(LATEST, eta);
    return { feedTimestamp, publishedEtaAt, publishedEtaSeconds: m * 60 + eta };
  });
}

/**
 * One snapshot per minute for `minutes` minutes, ending at LATEST. `changes` maps a
 * minutesAgo to the ETA (seconds after LATEST) BART published from then on.
 */
function minuteHistory(minutes: number, start: number, changes: Record<number, number> = {}, missing: number[] = []) {
  let eta = start;
  const points: [number, number][] = [];
  for (let m = minutes; m >= 0; m--) {
    eta = changes[m] ?? eta;
    if (!missing.includes(m)) points.push([m, eta]);
  }
  return history(points);
}

const summary = (points: PredictionHistoryPoint[], stale = false) =>
  summarizeHistory(analyzeHistory(points, LATEST), { stale });

describe('analyzeHistory', () => {
  it('orders snapshots and drops any newer than the prediction’s snapshot', () => {
    const points = history([[0, 300], [2, 300], [-1, 999], [1, 300]]);
    const { observations } = analyzeHistory(points, LATEST);
    expect(observations.map((o) => o.feedTimestamp)).toEqual([
      addSeconds(LATEST, -120),
      addSeconds(LATEST, -60),
      LATEST,
    ]);
  });

  it('measures each change from the previous published estimate', () => {
    const { observations, netChangeSeconds } = analyzeHistory(history([[2, 300], [1, 345], [0, 330]]), LATEST);
    expect(observations.map((o) => o.changeSeconds)).toEqual([null, 45, -15]);
    expect(netChangeSeconds).toBe(30);
  });

  it('uses the centralized prototype thresholds', () => {
    expect(REVISION_THRESHOLD_SECONDS).toBe(30);
    expect(HISTORY_GAP_SECONDS).toBe(90);
  });

  it(`counts only changes of at least ${REVISION_THRESHOLD_SECONDS} seconds (29 s is drift, 30 s counts)`, () => {
    const { revisionCount } = analyzeHistory(history([[3, 300], [2, 329], [1, 359], [0, 300]]), LATEST);
    expect(revisionCount).toBe(2); // +29 is drift; +30 and −59 count
    expect(analyzeHistory(history([[1, 300], [0, 271]]), LATEST).revisionCount).toBe(0); // −29
    expect(analyzeHistory(history([[1, 300], [0, 270]]), LATEST).revisionCount).toBe(1); // −30
  });

  it('treats 90 seconds between snapshots as continuous and 91 seconds as a gap', () => {
    const pair = (secondsApart: number) => [
      { feedTimestamp: addSeconds(LATEST, -secondsApart), publishedEtaAt: addSeconds(LATEST, 300), publishedEtaSeconds: 300 + secondsApart },
      { feedTimestamp: LATEST, publishedEtaAt: addSeconds(LATEST, 300), publishedEtaSeconds: 300 },
    ];
    expect(analyzeHistory(pair(90), LATEST).gapCount).toBe(0);
    expect(analyzeHistory(pair(91), LATEST).gapCount).toBe(1);
    expect(analyzeHistory(pair(91), LATEST).segments).toHaveLength(2);
  });

  it('splits the line where snapshots are more than 90 seconds apart', () => {
    const { segments, gapCount, observations } = analyzeHistory(history([[6, 300], [5, 300], [2, 300], [1, 300], [0, 300]]), LATEST);
    expect(gapCount).toBe(1);
    expect(segments.map((s) => s.length)).toEqual([2, 3]);
    expect(observations[2]?.afterGap).toBe(true);
  });
});

describe('summarizeHistory', () => {
  it('names the threshold for several changes of 30 seconds or more', () => {
    expect(summary(minuteHistory(14, 0, { 10: 45, 6: 75, 2: 125 }))).toBe(
      'Over the last 14 minutes, BART moved this ETA 2 min 5 sec later across three changes of 30 seconds or more.',
    );
  });

  it('uses the singular for one change of 30 seconds or more, here earlier', () => {
    expect(summary(minuteHistory(14, 400, { 8: 370 }))).toBe(
      'Over the last 14 minutes, BART moved this ETA 30 seconds earlier in one change of 30 seconds or more.',
    );
  });

  it('keeps the exact net movement when small drift accompanies a counted change', () => {
    expect(summary(minuteHistory(10, 300, { 8: 340, 4: 352 }))).toBe(
      'Over the last 10 minutes, BART moved this ETA 52 seconds later in one change of 30 seconds or more.',
    );
  });

  it('distinguishes no net change after revisions from an ETA that held', () => {
    expect(summary(minuteHistory(10, 300, { 6: 345, 2: 300 }))).toBe(
      'Over the last 10 minutes, BART changed this ETA twice by 30 seconds or more, but it ended where it started.',
    );
    expect(summary(minuteHistory(10, 300))).toBe('Over the last 10 minutes, BART’s ETA for this train held steady.');
  });

  it('calls changes under 30 seconds drift, even when they add up', () => {
    expect(summary(minuteHistory(5, 300, { 3: 308, 1: 303 }))).toBe(
      'Over the last 5 minutes, BART’s ETA drifted 3 seconds later in small changes of under 30 seconds.',
    );
    expect(summary(minuteHistory(5, 300, { 4: 329, 2: 358 }))).toBe(
      'Over the last 5 minutes, BART’s ETA drifted 58 seconds later in small changes of under 30 seconds.',
    );
  });

  it('handles one observation and missing history', () => {
    expect(summary(history([[0, 300]]))).toBe(
      'Only one snapshot so far: BART first published this ETA at 9:59:26 AM, so there is no change to show yet.',
    );
    expect(summary([])).toBe('No earlier snapshots of this ETA are available yet.');
  });

  it('anchors the window to the snapshot when the data is stale, with gaps too', () => {
    expect(summary(minuteHistory(6, 300, { 1: 360 }, [5, 4, 3]), true)).toBe(
      'From the first available snapshot to the 9:59:26 AM snapshot, the ETA ended 1 min later. ' +
        'One observed change of 30 seconds or more occurred outside one gap; additional changes during the gap are unknown.',
    );
  });
});

describe('summarizeHistory across gaps', () => {
  it('does not count a threshold-sized difference across a gap as an observed change', () => {
    const points = minuteHistory(6, 300, { 3: 330 }, [5, 4, 3]); // +30 s, but only across the gap
    expect(analyzeHistory(points, LATEST).revisionCount).toBe(0);
    expect(summary(points)).toBe(
      'From the first to the latest available snapshot, the ETA ended 30 seconds later. ' +
        'No change was observed outside one gap; changes during the gap are unknown.',
    );
  });

  it('does not classify small movement across a gap as drift', () => {
    const points = minuteHistory(6, 300, { 4: 310 }, [5, 4, 3]);
    expect(analyzeHistory(points, LATEST).smallChangeCount).toBe(0);
    expect(summary(points)).not.toMatch(/drift/);
    expect(summary(points)).toMatch(/ended 10 seconds later\. No change was observed outside one gap/);
  });

  it('separates endpoint movement from observed changes when both ordinary changes and a gap occur', () => {
    // +40 and +35 observed; +90 happens somewhere in the missing span.
    expect(summary(minuteHistory(14, 0, { 12: 40, 5: 130, 2: 165 }, [6, 5, 4]))).toBe(
      'From the first to the latest available snapshot, the ETA ended 2 min 45 sec later. ' +
        'Two observed changes of 30 seconds or more occurred outside one gap; additional changes during the gap are unknown.',
    );
  });

  it('handles a history whose only movement is across the gap', () => {
    expect(summary(minuteHistory(8, 300, { 4: 420 }, [5, 4, 3]))).toBe(
      'From the first to the latest available snapshot, the ETA ended 2 min later. ' +
        'No change was observed outside one gap; changes during the gap are unknown.',
    );
  });

  it('handles several gaps with natural singular and plural wording', () => {
    // Gaps between minutes 7→4 and 4→1; only the +40 at minute 7 was observed.
    expect(summary(minuteHistory(9, 300, { 7: 340, 4: 380, 1: 381 }, [6, 5, 3, 2]))).toBe(
      'From the first to the latest available snapshot, the ETA ended 1 min 21 sec later. ' +
        'One observed change of 30 seconds or more occurred outside two gaps; additional changes during the gaps are unknown.',
    );
  });

  it('reports small observed changes and an unchanged endpoint', () => {
    expect(summary(minuteHistory(8, 300, { 7: 310, 1: 300 }, [5, 4, 3]))).toBe(
      'From the first to the latest available snapshot, the ETA ended where it started. ' +
        'Outside one gap, only small changes of under 30 seconds were observed; changes during the gap are unknown.',
    );
  });

  it('leaves histories without gaps unchanged', () => {
    expect(summary(minuteHistory(14, 0, { 10: 45, 6: 75, 2: 125 }))).toBe(
      'Over the last 14 minutes, BART moved this ETA 2 min 5 sec later across three changes of 30 seconds or more.',
    );
  });

  it('anchors the window to the snapshot when the data is stale', () => {
    expect(summary(minuteHistory(14, 0, { 3: 60 }), true)).toBe(
      'In the 14 minutes before the 9:59:26 AM snapshot, BART moved this ETA 1 min later in one change of 30 seconds or more.',
    );
  });
});

describe('describeChart', () => {
  it('names a populated chart by its data, never as having no snapshots', () => {
    const name = describeChart(analyzeHistory(minuteHistory(6, 300, {}, [5, 4, 3]), LATEST), 'Embarcadero · Richmond train');
    expect(name).toBe(
      'Chart of BART’s published ETA for Embarcadero · Richmond train: 4 snapshots from 9:53:26 AM to 9:59:26 AM, with one gap in the feed.',
    );
    expect(name).not.toMatch(/no snapshots/i);
  });

  it('names a single snapshot', () => {
    expect(describeChart(analyzeHistory(history([[0, 300]]), LATEST), 'Balboa Park · Antioch train')).toBe(
      'Chart of BART’s published ETA for Balboa Park · Antioch train: one snapshot, at 9:59:26 AM.',
    );
  });
});

describe('describeObservation after a gap', () => {
  it('reports the difference from the previous available snapshot without calling it one change', () => {
    const { observations } = analyzeHistory(minuteHistory(6, 300, { 4: 420 }, [5, 4, 3]), LATEST);
    const afterGap = observations.find((o) => o.afterGap);
    expect(afterGap && describeObservation(afterGap, false)).toBe(
      'Snapshot 9:57:26 AM: BART published 10:06:26 AM, 9 min away, 2 min later than the previous available snapshot, ' +
        'across a 4 min gap in the feed; changes during the gap are unknown.',
    );
  });
});

describe('describeObservation', () => {
  it('gives the snapshot, published ETA, time away and change', () => {
    const { observations } = analyzeHistory(history([[1, 300], [0, 345]]), LATEST);
    const latest = observations[1];
    expect(latest && describeObservation(latest, true)).toBe(
      'Latest snapshot 9:59:26 AM: BART published 10:05:11 AM, 5 min 45 sec away, 45 seconds later than the previous snapshot.',
    );
  });
});
