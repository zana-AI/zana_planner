import type { ButtonHTMLAttributes, ReactNode } from 'react';

type IconButtonVariant = 'ghost' | 'soft' | 'danger';

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: ReactNode;
  label: string;
  variant?: IconButtonVariant;
}

export function IconButton({
  icon,
  label,
  variant = 'ghost',
  className = '',
  ...props
}: IconButtonProps) {
  return (
    <button
      className={['ui-icon-button', `ui-icon-button-${variant}`, className].filter(Boolean).join(' ')}
      aria-label={label}
      title={label}
      {...props}
    >
      {icon}
    </button>
  );
}
