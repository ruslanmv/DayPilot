import React, { useCallback, useEffect, useRef, useState } from 'react'
import { SETTINGS_MENU, type SettingsMenuItem, type SettingsSectionId } from '../settings/settingsData'

type SettingsMenuProps = {
  userName?: string
  workspaceName?: string
  /** Called with a section id; 'signout' is handled by onSignOut. */
  onOpenSection: (section: SettingsSectionId) => void
  onSignOut?: () => void
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
 * Bottom-left workspace button that opens an upward (drop-up) menu, in the
 * ChatGPT pattern. Full keyboard and ARIA support: roving focus with the arrow
 * keys, Home/End, Escape to close and restore focus, and a click-outside guard.
 */
export function SettingsMenu({
  userName = 'Ruslan M.',
  workspaceName = 'DayPilot Enterprise',
  onOpenSection,
  onSignOut,
}: SettingsMenuProps) {
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLUListElement>(null)
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([])

  const close = useCallback((restoreFocus = true) => {
    setOpen(false)
    if (restoreFocus) buttonRef.current?.focus()
  }, [])

  const activate = useCallback(
    (item: SettingsMenuItem) => {
      setOpen(false)
      if (item.id === 'signout') onSignOut?.()
      else onOpenSection(item.id)
      buttonRef.current?.focus()
    },
    [onOpenSection, onSignOut],
  )

  // Move DOM focus to the active item while the menu is open (roving tabindex).
  useEffect(() => {
    if (open) itemRefs.current[activeIndex]?.focus()
  }, [open, activeIndex])

  // Close on outside click.
  useEffect(() => {
    if (!open) return
    function onPointer(event: MouseEvent) {
      const target = event.target as Node
      if (menuRef.current?.contains(target) || buttonRef.current?.contains(target)) return
      setOpen(false)
    }
    document.addEventListener('mousedown', onPointer)
    return () => document.removeEventListener('mousedown', onPointer)
  }, [open])

  function openMenu(startAtEnd = false) {
    setActiveIndex(startAtEnd ? SETTINGS_MENU.length - 1 : 0)
    setOpen(true)
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
        event.preventDefault()
        setActiveIndex((i) => (i + 1) % SETTINGS_MENU.length)
        break
      case 'ArrowUp':
        event.preventDefault()
        setActiveIndex((i) => (i - 1 + SETTINGS_MENU.length) % SETTINGS_MENU.length)
        break
      case 'Home':
        event.preventDefault()
        setActiveIndex(0)
        break
      case 'End':
        event.preventDefault()
        setActiveIndex(SETTINGS_MENU.length - 1)
        break
      case 'Tab':
        // Keep focus trapped inside the open menu.
        event.preventDefault()
        setActiveIndex((i) =>
          event.shiftKey
            ? (i - 1 + SETTINGS_MENU.length) % SETTINGS_MENU.length
            : (i + 1) % SETTINGS_MENU.length,
        )
        break
      default:
        break
    }
  }

  return (
    <div className="dp-settings-menu">
      {open && (
        <ul
          ref={menuRef}
          className="dp-settings-dropup"
          role="menu"
          aria-label="Settings"
          onKeyDown={onMenuKeyDown}
        >
          {SETTINGS_MENU.map((item, index) => (
            <li key={item.id} role="none">
              <button
                ref={(el) => {
                  itemRefs.current[index] = el
                }}
                role="menuitem"
                tabIndex={index === activeIndex ? 0 : -1}
                className={
                  'dp-settings-item' +
                  (item.danger ? ' dp-settings-item--danger' : '') +
                  (item.id === 'signout' ? ' dp-settings-item--sep' : '')
                }
                onClick={() => activate(item)}
              >
                <span className="dp-settings-item__icon" aria-hidden="true">{item.icon}</span>
                <span className="dp-settings-item__body">
                  <span className="dp-settings-item__label">{item.label}</span>
                  {item.hint && <span className="dp-settings-item__hint">{item.hint}</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
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
        <span className="dp-settings-avatar" aria-hidden="true">{initials(userName)}</span>
        <span className="dp-settings-trigger__text">
          <span className="dp-settings-trigger__name">{userName}</span>
          <span className="dp-settings-trigger__workspace">{workspaceName}</span>
        </span>
        <span className="dp-settings-trigger__chevron" aria-hidden="true">⌄</span>
      </button>
    </div>
  )
}
