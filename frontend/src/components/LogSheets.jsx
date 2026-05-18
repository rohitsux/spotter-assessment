import LogSheetGrid from './LogSheetGrid.jsx'

/**
 * LogSheets — Section 4 of the editorial layout.
 *
 * Stacks one LogDay card per day in the trip. Day 1 expands by default
 * via <details open>; days 2+ collapse. Each card shows:
 *   - Admin block (driver, tractor, trailer, terminal, shipper, commodity,
 *     BOL placeholder, daily miles)
 *   - 24-hour duty-status grid (LogSheetGrid)
 *   - Totals row (off / sleeper / driving / on-duty / total / on-clock circled)
 *
 * The trip envelope already includes per-day totals and entries from the
 * backend — see services/trip_builder.aggregate_log_days.
 */
export default function LogSheets({ trip }) {
  if (!trip?.log_days?.length) return null

  return (
    <section className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <div className="small-caps">No. 04 · The Record</div>
          <h2 className="editorial-title text-[26px] leading-tight">Daily logs.</h2>
        </div>
        <span className="small-caps">
          {trip.log_days.length} sheet{trip.log_days.length === 1 ? '' : 's'} · driver&rsquo;s daily log
        </span>
      </div>

      {trip.log_days.map((day, i) => (
        <LogDayCard key={day.date} day={day} dayIndex={i + 1} openByDefault={i === 0} />
      ))}
    </section>
  )
}


function LogDayCard({ day, dayIndex, openByDefault }) {
  const dateLabel = fmtDate(day.date)
  const onClockLabel = `${parseFloat(day.total_on_clock_hrs).toFixed(1)} hr on-clock`
  const milesLabel = `${parseFloat(day.total_miles).toFixed(0)} mi`

  return (
    <details className="card" open={openByDefault}>
      <summary
        className="px-5 md:px-6 py-4 flex items-center justify-between gap-3"
        style={{ cursor: 'pointer', listStyle: 'none' }}
      >
        <div className="flex items-center gap-3 md:gap-4 flex-wrap">
          <div className="small-caps">Day {ordinal(dayIndex)}</div>
          <div className="font-serif text-[17px] md:text-[20px] leading-tight">{dateLabel}</div>
          <div className="small-caps">{milesLabel} · {onClockLabel}</div>
        </div>
        <svg className="chev" width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M4 6L8 10L12 6" stroke="currentColor" strokeWidth="1.5"
                strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </summary>

      <div className="border-t" style={{ borderColor: 'var(--line-2)' }}>
        {/* Admin block */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 md:gap-x-8 gap-y-4 px-5 md:px-6 py-5 border-b"
             style={{ borderColor: 'var(--line-2)' }}>
          <AdminField label="Driver"        value={day.driver_name} />
          <AdminField label="Tractor"       value={day.tractor_number} />
          <AdminField label="Trailer"       value={day.trailer_number} />
          <AdminField label="Date"          value={dateLabel} />
          <AdminField label="Shipper"       value={day.shipper} />
          <AdminField label="Commodity"     value={day.commodity} />
          <AdminField label="Daily miles"   value={milesLabel} />
          <AdminField label="On-clock"      value={`${parseFloat(day.total_on_clock_hrs).toFixed(2)} hrs`} />
        </div>

        {/* 24-hr grid */}
        <div className="px-5 md:px-6 py-6 overflow-x-auto">
          <LogSheetGrid
            entries={day.entries || []}
            totals={{
              off_duty_hrs: day.total_off_duty_hrs,
              sleeper_hrs:  day.total_sleeper_hrs,
              driving_hrs:  day.total_driving_hrs,
              on_duty_hrs:  day.total_on_duty_hrs,
            }}
          />
        </div>

        {/* Totals row */}
        <div className="px-5 md:px-6 py-5 border-t grid grid-cols-2 md:grid-cols-6 gap-4 md:gap-6"
             style={{ borderColor: 'var(--line-2)' }}>
          <TotalCell label="Off-Duty"     value={day.total_off_duty_hrs} />
          <TotalCell label="Sleeper Berth" value={day.total_sleeper_hrs} />
          <TotalCell label="Driving"      value={day.total_driving_hrs} />
          <TotalCell label="On-Duty (not driving)" value={day.total_on_duty_hrs} />
          <TotalCell label="Total" value={
            (parseFloat(day.total_off_duty_hrs) +
             parseFloat(day.total_sleeper_hrs) +
             parseFloat(day.total_driving_hrs) +
             parseFloat(day.total_on_duty_hrs)).toFixed(1)
          } checkmark />
          <OnClockCell value={day.total_on_clock_hrs} />
        </div>
      </div>
    </details>
  )
}


function AdminField({ label, value }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className="font-mono text-[13px] mt-1">{value}</div>
    </div>
  )
}


function TotalCell({ label, value, checkmark }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className="num-display text-[24px] mt-1 flex items-center gap-1.5">
        {parseFloat(value).toFixed(1)}{' '}
        <span className="text-[11px] font-normal" style={{ color: 'var(--ink-3)' }}>hrs</span>
        {checkmark && (
          <svg width="14" height="14" viewBox="0 0 14 14">
            <path d="M3 7L6 10L11 4"
                  stroke="oklch(50% 0.09 130)"
                  strokeWidth="1.75" fill="none"
                  strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </div>
    </div>
  )
}


function OnClockCell({ value }) {
  return (
    <div>
      <div className="label">On-clock</div>
      <div className="num-display text-[24px] mt-1 flex items-center">
        <span className="relative inline-flex items-center justify-center px-1.5">
          <svg className="absolute" width="44" height="26" viewBox="0 0 44 26" fill="none">
            <ellipse cx="22" cy="13" rx="20" ry="11"
                     stroke="var(--vermillion)" strokeWidth="1.5" fill="none" />
          </svg>
          <span className="relative">{parseFloat(value).toFixed(1)}</span>
        </span>
        <span className="text-[11px] ml-2" style={{ color: 'var(--ink-3)' }}>drive + on-duty</span>
      </div>
    </div>
  )
}


function ordinal(n) {
  if (n === 1) return 'One'
  if (n === 2) return 'Two'
  if (n === 3) return 'Three'
  if (n === 4) return 'Four'
  if (n === 5) return 'Five'
  return String(n)
}


function fmtDate(isoDate) {
  // isoDate is "YYYY-MM-DD" — format as "Monday, May 18, 2026" using UTC
  const d = new Date(`${isoDate}T00:00:00Z`)
  return d.toLocaleDateString('en-US', {
    timeZone: 'UTC',
    weekday:  'long',
    month:    'long',
    day:      'numeric',
    year:     'numeric',
  })
}
