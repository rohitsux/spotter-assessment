/**
 * LogSheetGrid — 24-hour duty-status grid SVG renderer per MOCKUP.html.
 * Pure React port of the vanilla-JS renderer (MOCKUP.html lines 726-1001).
 *
 * Mimics the FMCSA paper RODS layout (Decision 2):
 *   - 24 hour columns (Midnight ... 11p), plus a Total Hours column
 *   - 4 rows: 1=Off-Duty / 2=Sleeper / 3=Driving / 4=On-Duty (not driving)
 *   - 15-min ticks (taller at :00 and :30)
 *   - Stepped horizontal duty line with dots at every transition
 *   - Vertical drops drawn straight through intermediate rows
 *   - Brackets below the timeline for stationary on-duty periods
 *   - Remarks at ~45 deg below the grid (city, state, activity)
 *
 * Props:
 *   entries  : list[{ start_time_minutes, end_time_minutes, duty_status, city, state, remark, is_stationary }]
 *   totals   : { off_duty_hrs, sleeper_hrs, driving_hrs, on_duty_hrs }
 */

// Layout constants — pixel-equivalent to MOCKUP. Don't change without
// re-eyeballing against MOCKUP.html.
const HOUR_W  = 36
const ROW_H   = 32
const LEFT_W  = 96
const RIGHT_W = 60
const TOP_H   = 26
const REMARK_H = 110
const ROWS = 4

const GRID_W  = HOUR_W * 24
const TOTAL_W = LEFT_W + GRID_W + RIGHT_W
const TOTAL_H = TOP_H + ROW_H * ROWS + REMARK_H

const ROW_LABELS = [
  '1. Off Duty',
  '2. Sleeper Berth',
  '3. Driving',
  '4. On Duty (not driving)',
]

const HOUR_LABELS = [
  'Midnight', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11',
  'Noon',     '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11',
]

// Colors — match MOCKUP OKLCH values exactly
const C_INK       = 'oklch(28% 0.06 250)'
const C_GRID      = 'oklch(40% 0.04 250)'
const C_INK_3     = 'oklch(60% 0.015 250)'
const C_TICK      = 'oklch(65% 0.02 250)'
const C_VERMILLION = 'oklch(55% 0.20 30)'
const C_INK_2     = 'oklch(40% 0.02 250)'

function xAt(min) { return LEFT_W + (min / 60) * HOUR_W }
function yAt(row) { return TOP_H + (row - 0.5) * ROW_H }


