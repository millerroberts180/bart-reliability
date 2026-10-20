/* eslint-disable jsx-a11y/no-redundant-roles, jsx-a11y/no-interactive-element-to-noninteractive-role --
   On narrow screens CSS changes these elements' display to stack each row; some
   browsers then drop table semantics, so the roles are stated explicitly. (The
   second rule misreads <td> as an interactive gridcell.) */
import { formatClock, formatSpokenDuration } from '../domain/eta';
import { describeChangeFromPrevious, type HistoryAnalysis } from '../domain/history';

/** Every observation as text: the chart's accessible equivalent. */
export function ObservationTable({ analysis }: { analysis: HistoryAnalysis }) {
  const { observations } = analysis;
  return (
    <details className="history__table">
      <summary>{observations.length === 1 ? 'Show the observation' : `Show all ${observations.length} observations`}</summary>
      <table role="table">
        <caption className="visually-hidden">BART’s published ETA at each feed snapshot, oldest first.</caption>
        <thead role="rowgroup">
          <tr role="row">
            <th role="columnheader" scope="col">Snapshot</th>
            <th role="columnheader" scope="col">BART’s published ETA</th>
            <th role="columnheader" scope="col">Time away</th>
            <th role="columnheader" scope="col">Change from previous</th>
          </tr>
        </thead>
        <tbody role="rowgroup">
          {observations.map((o, i) => {
            const previous = observations[i - 1];
            const gapSeconds = previous
              ? Math.round((Date.parse(o.feedTimestamp) - Date.parse(previous.feedTimestamp)) / 1000)
              : 0;
            return [
              o.afterGap && (
                <tr key={`${o.feedTimestamp}-gap`} role="row" className="history__gap-row">
                  <td role="cell" colSpan={4}>
                    No snapshots for {formatSpokenDuration(gapSeconds)} (gap in the feed)
                  </td>
                </tr>
              ),
              <tr key={o.feedTimestamp} role="row">
                <td role="cell" data-label="Snapshot">
                  {formatClock(o.feedTimestamp)}
                  {i === observations.length - 1 && ' (latest)'}
                </td>
                <td role="cell" data-label="BART’s published ETA">
                  {formatClock(o.publishedEtaAt)}
                </td>
                <td role="cell" data-label="Time away">
                  {formatSpokenDuration(o.publishedEtaSeconds)}
                </td>
                <td role="cell" data-label="Change from previous">
                  {capitalize(describeChangeFromPrevious(o))}
                </td>
              </tr>,
            ];
          })}
        </tbody>
      </table>
    </details>
  );
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
