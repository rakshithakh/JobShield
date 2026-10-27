import { NavLink, Link, Outlet } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { cx } from "./ui";

const NAV = [["/analyze", "Analyse"], ["/demo", "Demo"], ["/history", "History"], ["/dashboard", "Dashboard"], ["/about", "How it works"]];

export default function Layout() {
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="skip-link">Skip to content</a>
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3">
          <Link to="/" className="flex items-center gap-2 font-serif text-xl font-semibold"><ShieldCheck className="size-6" aria-hidden="true" />JobSentinel</Link>
          <nav aria-label="Main" className="flex flex-wrap gap-1">
            {NAV.map(([to, label]) => (
              <NavLink key={to} to={to} className={({ isActive }) => cx("rounded-md px-3 py-2 text-sm font-medium", isActive ? "bg-note-bg text-ink underline decoration-2 underline-offset-8" : "text-ink-soft hover:bg-note-bg")}>{label}</NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:py-12"><Outlet /></main>
      <footer className="border-t border-line bg-surface">
        <div className="mx-auto grid max-w-6xl gap-6 px-4 py-8 text-sm text-ink-soft sm:grid-cols-[2fr_1fr_1fr]">
          <p className="max-w-md">JobSentinel is an aid to your own checking. A score is a count of warning signals, not proof that a posting or company is fraudulent or genuine.</p>
          <nav aria-label="Product" className="space-y-1"><p className="font-semibold text-ink">Product</p>
            <Link className="block underline-offset-2 hover:underline" to="/analyze">Analyse a posting</Link>
            <Link className="block underline-offset-2 hover:underline" to="/history">History</Link>
            <Link className="block underline-offset-2 hover:underline" to="/dashboard">Dashboard</Link></nav>
          <nav aria-label="Information" className="space-y-1"><p className="font-semibold text-ink">Information</p>
            <Link className="block underline-offset-2 hover:underline" to="/about#scoring">How scoring works</Link>
            <Link className="block underline-offset-2 hover:underline" to="/about#privacy">Privacy</Link>
            <Link className="block underline-offset-2 hover:underline" to="/about#limits">Limitations</Link>
            <a className="block underline-offset-2 hover:underline" href="https://cybercrime.gov.in" rel="noopener noreferrer" target="_blank">Report cybercrime (India)</a></nav>
        </div>
      </footer>
    </div>
  );
}
