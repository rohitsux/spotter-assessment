import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { MapContainer, TileLayer, Polyline, Marker, Popup, useMap } from 'react-leaflet'
import { useEffect } from 'react'

// ── helpers ──────────────────────────────────────────────────────────────────

const STOP_META = {
  DEADHEAD: { ring: 'var(--ink-2)',      icon: '/icons/delivery-van-icon.svg', label: 'depart'      },
  PICKUP:   { ring: 'var(--olive)',      icon: '/icons/delivery-van-icon.svg', label: 'pickup'      },
  DROPOFF:  { ring: 'var(--olive)',      icon: '/icons/delivery-van-icon.svg', label: 'dropoff'     },
  FUEL:     { ring: 'var(--vermillion)', icon: '/icons/gas-pump-icon.svg',     label: 'fuel'        },
  REST_10:  { ring: 'var(--navy)',       icon: '/icons/snooze-zzz-icon.svg',   label: '10-hr rest'  },
  BREAK_30: { ring: '#7c4a2f',           icon: '/icons/coffee-icon.svg',       label: '30-min break' },
}

function metaFor(type) {
  return STOP_META[type] ?? STOP_META.PICKUP
}

function fmtArrive(iso) {
  if (!iso) return ''
  return new Intl.DateTimeFormat('en-US', {
    hour: 'numeric', minute: '2-digit',
    weekday: 'short',
    timeZone: 'UTC',
  }).format(new Date(iso))
}

// ── FitBounds: sets initial view once the map is mounted ─────────────────────

function FitBounds({ latLngs }) {
  const map = useMap()
  useEffect(() => {
    if (!latLngs || latLngs.length < 2) return
    try {
      map.fitBounds(L.latLngBounds(latLngs), { padding: [30, 30] })
    } catch {
      // malformed coords — silently ignore
    }
  }, [map, latLngs])
  return null
}

// ── main component ────────────────────────────────────────────────────────────

export default function TripMap({ trip }) {
  if (!trip) return null

  // Build [lat, lng] array from ORS FeatureCollection (coords are [lng, lat])
  let latLngs = []
  if (trip.route_geometry?.features?.[0]?.geometry?.coordinates) {
    latLngs = trip.route_geometry.features[0].geometry.coordinates.map(
      ([lng, lat]) => [lat, lng]
    )
  }

  const pickup  = trip.pickup_location  ?? ''
  const dropoff = trip.dropoff_location ?? ''

  return (
    <section className="card overflow-hidden">
      {/* header */}
      <div className="px-5 md:px-7 pt-5 md:pt-6 pb-4 flex items-center justify-between">
        <div>
          <div className="small-caps mb-1">No. 03 · The Route</div>
          <h2 className="editorial-title text-[22px] md:text-[26px] leading-tight">
            {pickup} to {dropoff}.
          </h2>
          <p className="font-serif italic text-[14px] text-[var(--ink-2)] mt-1">
            Routed on the truck profile. Bridge clearances and weight limits respected.
          </p>
        </div>
      </div>

      {/* map */}
      <div className="relative" style={{ height: 380 }}>
        <MapContainer
          style={{ height: '100%', width: '100%' }}
          scrollWheelZoom={true}
        >
          <TileLayer
            attribution="&copy; OSM contributors"
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          {latLngs.length >= 2 && (
            <>
              <FitBounds latLngs={latLngs} />
              {/* vermillion hex approximation — Leaflet SVG ignores CSS vars */}
              <Polyline
                positions={latLngs}
                pathOptions={{ color: '#d23a2c', weight: 3, opacity: 0.85 }}
              />
            </>
          )}

          {(trip.stops ?? []).map((stop, i) => {
            const lat = parseFloat(stop.lat)
            const lng = parseFloat(stop.lng)
            if (isNaN(lat) || isNaN(lng)) return null

            const { ring, icon, label } = metaFor(stop.type)
            const divIcon = L.divIcon({
              html: `<div class="map-icon-badge" style="--ring:${ring}"><img src="${icon}" alt=""/></div>`,
              className: 'leaflet-marker-clean',
              iconSize: [40, 40],
              iconAnchor: [20, 20],
              popupAnchor: [0, -22],
            })

            const city = stop.city ?? ''
            const state = stop.state ? `, ${stop.state}` : ''

            return (
              <Marker key={i} position={[lat, lng]} icon={divIcon}>
                <Popup>
                  <span className="font-serif" style={{ fontSize: 13 }}>
                    <strong>{city}{state}</strong>
                    {' · '}{label}
                    {' · '}{fmtArrive(stop.arrive_at)}
                  </span>
                </Popup>
              </Marker>
            )
          })}
        </MapContainer>
      </div>

      {/* stop list */}
      <div className="px-5 md:px-7 py-5 border-t border-[var(--line-2)]">
        <div className="label mb-3">Stop sequence</div>
        <ol className="space-y-2.5">
          {(trip.stops ?? []).map((stop, i) => {
            const { ring, icon, label } = metaFor(stop.type)
            const city  = stop.city  ?? ''
            const state = stop.state ? `, ${stop.state}` : ''
            const mile  = stop.mile_marker ? Math.round(parseFloat(stop.mile_marker)) : '—'

            return (
              <li key={i} className="flex items-center gap-2 md:gap-3 text-[13px] flex-wrap">
                <span className="map-icon-badge shrink-0" style={{ '--ring': ring }}>
                  <img src={icon} alt="" />
                </span>
                <span className="font-mono text-[var(--ink-3)] w-16 md:w-20 shrink-0">
                  mile {mile}
                </span>
                <span className="font-medium">{city}{state}</span>
                <span className="text-[var(--ink-3)]">
                  · {label} · {fmtArrive(stop.arrive_at)}
                </span>
              </li>
            )
          })}
        </ol>
      </div>
    </section>
  )
}
