// Renders the whole static site, as the GitHub Pages build does, on the published files.
import { render } from '@testing-library/react';
import { App } from '../App';
import { StaticShowcaseSource } from '../data/ShowcaseSource';
import { StaticReplayClient } from '../data/StaticReplayClient';
import { createPublishedReplayHost, PUBLISHED_ROOT, type PublishedReplayHost } from './publishedReplay';
import { SHOWCASE_ROOT, showcaseFetch } from './publishedShowcase';

export function openSite(search = '', host: PublishedReplayHost = createPublishedReplayHost()) {
  window.history.replaceState(null, '', `/${search}`);
  const showcaseRequests: string[] = [];
  const result = render(
    <App
      client={new StaticReplayClient(PUBLISHED_ROOT, { fetch: host.fetch })}
      showcase={new StaticShowcaseSource(SHOWCASE_ROOT, { fetch: showcaseFetch(showcaseRequests) })}
    />,
  );
  return { host, showcaseRequests, ...result };
}
