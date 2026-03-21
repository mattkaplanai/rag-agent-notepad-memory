/**
 * STEP 8 — Navbar Component
 *
 * NavLink is like <a> but from React Router.
 * It automatically adds an "active" class when the URL matches the link.
 * This is how the active nav link gets highlighted.
 */
import { NavLink } from 'react-router-dom'

export default function Navbar() {
  return (
    <nav className="navbar">
      <NavLink to="/" className="navbar-brand">
        ✈ Refund Decision System
      </NavLink>
      <div className="navbar-links">
        <NavLink to="/" end>New Case</NavLink>
        <NavLink to="/history">History</NavLink>
      </div>
    </nav>
  )
}
