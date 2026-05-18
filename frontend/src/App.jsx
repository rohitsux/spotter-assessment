import Header from './components/Header.jsx'

/**
 * Editorial layout per MOCKUP.html (locked v5 spec):
 *   Header → TripForm → TripSummary → TripMap → LogSheets
 *
 * Only Header is wired in Phase 4.2; the four content cards land in 4.3–4.7.
 * The placeholder section below is just a typography/color check so we can
 * visually confirm the editorial shell against MOCKUP.html before building
 * real components.
 */
export default function App() {
  return (
    <>
      <Header />

      <main className="max-w-[1180px] mx-auto px-8 py-8 space-y-6">
        <section className="card p-7">
          <div className="small-caps mb-2">Setup verification — Phase 4.2</div>
          <h1 className="editorial-title text-4xl mb-3">
            The editorial shell is alive.
          </h1>
          <p className="text-[var(--ink-2)] mb-6 max-w-xl">
            Fonts, colors, and the <span className="font-mono">.card</span> /{' '}
            <span className="font-mono">.small-caps</span> /{' '}
            <span className="font-mono">.editorial-title</span> classes from{' '}
            <span className="font-mono">theme.css</span> are now available.
            Components land in Phase 4.3 onward.
          </p>

          <div className="flex items-center gap-6 flex-wrap">
            <span className="pill pill-ok">Trip is legal</span>
            <span className="pill pill-bad">Trip not legal</span>
            <button type="button" className="btn-primary">
              Plan trip
            </button>
            <span className="num-display text-3xl">1,088 mi</span>
            <span className="font-mono text-[12px] text-[var(--ink-3)]">
              cycle 46.25 / 70
            </span>
          </div>
        </section>

        <section className="card p-7">
          <div className="small-caps mb-2">Mascot asset check</div>
          <div className="flex items-end gap-6 flex-wrap">
            {/* All three SVGs now share viewBox 0 0 364.544 403.456 with the
                figure bottom-centered, so identical w/h produces identical
                visual footprint and they're drop-in swappable. */}
            <img src="/mascots/mascot-idle.svg" alt="idle" className="w-28" />
            <img src="/mascots/mascot-legal.svg" alt="legal" className="w-28" />
            <img src="/mascots/mascot-not-legal.svg" alt="not legal" className="w-28" />
          </div>
        </section>

        <section className="card p-7">
          <div className="small-caps mb-2">Marker icon check</div>
          <div className="flex items-center gap-4 flex-wrap">
            <span className="map-icon-badge">
              <img src="/icons/delivery-van-icon.svg" alt="pickup/dropoff" />
            </span>
            <span className="map-icon-badge">
              <img src="/icons/gas-pump-icon.svg" alt="fuel" />
            </span>
            <span className="map-icon-badge">
              <img src="/icons/snooze-zzz-icon.svg" alt="rest" />
            </span>
            <span className="map-icon-badge">
              <img src="/icons/coffee-icon.svg" alt="break" />
            </span>
          </div>
        </section>
      </main>
    </>
  )
}
