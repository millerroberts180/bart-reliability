import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { App } from './App';
import { REPOSITORY_URL } from './components/SiteHeader';
import { MockPredictionClient } from './data/MockPredictionClient';

function renderApp() {
  render(<App client={new MockPredictionClient()} />);
}

describe('App', () => {
  it('discloses simulated data in the opening, before the example', () => {
    renderApp();
    const opening = screen.getByRole('region', { name: 'ETA Reliability' });
    const disclosure = within(opening).getByRole('complementary', { name: 'Prototype using simulated data' });
    expect(disclosure).toHaveTextContent(/simulated/);
    const example = screen.getByRole('region', { name: 'Try an ETA forecast' });
    expect(disclosure.compareDocumentPosition(example) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('states that the project predicts ETA changes, not physical arrivals', () => {
    renderApp();
    expect(screen.getByRole('heading', { level: 1, name: 'ETA Reliability' })).toBeInTheDocument();
    expect(screen.getByText('How stable are BART’s published arrival estimates?')).toBeInTheDocument();
    expect(screen.getByText(/studies how BART changes its published arrival estimates/)).toBeInTheDocument();
    expect(screen.getByText('It does not predict when a train physically arrives.')).toBeInTheDocument();
  });

  it('never uses arrival-accuracy language', async () => {
    renderApp();
    await screen.findByTestId('step-final');
    expect(document.body.textContent).not.toMatch(/actual arrival|true arrival|arrival accuracy|more accurate than BART/i);
  });

  it('offers a call to action in the opening that moves focus to the forecast', async () => {
    const user = userEvent.setup();
    renderApp();
    const opening = screen.getByRole('region', { name: 'ETA Reliability' });
    const cta = within(opening).getByRole('link', { name: 'Try a simulated prediction' });
    expect(cta).toHaveAttribute('href', '#example-title');
    await user.click(cta);
    expect(screen.getByRole('heading', { level: 2, name: 'Try an ETA forecast' })).toHaveFocus();
  });

  it('no longer uses the former name as a heading', () => {
    renderApp();
    expect(screen.queryByRole('heading', { name: /Will this ETA hold/i })).not.toBeInTheDocument();
  });

  it('uses the site name in the header', () => {
    renderApp();
    expect(screen.getByRole('link', { name: 'ETA Reliability' })).toHaveAttribute('href', '#top');
    expect(screen.queryByText('Will This ETA Hold?')).not.toBeInTheDocument();
  });

  it('links to the repository from the primary navigation', () => {
    renderApp();
    const nav = screen.getByRole('navigation', { name: 'Primary' });
    expect(within(nav).getByRole('link', { name: 'Source on GitHub' })).toHaveAttribute('href', REPOSITORY_URL);
    expect(within(nav).getByRole('link', { name: 'ETA forecast' })).toHaveAttribute('href', '#example-title');
  });
});
