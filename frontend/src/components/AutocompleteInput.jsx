import { useEffect, useRef, useState } from 'react'
import { geocodeAutocomplete } from '../api'

/**
 * AutocompleteInput — editorial-styled text input with location suggestions.
 *
 * Uses the editorial `.input` class so it visually matches the other form
 * fields. Suggestions come from /api/geocode/?text=... (which proxies ORS
 * autocomplete server-side so the API key stays off the client).
 *
 * Behavior:
 *   - 250ms debounce after typing stops
 *   - Cancels in-flight requests when the query changes
 *   - Dropdown closes on Escape, blur, or selection
 *   - Up/Down/Enter for keyboard navigation
 *   - The whole value is bubbled up via onChange(label) — same shape as a
 *     plain controlled input, so swapping back to <input/> stays trivial
 */
export default function AutocompleteInput({ id, value, onChange, placeholder, className }) {
  const [suggestions, setSuggestions] = useState([])
  const [open, setOpen]               = useState(false)
  const [highlight, setHighlight]     = useState(-1)
  const debounceRef = useRef(null)
  const abortRef    = useRef(null)
  const wrapperRef  = useRef(null)

  // Debounced fetch on value change.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (abortRef.current)    abortRef.current.abort()

    const text = (value || '').trim()
    if (text.length < 2) {
      setSuggestions([])
      return
    }
    debounceRef.current = setTimeout(async () => {
      const ctrl = new AbortController()
      abortRef.current = ctrl
      try {
        const data = await geocodeAutocomplete(text, { signal: ctrl.signal })
        setSuggestions(data.results || [])
        setHighlight(-1)
      } catch (err) {
        if (err.name !== 'CanceledError' && err.name !== 'AbortError') {
          // Quietly drop autocomplete failures — they're non-blocking;
          // the user can still type any free-text value and submit.
          setSuggestions([])
        }
      }
    }, 250)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [value])

  // Click-outside closes the dropdown.
  useEffect(() => {
    function onDocClick(e) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  function selectSuggestion(s) {
    onChange(s.label)
    setOpen(false)
    setSuggestions([])
  }

  function onKeyDown(e) {
    if (!open || suggestions.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlight((h) => (h + 1) % suggestions.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlight((h) => (h <= 0 ? suggestions.length - 1 : h - 1))
    } else if (e.key === 'Enter' && highlight >= 0) {
      e.preventDefault()
      selectSuggestion(suggestions[highlight])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const showDropdown = open && suggestions.length > 0

  return (
    <div ref={wrapperRef} className="autocomplete-wrap">
      <input
        id={id}
        className={className || 'input'}
        type="text"
        autoComplete="off"
        placeholder={placeholder}
        value={value}
        onChange={(e) => {
          onChange(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {showDropdown && (
        <ul className="autocomplete-list" role="listbox">
          {suggestions.map((s, i) => (
            <li
              key={`${s.label}-${i}`}
              role="option"
              aria-selected={i === highlight}
              className={`autocomplete-item${i === highlight ? ' is-highlighted' : ''}`}
              onMouseDown={(e) => {
                // mousedown (not click) so the input doesn't blur first
                e.preventDefault()
                selectSuggestion(s)
              }}
              onMouseEnter={() => setHighlight(i)}
            >
              {s.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
