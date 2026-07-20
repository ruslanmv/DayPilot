import React, { useCallback, useEffect, useRef, useState } from 'react'

export type AccountUser = {
  name: string
  email: string
  role?: string
}

type AccountMenuProps = {
  user: AccountUser
  /** Opens the full Settings modal (on Profile & workspace). */
  onOpenSettings: () => void
  onSignOut: () => void
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase()
}

/**
 * Bottom-left account menu in the ChatGPT/Claude pattern: the profile card
 * toggles a compact popover anchored directly above it, containing only the
 * profile identity, Settings, and Sign out. It is deliberately NOT a second
 * settings navigation — every advanced section lives inside the full Settings
 * modal. Keyboard support: Enter/Space/ArrowUp open, arrows move between the
 * two items, Escape closes and restores focus, outside clicks close.
 */
export function AccountMenu({ user, onOpenSettings, onSignOut }: AccountMenuProps) {
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const popoverRef = useRef<HTMLDivElement>(null)
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([])
  const itemCount = 2 // Settings, Sign out

  const close = useCallback((restoreFocus = true) => {
    setOpen(false)
    if (restoreFocus) buttonRef.current?.focus()
  }, [])

  // Move DOM focus to the active item while the menu is open (roving tabindex).
  useEffect(() => {
    if (open) itemRefs.current[activeIndex]?.focus()
  }, [open, activeIndex])

  // Close on outside click.
  useEffect(() => {
    if (!open) return
    function onPointer(event: MouseEvent) {
      const target = event.target as Node
      if (popoverRef.current?.contains(target) || buttonRef.current?.contains(target)) return
      setOpen(false)
    }
    document.addEventListener('mousedown', onPointer)
    return () => document.removeEventListener('mousedown', onPointer)
  }, [open])

  function openMenu(startAtEnd = false) {
    setActiveIndex(startAtEnd ? itemCount - 1 : 0)
    setOpen(true)
  }

  function activateSettings() {
    // Close the popover first so only one overlay is ever open.
    setOpen(false)
    onOpenSettings()
  }

  function activateSignOut() {
    setOpen(false)
    onSignOut()
  }

  function onButtonKeyDown(event: React.KeyboardEvent) {
    if (event.key === 'ArrowUp' || event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      openMenu(event.key === 'ArrowUp')
    }
  }

  function onMenuKeyDown(event: React.KeyboardEvent) {
    switch (event.key) {
      case 'Escape':
        event.preventDefault()
        close()
        break
      case 'ArrowDown':
      case 'Tab':
        event.preventDefault()
        setActiveIndex((i) => (i + 1) % itemCount)
        break
      case 'ArrowUp':
        event.preventDefault()
        setActiveIndex((i) => (i - 1 + itemCount) % itemCount)
        break
      case 'Home':
        event.preventDefault()
        setActiveIndex(0)
        break
      case 'End':
        event.preventDefault()
        setActiveIndex(itemCount - 1)
        break
      default:
        break
    }
  }

  return (
    <div className="dp-account">
      {open && (
        <div
          ref={popoverRef}
          className="dp-account-popover"
          role="menu"
          aria-label="Account"
          onKeyDown={onMenuKeyDown}
        >
          <div className="dp-account-popover__profile">
            <span className="dp-settings-avatar" aria-hidden="true">{initials(user.name)}</span>
            <span className="dp-account-popover__who">
              <strong>{user.name}</strong>
              <span>{user.email}</span>
            </span>
          </div>

          <div className="dp-account-popover__divider" role="none" />

          <button
            ref={(el) => { itemRefs.current[0] = el }}
            type="button"
            role="menuitem"
            tabIndex={activeIndex === 0 ? 0 : -1}
            className="dp-account-popover__item"
            onClick={activateSettings}
          >
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="12" cy="12" r="3.2" stroke="currentColor" strokeWidth="1.7" />
              <path d="M19.2 12a7.2 7.2 0 0 0-.1-1.2l2-1.5-2-3.4-2.3 1a7.4 7.4 0 0 0-2.1-1.3L14.3 3h-4l-.4 2.6a7.4 7.4 0 0 0-2.1 1.3l-2.3-1-2 3.4 2 1.5a7.2 7.2 0 0 0 0 2.4l-2 1.5 2 3.4 2.3-1a7.4 7.4 0 0 0 2.1 1.3l.4 2.6h4l.4-2.6a7.4 7.4 0 0 0 2.1-1.3l2.3 1 2-3.4-2-1.5c.07-.4.1-.8.1-1.2Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
            </svg>
            <span>Settings</span>
          </button>

          <div className="dp-account-popover__divider" role="none" />

          <button
            ref={(el) => { itemRefs.current[1] = el }}
            type="button"
            role="menuitem"
            tabIndex={activeIndex === 1 ? 0 : -1}
            className="dp-account-popover__item dp-account-popover__item--signout"
            onClick={activateSignOut}
          >
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M14 6V5a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2v-1" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
              <path d="M9.5 12H21m0 0-3-3m3 3-3 3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>Sign out</span>
          </button>
        </div>
      )}

      <button
        ref={buttonRef}
        type="button"
        className="dp-settings-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => (open ? close(false) : openMenu())}
        onKeyDown={onButtonKeyDown}
      >
        <span className="dp-settings-avatar" aria-hidden="true">{initials(user.name)}</span>
        <span className="dp-settings-trigger__text">
          <span className="dp-settings-trigger__name">{user.name}</span>
          <span className="dp-settings-trigger__workspace">{user.role || user.email}</span>
        </span>
        <span className="dp-settings-trigger__chevron" aria-hidden="true">⌄</span>
      </button>
    </div>
  )
}
