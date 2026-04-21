import { useState, useEffect } from 'react'
import QueryPanel from './components/QueryPanel'
import SchemaViewer from './components/SchemaViewer'
import SqlExecutor from './components/SqlExecutor'
import SettingsPanel from './components/SettingsPanel'
import StatusBar from './components/StatusBar'
import styles from './App.module.css'

const TABS = [
  { id: 'query', label: 'Query', icon: '⚡' },
  { id: 'schema', label: 'Schema', icon: '🗄' },
  { id: 'execute', label: 'Execute SQL', icon: '▶' },
  { id: 'settings', label: 'Settings', icon: '⚙' },
]

export default function App() {
  const [activeTab, setActiveTab] = useState('query')
  const [health, setHealth] = useState(null)
  const [settings, setSettings] = useState({
    connectionString: '',
    schemaSource: 'db',
    openApiUrl: '',
    maxRetries: 3,
  })
  const [schemaStatus, setSchemaStatus] = useState({
    loaded: false, table_count: 0, column_count: 0, loaded_at: null, ttl_remaining_s: 0,
  })

  const refreshSchemaStatus = () => {
    fetch('/api/schema/status')
      .then(r => r.json())
      .then(setSchemaStatus)
      .catch(() => {})
  }

  useEffect(() => {
    fetch('/api/health')
      .then(r => r.json())
      .then(setHealth)
      .catch(() => setHealth({ status: 'unreachable' }))
    refreshSchemaStatus()
  }, [])

  return (
    <div className={styles.app}>
      <header className={styles.header}>
        <div className={styles.logo}>
          <span className={styles.logoIcon}>◈</span>
          <span className={styles.logoText}>Text-to-SQL Studio</span>
          <span className={styles.logoBadge}>Multi-Agent</span>
        </div>
        <nav className={styles.nav}>
          {TABS.map(tab => (
            <button
              key={tab.id}
              className={`${styles.navBtn} ${activeTab === tab.id ? styles.navBtnActive : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <span className={styles.navIcon}>{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </nav>
        <StatusBar health={health} />
      </header>

      <main className={styles.main}>
        {activeTab === 'query' && <QueryPanel settings={settings} schemaStatus={schemaStatus} />}
        {activeTab === 'schema' && <SchemaViewer settings={settings} />}
        {activeTab === 'execute' && <SqlExecutor settings={settings} />}
        {activeTab === 'settings' && (
          <SettingsPanel
            settings={settings}
            setSettings={setSettings}
            schemaStatus={schemaStatus}
            onSchemaLoaded={refreshSchemaStatus}
          />
        )}
      </main>
    </div>
  )
}
