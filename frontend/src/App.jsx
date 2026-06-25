import { useEffect, useState } from 'react'

const API = 'http://localhost:8011/api'
const zl = (n) => (n == null ? '—' : Number(n).toLocaleString('pl-PL') + ' zł')
const hrs = (n) => (n == null ? '—' : Math.round(n) + ' h/mc')
const FLAG = { implausible: '#c0392b', heavy: '#e67e22', normal: '#27ae60' }

const wrap = { maxWidth: 920, margin: '2rem auto', padding: '0 1rem', fontFamily: 'system-ui, sans-serif', color: '#222' }
const td = { padding: '6px 10px', borderBottom: '1px solid #eee' }
const th = { ...td, textAlign: 'left', color: '#777', fontWeight: 600, fontSize: 13 }

export default function App() {
  const [cities, setCities] = useState([])
  const [city, setCity] = useState(null)
  const [doctors, setDoctors] = useState([])
  const [doctorId, setDoctorId] = useState(null)

  useEffect(() => { fetch(`${API}/cities`).then((r) => r.json()).then(setCities).catch(() => {}) }, [])
  useEffect(() => {
    if (!city) return
    fetch(`${API}/cities/${encodeURIComponent(city)}/doctors`).then((r) => r.json()).then(setDoctors).catch(() => {})
  }, [city])

  if (doctorId) return <DoctorView id={doctorId} onBack={() => setDoctorId(null)} />

  return (
    <div style={wrap}>
      <h1>🩺 Greedy Doctor</h1>
      <p style={{ color: '#777' }}>
        Radni-lekarze wg <b>implied hours</b> — ile godzin trzeba by przepracować przy rynkowej stawce,
        by osiągnąć zadeklarowany roczny dochód. Wysokie godziny = dochód ponad model godzinowy.
      </p>

      <h2>Miasta</h2>
      {cities.length === 0 && <p style={{ color: '#777' }}>Brak kandydatów (pipeline w toku albo zero lekarzy &gt; 300k).</p>}
      {cities.map((c) => (
        <button key={c.city} onClick={() => setCity(c.city)}
          style={{ display: 'block', margin: '4px 0', padding: '8px 12px', border: '1px solid #ddd',
            borderRadius: 6, background: c.city === city ? '#f0f6ff' : '#fff', cursor: 'pointer', fontSize: 15 }}>
          {c.city} — <b>{c.n_doctors}</b> lekarz(y) &gt; 300k
        </button>
      ))}

      {city && (
        <>
          <h2>{city} — top {doctors.length}</h2>
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <thead><tr>
              <th style={th}>Lekarz</th><th style={th}>Specjalizacja</th><th style={th}>Rok</th>
              <th style={th}>Dochód</th><th style={th}>Godziny B2B / etat</th><th style={th}>Flaga</th>
            </tr></thead>
            <tbody>
              {doctors.map((d, i) => (
                <tr key={i} onClick={() => setDoctorId(d.radny_id)} style={{ cursor: 'pointer' }}>
                  <td style={td}>{d.name}</td>
                  <td style={td}>{(d.specializations || []).join(', ')}</td>
                  <td style={td}>{d.year}</td>
                  <td style={td}>{zl(d.total_income)}</td>
                  <td style={td}>{hrs(d.implied_h_b2b)} / {hrs(d.implied_h_etat)}</td>
                  <td style={{ ...td, color: FLAG[d.flag] || '#777', fontWeight: 600 }}>{d.flag}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}

function DoctorView({ id, onBack }) {
  const [d, setD] = useState(null)
  useEffect(() => { fetch(`${API}/doctors/${id}`).then((r) => r.json()).then(setD).catch(() => {}) }, [id])
  if (!d) return <div style={wrap}>…</div>
  return (
    <div style={wrap}>
      <button onClick={onBack} style={{ cursor: 'pointer', marginBottom: 12 }}>← wróć</button>
      <h1>{d.name}</h1>
      <p style={{ color: '#777' }}>
        {d.city} · {(d.specializations || []).join(', ') || 'brak specjalizacji w NIL/ZnanyLekarz'} · {d.tier}
      </p>
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <thead><tr>
          <th style={th}>Rok</th><th style={th}>Dochód</th><th style={th}>Godziny B2B</th>
          <th style={th}>Godziny etat</th><th style={th}>Flaga</th>
        </tr></thead>
        <tbody>
          {(d.years || []).map((y) => (
            <tr key={y.year}>
              <td style={td}>{y.year}</td>
              <td style={td}>{zl(y.total_income)}</td>
              <td style={td}>{hrs(y.implied_h_b2b)}</td>
              <td style={td}>{hrs(y.implied_h_etat)}</td>
              <td style={{ ...td, color: FLAG[y.flag] || '#777', fontWeight: 600 }}>{y.flag}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
