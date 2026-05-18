import { useState } from 'react'
import { createTrip } from '../api'
import AutocompleteInput from './AutocompleteInput.jsx'

/**
 * TripForm — Section 1 of the editorial layout, ported verbatim from MOCKUP.html.
 *
 * Four inputs (current location, pickup, dropoff, cycle used hrs), one Plan-trip
 * button. POSTs to /api/trips/ on submit; bubbles the resulting Trip envelope
 * to the parent via the `onTrip` prop.
 *
 * Error handling per resolved Q4: 502 surfaces as a top-of-form vermillion
 * banner. 400s surface per-field. Network errors get a "is the backend running"
 * banner.
 */
export default function TripForm({ onTrip, onLoadingChange }) {
  const [cur,  setCur]  = useState('Dallas, TX')
  const [pu,   setPu]   = useState('Houston, TX')
  const [drop, setDrop] = useState('Chicago, IL')
  const [cyc,  setCyc]  = useState('20.0')

  const [loading,     setLoading]     = useState(false)
  const [topError,    setTopError]    = useState(null)
  const [fieldErrors, setFieldErrors] = useState({})

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    onLoadingChange?.(true)
    setTopError(null)
    setFieldErrors({})

    try {
      const trip = await createTrip({
        current_location:       cur,
        pickup_location:        pu,
        dropoff_location:       drop,
        current_cycle_used_hrs: parseFloat(cyc),
      })
      onTrip(trip)
    } catch (err) {
      const status = err?.response?.status
      const data   = err?.response?.data

      if (status === 400 && data && typeof data === 'object') {
        setFieldErrors(data)
      } else if (status === 502 && data?.detail) {
        // Backend now sends a human-readable detail; ignore any legacy
        // upstream_message field (kept off-screen even if present).
        setTopError({ detail: data.detail })
      } else if (!err.response) {
        setTopError({
          detail: 'Could not reach the planner. Is the backend running?',
        })
      } else {
        setTopError({ detail: 'An unexpected error occurred. Try again in a moment.' })
      }
    } finally {
      setLoading(false)
      onLoadingChange?.(false)
    }
  }

  function fieldErr(name) {
    const msgs = fieldErrors[name]
    if (!msgs || msgs.length === 0) return null
    return (
      <p className="small-caps mt-1" style={{ color: 'var(--vermillion)' }}>
        {Array.isArray(msgs) ? msgs.join(' ') : String(msgs)}
      </p>
    )
  }

  return (
    <section className="card p-5 md:p-7 form-section-anchor">
      <div className="mascot-float" aria-hidden="true">
        <img src="/mascots/mascot-idle.svg" alt="" />
      </div>

      {topError && (
        <div
          className="card mb-5 p-4"
          style={{
            borderColor: 'var(--vermillion)',
            background: 'var(--vermillion-soft)',
          }}
        >
          <p className="font-serif text-[15px]" style={{ color: 'var(--ink)' }}>
            {topError.detail}
          </p>
        </div>
      )}

      <div className="mb-5">
        <div className="small-caps mb-2">No. 01 · The Brief</div>
        <h2 className="editorial-title text-[28px] md:text-[36px] leading-[1.05]">Plan a trip.</h2>
      </div>

      <form className="space-y-4" onSubmit={handleSubmit}>
        <div className="field-row">
          <label className="label" htmlFor="cur">Current location</label>
          <div>
            <AutocompleteInput id="cur" value={cur} onChange={setCur} />
            {fieldErr('current_location')}
          </div>
        </div>

        <div className="field-row">
          <label className="label" htmlFor="pu">Pickup</label>
          <div>
            <AutocompleteInput id="pu" value={pu} onChange={setPu} />
            {fieldErr('pickup_location')}
          </div>
        </div>

        <div className="field-row">
          <label className="label" htmlFor="do">Dropoff</label>
          <div>
            <AutocompleteInput id="do" value={drop} onChange={setDrop} />
            {fieldErr('dropoff_location')}
          </div>
        </div>

        <div className="field-row">
          <label className="label" htmlFor="cyc">
            Cycle used <span className="font-mono">(hrs)</span>
          </label>
          <div>
            <div className="flex items-end gap-4">
              <input
                className="input max-w-[120px]"
                id="cyc"
                type="number"
                step="0.1"
                min="0"
                max="70"
                value={cyc}
                onChange={(e) => setCyc(e.target.value)}
              />
              <span className="small-caps pb-2">of 70.0 available</span>
            </div>
            {fieldErr('current_cycle_used_hrs')}
          </div>
        </div>

        <div className="pt-2 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <span className="small-caps">Truck profile · driving-hgv · ORS</span>
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Planning…' : 'Plan trip'}
          </button>
        </div>
      </form>
    </section>
  )
}
