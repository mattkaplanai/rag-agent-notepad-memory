/**
 * STEP 13 — History Page
 *
 * Fetches paginated past decisions from GET /api/v1/decisions/
 * and displays them in a table.
 *
 * KEY CONCEPT: Data Fetching with useEffect
 * Whenever "page" state changes, the useEffect re-runs and fetches new data.
 * This is how pagination works in React — change state → effect runs → UI updates.
 */
import { useState, useEffect } from 'react'
import { fetchDecisions } from '../api/client.js'

function DecisionBadge({ decision }) {
  const cls = `badge badge-${decision?.toLowerCase() || 'error'}`
  return <span className={cls}>{decision}</span>
}

export default function HistoryPage() {
  const [data, setData]       = useState(null)   // { count, results, next, previous }
  const [page, setPage]       = useState(1)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError]     = useState(null)

  // Re-fetch whenever "page" changes
  useEffect(() => {
    setIsLoading(true)
    setError(null)

    fetchDecisions(page)
      .then(setData)
      .catch(err => setError(err.message))
      .finally(() => setIsLoading(false))
  }, [page])  // ← "page" in this array means: re-run when page changes

  const totalPages = data ? Math.ceil(data.count / 20) : 1

  return (
    <div>
      <div className="page-header">
        <h1>Decision History</h1>
        <p>{data ? `${data.count} total decisions` : 'Loading...'}</p>
      </div>

      <div className="card">
        {isLoading && (
          <div className="loading-container">
            <div className="spinner" />
            <p>Loading decisions...</p>
          </div>
        )}

        {error && (
          <div style={{ color: 'var(--red)', padding: 16 }}>
            Error: {error}
          </div>
        )}

        {!isLoading && !error && data?.results?.length === 0 && (
          <div className="empty-state">
            <div style={{ fontSize: '2.5rem' }}>📭</div>
            <p>No decisions yet. Submit a case to get started.</p>
          </div>
        )}

        {!isLoading && !error && data?.results?.length > 0 && (
          <>
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Case Type</th>
                    <th>Flight</th>
                    <th>Airline</th>
                    <th>Decision</th>
                    <th>Confidence</th>
                    <th>Time (s)</th>
                    <th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.map(d => (
                    <tr key={d.id}>
                      <td style={{ color: 'var(--gray-400)', fontSize: '0.8rem' }}>{d.id}</td>
                      <td>{d.case_type}</td>
                      <td style={{ fontSize: '0.82rem', color: 'var(--gray-600)' }}>
                        {d.flight_type}
                      </td>
                      <td style={{ fontSize: '0.85rem' }}>
                        {d.airline_name || <span style={{ color: 'var(--gray-400)' }}>—</span>}
                      </td>
                      <td><DecisionBadge decision={d.decision} /></td>
                      <td style={{ fontSize: '0.85rem', color: 'var(--gray-600)' }}>
                        {d.confidence}
                      </td>
                      <td style={{ fontSize: '0.85rem', color: 'var(--gray-600)' }}>
                        {d.processing_time_seconds ?? '—'}
                      </td>
                      <td style={{ fontSize: '0.82rem', color: 'var(--gray-600)' }}>
                        {new Date(d.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="pagination">
                <button
                  className="btn btn-outline btn-sm"
                  disabled={page === 1}
                  onClick={() => setPage(p => p - 1)}
                >
                  ← Previous
                </button>
                <span>Page {page} of {totalPages}</span>
                <button
                  className="btn btn-outline btn-sm"
                  disabled={page === totalPages}
                  onClick={() => setPage(p => p + 1)}
                >
                  Next →
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
