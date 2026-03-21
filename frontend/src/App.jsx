/**
 * STEP 6 — App Component (the root of your UI tree)
 *
 * WHAT IS A COMPONENT?
 * A component is just a JavaScript function that returns JSX (HTML-like syntax).
 * Every piece of the UI is a component. You compose them like LEGO bricks.
 *
 * WHAT IS REACT ROUTER?
 * React Router lets you have multiple "pages" in a Single Page Application.
 * The URL changes (/history vs /) but the page never actually reloads.
 * BrowserRouter — wraps everything, enables routing
 * Routes — the container for all your route definitions
 * Route — maps a URL path to a component (page)
 */
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar.jsx'
import HomePage from './pages/HomePage.jsx'
import HistoryPage from './pages/HistoryPage.jsx'

function App() {
  return (
    <BrowserRouter>
      <Navbar />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/history" element={<HistoryPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}

export default App
