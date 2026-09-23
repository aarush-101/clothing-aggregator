import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ProductCard } from '@/components/product-card';
import { recordClick } from '@/lib/api';

import { makeGroup, makeProduct } from './fixtures';
import { render, screen } from './render';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, recordClick: vi.fn() };
});

describe('ProductCard', () => {
  beforeEach(() => {
    vi.mocked(recordClick).mockClear();
  });

  it('shows the brand, title and price', () => {
    render(<ProductCard group={makeGroup()} position={1} searchId="s1" />);
    expect(screen.getByText('Kessler')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Kessler Relaxed Linen Shirt' }),
    ).toBeInTheDocument();
    expect(screen.getByText('$119')).toBeInTheDocument();
  });

  it('shows the original price and discount when reduced', () => {
    render(<ProductCard group={makeGroup()} position={1} searchId="s1" />);
    expect(screen.getByText('$149')).toBeInTheDocument();
    expect(screen.getByText('20% off')).toBeInTheDocument();
  });

  it('omits the discount badge at full price', () => {
    const group = makeGroup({}, { original_price: null, discount_percent: null });
    render(<ProductCard group={group} position={1} searchId="s1" />);
    expect(screen.queryByText(/% off/)).not.toBeInTheDocument();
  });

  it('shows the human-readable match reason', () => {
    render(<ProductCard group={makeGroup()} position={1} searchId="s1" />);
    expect(
      screen.getByText('Matches your requested black colour and linen material.'),
    ).toBeInTheDocument();
  });

  it('marks out-of-stock items', () => {
    const group = makeGroup({}, { in_stock: false });
    render(<ProductCard group={group} position={1} searchId="s1" />);
    expect(screen.getByText('Out of stock')).toBeInTheDocument();
  });

  it('links to the retailer with a safe, attributed outbound link', () => {
    render(<ProductCard group={makeGroup()} position={1} searchId="s1" />);
    const link = screen.getByTestId('view-at-retailer');
    expect(link).toHaveAttribute(
      'href',
      'https://northbound-supply.example/products/kessler-shirt',
    );
    expect(link).toHaveAttribute('target', '_blank');
    expect(link.getAttribute('rel')).toContain('noopener');
    expect(link.getAttribute('rel')).not.toContain('sponsored');
    expect(link).toHaveTextContent('View at Northbound Supply');
  });

  it('records the outbound click', async () => {
    const user = userEvent.setup();
    render(<ProductCard group={makeGroup()} position={3} searchId="s1" />);
    await user.click(screen.getByTestId('view-at-retailer'));

    expect(recordClick).toHaveBeenCalledWith(
      expect.objectContaining({
        retailer: 'northbound',
        product_id: 'p1',
        search_id: 's1',
        position: 3,
      }),
    );
  });

  it('links to every other retailer stocking a grouped item', () => {
    const group = makeGroup({
      offer_count: 3,
      offers: [
        makeProduct(),
        makeProduct({
          product_id: 'b',
          retailer: 'harbour',
          retailer_name: 'Harbour & Hale',
          price: 129,
          product_url: 'https://harbour.example/b',
        }),
        makeProduct({
          product_id: 'c',
          retailer: 'meridian',
          retailer_name: 'Meridian Menswear',
          price: 139,
          product_url: 'https://meridian.example/c',
        }),
      ],
      retailers: ['Northbound Supply', 'Harbour & Hale', 'Meridian Menswear'],
    });
    render(<ProductCard group={group} position={1} searchId="s1" />);
    expect(screen.getByText('Lowest of 3 retailers')).toBeInTheDocument();
    const harbour = screen.getByRole('link', { name: /Harbour & Hale/ });
    expect(harbour).toHaveAttribute('href', 'https://harbour.example/b');
    expect(screen.getByRole('link', { name: /Meridian Menswear/ })).toBeInTheDocument();
  });

  it('names the colourway when the title does not', () => {
    const { rerender } = render(
      <ProductCard
        group={makeGroup({}, { title: 'Allday Polo', colours: ['grey'] })}
        position={1}
        searchId="s1"
      />,
    );
    expect(screen.getByTestId('product-colour')).toHaveTextContent('grey');
    rerender(
      <ProductCard
        group={makeGroup({}, { title: 'Allday Polo Grey', colours: ['grey'] })}
        position={1}
        searchId="s1"
      />,
    );
    expect(screen.queryByTestId('product-colour')).not.toBeInTheDocument();
  });

  it('does not list a second offer from the same retailer as a comparison', () => {
    const group = makeGroup({
      offer_count: 2,
      offers: [makeProduct(), makeProduct({ product_id: 'b' })],
    });
    render(<ProductCard group={group} position={1} searchId="s1" />);
    expect(screen.queryByTestId('other-offers')).not.toBeInTheDocument();
  });

  it('shows free shipping when there is no shipping cost', () => {
    render(<ProductCard group={makeGroup()} position={1} searchId="s1" />);
    expect(screen.getByText('Free shipping')).toBeInTheDocument();
  });

  it('falls back to a placeholder when there is no image', () => {
    const group = makeGroup({}, { image_url: null });
    render(<ProductCard group={group} position={1} searchId="s1" />);
    expect(screen.getByText('No image available')).toBeInTheDocument();
  });

  it('is labelled for assistive technology', () => {
    render(<ProductCard group={makeGroup()} position={1} searchId="s1" />);
    expect(
      screen.getByRole('article', { name: 'Kessler Relaxed Linen Shirt' }),
    ).toBeInTheDocument();
  });
});
