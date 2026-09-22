'use client';

import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap text-sm font-medium transition-[background-color,color,border-color,opacity] disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 outline-none",
  {
    variants: {
      variant: {
        default:
          'bg-accent text-accent-foreground hover:opacity-88 active:opacity-80 rounded-sm',
        outline:
          'border border-border-strong bg-transparent text-foreground hover:bg-muted rounded-sm',
        ghost: 'text-foreground hover:bg-muted rounded-sm',
        link: 'text-foreground underline underline-offset-4 decoration-border-strong hover:decoration-foreground',
        quiet:
          'border border-border bg-card text-muted-foreground hover:text-foreground hover:border-border-strong rounded-sm',
      },
      size: {
        default: 'h-10 px-5',
        sm: 'h-8 px-3 text-[0.8125rem]',
        lg: 'h-12 px-7 text-[0.9375rem]',
        icon: 'size-9 rounded-sm',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp
        ref={ref}
        data-slot="button"
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Button.displayName = 'Button';

export { buttonVariants };