export default function LogSheetGrid({ entries = [], totals = {} }) {
  // 1. Normalize entries into renderer-shape segments
  const segments = entries.map((e) => ({
    start_min: e.start_time_minutes,
    end_min:   e.end_time_minutes,
    status:    e.duty_status,
  }))

  // 2. Remarks: one per duty-status transition that has a meaningful remark
  //    (the renderer ignores empty remarks). Use the entry's start time and
  //    its city/state/remark text.
  const remarks = entries
    .filter((e) => e.remark && e.start_time_minutes > 0 && e.start_time_minutes < 1440)
    .map((e) => ({
      minute:   e.start_time_minutes,
      city:     e.city || '',
      state:    e.state || '',
      activity: e.remark || '',
    }))

  // 3. Brackets below grid for stationary on-duty events (pickup/dropoff/fuel
  //    at a fixed location). Driving entries are NOT stationary.
  const brackets = entries
    .filter((e) => e.is_stationary && e.duty_status === 4)
    .map((e) => {
      const hrs = (e.end_time_minutes - e.start_time_minutes) / 60
      return {
        start_min: e.start_time_minutes,
        end_min:   e.end_time_minutes,
        label:     `${(e.remark || 'on-duty').toLowerCase()} ${hrs.toFixed(1)}`,
      }
    })

  const totalsArr = [
    totals.off_duty_hrs ?? 0,
    totals.sleeper_hrs ?? 0,
    totals.driving_hrs ?? 0,
    totals.on_duty_hrs ?? 0,
  ]

  return (
    <svg
      className="grid-svg"
      width={TOTAL_W}
      height={TOTAL_H}
      viewBox={`0 0 ${TOTAL_W} ${TOTAL_H}`}
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Outer frame */}
      <rect x={LEFT_W} y={TOP_H} width={GRID_W} height={ROW_H * ROWS}
            fill="#fff" stroke={C_GRID} strokeWidth="1" />
      <rect x={LEFT_W + GRID_W} y={TOP_H} width={RIGHT_W} height={ROW_H * ROWS}
            fill="#fff" stroke={C_GRID} strokeWidth="1" />

      {/* Top hour-label band */}
      <rect x={LEFT_W} y="0" width={GRID_W} height={TOP_H} fill={C_INK} />
      <rect x={LEFT_W + GRID_W} y="0" width={RIGHT_W} height={TOP_H} fill={C_INK} />

      {/* Hour labels */}
      {HOUR_LABELS.map((label, h) => {
        const x = LEFT_W + h * HOUR_W
        return (
          <text key={`hl-${h}`}
                x={x + HOUR_W / 2}
                y="17"
                textAnchor="middle"
                fontFamily="JetBrains Mono"
                fontSize="10"
                fill="#fff"
                fontWeight="500">
            {label}
          </text>
        )
      })}
      {/* Total Hours header */}
      <text x={LEFT_W + GRID_W + RIGHT_W / 2} y="11"
            textAnchor="middle" fontFamily="Karla" fontSize="9" fill="#fff" fontWeight="600">
        Total
      </text>
      <text x={LEFT_W + GRID_W + RIGHT_W / 2} y="21"
            textAnchor="middle" fontFamily="Karla" fontSize="9" fill="#fff" fontWeight="600">
        Hours
      </text>

      {/* Left row labels */}
      {ROW_LABELS.map((label, i) => {
        const r = i + 1
        const y = TOP_H + (r - 1) * ROW_H
        return (
          <g key={`row-${r}`}>
            <rect x="0" y={y} width={LEFT_W} height={ROW_H}
                  fill="#fff" stroke={C_GRID} strokeWidth="0.75" />
            <text x="6" y={y + ROW_H / 2 + 4}
                  fontFamily="Karla" fontSize="11" fill={C_INK}>
              {label}
            </text>
            {r < ROWS && (
              <line x1={LEFT_W} y1={y + ROW_H}
                    x2={LEFT_W + GRID_W + RIGHT_W} y2={y + ROW_H}
                    stroke={C_GRID} strokeWidth="0.75" />
            )}
          </g>
        )
      })}

      {/* 15-min ticks (inside each row band) */}
      {Array.from({ length: 24 * 4 }).map((_, idx) => {
        const h = Math.floor(idx / 4)
        const q = idx % 4
        const x = LEFT_W + h * HOUR_W + (q / 4) * HOUR_W
        return Array.from({ length: ROWS }).map((__, ri) => {
          const r = ri + 1
          const yTop = TOP_H + (r - 1) * ROW_H
          const yBot = yTop + ROW_H
          const tickH = q === 0 ? ROW_H : q === 2 ? ROW_H * 0.55 : ROW_H * 0.32
          return (
            <g key={`tick-${idx}-${r}`}>
              <line x1={x} y1={yTop} x2={x} y2={yTop + tickH}
                    stroke={C_TICK} strokeWidth="0.5" />
              <line x1={x} y1={yBot} x2={x} y2={yBot - tickH}
                    stroke={C_TICK} strokeWidth="0.5" />
            </g>
          )
        })
      })}

      {/* Vertical hour-boundary lines across all rows */}
      {Array.from({ length: 25 }).map((_, h) => {
        const x = LEFT_W + h * HOUR_W
        return (
          <line key={`hb-${h}`}
                x1={x} y1={TOP_H}
                x2={x} y2={TOP_H + ROW_H * ROWS}
                stroke={C_GRID}
                strokeWidth={h % 6 === 0 ? 0.9 : 0.6} />
        )
      })}

      {/* Duty-status stepped polyline */}
      {segments.length > 0 && (() => {
        let d = ''
        let prevY = yAt(segments[0].status)
        segments.forEach((seg, i) => {
          const x1 = xAt(seg.start_min)
          const x2 = xAt(seg.end_min)
          const y  = yAt(seg.status)
          if (i === 0) {
            d += `M ${x1} ${y} `
          } else {
            d += `L ${x1} ${prevY} L ${x1} ${y} `
          }
          d += `L ${x2} ${y} `
          prevY = y
        })
        return (
          <path d={d} stroke={C_INK} strokeWidth="2" fill="none"
                strokeLinecap="square" strokeLinejoin="miter" />
        )
      })()}

      {/* Transition dots */}
      {segments.length > 0 && Array.from(new Set(
        segments.flatMap((s) => [`${s.start_min}|${s.status}`, `${s.end_min}|${s.status}`])
      )).map((key) => {
        const [m, s] = key.split('|').map(Number)
        return (
          <circle key={`dot-${key}`}
                  cx={xAt(m)} cy={yAt(s)}
                  r="3" fill={C_VERMILLION} />
        )
      })}

      {/* Brackets below timeline (stationary on-duty) */}
      {brackets.map((b, i) => {
        const x1 = xAt(b.start_min)
        const x2 = xAt(b.end_min)
        const yBottom = TOP_H + ROW_H * ROWS
        const yB  = yBottom + 4
        const yB2 = yB + 5
        return (
          <g key={`br-${i}`}>
            <path d={`M ${x1} ${yB2} L ${x1} ${yB} L ${x2} ${yB} L ${x2} ${yB2}`}
                  stroke={C_INK_2} strokeWidth="1" fill="none" />
            <text x={(x1 + x2) / 2} y={yB2 + 9} textAnchor="middle"
                  fontFamily="JetBrains Mono" fontSize="9" fill={C_INK_2}>
              {b.label}
            </text>
          </g>
        )
      })}

      {/* Remarks at ~45 deg below */}
      {(() => {
        const remarkBaseY = TOP_H + ROW_H * ROWS + 26
        return (
          <g>
            <line x1={LEFT_W} y1={remarkBaseY + 4}
                  x2={LEFT_W + GRID_W} y2={remarkBaseY + 4}
                  stroke={C_TICK} strokeWidth="0.5" />
            <text x="0" y={remarkBaseY + 1}
                  fontFamily="Karla" fontSize="10" fontWeight="600" fill={C_INK}>
              Remarks
            </text>
            {remarks.map((r, i) => {
              const x = xAt(r.minute)
              const yTop = remarkBaseY + 4
              const yEnd = remarkBaseY + 70
              const xEnd = x + (yEnd - yTop)
              return (
                <g key={`rm-${i}`}>
                  <line x1={x} y1={TOP_H + ROW_H * ROWS}
                        x2={x} y2={yTop}
                        stroke={C_TICK} strokeWidth="0.5" />
                  <line x1={x} y1={yTop} x2={xEnd} y2={yEnd}
                        stroke={C_INK_3} strokeWidth="0.6" />
                  <g transform={`translate(${x + 4} ${yTop + 6}) rotate(45)`}>
                    <text x="0" y="0"
                          fontFamily="JetBrains Mono" fontSize="9"
                          fill={C_INK} fontWeight="600">
                      {r.city}{r.state ? `, ${r.state}` : ''}
                    </text>
                    <text x="0" y="11"
                          fontFamily="JetBrains Mono" fontSize="9" fill={C_INK_2}>
                      {r.activity}
                    </text>
                  </g>
                </g>
              )
            })}
          </g>
        )
      })()}

      {/* Total Hours column values */}
      {totalsArr.map((val, i) => {
        const r = i + 1
        const y = TOP_H + (r - 0.5) * ROW_H + 4
        return (
          <text key={`tot-${r}`}
                x={LEFT_W + GRID_W + RIGHT_W / 2}
                y={y}
                textAnchor="middle"
                fontFamily="JetBrains Mono"
                fontSize="13"
                fill={C_INK}
                fontWeight="500">
            {parseFloat(val).toFixed(2)}
          </text>
        )
      })}
    </svg>
  )
}
