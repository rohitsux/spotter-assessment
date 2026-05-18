import axios from 'axios'

const client = axios.create({ baseURL: '/api', timeout: 30000 })

export const createTrip = (payload) => client.post('/trips/', payload).then(r => r.data)
export const getTrip    = (id)      => client.get(`/trips/${id}/`).then(r => r.data)

// Returns { results: [{label, lng, lat}, ...] }. Empty/short queries return
// { results: [] } without hitting upstream — see backend view.
export const geocodeAutocomplete = (text, { signal } = {}) =>
  client.get('/geocode/', { params: { text }, signal }).then(r => r.data)
