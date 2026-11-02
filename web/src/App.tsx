import { useEffect, useRef } from 'react';
import { ReplayStrip } from './components/ReplayStrip';
import { SiteFooter } from './components/SiteFooter';
import { SiteHeader } from './components/SiteHeader';
import type { PredictionClient } from './data/PredictionClient';
import { PredictionClientProvider } from './data/PredictionClientContext';
import { ShowcaseProvider } from './data/ShowcaseContext';
import type { ShowcaseSource } from './data/ShowcaseSource';
import { useView, VIEW_LABELS, type View } from './hooks/useView';
import { ExplorerView } from './views/ExplorerView';
import { HighlightsView } from './views/HighlightsView';
import { NetworkMapView } from './views/NetworkMapView';

export const VIEW_TITLE_ID = 'view-title';

/**
 * The site, for whichever prediction client (and showcase) it is given. Each data mode's
 * module in src/modes/ supplies its own, so App imports none of them.
 */
export function App({ client, showcase = null }: { client: PredictionClient; showcase?: ShowcaseSource | null }) {
  return (
    <PredictionClientProvider client={client}>
      <ShowcaseProvider source={showcase}>
        <Shell />
      </ShowcaseProvider>
    </PredictionClientProvider>
  );
}

function Shell() {
  const view = useView();
  useViewChange(view);
  return (
    <>
      <SiteHeader view={view} />
      <main id="main" className="page" tabIndex={-1}>
        <ReplayStrip />
        {view === 'highlights' && <HighlightsView />}
        {view === 'map' && <NetworkMapView />}
        {view === 'explorer' && <ExplorerView />}
      </main>
      <SiteFooter />
    </>
  );
}

/** Names the view in the document title, and after a change of view moves focus to its heading. */
function useViewChange(view: View) {
  const previous = useRef<View | null>(null);
  useEffect(() => {
    document.title = `${VIEW_LABELS[view]} · ETA Reliability`;
    if (previous.current !== null && previous.current !== view) {
      window.scrollTo({ top: 0 });
      document.getElementById(VIEW_TITLE_ID)?.focus({ preventScroll: true });
    }
    previous.current = view;
  }, [view]);
}
