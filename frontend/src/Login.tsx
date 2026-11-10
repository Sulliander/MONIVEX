import { useEffect, useState, type FormEvent } from "react";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  Eye,
  EyeOff,
  LockKeyhole,
  ShieldCheck,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "./api";
import { Button } from "./components/ui/button";

type LoginResult = { two_factor_required: boolean; csrf_token?: string };
export default function Login({
  done,
  notice,
}: {
  done: () => Promise<void>;
  notice: string;
}) {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [factor, setFactor] = useState(false);
  const [recovery, setRecovery] = useState(false);
  const [visible, setVisible] = useState(false);
  const [caps, setCaps] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [blockedUntil, setBlockedUntil] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const [expires, setExpires] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const remaining = Math.max(0, Math.ceil((blockedUntil - now) / 1000));
  const expired = factor && now >= expires;
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const result = await api<LoginResult>(
        factor ? "/auth/login/verify" : "/auth/login",
        "POST",
        factor ? { code } : { username, password },
      );
      setPassword("");
      setCode("");
      if (result.two_factor_required) {
        setFactor(true);
        setExpires(Date.now() + 300000);
        setVisible(false);
      } else {
        sessionStorage.setItem("csrf", result.csrf_token!);
        navigate("/");
        await done();
      }
    } catch (e) {
      setError((e as Error).message);
      if (e instanceof ApiError && e.status === 429)
        setBlockedUntil(Date.now() + (e.retryAfter || 900) * 1000);
      if (factor && e instanceof ApiError && e.status === 401) {
        setFactor(false);
        setCode("");
      }
    } finally {
      setBusy(false);
    }
  }
  async function back() {
    setBusy(true);
    try {
      await api("/auth/login/cancel", "POST");
      setFactor(false);
      setRecovery(false);
      setCode("");
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-card login-card">
      <div className="brand">
        <Activity size={28} />
        <span>MONIVEX</span>
      </div>
      <div className="auth-icon">
        {factor ? <ShieldCheck size={26} /> : <LockKeyhole size={26} />}
      </div>
      <p className="eyebrow">Bezpieczny dostęp do infrastruktury</p>
      <h1>{factor ? "Potwierdź swoją tożsamość" : "Zaloguj się"}</h1>
      <p className="muted">
        {factor
          ? recovery
            ? "Wprowadź jeden z zapisanych kodów odzyskiwania. Każdy kod działa tylko raz."
            : "Wpisz sześciocyfrowy kod z Microsoft Authenticator, Google Authenticator lub 2FAS."
          : "Witaj ponownie. Zaloguj się do swojej instalacji MONIVEX."}
      </p>
      {notice && !error && (
        <p role="status" className="security-notice">
          {notice}
        </p>
      )}
      <form onSubmit={(e) => void submit(e)}>
        {!factor ? (
          <>
            <label>
              Nazwa użytkownika
              <input
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                required
                maxLength={64}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoFocus
              />
            </label>
            <label>
              Hasło
              <div className="password-input">
                <input
                  type={visible ? "text" : "password"}
                  data-private
                  autoComplete="current-password"
                  required
                  maxLength={256}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyUp={(e) => setCaps(e.getModifierState("CapsLock"))}
                />
                <button
                  type="button"
                  aria-label={visible ? "Ukryj hasło" : "Pokaż hasło"}
                  aria-pressed={visible}
                  onClick={() => setVisible(!visible)}
                >
                  {visible ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </label>
            {caps && <p className="hint">Caps Lock jest włączony.</p>}
          </>
        ) : (
          <>
            <label>
              {recovery ? "Kod odzyskiwania" : "Kod z aplikacji"}
              <input
                key={recovery ? "recovery" : "totp"}
                data-private
                className="factor-input"
                autoComplete="one-time-code"
                inputMode={recovery ? "text" : "numeric"}
                pattern={recovery ? undefined : "[0-9]{6}"}
                maxLength={recovery ? 80 : 6}
                required
                value={code}
                onChange={(e) => setCode(e.target.value)}
                autoFocus
              />
            </label>
            <p className="hint">
              {expired
                ? "Etap logowania wygasł. Wróć do logowania."
                : `Czas na potwierdzenie: ${Math.max(0, Math.ceil((expires - now) / 1000))} s.`}
            </p>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setRecovery(!recovery);
                setCode("");
                setError("");
              }}
            >
              {recovery
                ? "Użyj aplikacji uwierzytelniającej"
                : "Użyj kodu odzyskiwania"}
            </Button>
          </>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {remaining > 0 && (
          <p role="status" className="security-notice">
            Blokada bezpieczeństwa: spróbuj ponownie za{" "}
            {Math.ceil(remaining / 60)} min.
          </p>
        )}
        <Button disabled={busy || remaining > 0 || !!expired}>
          {busy
            ? "Weryfikacja…"
            : factor
              ? "Potwierdź logowanie"
              : "Zaloguj się"}
          <ArrowRight size={16} />
        </Button>
      </form>
      {factor && (
        <Button variant="ghost" disabled={busy} onClick={() => void back()}>
          <ArrowLeft size={16} />
          Wróć do logowania
        </Button>
      )}
      <div className="auth-footer">
        <ShieldCheck size={16} />
        <span>
          Dostęp tylko dla uprawnionych użytkowników. Konta tworzy administrator
          instalacji.
        </span>
      </div>
    </main>
  );
}
