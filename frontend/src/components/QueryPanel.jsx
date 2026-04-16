import { useState, useRef } from 'react'
import ResultsTable from './ResultsTable'
import SqlBlock from './SqlBlock'
import styles from './QueryPanel.module.css'

const EXAMPLE_QUERIES = [
  'How many students are enrolled per department?',
  'Top 5 professors by course count',
  'List students with CGPA above 8.5 ordered by CGPA',
  'Which courses have more than 30 enrolled students?',
  'Show average exam scores per subject',
]

export default function QueryPanel({ settings }) {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [executeQuery, setExecuteQuery] = useState(false)
  const textareaRef = useRef(null)

  const handleSubmit = async (e) => {
    e?.preventDefault()
    if (!query.trim() || loading) return

    setLoading(true)
    setResult(null)
    setError(null)

    try {
      const body = {
        english_query: query.trim(),
        schema_source: settings.schemaSource,
        max_retries: settings.maxRetries,
        execute_query: executeQuery,
      }

      if (settings.schemaSource === 'db') {
        body.connection_string = settings.connectionString || undefined
      } else if (settings.schemaSource === 'openapi_url') {
        body.openapi_url = settings.openApiUrl
      }

      const res = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Request failed')
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      handleSubmit()
    }
  }

  return (
    <div className={styles.panel}>
      <div className={styles.inputSection}>
        <div className={styles.sectionHeader}>
          <span className={styles.sectionTitle}>Natural Language Query</span>
          <div className={styles.headerActions}>
            <label className={styles.toggle}>
              <input
                type="checkbox"
                checked={executeQuery}
                onChange={e => setExecuteQuery(e.target.checked)}
              />
              <span className={styles.toggleTrack}>
                <span className={styles.toggleThumb} />
              </span>
              <span className={styles.toggleLabel}>Execute SQL</span>
            </label>
          </div>
        </div>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.textareaWrapper}>
            <textarea
              ref={textareaRef}
              className={styles.textarea}
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask anything about your data… e.g. 'How many students are enrolled per department?'"
              rows={4}
            />
            <div className={styles.textareaFooter}>
              <span className={styles.hint}>Ctrl+Enter to run</span>
              <button
                type="submit"
                className={`${styles.runBtn} ${loading ? styles.runBtnLoading : ''}`}
                disabled={loading || !query.trim()}
              >
                {loading ? (
                  <>
                    <span className={styles.spinner} />
                    Generating…
                  </>
                ) : (
                  <>
                    <span>⚡</span>
                    Generate SQL
                  </>
                )}
              </button>
            </div>
          </div>
        </form>

        <div className={styles.examples}>
          <span className={styles.examplesLabel}>Try:</span>
          {EXAMPLE_QUERIES.map(q => (
            <button
              key={q}
              className={styles.exampleBtn}
              onClick={() => { setQuery(q); textareaRef.current?.focus() }}
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      <div className={styles.outputSection}>
        {error && (
          <div className={styles.errorBox}>
            <span className={styles.errorIcon}>✕</span>
            <div>
              <div className={styles.errorTitle}>Error</div>
              <div className={styles.errorMsg}>{error}</div>
            </div>
          </div>
        )}

        {result && (
          <div className={styles.resultArea}>
            <div className={styles.resultMeta}>
              <StatusBadge status={result.status} />
              <MetaChip icon="↺" label={`${result.attempts} attempt${result.attempts !== 1 ? 's' : ''}`} />
              <MetaChip icon="⏱" label={`${result.elapsed_s?.toFixed(2)}s`} />
              {result.query_result && (
                <MetaChip icon="⊞" label={`${result.query_result.row_count} rows`} color="green" />
              )}
            </div>

            {result.sql && (
              <div className={styles.sqlSection}>
                <div className={styles.blockLabel}>Generated SQL</div>
                <SqlBlock sql={result.sql} />
              </div>
            )}

            {result.error && (
              <div className={styles.warningBox}>
                <span>⚠</span>
                <span>{result.error}</span>
              </div>
            )}

            {result.query_result && !result.query_result.error && (
              <div className={styles.tableSection}>
                <div className={styles.blockLabel}>
                  Query Results
                  {result.query_result.truncated && (
                    <span className={styles.truncatedNote}>(truncated to 500 rows)</span>
                  )}
                </div>
                <ResultsTable data={result.query_result} />
              </div>
            )}

            {result.query_result?.error && (
              <div className={styles.errorBox}>
                <span className={styles.errorIcon}>✕</span>
                <div>
                  <div className={styles.errorTitle}>Execution Error</div>
                  <div className={styles.errorMsg}>{result.query_result.error}</div>
                </div>
              </div>
            )}
          </div>
        )}

        {!result && !error && !loading && (
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon}>◈</div>
            <div className={styles.emptyTitle}>Ready to query</div>
            <div className={styles.emptyDesc}>
              Type a question in natural language and the multi-agent pipeline will generate validated PostgreSQL for you.
            </div>
          </div>
        )}

        {loading && (
          <div className={styles.loadingState}>
            <div className={styles.agentSteps}>
              {['Schema Agent', 'Query Agent', 'SQL Generator', 'Validator'].map((agent, i) => (
                <div key={agent} className={styles.agentStep} style={{ animationDelay: `${i * 0.4}s` }}>
                  <span className={styles.agentDot} />
                  <span>{agent}</span>
                </div>
              ))}
            </div>
            <div className={styles.loadingText}>Running pipeline…</div>
          </div>
        )}
      </div>
    </div>
  )
}

function StatusBadge({ status }) {
  const ok = status === 'success'
  return (
    <span className={styles.statusBadge} style={{
      color: ok ? 'var(--accent-green)' : 'var(--accent-red)',
      background: ok ? 'rgba(63,185,80,0.1)' : 'rgba(248,81,73,0.1)',
      border: `1px solid ${ok ? 'rgba(63,185,80,0.3)' : 'rgba(248,81,73,0.3)'}`,
    }}>
      {ok ? '✓' : '✕'} {status}
    </span>
  )
}

function MetaChip({ icon, label, color }) {
  return (
    <span className={styles.metaChip} style={color === 'green' ? { color: 'var(--accent-green)' } : {}}>
      {icon} {label}
    </span>
  )
}
