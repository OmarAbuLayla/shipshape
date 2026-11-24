import { Link, NavLink, Route, Routes } from "react-router-dom";

import { ErrorBoundary } from "./components/ErrorBoundary";
import { Moon, Sun } from "./components/icons";
import { providerName } from "./lib/format";
import { useHealth, useTheme } from "./lib/hooks";
import { FixesPage } from "./pages/FixesPage";
import { History } from "./pages/History";
import { Lessons } from "./pages/Lessons";
import { Profile } from "./pages/Profile";
import { Home } from "./pages/Home";
import { ScanPage } from "./pages/ScanPage";

export function App() {
  const [theme, toggleTheme] = useTheme();
  const health = useHealth();
  const llm = health.data?.llm;

  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand" aria-label="Shipshape home">
          {/* Two versions of the logo; CSS shows the one that matches the theme. */}
          <img className="logo-light" src="/brand/logo-light.svg" alt="" width={133} height={40} />
          <img className="logo-dark" src="/brand/logo-dark.svg" alt="" width={133} height={40} />
        </Link>
        <nav className="nav">
          <NavLink to="/" end>
            New scan
          </NavLink>
          <NavLink to="/history">History</NavLink>
          <NavLink to="/lessons">Lessons</NavLink>
          <NavLink to="/profile">Profile</NavLink>
        </nav>
        <div className="right">
          {health.error ? (
            <span className="llm-pill" title={health.error}>
              <i style={{ background: "var(--crit)" }} /> Server offline
            </span>
          ) : llm ? (
            <span
              className={`llm-pill ${llm.configured ? "on" : ""}`}
              title={llm.configured ? "AI explanations are available" : (llm.problem ?? "")}
            >
              <i /> {llm.configured ? `${providerName(llm.provider)} · ${llm.model}` : "No AI key"}
            </span>
          ) : null}
          <button
            className="btn ghost small"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          >
            {theme === "dark" ? <Sun /> : <Moon />}
          </button>
        </div>
      </header>
      <main className="main">
        <ErrorBoundary>
        <Routes>
          <Route path="/" element={<Home llmReady={!!llm?.configured} llmLabel={llm ? providerName(llm.provider) : null} />} />
          <Route path="/scans/:id" element={<ScanPage />} />
          <Route path="/scans/:id/fixes" element={<FixesPage />} />
          <Route path="/history" element={<History />} />
          <Route path="/lessons" element={<Lessons />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/lessons/:slug" element={<Lessons />} />
          <Route
            path="*"
            element={
              <div className="page empty">
                That page doesn't exist. <Link to="/">Start a scan</Link>
              </div>
            }
          />
        </Routes>
        </ErrorBoundary>
      </main>
    </div>
  );
}
