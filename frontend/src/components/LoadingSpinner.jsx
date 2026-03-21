/**
 * STEP 9 — LoadingSpinner Component
 *
 * PROPS: Props are how you pass data INTO a component (like function arguments).
 * Here we pass "elapsed" (seconds) so the spinner shows how long it's been running.
 *
 * The pipeline takes 15-30 seconds, so we show animated steps
 * that activate based on elapsed time to give feedback.
 */
export default function LoadingSpinner({ elapsed = 0 }) {
  const steps = [
    { label: '🔍 Classifier — extracting case details',    activeAt: 0  },
    { label: '📚 Researcher — searching regulations',      activeAt: 3  },
    { label: '🔢 Analyst — calculating refund amounts',    activeAt: 10 },
    { label: '✍️  Writer — drafting decision letter',      activeAt: 18 },
    { label: '⚖️  Judge — validating final decision',      activeAt: 24 },
  ]

  return (
    <div className="loading-container">
      <div className="spinner" />
      <p><strong>Processing your case...</strong> ({elapsed}s)</p>
      <div className="loading-steps">
        {steps.map((step, i) => {
          const isDone   = elapsed > (steps[i + 1]?.activeAt ?? 999)
          const isActive = !isDone && elapsed >= step.activeAt
          return (
            <div key={i} className="loading-step">
              <div className={`step-dot ${isDone ? 'done' : isActive ? 'active' : ''}`} />
              <span style={{ opacity: elapsed >= step.activeAt ? 1 : 0.4 }}>
                {step.label}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
