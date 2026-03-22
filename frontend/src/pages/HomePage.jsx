/**
 * STEP 12 — Home Page (Async / Polling Edition)
 *
 * HOW ASYNC ARCHITECTURE CHANGES THIS PAGE:
 *
 * Before (synchronous):
 *   POST /analyze/ → wait 30-60s → get result
 *   Problem: if 100 users submit at once, the 100th user waits for all 99 before them.
 *
 * After (async with Celery):
 *   POST /analyze/ → get job_id in ~1s → poll every 2s → result appears when ready
 *   Benefit: all 100 users get their job_id instantly. Workers process in parallel.
 *
 * NEW STATE:
 *   - jobId      → the Celery task UUID returned by /analyze/
 *   - jobStatus  → "QUEUED" | "PENDING" | "STARTED" | "SUCCESS" | "FAILURE"
 *   - pollRef    → stores the setInterval ID so we can cancel it
 */
import { useState, useEffect, useRef } from 'react'
import CaseForm from '../components/CaseForm.jsx'
import DecisionResult from '../components/DecisionResult.jsx'
import LoadingSpinner from '../components/LoadingSpinner.jsx'
import { analyzeCase, fetchJobStatus, fetchHealth } from '../api/client.js'

export default function HomePage() {
  const [isLoading, setIsLoading]   = useState(false)
  const [result, setResult]         = useState(null)
  const [source, setSource]         = useState(null)
  const [error, setError]           = useState(null)
  const [elapsed, setElapsed]       = useState(0)
  const [health, setHealth]         = useState(null)
  const [jobStatus, setJobStatus]   = useState(null)  // NEW: current job state

  const timerRef = useRef(null)
  const pollRef  = useRef(null)   // NEW: polling interval handle

  // Check API health once when the page loads
  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth({ status: 'unavailable' }))
  }, [])

  // Elapsed timer — counts seconds while loading
  useEffect(() => {
    if (isLoading) {
      setElapsed(0)
      timerRef.current = setInterval(() => setElapsed(prev => prev + 1), 1000)
    } else {
      clearInterval(timerRef.current)
    }
    return () => clearInterval(timerRef.current)
  }, [isLoading])

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  /**
   * Start polling the job status endpoint every 2 seconds.
   * Stops when the job reaches SUCCESS or FAILURE.
   */
  function startPolling(jobId) {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const data = await fetchJobStatus(jobId)
        setJobStatus(data.status)

        if (data.status === 'SUCCESS') {
          stopPolling()
          setIsLoading(false)
          // The result from Celery is the full serialized RefundDecision
          setResult(data.result)
          setSource(data.result?.source || 'pipeline')
        } else if (data.status === 'FAILURE') {
          stopPolling()
          setIsLoading(false)
          setError(data.error || 'The AI pipeline failed. Please try again.')
        }
        // PENDING / STARTED → keep polling
      } catch (err) {
        stopPolling()
        setIsLoading(false)
        setError('Lost connection while waiting for results. Please try again.')
      }
    }, 2000)  // poll every 2 seconds
  }

  async function handleSubmit(formData) {
    setIsLoading(true)
    setResult(null)
    setError(null)
    setSource(null)
    setJobStatus('SUBMITTING')
    stopPolling()

    try {
      const response = await analyzeCase(formData)

      // Cache hit → immediate result (no polling needed)
      if (response.source && response.result) {
        setResult(response.result)
        setSource(response.source)
        setIsLoading(false)
        return
      }

      // Async job → start polling
      if (response.job_id) {
        setJobStatus('QUEUED')
        startPolling(response.job_id)
        // isLoading stays true — spinner shows while polling
      }
    } catch (err) {
      setError(err.message || 'Submission failed. Please try again.')
      setIsLoading(false)
    }
  }

  // Cleanup on unmount
  useEffect(() => () => { stopPolling(); clearInterval(timerRef.current) }, [])

  // Human-readable status label for the spinner
  const statusLabel = {
    SUBMITTING: 'Submitting case...',
    QUEUED:     'Queued — waiting for a worker...',
    PENDING:    'Queued — waiting for a worker...',
    STARTED:    'AI pipeline running...',
  }[jobStatus] || 'Processing...'

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

      {isLoading && (
        <div className="card">
          <LoadingSpinner elapsed={elapsed} statusLabel={statusLabel} />
        </div>
      )}

      {error && (
        <div className="card" style={{ borderLeft: '4px solid var(--red)', background: 'var(--red-bg)' }}>
          <strong style={{ color: 'var(--red)' }}>Error:</strong> {error}
        </div>
      )}

      {result && !isLoading && (
        <div className="card">
          <h2 className="card-title">Decision Result</h2>
          <DecisionResult result={result} source={source} />
        </div>
      )}
    </div>
  )
}
