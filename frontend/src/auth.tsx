import { useEffect, useState, type FormEvent, type ReactNode } from "react";

const API_BASE = import.meta.env.VITE_API_URL || `${window.location.protocol}//${window.location.hostname}:5300`;
type Session = { authenticated: boolean; auth_enabled: boolean; user?: { username: string; roles: string[] } };

export function csrfHeaders(): Record<string, string> {
  const value = document.cookie.match(/(?:^|; )local_csrf=([^;]*)/)?.[1];
  return value ? { "X-CSRF-Token": decodeURIComponent(value) } : {};
}

async function sessionRequest(path: string, options?: RequestInit): Promise<Session> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { ...csrfHeaders(), "Content-Type": "application/json", ...(options?.headers || {}) },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(body.detail || "Authentication request failed."), { status: response.status });
  return body as Session;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<"loading" | "login" | "ready">("loading");
  const [session, setSession] = useState<Session | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void sessionRequest("/api/auth/session")
      .then((value) => { setSession(value); setStatus(value.auth_enabled && !value.authenticated ? "login" : "ready"); })
      .catch((reason: any) => { setStatus(reason?.status === 401 ? "login" : "ready"); });
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const value = await sessionRequest("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
      setSession(value); setStatus("ready"); setPassword("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Sign-in failed.");
    } finally { setBusy(false); }
  }

  async function signOut() {
    setBusy(true); setError("");
    try { await sessionRequest("/api/auth/logout", { method: "POST" }); setSession(null); setStatus("login"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Sign-out failed."); }
    finally { setBusy(false); }
  }

  if (status === "loading") return <div className="panel state">Checking operator session…</div>;
  if (status === "login") return <main className="main"><section className="panel auth-panel"><span className="eyebrow">Local operator access</span><h1>Sign in to continue.</h1><p>Use the bootstrap credentials configured for this local deployment.</p><form onSubmit={submit}><label>Username<input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required /></label><label>Password<input autoComplete="current-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>{error && <div className="banner error"><strong>Could not sign in</strong><span>{error}</span></div>}<button className="action-button" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button></form></section></main>;
  if (session?.auth_enabled && session.authenticated && session.user) return <><div style={{ display: "flex", justifyContent: "flex-end", gap: 12, padding: "10px 24px", fontSize: 13 }}><span>Signed in as <strong>{session.user.username}</strong> · {session.user.roles.join(", ")}</span><button onClick={() => void signOut()} disabled={busy}>{busy ? "Signing out…" : "Sign out"}</button></div>{children}</>;
  return <>{children}</>;
}
