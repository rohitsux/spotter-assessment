/**
 * Editorial masthead, ported from MOCKUP.html lines 175–188 (the locked v5 spec).
 *
 *   [S] Spotter Trip Planner          Vol. 1 · No. 1 · Single Driver
 *       Hours of Service · 70 hr / 8 day
 */
export default function Header() {
  return (
    <header
      className="border-b bg-[var(--surface)]"
      style={{ borderColor: 'var(--line)' }}
    >
      <div className="max-w-[1180px] mx-auto px-8 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 flex items-center justify-center"
            style={{ border: '1px solid var(--ink)' }}
          >
            <span
              className="font-serif italic text-[20px]"
              style={{ color: 'var(--ink)' }}
            >
              S
            </span>
          </div>
          <div>
            <div className="font-serif text-[20px] leading-none">
              Spotter{' '}
              <span className="italic" style={{ color: 'var(--vermillion)' }}>
                Trip Planner
              </span>
            </div>
            <div className="small-caps mt-1">Hours of Service · 70 hr / 8 day</div>
          </div>
        </div>
        <div className="small-caps">Vol. 1 · No. 1 · Single Driver</div>
      </div>
    </header>
  )
}
