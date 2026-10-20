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
    // Said once in the short opening and again in the full question.
    const opening = screen.getByRole('region', { name: 'ETA Reliability' });
    expect(within(opening).getByText('It does not predict when a train physically arrives.')).toBeInTheDocument();
    const question = screen.getByRole('region', { name: 'The question' });
    expect(within(question).getByText('It does not predict when a train physically arrives.')).toBeInTheDocument();
  });

  it('puts the forecast before the full explanation, without removing it', () => {
    renderApp();
    const opening = screen.getByRole('region', { name: 'ETA Reliability' });
    const example = screen.getByRole('region', { name: 'Try an ETA forecast' });
    const question = screen.getByRole('region', { name: 'The question' });
    const follows = (a: Element, b: Element) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    expect(follows(opening, example) && follows(example, question)).toBe(true);
    // The opening stays short: a lede, one statement and the disclosure, no long prose.
    expect(within(opening).getAllByRole('paragraph').length).toBeLessThanOrEqual(5);
    expect(within(opening).queryByText(/six minutes away/)).not.toBeInTheDocument();
    expect(within(question).getByText(/six minutes away/)).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Primary' });
    expect(within(nav).getByRole('link', { name: 'The question' })).toHaveAttribute('href', '#question');
    expect(question).toHaveAttribute('id', 'question');
  });

  it('never uses arrival-accuracy language', async () => {
    renderApp();
    await screen.findByTestId('forecast');
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

  it('states independence from BART in the footer', () => {
    renderApp();
    expect(screen.getByRole('contentinfo')).toHaveTextContent(
      'Independent project using BART open data. Not affiliated with or endorsed by BART.',
    );
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
