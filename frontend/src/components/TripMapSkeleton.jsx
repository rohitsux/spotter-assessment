/**
 * TripMapSkeleton — shimmer placeholder rendered while the form is POSTing.
 * Mirrors TripMap's layout (header + 380px map block + stop-sequence rows)
 * so the page doesn't jump when the real map swaps in.
 *
 * The map block itself is a subtle paper background with a single shimmer
 * line where the polyline will eventually be — keeps the eye in the right
 * place without pretending to be a real map.
 */
export default function TripMapSkeleton() {
  return (
    <section className="card overflow-hidden" aria-busy="true" aria-live="polite">
      {/* header */}
      <div className="px-7 pt-6 pb-4">
        <div className="space-y-2">
          <span className="shimmer-bar" style={{ width: 110, height: 10 }} />
          <div><span className="shimmer-bar" style={{ width: 260, height: 24 }} /></div>
          <div><span className="shimmer-bar" style={{ width: 320, height: 12 }} /></div>
        </div>
      </div>

      {/* map block — paper background + a wandering polyline placeholder */}
      <div
        className="relative"
        style={{
          height: 380,
          background: 'var(--bg-2)',
          borderTop: '1px solid var(--line-2)',
          borderBottom: '1px solid var(--line-2)',
        }}
      >
        {/* The polyline stub: a thin shimmer line traced diagonally across
            the block so the eye sees "route goes here" without faking
            real geography. */}
        <div
          className="shimmer-bar"
          style={{
            position: 'absolute',
            left: '12%',
            top: '70%',
            width: '76%',
            height: 3,
            transform: 'rotate(-12deg)',
            transformOrigin: 'left center',
            borderRadius: 2,
          }}
          aria-hidden="true"
        />
      </div>

      {/* stop list — 4 placeholder rows matching the real stop list shape */}
      <div className="px-7 py-5 border-t" style={{ borderColor: 'var(--line-2)' }}>
        <span className="shimmer-bar" style={{ width: 100, height: 10 }} />
        <ol className="space-y-2.5 mt-3">
          {[0, 1, 2, 3].map((i) => (
            <li key={i} className="flex items-center gap-3">
              <span className="shimmer-bar" style={{ width: 40, height: 40, borderRadius: 999 }} />
              <span className="shimmer-bar" style={{ width: 70, height: 12 }} />
              <span className="shimmer-bar" style={{ width: 140, height: 14 }} />
              <span className="shimmer-bar" style={{ width: 180, height: 12 }} />
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}
