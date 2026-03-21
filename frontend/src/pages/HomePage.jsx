/**
 * STEP 12 — Home Page
 *
 * KEY REACT CONCEPT: useEffect
 * useEffect runs code AFTER the component renders.
 *   useEffect(() => { ... }, [])       → runs once when component mounts
 *   useEffect(() => { ... }, [value]) → runs when "value" changes
 *
 * Here we use it to:
 *  1. Check API health when the page loads
 *  2. Run a timer every second while a case is being analyzed
 *
 * STATE in this component:
 *  - isLoading   → is the API call in progress?
 *  - result      → the decision returned by the API
 *  - error       → any error message
 *  - elapsed     → seconds since the API call started (for the progress indicator)
 *  - health      → API health status
 */
import { useState, useEffect, useRef } from 'react'
import CaseForm from '../components/CaseForm.jsx'
import DecisionResult from '../components/DecisionResult.jsx'
import LoadingSpinner from '../components/LoadingSpinner.jsx'
import { analyzeCase, fetchHealth } from '../api/client.js'

export default function HomePage() {
  const [isLoading, setIsLoading] = useState(false)
  const [result, setResult]       = useState(null)
  const [source, setSource]       = useState(null)
  const [error, setError]         = useState(null)
  const [elapsed, setElapsed]     = useState(0)
  const [health, setHealth]       = useState(null)

  // useRef is like useState but does NOT trigger a re-render.
  // We use it to store the timer ID so we can cancel it later.
  const timerRef = useRef(null)

  // Check API health once when the page loads (empty dependency array = run once)
  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth({ status: 'unavailable' }))
  }, [])

  // Start/stop the elapsed timer based on isLoading
  useEffect(() => {
    if (isLoading) {
      setElapsed(0)
      timerRef.current = setInterval(() => {
        setElapsed(prev => prev + 1)
      }, 1000)
    } else {
      clearInterval(timerRef.current)
    }
    // Cleanup: stop timer when component unmounts
    return () => clearInterval(timerRef.current)
  }, [isLoading])

  async function handleSubmit(formData) {
    setIsLoading(true)
    setResult(null)
    setError(null)
    setSource(null)

    try {
      const response = await analyzeCase(formData)
      setResult(response)
      setSource(response.source)
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again.')
    } finally {
      // finally runs whether the request succeeded or failed
      setIsLoading(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>✈ Airline Refund Decision</h1>
        <p>
          Submit your case for AI-powered DOT regulation analysis.
          {health && (
            <span style={{ marginLeft: 8, fontSize: '0.8rem', color: health.status === 'healthy' ? 'var(--green)' : 'var(--red)' }}>
              ● API {health.status} · {health.total_decisions} decisions processed
            </span>
          )}
        </p>
      </div>

      <div className="card">
        <h2 className="card-title">Case Details</h2>
        <CaseForm onSubmit={handleSubmit} isLoading={isLoading} />
      </div>

      {/* Show spinner while loading */}
      {isLoading && (
        <div className="card">
          <LoadingSpinner elapsed={elapsed} />
        </div>
      )}

      {/* Show error if something went wrong */}
      {error && (
        <div className="card" style={{ borderLeft: '4px solid var(--red)', background: 'var(--red-bg)' }}>
          <strong style={{ color: 'var(--red)' }}>Error:</strong> {error}
        </div>
      )}

      {/* Show result when ready */}
      {result && !isLoading && (
        <div className="card">
          <h2 className="card-title">Decision Result</h2>
          <DecisionResult result={result} source={source} />
        </div>
      )}
    </div>
  )
}
