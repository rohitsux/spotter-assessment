/**
 * LogSheetsSkeleton — shimmer placeholder for the daily-logs section
 * while the Plan-trip POST is in flight. Mirrors LogSheets' layout:
 * section heading + 3 stacked day cards (first expanded with admin
 * block + grid placeholder + totals; others collapsed headers).
 */
export default function LogSheetsSkeleton() {
  return (
    <section className="space-y-4" aria-busy="true" aria-live="polite">
      {/* Section heading */}
      <div className="flex items-baseline justify-between gap-3">
        <div className="space-y-2">
          <span className="shimmer-bar" style={{ width: 110, height: 10 }} />
          <div><span className="shimmer-bar" style={{ width: 180, height: 24 }} /></div>
        </div>
        <span className="shimmer-bar" style={{ width: 180, height: 11 }} />
      </div>

      {/* Day 1 — expanded */}
      <div className="card">
        {/* summary header */}
        <div className="px-5 md:px-6 py-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 md:gap-4 flex-wrap">
            <span className="shimmer-bar" style={{ width: 70, height: 11 }} />
            <span className="shimmer-bar" style={{ width: 200, height: 18 }} />
            <span className="shimmer-bar" style={{ width: 130, height: 11 }} />
          </div>
          <span className="shimmer-bar shrink-0" style={{ width: 16, height: 16, borderRadius: 4 }} />
        </div>

        {/* admin block */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 md:gap-x-8 gap-y-4 px-5 md:px-6 py-5 border-t border-b"
             style={{ borderColor: 'var(--line-2)' }}>
          {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
            <div key={i} className="space-y-1.5">
              <span className="shimmer-bar" style={{ width: 70, height: 10 }} />
              <div><span className="shimmer-bar" style={{ width: 110, height: 13 }} /></div>
            </div>
          ))}
        </div>

        {/* 24-hr grid placeholder */}
        <div className="px-5 md:px-6 py-6 overflow-x-auto">
          <div style={{ width: 1284, height: 238, position: 'relative' }}>
            {/* dark header band */}
            <span
              className="shimmer-bar"
              style={{
                position: 'absolute', left: 96, top: 0,
                width: 1188, height: 26, borderRadius: 0,
              }}
              aria-hidden="true"
            />
            {/* 4 row placeholders */}
            {[0, 1, 2, 3].map((r) => (
              <span
                key={r}
                className="shimmer-bar"
                style={{
                  position: 'absolute', left: 0, top: 26 + r * 32,
                  width: 1284, height: 30, borderRadius: 0,
                }}
                aria-hidden="true"
              />
            ))}
          </div>
        </div>

        {/* totals row */}
        <div className="px-5 md:px-6 py-5 border-t grid grid-cols-2 md:grid-cols-6 gap-4 md:gap-6"
             style={{ borderColor: 'var(--line-2)' }}>
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="space-y-2">
              <span className="shimmer-bar" style={{ width: '60%', height: 10 }} />
              <div><span className="shimmer-bar" style={{ width: '50%', height: 24 }} /></div>
            </div>
          ))}
        </div>
      </div>

      {/* Day 2 & 3 — collapsed headers only */}
      {[0, 1].map((i) => (
        <div key={i} className="card">
          <div className="px-5 md:px-6 py-4 flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 md:gap-4 flex-wrap">
              <span className="shimmer-bar" style={{ width: 70, height: 11 }} />
              <span className="shimmer-bar" style={{ width: 200, height: 18 }} />
              <span className="shimmer-bar" style={{ width: 130, height: 11 }} />
            </div>
            <span className="shimmer-bar shrink-0" style={{ width: 16, height: 16, borderRadius: 4 }} />
          </div>
        </div>
      ))}
    </section>
  )
}
