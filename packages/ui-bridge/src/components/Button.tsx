import React from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost'

const variantStyles: Record<ButtonVariant, React.CSSProperties> = {
  primary: { borderColor: 'rgba(0, 217, 255, .75)', background: 'rgba(0, 217, 255, .14)', color: '#d8f7ff' },
  secondary: { borderColor: 'rgba(255, 204, 102, .55)', background: 'rgba(255, 204, 102, .10)', color: '#ffe5a8' },
  danger: { borderColor: 'rgba(255, 98, 121, .65)', background: 'rgba(255, 98, 121, .10)', color: '#ffd4db' },
  ghost: { borderColor: 'rgba(142, 183, 194, .28)', background: 'transparent', color: '#b9d7df' },
}

export function Button({
  children,
  variant = 'primary',
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      {...props}
      style={{
        border: '1px solid',
        borderRadius: 12,
        padding: '10px 14px',
        cursor: props.disabled ? 'not-allowed' : 'pointer',
        fontWeight: 700,
        letterSpacing: .2,
        opacity: props.disabled ? .55 : 1,
        ...variantStyles[variant],
        ...props.style,
      }}
    >
      {children}
    </button>
  )
}
