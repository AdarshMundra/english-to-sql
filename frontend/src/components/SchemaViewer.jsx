import { useState } from 'react'
import styles from './SchemaViewer.module.css'

export default function SchemaViewer({ settings }) {
  const [loading, setLoading] = useState(false)
  const [schema, setSchema] = useState(null)
  const [error, setError] = useState(null)
  const [selectedTable, setSelectedTable] = useState(null)
  const [connStr, setConnStr] = useState(settings.connectionString || '')
  const [openApiUrl, setOpenApiUrl] = useState(settings.openApiUrl || '')
  const [source, setSource] = useState(settings.schemaSource || 'db')

  const load = async () => {
    setLoading(true)
    setError(null)
    setSchema(null)
    setSelectedTable(null)

    try {
      const body = { schema_source: source }
      if (source === 'db') body.connection_string = connStr || undefined
      if (source === 'openapi_url') body.openapi_url = openApiUrl

      const res = await fetch(`${import.meta.env.VITE_API_URL}/schema/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to load schema')
      setSchema(data)
      if (data.tables?.length) setSelectedTable(data.tables[0].name)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const activeTable = schema?.tables?.find(t => t.name === selectedTable)

  return (
    <div className={styles.panel}>
      <div className={styles.toolbar}>
        <div className={styles.toolbarLeft}>
          <span className={styles.title}>Schema Browser</span>
        </div>
        <div className={styles.toolbarRight}>
          <select
            className={styles.select}
            value={source}
            onChange={e => setSource(e.target.value)}
          >
            <option value="db">PostgreSQL DB</option>
            <option value="openapi_url">OpenAPI URL</option>
          </select>
          {source === 'db' ? (
            <input
              className={styles.input}
              placeholder="postgresql://user:pass@host/db"
              value={connStr}
              onChange={e => setConnStr(e.target.value)}
            />
          ) : (
            <input
              className={styles.input}
              placeholder="https://example.com/openapi.json"
              value={openApiUrl}
              onChange={e => setOpenApiUrl(e.target.value)}
            />
          )}
          <button className={styles.loadBtn} onClick={load} disabled={loading}>
            {loading ? <><span className={styles.spinner} /> Loading…</> : 'Load Schema'}
          </button>
        </div>
      </div>

      {error && (
        <div className={styles.errorBox}>
          <span>✕</span>
          <span>{error}</span>
        </div>
      )}

      {schema && (
        <div className={styles.content}>
          <aside className={styles.sidebar}>
            <div className={styles.sidebarHeader}>
              <span className={styles.sidebarTitle}>Tables</span>
              <span className={styles.sidebarCount}>{schema.table_count}</span>
            </div>
            <div className={styles.tableList}>
              {schema.tables.map(t => (
                <button
                  key={t.name}
                  className={`${styles.tableItem} ${selectedTable === t.name ? styles.tableItemActive : ''}`}
                  onClick={() => setSelectedTable(t.name)}
                >
                  <span className={styles.tableIcon}>⊞</span>
                  <span className={styles.tableName}>{t.name}</span>
                  <span className={styles.colCount}>{t.columns.length}</span>
                </button>
              ))}
            </div>

            {schema.relationships?.length > 0 && (
              <div className={styles.relSection}>
                <div className={styles.sidebarTitle} style={{ padding: '8px 12px 4px' }}>Relationships</div>
                {schema.relationships.map((r, i) => (
                  <div key={i} className={styles.relItem}>{r}</div>
                ))}
              </div>
            )}
          </aside>

          <main className={styles.tableDetail}>
            {activeTable && (
              <>
                <div className={styles.tableHeader}>
                  <span className={styles.tableHeaderName}>{activeTable.name}</span>
                  {activeTable.row_count != null && (
                    <span className={styles.rowCountBadge}>~{activeTable.row_count.toLocaleString()} rows</span>
                  )}
                </div>
                <div className={styles.columnTableWrapper}>
                  <table className={styles.columnTable}>
                    <thead>
                      <tr>
                        <th>Column</th>
                        <th>Type</th>
                        <th>Nullable</th>
                        <th>PK</th>
                        <th>FK</th>
                        <th>References</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activeTable.columns.map(col => (
                        <tr key={col.name}>
                          <td className={`${styles.colName} ${col.is_primary_key ? styles.pkCol : ''}`}>
                            {col.is_primary_key && <span className={styles.pkTag}>PK</span>}
                            {col.name}
                          </td>
                          <td className={styles.colType}>{col.data_type}</td>
                          <td>
                            <span className={col.nullable ? styles.yes : styles.no}>
                              {col.nullable ? 'Yes' : 'No'}
                            </span>
                          </td>
                          <td>{col.is_primary_key ? <span className={styles.checkYes}>✓</span> : <span className={styles.checkNo}>—</span>}</td>
                          <td>{col.is_foreign_key ? <span className={styles.checkYes}>✓</span> : <span className={styles.checkNo}>—</span>}</td>
                          <td className={styles.refCol}>{col.references || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </main>
        </div>
      )}

      {!schema && !loading && !error && (
        <div className={styles.emptyState}>
          <div className={styles.emptyIcon}>🗄</div>
          <div className={styles.emptyTitle}>No schema loaded</div>
          <div className={styles.emptyDesc}>Configure the connection and click "Load Schema" to browse your database structure.</div>
        </div>
      )}

      {loading && (
        <div className={styles.emptyState}>
          <span className={styles.spinnerLg} />
          <div className={styles.emptyDesc}>Introspecting schema…</div>
        </div>
      )}
    </div>
  )
}
