import axios from 'axios'

// baseURL resolution:
//   - Dev (no env var): "/api" → Vite proxies to Django on :8000
//   - Prod (Vercel): VITE_API_BASE_URL is set to the Railway URL, e.g.
//     "https://spotter-backend-production.up.railway.app/api"
// Strip a trailing slash so we don't end up with "//trips/".
const rawBase = import.meta.env.VITE_API_BASE_URL || '/api'
const baseURL = rawBase.replace(/\/+$/, '')

const client = axios.create({ baseURL, timeout: 30000 })

export const createTrip = (payload) => client.post('/trips/', payload).then(r => r.data)
export const getTrip    = (id)      => client.get(`/trips/${id}/`).then(r => r.data)

// Returns { results: [{label, lng, lat}, ...] }. Empty/short queries return
// { results: [] } without hitting upstream — see backend view.
export const geocodeAutocomplete = (text, { signal } = {}) =>
  client.get('/geocode/', { params: { text }, signal }).then(r => r.data)
