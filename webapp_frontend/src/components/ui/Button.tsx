import type { ButtonHTMLAttributes, ReactNode } from 'react';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  leftIcon?: ReactNode;
}

const variantClass: Record<ButtonVariant, string> = {
  primary: 'btn-primary',
  secondary: 'btn-secondary',
  ghost: 'btn-ghost',
  danger: 'btn-destructive',
};

export function Button({
  variant = 'secondary',
  size = 'md',
  fullWidth = false,
  leftIcon,
  className = '',
  children,
  ...props
}: ButtonProps) {
  const classNames = [
    'btn',
    variantClass[variant],
    size === 'sm' ? 'btn-sm' : '',
    fullWidth ? 'btn-block' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button className={classNames} {...props}>
      {leftIcon}
      {children}
    </button>
  );
}
