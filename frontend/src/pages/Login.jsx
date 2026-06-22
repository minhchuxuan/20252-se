import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { Icon } from "../components/icons";

export default function Login() {
  const { login, toast } = useAuth();
  const [form, setForm] = useState({ email: "admin@demo.com", password: "demo1234" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await login(form.email, form.password);
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
          <div className="brand-logo"><Icon name="bolt" size={20} style={{ color: "#fff" }} /></div>
          <div className="brand-name" style={{ color: "var(--c-text)" }}>
            Energy Optimizer<small style={{ color: "var(--c-text-soft)" }}>AI-Driven Smart Home</small>
          </div>
        </div>
        <p className="muted" style={{ fontSize: 13.5, marginTop: 0 }}>
          Sign in to monitor and optimise your home energy.
        </p>

        <div className="form-row">
          <label className="field">Email</label>
          <input type="email" value={form.email} onChange={set("email")} required />
        </div>
        <div className="form-row">
          <label className="field">Password</label>
          <input type="password" value={form.password} onChange={set("password")} required minLength={6} />
        </div>

        <button className="btn btn-primary" style={{ width: "100%", justifyContent: "center" }} disabled={busy}>
          {busy ? "Please wait…" : "Sign in"}
        </button>

        <div className="demo-creds">
          <strong>Demo accounts</strong> (password <code>demo1234</code>):<br />
          admin@demo.com · resident@demo.com · dev@demo.com
        </div>
      </form>
    </div>
  );
}
