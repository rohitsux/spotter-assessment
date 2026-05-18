/**
 * TripSummarySkeleton — shimmer placeholder rendered while the form is
 * POSTing. Mimics the editorial layout of <TripSummary> so the page doesn't
 * jump when the real card swaps in: same grid, same gaps, same heights.
 *
 * Uses inline-styled <div>s with a CSS keyframe shimmer (defined in
 * theme.css as .shimmer-bar) — no Tailwind utility for animated gradients.
 */
export default function TripSummarySkeleton() {
  return (
    <section className="card p-7 relative" aria-busy="true" aria-live="polite">
      <div className="flex items-start justify-between gap-6">
        <div className="flex-1">
          <div className="small-caps mb-2">No. 02 · The Verdict</div>

          {/* Pill row + route */}
          <div className="flex items-center gap-3 mb-3">
            <span className="shimmer-bar" style={{ width: 130, height: 18 }} />
            <span className="shimmer-bar" style={{ width: 220, height: 12 }} />
          </div>

          {/* 4-stat grid */}
          <div className="grid grid-cols-4 gap-6 mt-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i}>
                <span className="shimmer-bar" style={{ width: '60%', height: 10 }} />
                <div style={{ marginTop: 12 }}>
                  <span className="shimmer-bar" style={{ width: '70%', height: 36 }} />
                </div>
              </div>
            ))}
          </div>

          {/* Start / end row */}
          <div className="h-rule mt-6 pt-4 grid grid-cols-2 gap-6">
            {[0, 1].map((i) => (
              <div key={i}>
                <span className="shimmer-bar" style={{ width: '40%', height: 10 }} />
                <div style={{ marginTop: 6 }}>
                  <span className="shimmer-bar" style={{ width: '80%', height: 14 }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
