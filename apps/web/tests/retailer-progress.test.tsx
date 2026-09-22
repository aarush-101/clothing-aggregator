import { describe, expect, it } from 'vitest';

import { PartialResultsNotice } from '@/components/result-states';
import { RetailerProgress } from '@/components/retailer-progress';
import type { RetailerStatus } from '@/lib/types';

import { render, screen } from './render';

function status(overrides: Partial<RetailerStatus> = {}): RetailerStatus {
  return {
    key: 'northbound',
    name: 'Northbound Supply',
    state: 'pending',
    product_count: 0,
    duration_ms: null,
    error: null,
    attempts: 0,
    ...overrides,
  };
}

describe('RetailerProgress', () => {
  it('renders nothing when there are no retailers', () => {
    const { container } = render(<RetailerProgress retailers={[]} isLoading />);
    expect(container).toBeEmptyDOMElement();
  });

  it('names every retailer being searched', () => {
    render(
      <RetailerProgress
        retailers={[
          status({ state: 'running' }),
          status({ key: 'harbour', name: 'Harbour & Hale', state: 'pending' }),
        ]}
        isLoading
      />,
    );
    expect(screen.getByText('Northbound Supply')).toBeInTheDocument();
    expect(screen.getByText('Harbour & Hale')).toBeInTheDocument();
    expect(screen.getByText('Searching…')).toBeInTheDocument();
    expect(screen.getByText('Queued')).toBeInTheDocument();
  });

  it('reports match counts once a retailer completes', () => {
    render(
      <RetailerProgress
        retailers={[status({ state: 'completed', product_count: 4, duration_ms: 320 })]}
        isLoading={false}
      />,
    );
    expect(screen.getByText('4 matches')).toBeInTheDocument();
    expect(screen.getByText('320ms')).toBeInTheDocument();
  });

  it('distinguishes zero matches from a failure', () => {
    render(
      <RetailerProgress
        retailers={[
          status({ state: 'completed', product_count: 0 }),
          status({ key: 'atlas', name: 'Atlas', state: 'failed', error: 'HTTP 503' }),
        ]}
        isLoading={false}
      />,
    );
    expect(screen.getByText('No matches')).toBeInTheDocument();
    expect(screen.getByText('HTTP 503')).toBeInTheDocument();
  });

  it('shows how many retailers have finished', () => {
    render(
      <RetailerProgress
        retailers={[status({ state: 'completed' }), status({ key: 'b', state: 'running' })]}
        isLoading
      />,
    );
    expect(screen.getByText('1/2')).toBeInTheDocument();
  });

  it('announces progress politely', () => {
    const { container } = render(
      <RetailerProgress retailers={[status({ state: 'running' })]} isLoading />,
    );
    expect(container.querySelector('[aria-live="polite"]')).toBeInTheDocument();
    expect(container.querySelector('[aria-busy="true"]')).toBeInTheDocument();
  });
});

describe('PartialResultsNotice', () => {
  it('renders nothing when everything succeeded', () => {
    const { container } = render(
      <PartialResultsNotice failedRetailers={[]} warnings={[]} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('names the retailers that failed without hiding the results', () => {
    render(
      <PartialResultsNotice
        failedRetailers={[status({ key: 'atlas', name: 'Atlas Trading Co.', state: 'failed' })]}
        warnings={[]}
      />,
    );
    const notice = screen.getByTestId('partial-results-notice');
    expect(notice).toHaveTextContent('Showing partial results');
    expect(notice).toHaveTextContent('Atlas Trading Co.');
    expect(notice).toHaveAttribute('role', 'status');
  });

  it('surfaces backend warnings such as a stale-cache refresh', () => {
    render(
      <PartialResultsNotice
        failedRetailers={[]}
        warnings={['Showing recent results while we refresh them.']}
      />,
    );
    expect(
      screen.getByText('Showing recent results while we refresh them.'),
    ).toBeInTheDocument();
  });
});
