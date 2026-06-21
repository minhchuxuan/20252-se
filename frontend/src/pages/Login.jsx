import { useState } from "react";
import { useAuth } from "../auth/AuthContext";

export default function Login() {
  const { login, register, toast } = useAuth();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "admin@demo.com", password: "demo1234", full_name: "", home_name: "My Home" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (mode === "login") await login(form.email, form.password);
      else await register({ email: form.email, password: form.password, full_name: form.full_name, home_name: form.home_name });
    } catch (err) {
      toast(err.message, "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <div className="brand" style={{ paddingBottom: 8 }}>
          <div className="brand-logo">⚡</div>
          <div className="brand-name" style={{ color: "var(--c-text)" }}>
            Energy Optimizer<small style={{ color: "var(--c-text-soft)" }}>AI-Driven Smart Home</small>
          </div>
        </div>
        <p className="muted" style={{ fontSize: 13.5, marginTop: 0 }}>
          {mode === "login" ? "Sign in to monitor and optimise your home energy." : "Create an administrator account for a new building."}
        </p>

        {mode === "register" && (
          <div className="form-row">
            <label className="field">Full name</label>
            <input value={form.full_name} onChange={set("full_name")} required placeholder="Your name" />
          </div>
        )}
        <div className="form-row">
          <label className="field">Email</label>
          <input type="email" value={form.email} onChange={set("email")} required />
        </div>
        <div className="form-row">
          <label className="field">Password</label>
          <input type="password" value={form.password} onChange={set("password")} required minLength={6} />
        </div>
        {mode === "register" && (
          <div className="form-row">
            <label className="field">Home name</label>
            <input value={form.home_name} onChange={set("home_name")} />
          </div>
        )}

        <button className="btn btn-primary" style={{ width: "100%", justifyContent: "center" }} disabled={busy}>
          {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
        </button>

        <div style={{ textAlign: "center", marginTop: 14, fontSize: 13.5 }}>
          {mode === "login" ? (
            <>No account? <a onClick={() => setMode("register")} style={{ cursor: "pointer" }}>Register</a></>
          ) : (
            <>Have an account? <a onClick={() => setMode("login")} style={{ cursor: "pointer" }}>Sign in</a></>
          )}
        </div>

        {mode === "login" && (
          <div className="demo-creds">
            <strong>Demo accounts</strong> (password <code>demo1234</code>):<br />
            admin@demo.com · resident@demo.com · dev@demo.com
          </div>
        )}
      </form>
    </div>
  );
}
