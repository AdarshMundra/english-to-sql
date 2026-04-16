import styles from './StatusBar.module.css'

export default function StatusBar({ health }) {
  if (!health) return <div className={styles.bar}><span className={styles.dot} style={{ background: '#8b949e' }} />Connecting…</div>

  const ok = health.status === 'ok'
  return (
    <div className={styles.bar}>
      <span className={styles.dot} style={{ background: ok ? 'var(--accent-green)' : 'var(--accent-red)' }} />
      <span className={styles.label}>{ok ? 'API Online' : 'API Unreachable'}</span>
      {ok && <span className={styles.model}>{health.openai_model}</span>}
    </div>
  )
}
