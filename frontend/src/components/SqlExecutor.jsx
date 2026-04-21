import { useState } from 'react'
import ResultsTable from './ResultsTable'
import styles from './SqlExecutor.module.css'

const SAMPLE_QUERIES = [
  'SELECT * FROM students LIMIT 10',
  'SELECT d.name, COUNT(s.id) AS total FROM departments d LEFT JOIN students s ON s.department_id = d.id GROUP BY d.name ORDER BY total DESC',
  'SELECT name, cgpa FROM students WHERE cgpa > 8.5 ORDER BY cgpa DESC',
]

export default function SqlExecutor({ settings }) {
  const [sql, setSql] = useState('')
  const [connStr, setConnStr] = useState(settings.connectionString || '')
  const [maxRows, setMaxRows] = useState(100)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const execute = async () => {
    if (!sql.trim() || loading) return
    setLoading(true)
    setResult(null)
    setError(null)

    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sql: sql.trim(),
          connection_string: connStr || undefined,
          max_rows: maxRows,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Execution failed')
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) execute()
  }

  return (
    <div className={styles.panel}>
      <div className={styles.inputSection}>
        <div className={styles.header}>
          <span className={styles.title}>Direct SQL Executor</span>
          <span className={styles.note}>Only SELECT statements are permitted</span>
        </div>

        <div className={styles.connRow}>
          <input
            className={styles.connInput}
            placeholder="postgresql://user:pass@host/db  (or use Settings default)"
            value={connStr}
            onChange={e => setConnStr(e.target.value)}
          />
          <label className={styles.rowsLabel}>
            Max rows:
            <select
              className={styles.rowsSelect}
              value={maxRows}
              onChange={e => setMaxRows(Number(e.target.value))}
            >
              {[50, 100, 250, 500, 1000].map(n => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </label>
        </div>

        <div className={styles.editorWrapper}>
          <textarea
            className={styles.editor}
            value={sql}
            onChange={e => setSql(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="SELECT * FROM students LIMIT 10;"
            rows={8}
            spellCheck={false}
          />
          <div className={styles.editorFooter}>
            <div className={styles.samples}>
              {SAMPLE_QUERIES.map(q => (
                <button key={q} className={styles.sampleBtn} onClick={() => setSql(q)}>
                  {q.substring(0, 40)}{q.length > 40 ? '…' : ''}
                </button>
              ))}
            </div>
            <button
              className={`${styles.execBtn} ${loading ? styles.execBtnLoading : ''}`}
              onClick={execute}
              disabled={loading || !sql.trim()}
            >
              {loading ? (
                <><span className={styles.spinner} /> Running…</>
              ) : (
                <><span>▶</span> Run Query</>
              )}
            </button>
          </div>
        </div>
      </div>

      <div className={styles.outputSection}>
        {error && (
          <div className={styles.errorBox}>
            <span className={styles.errorIcon}>✕</span>
            <div>
              <div className={styles.errorTitle}>Execution Error</div>
              <div className={styles.errorMsg}>{error}</div>
            </div>
          </div>
        )}

        {result && (
          <>
            <div className={styles.resultLabel}>
              Results
              {result.truncated && (
                <span className={styles.truncNote}>truncated to {maxRows} rows</span>
              )}
            </div>
            <ResultsTable data={result} />
          </>
        )}

        {!result && !error && !loading && (
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon}>▶</div>
            <div className={styles.emptyTitle}>Execute SQL directly</div>
            <div className={styles.emptyDesc}>Write a SELECT statement above and press Run Query or Ctrl+Enter.</div>
          </div>
        )}
      </div>
    </div>
  )
}
