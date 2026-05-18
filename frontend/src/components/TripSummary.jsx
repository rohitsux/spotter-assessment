// TripSummary — verdict card. Port of MOCKUP.html §02 (legal + not-legal cases).
// No internal state. Formatting helpers are co-located below the component.

export default function TripSummary({ trip }) {
  const miles        = fmtMiles(trip.total_miles);
  const onClock      = fmtOnClock(trip.cycle_used_at_end, trip.current_cycle_used_hrs);
  const days         = fmtDays(trip);
  const remaining    = fmtRemaining(trip.cycle_used_at_end);
  const hoursShort   = trip.is_legal ? null : fmtHoursShort(trip.not_legal_reason, trip.cycle_used_at_end);
  const startLabel   = fmtDate(trip.start_at);
  const endLabel     = fmtDate(trip.end_at);
  const mascotSrc    = trip.is_legal ? '/mascots/mascot-legal.svg' : '/mascots/mascot-not-legal.svg';

  return (
    <section className="card p-7 relative">
      {/* Decorative mascot — purely visual, verdict text conveys legality */}
      <div className="verdict-mascot">
        <img src={mascotSrc} alt="" aria-hidden="true" />
      </div>

      <div className="flex items-start justify-between gap-6">
        <div className="flex-1">
          <div className="small-caps mb-2">No. 02 · The Verdict</div>

          {/* Pill + route. When current != pickup, show all three legs
              so the dispatcher sees the deadhead in the route header. */}
          <div className="flex items-center gap-3 mb-3 flex-wrap">
            {trip.is_legal ? (
              <span className="pill pill-ok">Trip is legal</span>
            ) : (
              <span className="pill pill-bad">Trip not legal in current cycle</span>
            )}
            <span className="small-caps">{routeLine(trip)}</span>
          </div>

          {/* Not-legal reason banner */}
          {!trip.is_legal && trip.not_legal_reason && (
            <div
              className="mt-4 p-4 rounded-sm"
              style={{ background: 'var(--vermillion-soft)', borderLeft: '3px solid var(--vermillion)' }}
            >
              <div className="small-caps mb-1" style={{ color: 'var(--vermillion)' }}>Reason</div>
              <p className="font-serif text-[15px] leading-snug text-[var(--ink)] max-w-[60ch]">
                {trip.not_legal_reason}
              </p>
            </div>
          )}

          {/* Stat grid */}
          <div className="grid grid-cols-4 gap-6 mt-4">
            <div>
              <div className="label">Distance</div>
              <div className="num-display text-[40px] leading-none mt-2">
                {miles} <span className="text-[13px] text-[var(--ink-3)] font-normal">mi</span>
              </div>
            </div>
            <div>
              <div className="label">Cycle on-duty</div>
              <div className="num-display text-[40px] leading-none mt-2">
                {onClock} <span className="text-[13px] text-[var(--ink-3)] font-normal">hrs</span>
              </div>
            </div>
            <div>
              <div className="label">Days</div>
              <div className="num-display text-[40px] leading-none mt-2">
                {days} <span className="text-[13px] text-[var(--ink-3)] font-normal">days</span>
              </div>
            </div>

            {trip.is_legal ? (
              <div>
                <div className="label">Cycle remaining at end</div>
                <div className="num-display text-[40px] leading-none mt-2">
                  {remaining} <span className="text-[13px] text-[var(--ink-3)] font-normal">/ 70.0</span>
                </div>
              </div>
            ) : (
              <div>
                <div className="label" style={{ color: 'var(--vermillion)' }}>Hours short</div>
                <div className="num-display text-[40px] leading-none mt-2" style={{ color: 'var(--vermillion)' }}>
                  {hoursShort} <span className="text-[13px] font-normal" style={{ color: 'var(--vermillion)' }}>hrs</span>
                </div>
              </div>
            )}
          </div>

          {/* Start / end row */}
          <div className="h-rule mt-6 pt-4 grid grid-cols-2 gap-6">
            <div>
              <div className="label">Starts</div>
              <div className="font-mono text-[14px] mt-1">{startLabel}</div>
            </div>
            <div>
              <div className="label">Ends</div>
              <div className="font-mono text-[14px] mt-1">{endLabel}</div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function routeLine(trip) {
  const cur = (trip.current_location || '').trim();
  const pu  = (trip.pickup_location  || '').trim();
  const drop = (trip.dropoff_location || '').trim();
  // If the user typed current == pickup, or the backend skipped the deadhead
  // (haversine < threshold), no DEADHEAD stop appears — fall back to the
  // simple 2-leg line. Detect via the persisted stops array.
  const hasDeadhead = Array.isArray(trip.stops)
    && trip.stops.some((s) => s.type === 'DEADHEAD');
  if (hasDeadhead && cur) {
    return `${cur} → ${pu} → ${drop}`;
  }
  return `${pu} → ${drop}`;
}

function fmtMiles(totalMiles) {
  return parseFloat(totalMiles).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

function fmtOnClock(cycleUsedAtEnd, currentCycleUsed) {
  const result = parseFloat(cycleUsedAtEnd) - parseFloat(currentCycleUsed);
  return result.toFixed(2);
}

function fmtDays(trip) {
  if (trip.log_days && trip.log_days.length > 0) {
    return trip.log_days.length;
  }
  const startMs = new Date(trip.start_at).getTime();
  const endMs   = new Date(trip.end_at).getTime();
  return Math.max(1, Math.ceil((endMs - startMs) / 86400000));
}

function fmtRemaining(cycleUsedAtEnd) {
  return (70 - parseFloat(cycleUsedAtEnd)).toFixed(2);
}

function fmtHoursShort(reason, cycleUsedAtEnd) {
  // Try to pull "needs X.X more" from the backend message.
  if (reason) {
    const match = reason.match(/needs\s+([\d.]+)\s+more/i);
    if (match) return parseFloat(match[1]).toFixed(2);
  }
  // Fallback: how many hours over 70 is cycle_used_at_end.
  const over = parseFloat(cycleUsedAtEnd) - 70;
  if (!isNaN(over) && over > 0) return over.toFixed(2);
  return '—';
}

function fmtDate(iso) {
  return new Date(iso).toLocaleString('en-US', {
    timeZone:  'UTC',
    weekday:   'short',
    month:     'short',
    day:       'numeric',
    hour:      'numeric',
    minute:    '2-digit',
    timeZoneName: 'short',
  });
}
