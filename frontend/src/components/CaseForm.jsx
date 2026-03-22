/**
 * STEP 10 — CaseForm Component
 *
 * KEY REACT CONCEPT: useState
 * useState is a "hook" — a special function that lets a component remember data.
 *
 *   const [value, setValue] = useState(initialValue)
 *     - "value"    → the current data (read it)
 *     - "setValue" → the function to update it (write it)
 *
 * When setValue is called, React automatically re-renders the component
 * with the new value. This is React's "reactivity" — the UI updates automatically.
 *
 * PROPS:
 *   onSubmit — a function passed from the parent (HomePage).
 *              When the form is submitted, we call this with the form data.
 *   isLoading — boolean, disables the button while the API is running.
 */
import { useState } from 'react'

// These match exactly what the Django API expects
const CASE_TYPES = [
  'Flight Cancellation',
  'Schedule Change / Significant Delay',
  'Downgrade to Lower Class',
  'Baggage Lost or Delayed',
  'Ancillary Service Not Provided',
  '24-Hour Cancellation (within 24h of booking)',
]

const FLIGHT_TYPES = ['Domestic (within US)', 'International']
const TICKET_TYPES = ['Refundable', 'Non-refundable']
const PAYMENT_METHODS = ['Credit Card', 'Debit Card', 'Cash', 'Check', 'Airline Miles', 'Other']
const ALTERNATIVES = [
  'No — I did not accept any alternative',
  'Yes — I accepted a rebooked flight',
  'Yes — I accepted a travel voucher / credit',
  'Yes — I accepted other compensation (miles, etc.)',
  'Yes — I traveled on the flight anyway',
]

const INITIAL_FORM = {
  case_type: CASE_TYPES[0],
  flight_type: FLIGHT_TYPES[0],
  ticket_type: TICKET_TYPES[0],
  payment_method: PAYMENT_METHODS[0],
  accepted_alternative: ALTERNATIVES[0],
  description: '',
}

export default function CaseForm({ onSubmit, isLoading }) {
  // useState remembers the form values between renders
  const [form, setForm] = useState(INITIAL_FORM)

  // One handler for ALL fields — updates only the changed field
  // This pattern avoids writing a separate handler for each input
  function handleChange(e) {
    setForm(prev => ({ ...prev, [e.target.name]: e.target.value }))
  }

  function handleSubmit(e) {
    e.preventDefault()         // Prevent the browser from reloading the page
    if (!form.description.trim()) return
    onSubmit(form)             // Call the parent's function with the form data
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-grid">
        <div className="form-group">
          <label>Case Type</label>
          <select name="case_type" value={form.case_type} onChange={handleChange}>
            {CASE_TYPES.map(v => <option key={v}>{v}</option>)}
          </select>
        </div>

        <div className="form-group">
          <label>Flight Type</label>
          <select name="flight_type" value={form.flight_type} onChange={handleChange}>
            {FLIGHT_TYPES.map(v => <option key={v}>{v}</option>)}
          </select>
        </div>

        <div className="form-group">
          <label>Ticket Type</label>
          <select name="ticket_type" value={form.ticket_type} onChange={handleChange}>
            {TICKET_TYPES.map(v => <option key={v}>{v}</option>)}
          </select>
        </div>

        <div className="form-group">
          <label>Payment Method</label>
          <select name="payment_method" value={form.payment_method} onChange={handleChange}>
            {PAYMENT_METHODS.map(v => <option key={v}>{v}</option>)}
          </select>
        </div>

        <div className="form-group full-width">
          <label>Did you accept an alternative?</label>
          <select name="accepted_alternative" value={form.accepted_alternative} onChange={handleChange}>
            {ALTERNATIVES.map(v => <option key={v}>{v}</option>)}
          </select>
        </div>

        <div className="form-group full-width">
          <label>Case Description</label>
          <textarea
            name="description"
            value={form.description}
            onChange={handleChange}
            placeholder="Describe what happened — include flight details, dates, amounts paid, and any communication with the airline..."
            required
            minLength={10}
          />
        </div>
      </div>

      <button type="submit" className="btn btn-primary" disabled={isLoading || !form.description.trim()}>
        {isLoading ? '⏳ Analyzing...' : '🔍 Analyze Case'}
      </button>
    </form>
  )
}
