# Frontend — Complete Developer Guide

## Overview

A React 18 + Vite single-page application that provides a browser UI for the Text-to-SQL pipeline. Built entirely with CSS Modules (no Tailwind, no component library). Communicates with the FastAPI backend via `fetch`.

---

## Tech Stack

| Technology | Version | Purpose |
|---|---|---|
| React | 18.3.1 | UI framework |
| Vite | 5.4.2 | Build tool + dev server |
| `@vitejs/plugin-react` | 4.3.1 | JSX transform + Fast Refresh |
| CSS Modules | — | Scoped styling per component |

No third-party UI library, no router, no state management library.

---

## Folder Structure

```
frontend/
├── src/
│   ├── main.jsx                        # React entry point
│   ├── index.css                       # Global CSS variables + reset
│   ├── App.jsx                         # Root component, tab navigation
│   ├── App.module.css
│   └── components/
│       ├── QueryPanel.jsx              # Tab 1: Natural language → SQL
│       ├── QueryPanel.module.css
│       ├── SchemaViewer.jsx            # Tab 2: Browse DB/OpenAPI schema
│       ├── SchemaViewer.module.css
│       ├── SqlExecutor.jsx             # Tab 3: Run raw SQL directly
│       ├── SqlExecutor.module.css
│       ├── SettingsPanel.jsx           # Tab 4: Connection + pipeline config
│       ├── SettingsPanel.module.css
│       ├── ResultsTable.jsx            # Shared: display query result rows
│       ├── ResultsTable.module.css
│       ├── SqlBlock.jsx                # Shared: syntax-highlighted SQL display
│       ├── SqlBlock.module.css
│       └── StatusBar.jsx              # Header: API online/offline indicator
│           StatusBar.module.css
├── index.html
├── package.json
├── vite.config.js
├── .env                               # VITE_API_URL=http://localhost:8000
├── .env.example
└── .env.production                    # VITE_API_URL=<production backend URL>
```

---

## Environment Configuration

The only environment variable:

```bash
VITE_API_URL=http://localhost:8000   # dev
VITE_API_URL=https://your-api.onrender.com   # production
```

All API calls use `${import.meta.env.VITE_API_URL}` as the base. Vite inlines this at build time — it is **not** a runtime secret and is visible in the built JS bundle.

---

## App.jsx — Root Component

### State
```javascript
const [activeTab, setActiveTab] = useState('query')
const [health, setHealth] = useState(null)
const [settings, setSettings] = useState({
  connectionString: '',
  schemaSource: 'db',
  openApiUrl: '',
  maxRetries: 3,
})
```

### Tabs
```javascript
const TABS = [
  { id: 'query',    label: 'Query',      icon: '⚡' },
  { id: 'schema',   label: 'Schema',     icon: '🗄' },
  { id: 'execute',  label: 'Execute SQL', icon: '▶' },
  { id: 'settings', label: 'Settings',   icon: '⚙' },
]
```

### Health check
On mount, `App` hits `/health`. The `StatusBar` component shows "API Online" (green) or "API Unreachable" (red) + the model name.

### Settings flow
`settings` state is defined in `App` and passed down as props to all tab components. `SettingsPanel` receives `setSettings` to update it. This is the only prop drilling — no context/state library needed.

---

## QueryPanel.jsx — Tab 1

**Purpose:** Type an English question, optionally toggle "Execute SQL", submit to `/query`, display the generated SQL and results.

### State
```javascript
const [query, setQuery]           // textarea content
const [loading, setLoading]       // disables form during request
const [result, setResult]         // QueryResponse from API
const [error, setError]           // network/API error message
const [executeQuery, setExecuteQuery]  // toggle: also run the SQL
```

### API Call
```javascript
POST /query
{
  english_query: query,
  schema_source: settings.schemaSource,
  max_retries: settings.maxRetries,
  execute_query: executeQuery,
  connection_string: ...,   // if schema_source === 'db'
  openapi_url: ...,         // if schema_source === 'openapi_url'
}
```

### Keyboard shortcut
`Ctrl+Enter` (or `Cmd+Enter`) submits the form.

### Example queries (hardcoded)
```javascript
'How many students are enrolled per department?'
'Top 5 professors by course count'
'List students with CGPA above 8.5 ordered by CGPA'
'Which courses have more than 30 enrolled students?'
'Show average exam scores per subject'
```

### Loading state
Shows an animated "Running pipeline…" view with four agent names (Schema Agent → Query Agent → SQL Generator → Validator) fading in sequentially using CSS `animation-delay`.

### Result display
- `StatusBadge` — green ✓ success / red ✕ failed
- `MetaChip` — attempts count, elapsed time, row count (if executed)
- `SqlBlock` — displays the generated SQL with a copy button
- `ResultsTable` — shows rows if `execute_query=True` and execution succeeded

---

## SchemaViewer.jsx — Tab 2

**Purpose:** Browse table structure without running a query. Calls `POST /schema/preview`.

### Local state (independent of global settings)
```javascript
const [connStr, setConnStr]         // overrides settings default
const [openApiUrl, setOpenApiUrl]   // overrides settings default
const [source, setSource]           // "db" | "openapi_url"
const [schema, setSchema]           // SchemaOut from API
const [selectedTable, setSelectedTable]
```

