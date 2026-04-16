import { useState } from 'react'
import styles from './SqlBlock.module.css'

export default function SqlBlock({ sql }) {
  const [copied, setCopied] = useState(false)

  const copy = () => {
    navigator.clipboard.writeText(sql)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  return (
    <div className={styles.block}>
      <div className={styles.toolbar}>
        <span className={styles.lang}>SQL</span>
        <button className={styles.copyBtn} onClick={copy}>
          {copied ? '✓ Copied' : 'Copy'}
        </button>
      </div>
      <pre className={styles.code}><code>{sql}</code></pre>
    </div>
  )
}
