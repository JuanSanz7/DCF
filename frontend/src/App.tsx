import { useQuery, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { useEffect, useState } from 'react'
import { Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { Spinner } from './components/ui'
import { api, type AuthStatus } from './lib/api'
import Company from './pages/Company'
import Portfolio from './pages/Portfolio'
import Workspace from './pages/Workspace'

function Mark() {
  return (
    <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden><path d="M3 25 C10 25 11 7 16 7 S22 25 29 25" fill="none" stroke="#12b3d6" strokeWidth="2.6" /><path d="M19.5 3v26" stroke="#c77dd6" strokeWidth="2.2" /></svg>
  )
}

export default function App() {
  const auth = useQuery({ queryKey: ['auth'], queryFn: api.authStatus })
  const qc = useQueryClient()
  const location = useLocation()
  useEffect(() => {
    const h = () => qc.invalidateQueries({ queryKey: ['auth'] })
    window.addEventListener('dcf:unauthorized', h)
    return () => window.removeEventListener('dcf:unauthorized', h)
  }, [qc])
  if (auth.isLoading) return <div className="p-10"><Spinner /></div>
  if (auth.isError) return <div className="p-10 text-bad">The server is not reachable. Reload the page in a minute (a free server may be waking up).</div>
  const st = auth.data!
  if (!st.user) return <Login status={st} onDone={() => { localStorage.removeItem('dcf:draft'); qc.resetQueries() }} />
  const link = ({ isActive }: { isActive: boolean }) => clsx('px-2.5 py-1 text-[13px] rounded-md', isActive ? 'text-white font-medium bg-white/12' : 'text-on-navy-2 hover:text-white')
  const logout = async () => { await api.logout(); localStorage.removeItem('dcf:draft'); await qc.resetQueries() }
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 h-12 border-b border-white/10 bg-navy-950 text-on-navy">
        <div className="mx-auto flex h-full max-w-[1600px] items-center gap-4 px-4 sm:gap-6 lg:px-6">
          <NavLink to="/new" className="flex items-center gap-2 font-cond text-[16px] font-semibold"><Mark /> <span className="hidden sm:inline">Value field</span></NavLink>
          <nav className="flex items-center gap-1">
            <NavLink to="/new" className={({ isActive }) => link({ isActive: isActive || location.pathname.startsWith('/v/') })}>Valuation</NavLink>
            <NavLink to="/archive" className={({ isActive }) => link({ isActive: isActive || location.pathname.startsWith('/c/') })}>Archive</NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-2 text-[13px] text-on-navy-2">
            <span className="hidden sm:inline">{st.user.username}</span>
            <button className="rounded-md px-2 py-1 text-[12px] hover:bg-white/10 hover:text-white" onClick={logout}>Sign out</button>
          </div>
        </div>
      </header>
      {!st.persistent_storage && (
        <div className="border-b border-warn/30 bg-warn-soft px-4 py-2 text-center text-[12.5px] text-warn">
          {st.config_errors?.length ? st.config_errors.join(' ') + ' Until then, ' : 'This server has no permanent database yet: '}
          saved valuations and accounts will be lost when it restarts.
        </div>
      )}
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/new" replace />} />
          <Route path="/archive" element={<Portfolio />} />
          <Route path="/new" element={<Workspace />} />
          <Route path="/v/:id" element={<Workspace />} />
          <Route path="/c/:ticker" element={<Company />} />
          <Route path="*" element={<Navigate to="/new" replace />} />
        </Routes>
      </main>
    </div>
  )
}

function Login({ status, onDone }: { status: AuthStatus; onDone: () => void }) {
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [u, setU] = useState('')
  const [pw, setPw] = useState('')
  const [inv, setInv] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null)
    try { if (mode === 'login') await api.login(u, pw); else await api.signup(u, pw, inv || undefined); onDone() }
    catch (x) { setErr((x as Error).message) } finally { setBusy(false) }
  }
  return (
    <div className="side flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2 font-cond text-[22px] font-semibold text-white"><Mark /> Value field</div>
        <p className="mb-5 text-[14px] leading-relaxed text-on-navy-2">Discounted cash flow valuation with Monte Carlo simulation. See every plausible value of a company against its market price, and keep a register of your valuations over time.</p>
        <form className="rounded-lg bg-panel p-5 text-ink shadow-[0_24px_60px_rgba(0,0,0,.25)] [&_.label]:!text-ink-2" onSubmit={submit}>
          <h1 className="mb-3 text-[17px] font-semibold">{mode === 'login' ? 'Sign in' : 'Create your account'}</h1>
          <label className="block"><span className="label">Username</span><input autoFocus autoComplete="username" className="field mt-1" value={u} onChange={e => setU(e.target.value)} /></label>
          <label className="mt-3 block"><span className="label">Password</span><input type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} className="field mt-1" value={pw} onChange={e => setPw(e.target.value)} /></label>
          {mode === 'signup' && <p className="hint mt-1">At least 8 characters. Your valuations are private to your account.</p>}
          {mode === 'signup' && status.invite_required && (
            <label className="mt-3 block"><span className="label">Invitation code</span><input className="field mt-1" value={inv} onChange={e => setInv(e.target.value)} /></label>
          )}
          {err && <p className="mt-3 text-[13px] text-bad">{err}</p>}
          <button className="btn-primary mt-4 h-9 w-full justify-center" disabled={busy || !u || !pw}>{busy && <Spinner />} {mode === 'login' ? 'Sign in' : 'Create account'}</button>
        </form>
        {status.signup_open && (
          <p className="mt-4 text-center text-[13px] text-on-navy-2">
            {mode === 'login' ? 'New here? ' : 'Already have an account? '}
            <button className="font-medium text-cyan underline underline-offset-2" onClick={() => { setMode(mode === 'login' ? 'signup' : 'login'); setErr(null) }}>
              {mode === 'login' ? 'Create an account' : 'Sign in'}
            </button>
          </p>
        )}
      </div>
    </div>
  )
}
