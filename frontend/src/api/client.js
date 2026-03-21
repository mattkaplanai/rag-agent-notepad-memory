/**
 * STEP 7 — API Client
 *
 * This is the single place where all Django API calls are defined.
 * Centralizing API calls here means:
 *  - If the URL changes, you update ONE file
 *  - Every component imports from here instead of hardcoding URLs
 *
 * We use the native browser fetch() API — no extra library needed.
 * fetch() returns a Promise, which is JavaScript's way of handling async operations.
 */

const BASE_URL = '/api/v1'

/**
 * Submit a refund case to the Django pipeline.
 * @param {Object} caseData - The form data
 * @returns {Promise<Object>} - The decision result
 */
export async function analyzeCase(caseData) {
  const response = await fetch(`${BASE_URL}/analyze/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(caseData),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.detail || error.description?.[0] || 'Submission failed')
  }

  return response.json()
}

/**
 * Fetch paginated list of past decisions.
 * @param {number} page - Page number (starts at 1)
 * @returns {Promise<Object>} - { count, next, previous, results }
 */
export async function fetchDecisions(page = 1) {
  const response = await fetch(`${BASE_URL}/decisions/?page=${page}`)
  if (!response.ok) throw new Error('Failed to load decisions')
  return response.json()
}

/**
 * Fetch a single decision by ID.
 * @param {number|string} id
 * @returns {Promise<Object>}
 */
export async function fetchDecision(id) {
  const response = await fetch(`${BASE_URL}/decisions/${id}/`)
  if (!response.ok) throw new Error('Decision not found')
  return response.json()
}

/**
 * Check API health.
 * @returns {Promise<Object>} - { status, service, total_decisions }
 */
export async function fetchHealth() {
  const response = await fetch(`${BASE_URL}/health/`)
  if (!response.ok) throw new Error('API unavailable')
  return response.json()
}
