import { Opening } from './components/Opening';
import { PredictionExample } from './components/PredictionExample';
import { ProjectQuestion } from './components/ProjectQuestion';
import { SiteFooter } from './components/SiteFooter';
import { SiteHeader } from './components/SiteHeader';
import type { PredictionClient } from './data/PredictionClient';
import { PredictionClientProvider } from './data/PredictionClientContext';

/**
 * The page, for whichever prediction client it is given. Each data mode's module in
 * src/modes/ supplies its own client, so App imports none of them.
 */
export function App({ client }: { client: PredictionClient }) {
  return (
    <PredictionClientProvider client={client}>
      <SiteHeader />
      <main id="top" className="page">
        <Opening />
        <PredictionExample />
        <ProjectQuestion />
      </main>
      <SiteFooter />
    </PredictionClientProvider>
  );
}
