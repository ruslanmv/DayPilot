import React, { useMemo, useState } from 'react'
import './wellness.css'

type Weather = {
  location: string
  time: string
  temperature: number
  humidity: number
  feelsLike: number
  wind: number
  code: number
}
type GeoResponse = { results?: Array<{ name: string; country?: string; latitude: number; longitude: number }> }
type ForecastResponse = { current?: { time: string; temperature_2m: number; relative_humidity_2m: number; apparent_temperature: number; wind_speed_10m: number; weather_code: number } }
function weatherDescription(code: number): string {
  if (code === 0) return 'Clear skies'
  if ([1, 2, 3].includes(code)) return 'Cloudy or partly cloudy'
  if ([45, 48].includes(code)) return 'Foggy'
  if (code >= 51 && code <= 67) return 'Rain or drizzle'
  if (code >= 71 && code <= 77) return 'Snow'
  if (code >= 80 && code <= 82) return 'Showers'
  if (code >= 95) return 'Thunderstorms'
  return 'Variable conditions'
}
export function comfortSuggestions(temperature: number | null, humidity: number | null): string[] {
  const suggestions: string[] = []
  if (temperature === null && humidity === null) return ['Enter indoor readings from a thermometer and hygrometer to get workplace-specific suggestions. Outdoor conditions do not measure your room.']
  if (temperature !== null) {
    if (temperature < 20) suggestions.push('Your room may feel cool for sedentary work. Consider an extra layer and check for drafts.')
    else if (temperature > 26) suggestions.push('Your room may feel warm. Try shading direct sunlight, adjusting ventilation or cooling, and taking water breaks.')
    else suggestions.push('Your entered air temperature is in a common office range; comfort also depends on clothing, activity, radiation and airflow.')
  }
  if (humidity !== null) {
    if (humidity < 30) suggestions.push('Humidity is low. If you notice dryness, review ventilation and discuss safe humidity control for your space.')
    else if (humidity > 60) suggestions.push('Humidity is high. Check for condensation and improve moisture control or ventilation as appropriate.')
    else suggestions.push('Entered humidity is in a commonly used practical range; this alone cannot establish thermal comfort.')
  }
  return suggestions
}
export function WeatherWorkspace() {
  const [city, setCity] = useState('')
  const [weather, setWeather] = useState<Weather | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [indoorTemp, setIndoorTemp] = useState('')
  const [indoorHumidity, setIndoorHumidity] = useState('')
  const [notes, setNotes] = useState('')
  const temperature = indoorTemp.trim() && Number.isFinite(Number(indoorTemp)) && Number(indoorTemp) >= -10 && Number(indoorTemp) <= 50 ? Number(indoorTemp) : null
  const humidity = indoorHumidity.trim() && Number.isFinite(Number(indoorHumidity)) && Number(indoorHumidity) >= 0 && Number(indoorHumidity) <= 100 ? Number(indoorHumidity) : null
  const suggestions = useMemo(() => comfortSuggestions(temperature, humidity), [temperature, humidity])
  async function loadWeather(event: React.FormEvent) {
    event.preventDefault()
    if (city.trim().length < 2) return
    setBusy(true)
    setError('')
    setWeather(null)
    try {
      const params = new URLSearchParams({ name: city.trim(), count: '1', language: 'en', format: 'json' })
      const geoResponse = await fetch(`https://geocoding-api.open-meteo.com/v1/search?${params.toString()}`)
      if (!geoResponse.ok) throw new Error('Location lookup is temporarily unavailable.')
      const geo = await geoResponse.json() as GeoResponse
      const found = geo.results?.[0]
      if (!found) throw new Error('City not found. Try including your region or country.')
      const forecastParams = new URLSearchParams({
        latitude: String(found.latitude), longitude: String(found.longitude),
        current: 'temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,weather_code',
        timezone: 'auto',
      })
      const response = await fetch(`https://api.open-meteo.com/v1/forecast?${forecastParams.toString()}`)
      if (!response.ok) throw new Error('Weather service is temporarily unavailable.')
      const data = await response.json() as ForecastResponse
      if (!data.current || !Number.isFinite(data.current.temperature_2m)) throw new Error('Current weather readings are unavailable.')
      setWeather({
        location: [found.name, found.country].filter(Boolean).join(', '), time: data.current.time,
        temperature: data.current.temperature_2m, humidity: data.current.relative_humidity_2m,
        feelsLike: data.current.apparent_temperature, wind: data.current.wind_speed_10m, code: data.current.weather_code,
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load weather. Please retry.')
    } finally { setBusy(false) }
  }
  return <div className="dp-wellness-page dp-weather-page">
    <div className="dp-wellness-heading"><div><span className="dp-wellness-kicker">WEATHER & WORKSPACE</span><h1>Make your workspace comfortable</h1><p>Outdoor weather, indoor observations, and practical adjustments in one place.</p></div><span className="dp-wellness-chip">No location permission needed</span></div>
    <div className="dp-wellness-grid">
      <section className="dp-wellness-card dp-weather-outdoor">
        <div className="dp-wellness-section-title"><h2>Outdoor weather</h2><span>Open-Meteo</span></div>
        <form className="dp-weather-city" onSubmit={loadWeather}>
          <label htmlFor="dp-workplace-city">City or town</label>
          <div><input id="dp-workplace-city" autoComplete="address-level2" type="search" placeholder="Enter a city" value={city} onChange={event => setCity(event.target.value)} required minLength={2} /><button type="submit" disabled={busy}>{busy ? 'Loading…' : 'Check weather'}</button></div>
        </form>
        {error && <p role="alert" className="dp-weather-error">{error}</p>}
        {weather ? <div aria-live="polite">
          <div className="dp-weather-hero"><span aria-hidden="true">{weather.code >= 51 ? '🌧️' : weather.code <= 1 ? '☀️' : '⛅'}</span><div><strong>{weather.temperature.toFixed(1)}°C</strong><p>{weather.location}</p></div></div>
          <p>{weatherDescription(weather.code)} · Reported {weather.time.replace('T', ' ')} local time</p>
          <div className="dp-weather-metrics"><div><span>Outdoor humidity</span><strong>{weather.humidity}%</strong></div><div><span>Feels like</span><strong>{weather.feelsLike}°C</strong></div><div><span>Wind</span><strong>{weather.wind} km/h</strong></div></div>
        </div> : !busy && !error ? <p className="dp-weather-placeholder">Search for a city to see current modelled outdoor conditions. No weather values are fabricated.</p> : null}
        <p className="dp-wellness-small">Weather is model-derived outdoor data, not a measurement inside your workplace.</p>
      </section>
      <section className="dp-wellness-card dp-weather-indoor">
        <div className="dp-wellness-section-title"><h2>Your indoor environment</h2><span>Manual observations</span></div>
        <p>Use a real thermometer and hygrometer. These inputs are not automatically measured by DayPilot.</p>
        <div className="dp-weather-fields">
          <label>Air temperature (°C)<input type="number" inputMode="decimal" step="0.1" min="-10" max="50" placeholder="e.g. 23" value={indoorTemp} onChange={e => setIndoorTemp(e.target.value)} /></label>
          <label>Relative humidity (%)<input type="number" inputMode="numeric" step="1" min="0" max="100" placeholder="e.g. 50" value={indoorHumidity} onChange={e => setIndoorHumidity(e.target.value)} /></label>
        </div>
        {indoorTemp && temperature === null && <p className="dp-weather-error">Enter an indoor temperature between −10°C and 50°C.</p>}
        {indoorHumidity && humidity === null && <p className="dp-weather-error">Enter humidity from 0% to 100%.</p>}
        <div className="dp-weather-advice"><h3>Suggestions for your workstation</h3><ul>{suggestions.map(item => <li key={item}>{item}</li>)}</ul></div>
      </section>
    </div>
    <section className="dp-wellness-card dp-weather-checklist">
      <div className="dp-wellness-section-title"><h2>Healthy workplace checklist</h2><span>Comfort · light · air</span></div>
      <div className="dp-weather-checks"><div><span>🌤️</span><strong>Prevent screen glare</strong><p>Move the screen away from direct sunlight or adjust blinds without darkening the room unnecessarily.</p></div><div><span>💨</span><strong>Refresh indoor air</strong><p>Check ventilation and indoor air quality. Outdoor humidity is not a substitute for indoor readings.</p></div><div><span>🪑</span><strong>Choose a neutral posture</strong><p>Adjust your seat, screen and keyboard; take regular non-screen breaks and vary your position.</p></div></div>
      <label className="dp-weather-notes">Notes about your workspace<textarea rows={2} placeholder="e.g. afternoon glare or air conditioning draft" value={notes} onChange={e => setNotes(e.target.value)} /></label>
      <p className="dp-wellness-small">Notes stay in this tab while it is open. No health or indoor measurements are uploaded by DayPilot.</p>
    </section>
    <p className="dp-wellness-small">This is practical guidance, not a thermal comfort compliance calculation. The <a href="https://comfort.cbe.berkeley.edu/" target="_blank" rel="noopener noreferrer">UC Berkeley CBE Thermal Comfort Tool</a> evaluates PMV/PPD and adaptive comfort using additional factors including radiant temperature, air speed, clothing and metabolic rate. Use it for a fuller assessment.</p>
  </div>
}