### Layout
Two-panel: left sidebar (table list + relationships), right main panel (column detail table).

Column table shows: Column name, Type, Nullable (Yes/No), PK (✓/—), FK (✓/—), References.

Primary key columns are highlighted with a `PK` badge.

---

## SqlExecutor.jsx — Tab 3

**Purpose:** Run raw SQL directly against the database. Calls `POST /execute`.

### Features
- Textarea for SQL input (8 rows)
- Connection string input (overrides settings)
- Max rows selector (50 / 100 / 250 / 500 / 1000)
- Sample queries to click-to-fill:
  ```sql
  SELECT * FROM students LIMIT 10
  SELECT d.name, COUNT(s.id) ... (department enrollment count)
  SELECT name, cgpa FROM students WHERE cgpa > 8.5 ...
  ```
- `Ctrl+Enter` to run
- Displays `ResultsTable` with result rows

Note: Only SELECT is allowed — the backend tool rejects write operations.

---

## SettingsPanel.jsx — Tab 4

**Purpose:** Global configuration that persists in `App` state for the session (not in localStorage — resets on page refresh).

### Fields
- **Default Schema Source** — dropdown: PostgreSQL Database / OpenAPI URL
- **PostgreSQL Connection String** — text input (shown when schema_source=db)
- **OpenAPI Spec URL** — text input (shown when schema_source=openapi_url)
- **Max Retries** — range slider 1–10

### Pipeline flow diagram
The settings tab renders a visual 5-step diagram of the agent pipeline with colored step numbers.

### API information panel
Displays `VITE_API_URL`, Swagger UI URL, pipeline description, and SQL dialect.

---

## ResultsTable.jsx — Shared Component

Renders query results as an HTML table.

Props: `{ columns, rows, row_count, execution_time_ms, truncated }`

- Row numbers in first column (#)
- `NULL` values rendered as the text "NULL" with a distinct style
- Shows row count + execution time in a metadata line above the table
- Scrollable table wrapper for wide results

---

## SqlBlock.jsx — Shared Component

Renders SQL in a `<pre><code>` block with:
- Language label ("SQL")
- Copy button — uses `navigator.clipboard.writeText()`, shows "✓ Copied" for 1.8s

No syntax highlighting library (plain text inside `<code>`).

---

## StatusBar.jsx — Header Component

Receives `health` prop from `App` (result of `/health` fetch on mount).

States:
- `null` — "Connecting…" (grey dot)
- `{status: "ok", openai_model: "gpt-4o"}` — "API Online" (green dot) + model name
- `{status: "unreachable"}` — "API Unreachable" (red dot)

---

## Vite Configuration

```javascript
// vite.config.js
export default defineConfig({
  plugins: [react()],
  server: { port: 3000 },
})
```

Dev server runs on port 3000 (backend on 8000). No proxy is configured — CORS is handled by the backend (`allow_origins=["*"]`).

---

## Build & Deploy

```bash
npm run build    # outputs to frontend/dist/
npm run preview  # locally preview the production build
```

The `dist/` folder contains:
- `index.html`
- `assets/index-[hash].js` — bundled React app
- `assets/index-[hash].css` — bundled styles

For Vercel deployment, Vite's build output is automatically detected.

---

## Data Flow: Query Tab Example

```
User types: "How many students per department?"
User clicks: "Generate SQL"

    handleSubmit()
        │
        ├─ setLoading(true)
        ├─ fetch(POST /query, {english_query, schema_source, ...})
        │
        │   [backend runs 5-agent pipeline ~5–15s]
        │
        ├─ response: { status: "success", sql: "SELECT d.name...", attempts: 1, elapsed_s: 6.2 }
        │
        └─ setResult(data)

UI renders:
    StatusBadge: ✓ success
    MetaChip:    ↺ 1 attempt   ⏱ 6.20s
    SqlBlock:    SELECT d.name, COUNT(s.student_id) AS...
```

If `Execute SQL` toggle is ON:
```
    additional in response: { query_result: { columns: [...], rows: [...], row_count: 7 } }

UI renders:
    MetaChip:    ⊞ 7 rows  (green)
    ResultsTable: | name              | student_count |
                  | Computer Science  | 7             |
                  | ...               |               |
```

---

## Component Dependency Tree

```
App
├── StatusBar           (reads: health)
├── QueryPanel          (reads: settings)
│   ├── SqlBlock        (shared)
│   └── ResultsTable    (shared)
├── SchemaViewer        (reads: settings)
├── SqlExecutor         (reads: settings)
│   └── ResultsTable    (shared)
└── SettingsPanel       (reads: settings, writes: setSettings)
```

---

## CSS Architecture

Global variables in `index.css`:
```css
--bg-primary, --bg-secondary, --bg-tertiary
--text-primary, --text-secondary, --text-muted
--border-default, --border-subtle
--accent-blue, --accent-green, --accent-red, --accent-orange, --accent-purple
--font-mono
```

Dark theme by default. Each component has its own `.module.css` file with locally scoped class names.

---

## Adding a New Tab

1. Create `src/components/MyTab.jsx` + `MyTab.module.css`
2. Add to `TABS` array in `App.jsx`
3. Add `{activeTab === 'mytab' && <MyTab settings={settings} />}` in `<main>`
4. Pass any needed API calls; use `import.meta.env.VITE_API_URL` as base URL
