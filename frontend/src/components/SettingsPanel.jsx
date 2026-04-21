import { useState } from 'react'
import styles from './SettingsPanel.module.css'

export default function SettingsPanel({ settings, setSettings }) {
  const [saved, setSaved] = useState(false)

  const update = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }))
  }

  const handleSave = () => {
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className={styles.panel}>
      <div className={styles.content}>
        <div className={styles.pageTitle}>Settings</div>
        <div className={styles.pageDesc}>
          Configure default connection and pipeline options used across all tabs.
        </div>

        <div className={styles.section}>
          <div className={styles.sectionTitle}>Database Connection</div>

          <div className={styles.field}>
            <label className={styles.label}>Default Schema Source</label>
            <select
              className={styles.select}
              value={settings.schemaSource}
              onChange={e => update('schemaSource', e.target.value)}
            >
              <option value="db">PostgreSQL Database</option>
              <option value="openapi_url">OpenAPI URL</option>
            </select>
            <span className={styles.fieldHint}>Determines which schema source is used in the Query tab.</span>
          </div>

          {settings.schemaSource === 'db' && (
            <div className={styles.field}>
              <label className={styles.label}>PostgreSQL Connection String</label>
              <input
                className={styles.input}
                type="text"
                value={settings.connectionString}
                onChange={e => update('connectionString', e.target.value)}
                placeholder="postgresql://user:password@localhost:5432/database"
                spellCheck={false}
              />
              <span className={styles.fieldHint}>
                Used as default when not overridden in individual requests.
                Stored in memory only — not persisted between sessions.
              </span>
            </div>
          )}

          {settings.schemaSource === 'openapi_url' && (
            <div className={styles.field}>
              <label className={styles.label}>OpenAPI Spec URL</label>
              <input
                className={styles.input}
                type="text"
                value={settings.openApiUrl}
                onChange={e => update('openApiUrl', e.target.value)}
                placeholder="https://petstore3.swagger.io/api/v3/openapi.json"
                spellCheck={false}
              />
              <span className={styles.fieldHint}>URL to an OpenAPI 3.x JSON or YAML specification.</span>
            </div>
          )}
        </div>

        <div className={styles.section}>
          <div className={styles.sectionTitle}>Pipeline Options</div>

          <div className={styles.field}>
            <label className={styles.label}>Max Retries</label>
            <div className={styles.sliderRow}>
              <input
                type="range"
                className={styles.slider}
                min={1}
                max={10}
                value={settings.maxRetries}
                onChange={e => update('maxRetries', Number(e.target.value))}
              />
              <span className={styles.sliderValue}>{settings.maxRetries}</span>
            </div>
            <span className={styles.fieldHint}>
              How many times the Validator→Generator retry loop can run per query (1–10).
            </span>
          </div>
        </div>

        <div className={styles.section}>
          <div className={styles.sectionTitle}>API Information</div>
          <div className={styles.infoGrid}>
            <InfoRow label="Backend URL" value={import.meta.env.VITE_API_URL} mono />
            <InfoRow label="Swagger UI" value={`${import.meta.env.VITE_API_URL}/docs`} mono />
            <InfoRow label="Pipeline" value="5-agent LangGraph" />
            <InfoRow label="SQL Dialect" value="PostgreSQL SELECT only" />
          </div>
        </div>

        <div className={styles.agentDiagram}>
          <div className={styles.sectionTitle}>Pipeline Flow</div>
          <div className={styles.steps}>
            {[
              { num: 1, name: 'Schema Agent', desc: 'Introspects DB or parses OpenAPI spec', color: '#58a6ff' },
              { num: 2, name: 'Query Agent', desc: 'Extracts intent, filters, joins', color: '#bc8cff' },
              { num: 3, name: 'SQL Generator', desc: 'Generates SELECT from schema + key points', color: '#ffa657' },
              { num: 4, name: 'Validator', desc: 'Syntax → schema refs → EXPLAIN → LLM semantic', color: '#d29922' },
              { num: 5, name: 'Executor', desc: 'Runs SQL and returns rows (opt-in)', color: '#3fb950' },
            ].map((step, i) => (
              <div key={step.num} className={styles.step}>
                <div className={styles.stepNum} style={{ borderColor: step.color, color: step.color }}>
                  {step.num}
                </div>
                {i < 4 && <div className={styles.stepArrow}>→</div>}
                <div className={styles.stepInfo}>
                  <div className={styles.stepName} style={{ color: step.color }}>{step.name}</div>
                  <div className={styles.stepDesc}>{step.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className={styles.actions}>
          <button className={styles.saveBtn} onClick={handleSave}>
            {saved ? '✓ Saved' : 'Apply Settings'}
          </button>
        </div>
      </div>
    </div>
  )
}

function InfoRow({ label, value, mono }) {
  return (
    <div className={styles.infoRow}>
      <span className={styles.infoLabel}>{label}</span>
      <span className={`${styles.infoValue} ${mono ? styles.infoMono : ''}`}>{value}</span>
    </div>
  )
}
