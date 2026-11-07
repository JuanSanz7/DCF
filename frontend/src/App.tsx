import { useQuery, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { useEffect, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { Spinner } from './components/ui'
import { api } from './lib/api'
import Company from './pages/Company'
import Portfolio from './pages/Portfolio'
import Settings from './pages/Settings'
import Workspace from './pages/Workspace'

function Mark() {
  return (
    <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden><path d="M3 25 C10 25 11 7 16 7 S22 25 29 25" fill="none" stroke="#0e7c86" strokeWidth="2.6" /><path d="M19.5 3v26" stroke="#b4236a" strokeWidth="2.2" /></svg>
  )
}

export default function App() {
  const auth = useQuery({ queryKey: ['auth'], queryFn: api.authStatus })
  const qc = useQueryClient()
  useEffect(() => {
    const h = () => qc.invalidateQueries({ queryKey: ['auth'] })
    window.addEventListener('dcf:unauthorized', h)
    return () => window.removeEventListener('dcf:unauthorized', h)
  }, [qc])
  if (auth.isLoading) return <div className="p-10"><Spinner /></div>
  if (auth.data?.required && !auth.data.signed_in) return <Login onDone={() => qc.invalidateQueries()} />
  const link = ({ isActive }: { isActive: boolean }) => clsx('px-2.5 py-1 text-[13px] rounded-md', isActive ? 'text-ink font-medium bg-paper' : 'text-ink-3 hover:text-ink')
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 h-12 border-b border-rule bg-panel">
        <div className="mx-auto flex h-full max-w-[1600px] items-center gap-6 px-4 lg:px-6">
          <NavLink to="/" className="flex items-center gap-2 font-cond text-[16px] font-semibold"><Mark /> <span className="hidden sm:inline">Value field</span></NavLink>
          <nav className="flex items-center gap-1">
            <NavLink to="/" end className={link}>Register</NavLink>
            <NavLink to="/new" className={link}>Workspace</NavLink>
            <NavLink to="/settings" className={link}><span className="sm:hidden">Settings</span><span className="hidden sm:inline">House assumptions</span></NavLink>
          </nav>
        </div>
      </header>
      <main className="pt-4">
        <Routes>
          <Route path="/" element={<Portfolio />} />
          <Route path="/new" element={<Workspace />} />
          <Route path="/v/:id" element={<Workspace />} />
          <Route path="/c/:ticker" element={<Company />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  )
}

function Login({ onDone }: { onDone: () => void }) {
  const [pw, setPw] = useState('')
  const [err, setErr] = useState<string | null>(null)
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form className="w-full max-w-sm rounded-lg border border-rule bg-panel p-6" onSubmit={async e => { e.preventDefault(); try { await api.login(pw); onDone() } catch (x) { setErr((x as Error).message) } }}>
        <div className="mb-4 flex items-center gap-2 font-cond text-[18px] font-semibold"><Mark /> Value field</div>
        <label className="block"><span className="label">Password</span><input type="password" autoFocus className="field mt-1" value={pw} onChange={e => setPw(e.target.value)} /></label>
        {err && <p className="mt-2 text-[13px] text-bad">{err}</p>}
        <button className="btn-primary mt-4 w-full justify-center">Sign in</button>
      </form>
    </div>
  )
}
