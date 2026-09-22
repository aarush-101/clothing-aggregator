import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { SearchBar } from '@/components/search-bar';

import { render, screen } from './render';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), prefetch: vi.fn() }),
}));

describe('SearchBar', () => {
  it('navigates to the results page with the encoded query', async () => {
    const user = userEvent.setup();
    render(<SearchBar />);

    await user.type(screen.getByRole('searchbox'), 'black linen shirt under $120');
    await user.click(screen.getByRole('button', { name: 'Search' }));

    expect(push).toHaveBeenCalledWith('/search?q=black%20linen%20shirt%20under%20%24120');
  });

  it('submits on Enter', async () => {
    const user = userEvent.setup();
    const onSubmitQuery = vi.fn();
    render(<SearchBar onSubmitQuery={onSubmitQuery} />);

    await user.type(screen.getByRole('searchbox'), 'linen shirt{Enter}');
    expect(onSubmitQuery).toHaveBeenCalledWith('linen shirt');
  });

  it('trims whitespace before submitting', async () => {
    const user = userEvent.setup();
    const onSubmitQuery = vi.fn();
    render(<SearchBar onSubmitQuery={onSubmitQuery} />);

    await user.type(screen.getByRole('searchbox'), '   linen shirt   {Enter}');
    expect(onSubmitQuery).toHaveBeenCalledWith('linen shirt');
  });

  it('refuses an empty query and explains why', async () => {
    const user = userEvent.setup();
    const onSubmitQuery = vi.fn();
    render(<SearchBar onSubmitQuery={onSubmitQuery} />);

    await user.click(screen.getByRole('button', { name: 'Search' }));

    expect(onSubmitQuery).not.toHaveBeenCalled();
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Describe what you are looking for.');
    expect(screen.getByRole('searchbox')).toHaveAttribute('aria-invalid', 'true');
  });

  it('clears the error once the shopper types', async () => {
    const user = userEvent.setup();
    render(<SearchBar />);

    await user.click(screen.getByRole('button', { name: 'Search' }));
    expect(screen.getByRole('alert')).toBeInTheDocument();

    await user.type(screen.getByRole('searchbox'), 'l');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('has an accessible label and search landmark', () => {
    render(<SearchBar />);
    expect(screen.getByRole('search')).toBeInTheDocument();
    expect(
      screen.getByLabelText('Describe the menswear you are looking for'),
    ).toBeInTheDocument();
  });

  it('shows the current query when arriving on a results page', () => {
    render(<SearchBar initialQuery="cream overshirt" />);
    expect(screen.getByRole('searchbox')).toHaveValue('cream overshirt');
  });
});
