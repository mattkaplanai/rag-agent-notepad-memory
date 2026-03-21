/**
 * STEP 11 — DecisionResult Component
 *
 * This receives the API response and displays it beautifully.
 * Props: { result, source }
 *
 * CONDITIONAL RENDERING in React:
 *   {condition && <Component />}  → renders only if condition is true
 *   {condition ? <A /> : <B />}  → renders A if true, B if false
 */

function DecisionBanner({ decision, confidence, processingTime, source }) {
  const cls = decision?.toLowerCase() || 'error'
  const emoji = { approved: '✅', denied: '❌', partial: '⚠️', error: '🚫' }[cls] || '❓'

  return (
    <div className={`decision-banner ${cls}`}>
      <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <span className="decision-label">{emoji} {decision}</span>
        <span className="confidence-badge">{confidence} confidence</span>
        {source && <span className="source-tag">{source}</span>}
      </div>
      {processingTime && (
        <p className="processing-time">Processed in {processingTime}s</p>
      )}
    </div>
  )
}

export default function DecisionResult({ result, source }) {
  // The API response structure differs slightly between cache hits and fresh results
  // Extract the actual decision data from wherever it is
  const data = result?.result ?? result

  if (!data) return null

  const {
    decision,
    confidence,
    reasons = [],
    applicable_regulations = [],
    refund_details,
    decision_letter,
    passenger_action_items = [],
    processing_time_seconds,
  } = data

  return (
    <div>
      <DecisionBanner
        decision={decision}
        confidence={confidence}
        processingTime={processing_time_seconds}
        source={source}
      />

      {/* Reasons */}
      {reasons.length > 0 && (
        <div className="result-section">
          <h4>Reasons</h4>
          <ul className="reasons-list">
            {reasons.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}

      {/* Refund Details */}
      {refund_details && (
        <div className="result-section">
          <h4>Refund Details</h4>
          <div style={{ background: 'var(--gray-50)', padding: '12px 16px', borderRadius: 6, fontSize: '0.9rem' }}>
            {typeof refund_details === 'string'
              ? refund_details
              : Object.entries(refund_details).map(([k, v]) => (
                  <div key={k} style={{ marginBottom: 4 }}>
                    <strong>{k.replace(/_/g, ' ')}:</strong> {String(v)}
                  </div>
                ))
            }
          </div>
        </div>
      )}

      {/* Applicable Regulations */}
      {applicable_regulations.length > 0 && (
        <div className="result-section">
          <h4>Applicable Regulations</h4>
          <div>
            {applicable_regulations.map((r, i) => (
              <span key={i} className="regulation-tag">{r}</span>
            ))}
          </div>
        </div>
      )}

      {/* Passenger Action Items */}
      {passenger_action_items.length > 0 && (
        <div className="result-section">
          <h4>Your Next Steps</h4>
          <ul className="reasons-list">
            {passenger_action_items.map((item, i) => <li key={i}>{item}</li>)}
          </ul>
        </div>
      )}

      {/* Decision Letter */}
      {decision_letter && (
        <div className="result-section">
          <h4>Formal Decision Letter</h4>
          <pre className="letter-box">{decision_letter}</pre>
        </div>
      )}
    </div>
  )
}
