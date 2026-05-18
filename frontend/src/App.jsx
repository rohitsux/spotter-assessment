import { useState } from 'react'
import Header from './components/Header.jsx'
import TripForm from './components/TripForm.jsx'
import TripSummary from './components/TripSummary.jsx'
import TripSummarySkeleton from './components/TripSummarySkeleton.jsx'

/**
 * Editorial layout per MOCKUP.html (locked v5 spec):
 *   Header → TripForm → TripSummary → TripMap → LogSheets
 *
 * While the POST is in flight we render a shimmer skeleton with the same
 * dimensions as TripSummary so the page doesn't jump on swap.
 */
export default function App() {
  const [trip, setTrip] = useState(null)
  const [loading, setLoading] = useState(false)

  function handleTrip(t) {
    setTrip(t)
  }

  return (
    <>
      <Header />
      <main className="max-w-[1180px] mx-auto px-8 py-8 space-y-6">
        <TripForm onTrip={handleTrip} onLoadingChange={setLoading} />
        {loading && <TripSummarySkeleton />}
        {!loading && trip && <TripSummary trip={trip} />}
      </main>
    </>
  )
}
