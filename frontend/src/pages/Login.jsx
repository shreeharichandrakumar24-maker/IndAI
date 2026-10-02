import { useState } from 'react';
import { signIn } from '../services/auth';

export default function Login({ onDone }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await signIn(email.trim(), password);
      onDone();
    } catch (err) {
      setError(err.message || 'Sign-in failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="shell">
      <div className="main">
        <div className="page" style={{ maxWidth: 440, margin: '8vh auto 0' }}>
          <div className="page-head">
            <div>
              <h2>IndAI — sign in</h2>
              <p className="page-desc">Industrial Admin Platform. Accounts are created by your manager.</p>
            </div>
          </div>
          {error && <div className="alert-banner" role="alert">{error}</div>}
          <section className="panel">
            <form onSubmit={submit}>
              <label className="detail-label" htmlFor="login-email">Work email</label>
              <input
                id="login-email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                style={{ width: '100%', marginBottom: 12 }}
                required
              />
              <label className="detail-label" htmlFor="login-password">Password</label>
              <input
                id="login-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                style={{ width: '100%', marginBottom: 16 }}
                required
              />
              <button type="submit" className="btn-primary" disabled={busy} style={{ width: '100%' }}>
                {busy ? 'Signing in…' : 'Sign in →'}
              </button>
            </form>
          </section>
          <p className="muted">No account yet? Ask your manager to create one for you.</p>
        </div>
      </div>
    </div>
  );
}
