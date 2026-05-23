import type { ButtonHTMLAttributes, ReactNode } from 'react';

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: ReactNode;
  label: string;
}

export function IconButton({
  icon,
  label,
  className = '',
  ...props
}: IconButtonProps) {
  return (
    <button
      className={['icon-btn-v2', className].filter(Boolean).join(' ')}
      aria-label={label}
      title={label}
      type="button"
      {...props}
    >
      {icon}
    </button>
  );
}
