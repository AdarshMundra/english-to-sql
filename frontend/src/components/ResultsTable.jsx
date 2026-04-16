import styles from './ResultsTable.module.css'

export default function ResultsTable({ data }) {
  const { columns, rows, row_count, execution_time_ms } = data

  if (!rows || rows.length === 0) {
    return (
      <div className={styles.empty}>
        No rows returned ({execution_time_ms?.toFixed(1)}ms)
      </div>
    )
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.meta}>
        {row_count} row{row_count !== 1 ? 's' : ''} · {execution_time_ms?.toFixed(1)}ms
      </div>
      <div className={styles.tableWrapper}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.rowNum}>#</th>
              {columns.map(col => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                <td className={styles.rowNum}>{i + 1}</td>
                {row.map((cell, j) => (
                  <td key={j} className={cell === null ? styles.null : ''}>
                    {cell === null ? 'NULL' : String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
