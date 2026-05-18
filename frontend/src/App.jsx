import { useState } from 'react'
import Header from './components/Header.jsx'
import TripForm from './components/TripForm.jsx'

/**
 * Editorial layout per MOCKUP.html (locked v5 spec):
 *   Header → TripForm → TripSummary → TripMap → LogSheets
 *
 * Phase 4.3 wires only Header + TripForm. The summary/map/log sections land
 * in 4.4–4.7. For now, the resulting Trip envelope is logged to the console
 * so the network call can be verified.
 */
export default function App() {
  const [trip, setTrip] = useState(null)

  function handleTrip(t) {
    setTrip(t)
    console.log('Trip planned:', t)
  }

  return (
    <>
      <Header />
      <main className="max-w-[1180px] mx-auto px-8 py-8 space-y-6">
        <TripForm onTrip={handleTrip} />

        {trip && (
          <section className="card p-7">
            <div className="small-caps mb-2">Phase 4.3 verification</div>
            <p className="font-serif text-[16px]">
              Got Trip #{trip.id} —{' '}
              {trip.is_legal ? 'legal' : 'NOT legal'},{' '}
              <span className="font-mono">{trip.total_miles} mi</span>,{' '}
              <span className="font-mono">{trip.log_days.length} log day(s)</span>.
              Summary card, map, and log sheets land in Phases 4.4–4.7.
            </p>
          </section>
        )}
      </main>
    </>
  )
}
