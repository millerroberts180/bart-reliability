import type { ShowcaseState } from '../data/ShowcaseContext';

/** What a view says when the curated showcase is loading, failed, or not part of this build. */
export function ShowcaseUnavailable({ state }: { state: Exclude<ShowcaseState, { status: 'ready' }> }) {
  if (state.status === 'loading') {
    return (
      <p className="notice" role="status">
        Loading the replay…
      </p>
    );
  }
  if (state.status === 'error') {
    return (
      <div className="notice notice--error" role="alert">
        <p>The replay could not be loaded. {state.message}</p>
        <button type="button" className="button" onClick={state.retry}>
          Try again
        </button>
      </div>
    );
  }
  return (
    <p className="notice">
      This view shows the curated historical replay, which only the published site includes. Build or serve the site with
      VITE_DATA_MODE=static to see it.
    </p>
  );
}
