import type { HTMLAttributes } from 'react';

type BadgeVariant = 'neutral' | 'progress' | 'status' | 'privacy' | 'warning' | 'danger';

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

export function Badge({ variant = 'neutral', className = '', children, ...props }: BadgeProps) {
  return (
    <span className={['ui-badge', `ui-badge-${variant}`, className].filter(Boolean).join(' ')} {...props}>
      {children}
    </span>
  );
}
