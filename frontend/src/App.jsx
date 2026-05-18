import { useState } from 'react'
import Header from './components/Header.jsx'
import TripForm from './components/TripForm.jsx'
import TripSummary from './components/TripSummary.jsx'
import TripSummarySkeleton from './components/TripSummarySkeleton.jsx'
import TripMap from './components/TripMap.jsx'
import TripMapSkeleton from './components/TripMapSkeleton.jsx'
import LogSheets from './components/LogSheets.jsx'
import LogSheetsSkeleton from './components/LogSheetsSkeleton.jsx'

/**
 * Editorial layout per MOCKUP.html (locked v5 spec):
 *   Header → TripForm → TripSummary → TripMap → LogSheets
 *
 * Wired so far: Header, TripForm, TripSummary, TripMap. LogSheets land in 4.6–4.7.
 */
export default function App() {
  const [trip, setTrip] = useState(null)
  const [loading, setLoading] = useState(false)

  return (
    <>
      <Header />
      <main className="max-w-[1180px] mx-auto px-4 md:px-8 py-6 md:py-8 space-y-6">
        <TripForm onTrip={setTrip} onLoadingChange={setLoading} />
        {loading && (
          <>
            <TripSummarySkeleton />
            <TripMapSkeleton />
            <LogSheetsSkeleton />
          </>
        )}
        {!loading && trip && (
          <>
            <TripSummary trip={trip} />
            <TripMap trip={trip} />
            <LogSheets trip={trip} />
          </>
        )}
      </main>
    </>
  )
}
