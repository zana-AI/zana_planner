import type { HTMLAttributes } from 'react';

type BadgeVariant = 'neutral' | 'good' | 'warn' | 'bad' | 'progress' | 'status' | 'privacy' | 'warning' | 'danger';

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  showDot?: boolean;
}

const variantClass: Record<string, string> = {
  neutral: '',
  good: 'good',
  warn: 'warn',
  bad: 'bad',
  progress: '',
  status: '',
  privacy: '',
  warning: 'warn',
  danger: 'bad',
};

export function Badge({ variant = 'neutral', showDot = false, className = '', children, ...props }: BadgeProps) {
  const pillVariant = variantClass[variant] || '';
  return (
    <span className={['pill', pillVariant, className].filter(Boolean).join(' ')} {...props}>
      {showDot ? <span className="dot" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}
