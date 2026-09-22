'use client';

import * as React from 'react';

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { formatPriceCompact } from '@/lib/format';
import {
  countActiveFilters,
  toggleValue,
  type FacetValue,
  type Facets,
  type FilterKey,
  type FilterState,
} from '@/lib/filters';

const VISIBLE_FACET_VALUES = 6;

function FacetGroup({
  id,
  idPrefix,
  title,
  values,
  selected,
  onToggle,
}: {
  id: string;
  idPrefix: string;
  title: string;
  values: FacetValue[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  const [expanded, setExpanded] = React.useState(false);
  if (values.length === 0) return null;

  const visible = expanded ? values : values.slice(0, VISIBLE_FACET_VALUES);

  return (
    <AccordionItem value={id}>
      <AccordionTrigger>
        {title}
        {selected.length > 0 ? (
          <span className="ml-2 text-foreground tabular-nums">({selected.length})</span>
        ) : null}
      </AccordionTrigger>
      <AccordionContent>
        <ul className="space-y-2.5">
          {visible.map((facet) => {
            const inputId = `${idPrefix}${id}-${facet.value}`;
            return (
              <li key={facet.value} className="flex items-center gap-2.5">
                <Checkbox
                  id={inputId}
                  checked={selected.includes(facet.value)}
                  onCheckedChange={() => onToggle(facet.value)}
                />
                <Label htmlFor={inputId} className="flex flex-1 cursor-pointer gap-2">
                  <span className="min-w-0 flex-1 truncate capitalize">{facet.label}</span>
                  <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                    {facet.count}
                  </span>
                </Label>
              </li>
            );
          })}
        </ul>
        {values.length > VISIBLE_FACET_VALUES ? (
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="mt-3 text-xs text-muted-foreground underline underline-offset-4 transition-colors hover:text-foreground"
          >
            {expanded ? 'Show fewer' : `Show all ${values.length}`}
          </button>
        ) : null}
      </AccordionContent>
    </AccordionItem>
  );
}

export interface FilterPanelProps {
  facets: Facets;
  filters: FilterState;
  onChange: (filters: FilterState) => void;
  onReset: () => void;
  /**
   * The panel is rendered twice - a desktop sidebar and a mobile sheet - so
   * each instance needs its own element ids to keep `label[for]` unambiguous.
   */
  idPrefix?: string;
}

export function FilterPanel({
  facets,
  filters,
  onChange,
  onReset,
  idPrefix = '',
}: FilterPanelProps) {
  const activeCount = countActiveFilters(filters);
  const priceRange = filters.priceRange ?? [facets.priceMin, facets.priceMax];
  const priceDisabled = facets.priceMax <= facets.priceMin;

  const toggleFacet = (key: FilterKey) => (value: string) =>
    onChange({ ...filters, [key]: toggleValue(filters[key], value) });

  return (
    <div data-testid="filter-panel">
      <div className="flex items-baseline justify-between gap-3 pb-1">
        <h2 className="label-eyebrow">Refine</h2>
        {activeCount > 0 ? (
          <button
            type="button"
            onClick={onReset}
            className="text-xs text-muted-foreground underline underline-offset-4 transition-colors hover:text-foreground"
          >
            Clear all ({activeCount})
          </button>
        ) : null}
      </div>

      <Accordion
        type="multiple"
        defaultValue={['price', 'availability', 'brands', 'retailers']}
        className="border-t border-border"
      >
        <AccordionItem value="price">
          <AccordionTrigger>Price</AccordionTrigger>
          <AccordionContent>
            {priceDisabled ? (
              <p className="text-xs text-muted-foreground">
                All results are {formatPriceCompact(facets.priceMin)}.
              </p>
            ) : (
              <div className="space-y-4 pt-1">
                <Slider
                  aria-label="Price range"
                  min={facets.priceMin}
                  max={facets.priceMax}
                  step={5}
                  value={priceRange}
                  onValueChange={(value) =>
                    onChange({ ...filters, priceRange: [value[0] ?? 0, value[1] ?? 0] })
                  }
                  minStepsBetweenThumbs={1}
                />
                <div className="flex items-center justify-between text-xs text-muted-foreground tabular-nums">
                  <span>{formatPriceCompact(priceRange[0])}</span>
                  <span>{formatPriceCompact(priceRange[1])}</span>
                </div>
              </div>
            )}
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="availability">
          <AccordionTrigger>Availability</AccordionTrigger>
          <AccordionContent>
            <ul className="space-y-2.5">
              <li className="flex items-center gap-2.5">
                <Checkbox
                  id={`${idPrefix}filter-in-stock`}
                  checked={filters.inStockOnly}
                  onCheckedChange={(checked) =>
                    onChange({ ...filters, inStockOnly: checked === true })
                  }
                />
                <Label htmlFor={`${idPrefix}filter-in-stock`} className="cursor-pointer">
                  In stock only
                </Label>
              </li>
              {facets.hasDiscounts ? (
                <li className="flex items-center gap-2.5">
                  <Checkbox
                    id={`${idPrefix}filter-on-sale`}
                    checked={filters.onSaleOnly}
                    onCheckedChange={(checked) =>
                      onChange({ ...filters, onSaleOnly: checked === true })
                    }
                  />
                  <Label htmlFor={`${idPrefix}filter-on-sale`} className="cursor-pointer">
                    Reduced only
                  </Label>
                </li>
              ) : null}
            </ul>
          </AccordionContent>
        </AccordionItem>

        <FacetGroup
          id="brands"
          idPrefix={idPrefix}
          title="Brand"
          values={facets.brands}
          selected={filters.brands}
          onToggle={toggleFacet('brands')}
        />
        <FacetGroup
          id="retailers"
          idPrefix={idPrefix}
          title="Retailer"
          values={facets.retailers}
          selected={filters.retailers}
          onToggle={toggleFacet('retailers')}
        />
        <FacetGroup
          id="colours"
          idPrefix={idPrefix}
          title="Colour"
          values={facets.colours}
          selected={filters.colours}
          onToggle={toggleFacet('colours')}
        />
        <FacetGroup
          id="sizes"
          idPrefix={idPrefix}
          title="Size"
          values={facets.sizes}
          selected={filters.sizes}
          onToggle={toggleFacet('sizes')}
        />
        <FacetGroup
          id="materials"
          idPrefix={idPrefix}
          title="Material"
          values={facets.materials}
          selected={filters.materials}
          onToggle={toggleFacet('materials')}
        />
      </Accordion>

      {activeCount > 0 ? (
        <Button variant="quiet" size="sm" onClick={onReset} className="mt-5 w-full">
          Clear all filters
        </Button>
      ) : null}
    </div>
  );
}
