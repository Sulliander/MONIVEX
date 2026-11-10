import { useEffect, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Download,
  KeyRound,
  MonitorSmartphone,
  ShieldCheck,
} from "lucide-react";
import { api } from "./api";
import { Button } from "./components/ui/button";
import { useDateFormatter } from "./dates";

type Security = {
  two_factor_enabled: boolean;
  recovery_codes_remaining: number;
  require_admin_totp: boolean;
  can_manage_policy: boolean;
  setup_required: boolean;
};
type Session = {
  id: string;
  current: boolean;
  created_at: number | null;
  expires_at: number;
  client_ip: string;
  user_agent: string;
};
type Event = { id: number; action: string; created_at: number };
type Action = "setup" | "confirm" | "disable" | "regenerate" | "policy" | null;
const actions: Record<string, string> = {
  "installation.initialized": "Utworzono instalację",
  "auth.login": "Zalogowano hasłem",
  "auth.login_2fa": "Zalogowano z 2FA",
  "auth.login_failed": "Nieudana próba logowania",
  "auth.factor_failed": "Odrzucono kod drugiego składnika",
  "auth.reauthentication_failed": "Nieudane ponowne uwierzytelnienie",
  "auth.logout": "Wylogowano",
  "auth.logout_all": "Zakończono wszystkie sesje",
  "auth.password_changed": "Zmieniono hasło",
  "auth.2fa_setup_started": "Rozpoczęto konfigurację 2FA",
  "auth.2fa_confirmation_failed": "Odrzucono kod aktywacji 2FA",
  "auth.2fa_enabled": "Włączono 2FA",
  "auth.2fa_disabled": "Wyłączono 2FA",
  "auth.recovery_used": "Użyto kodu odzyskiwania",
  "auth.recovery_regenerated": "Wygenerowano nowe kody odzyskiwania",
  "auth.session_revoked": "Unieważniono sesję",
  "auth.policy_enabled": "Włączono wymóg 2FA administratorów",
  "auth.policy_disabled": "Wyłączono wymóg 2FA administratorów",
};
export default function Account() {
  const client = useQueryClient();
  const date = useDateFormatter();
  const security = useQuery({
    queryKey: ["account-security"],
    queryFn: () => api<Security>("/auth/security"),
  });
  const sessions = useQuery({
    queryKey: ["account-sessions"],
    queryFn: () => api<Session[]>("/auth/sessions"),
  });
  const [before, setBefore] = useState<number | undefined>();
  const events = useQuery({
    queryKey: ["account-events", before],
    queryFn: () =>
      api<{ items: Event[]; next_before: number | null }>(
        `/auth/events?limit=20${before ? `&before=${before}` : ""}`,
      ),
  });
  const [action, setAction] = useState<Action>(null);
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [code, setCode] = useState("");
  const [setup, setSetup] = useState<{
    secret: string;
    qr_data_url: string;
  } | null>(null);
  const [codes, setCodes] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [logoutConfirm, setLogoutConfirm] = useState(false);
  const [revokeConfirm, setRevokeConfirm] = useState<Session | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [passwordCode, setPasswordCode] = useState("");
  useEffect(() => {
    if (action)
      document
        .getElementById(
          action === "confirm" ? "factor-confirm" : "reauth-password",
        )
        ?.focus();
  }, [action]);
  useEffect(() => {
    if (!codes.length) return;
    document.getElementById("recovery-codes-panel")?.focus();
    const prevent = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", prevent);
    return () => window.removeEventListener("beforeunload", prevent);
  }, [codes]);
  function expired(message?: string) {
    window.dispatchEvent(
      new CustomEvent("monivex:session-expired", { detail: message }),
    );
  }
  async function refresh() {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["account-security"] }),
      client.invalidateQueries({ queryKey: ["account-sessions"] }),
      client.invalidateQueries({ queryKey: ["account-events"] }),
      client.invalidateQueries({ queryKey: ["me"] }),
    ]);
  }
  function start(value: Action) {
    setAction(value);
    setError("");
    setMessage("");
    setPassword("");
    setCode("");
    setSetup(null);
  }
  async function perform(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const payload = { current_password: password, code };
      if (action === "setup") {
        setSetup(await api("/auth/2fa/setup", "POST", payload));
        setAction("confirm");
        setCode("");
      } else {
        const path =
          action === "confirm"
            ? "/2fa/enable"
            : action === "disable"
              ? "/2fa/disable"
              : action === "regenerate"
                ? "/2fa/recovery-codes"
                : "/policy";
        const result = await api<{
          csrf_token?: string;
          recovery_codes?: string[];
        }>("/auth" + path, action === "policy" ? "PUT" : "POST", {
          ...payload,
          ...(action === "policy"
            ? { require_admin_totp: !security.data?.require_admin_totp }
            : {}),
        });
        if (result.csrf_token)
          sessionStorage.setItem("csrf", result.csrf_token);
        setPassword("");
        setCode("");
        setSetup(null);
        setAction(null);
        if (result.recovery_codes) {
          setCodes(result.recovery_codes);
          setSaved(false);
        }
        setMessage("Zapisano ustawienia bezpieczeństwa.");
        await refresh();
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function changePassword(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (newPassword !== confirmation) {
      setError("Nowe hasła muszą być identyczne.");
      return;
    }
    setBusy(true);
    try {
      await api("/auth/password", "POST", {
        current_password: currentPassword,
        new_password: newPassword,
        code: passwordCode,
      });
      expired("Hasło zostało zmienione. Zaloguj się ponownie.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function logoutAll() {
    setBusy(true);
    setError("");
    try {
      await api("/auth/logout-all", "POST");
      expired();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function revokeSession() {
    if (!revokeConfirm) return;
    setBusy(true);
    setError("");
    try {
      await api(`/auth/sessions/${revokeConfirm.id}`, "DELETE");
      if (revokeConfirm.current) expired();
      else {
        setRevokeConfirm(null);
        await refresh();
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function download() {
    const url = URL.createObjectURL(
      new Blob(
        [
          "MONIVEX — jednorazowe kody odzyskiwania\nPrzechowuj poza urządzeniem z aplikacją uwierzytelniającą.\n\n" +
            codes.join("\n"),
        ],
        { type: "text/plain;charset=utf-8" },
      ),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "monivex-kody-odzyskiwania.txt";
    link.click();
    URL.revokeObjectURL(url);
  }
  const labels = {
    setup: "Skonfiguruj 2FA",
    confirm: "Potwierdź i włącz 2FA",
    disable: "Wyłącz 2FA",
    regenerate: "Wygeneruj nowe kody odzyskiwania",
    policy: security.data?.require_admin_totp
      ? "Wyłącz wymóg 2FA administratorów"
      : "Wymagaj 2FA od administratorów",
  };
  return (
    <div className="account-security">
      <div className="page-title">
        <div>
          <p className="eyebrow">Ustawienia</p>
          <h1>Bezpieczeństwo konta</h1>
          <p className="muted">
            Zadbaj o dostęp, drugi składnik i urządzenia połączone z Twoim
            kontem.
          </p>
        </div>
        <ShieldCheck size={32} />
      </div>
      {(error || security.error || sessions.error || events.error) && (
        <p role="alert" className="error">
          {error ||
            security.error?.message ||
            sessions.error?.message ||
            events.error?.message}
        </p>
      )}
      {message && (
        <p role="status" className="security-notice">
          {message}
        </p>
      )}
      {security.data?.setup_required && (
        <p role="alert" className="security-notice">
          Instalacja wymaga 2FA dla administratorów. Możesz bezpiecznie
          skonfigurować drugi składnik tutaj; pozostałe funkcje będą dostępne po
          aktywacji.
        </p>
      )}
      {codes.length > 0 && (
        <section
          className="card recovery-card"
          id="recovery-codes-panel"
          tabIndex={-1}
          role="region"
          aria-label="Nowe kody odzyskiwania"
        >
          <h2>Zachowaj kody odzyskiwania</h2>
          <p>
            Te dziesięć kodów widzisz tylko teraz. Każdy zastępuje drugi
            składnik jeden raz. Zapisz je w menedżerze haseł lub przechowuj
            wydruk w bezpiecznym miejscu. Poprzednie kody zostały unieważnione.
          </p>
          <div data-private className="recovery-codes">
            {codes.map((c) => (
              <code key={c}>{c}</code>
            ))}
          </div>
          <Button variant="outline" onClick={download}>
            <Download size={16} />
            Pobierz kody
          </Button>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={saved}
              onChange={(e) => setSaved(e.target.checked)}
            />
            Kody są zapisane w bezpiecznym miejscu
          </label>
          <Button disabled={!saved} onClick={() => setCodes([])}>
            Ukryj kody odzyskiwania
          </Button>
        </section>
      )}
      <div className="security-grid">
        <section className="card">
          <div className="security-heading">
            <ShieldCheck size={22} />
            <h2>Uwierzytelnianie dwuskładnikowe</h2>
          </div>
          {security.isPending ? (
            <p role="status">Ładowanie…</p>
          ) : (
            security.data && (
              <>
                <span
                  className={`badge ${security.data.two_factor_enabled ? "secure-badge" : ""}`}
                >
                  {security.data.two_factor_enabled
                    ? "2FA aktywne"
                    : "2FA wyłączone"}
                </span>
                <p className="muted">
                  Microsoft Authenticator, Google Authenticator i 2FAS. Kody
                  TOTP zmieniają się co 30 sekund.
                </p>
                {security.data.two_factor_enabled ? (
                  <>
                    <p>
                      Pozostałe kody odzyskiwania:{" "}
                      <strong>{security.data.recovery_codes_remaining}</strong>
                    </p>
                    <div className="actions">
                      <Button
                        variant="outline"
                        disabled={busy || !!codes.length}
                        onClick={() => start("regenerate")}
                      >
                        Odnów kody odzyskiwania
                      </Button>
                      <Button
                        variant="outline"
                        disabled={busy || !!codes.length}
                        onClick={() => start("disable")}
                      >
                        Wyłącz 2FA
                      </Button>
                    </div>
                  </>
                ) : (
                  <Button
                    disabled={busy || !!codes.length}
                    onClick={() => start("setup")}
                  >
                    Skonfiguruj 2FA
                  </Button>
                )}
              </>
            )
          )}
        </section>
        <section className="card">
          <div className="security-heading">
            <KeyRound size={22} />
            <h2>Zmień hasło</h2>
          </div>
          <p className="muted">
            Zmiana hasła zakończy wszystkie sesje, również bieżącą.
          </p>
          <form onSubmit={(e) => void changePassword(e)}>
            <label>
              Obecne hasło
              <input
                type="password"
                data-private
                autoComplete="current-password"
                required
                maxLength={256}
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
              />
            </label>
            <label>
              Nowe hasło
              <input
                type="password"
                data-private
                autoComplete="new-password"
                required
                minLength={12}
                maxLength={256}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </label>
            <label>
              Powtórz nowe hasło
              <input
                type="password"
                data-private
                autoComplete="new-password"
                required
                minLength={12}
                maxLength={256}
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
              />
            </label>
            {security.data?.two_factor_enabled && (
              <label>
                Kod uwierzytelniający do zmiany hasła
                <input
                  data-private
                  autoComplete="one-time-code"
                  required
                  maxLength={80}
                  value={passwordCode}
                  onChange={(e) => setPasswordCode(e.target.value)}
                />
                <span className="hint">
                  Kod z aplikacji lub jednorazowy kod odzyskiwania.
                </span>
              </label>
            )}
            <Button disabled={busy || !!codes.length}>
              Zmień hasło i zakończ sesje
            </Button>
          </form>
        </section>
      </div>
      {action && (
        <section
          className="card account-action"
          aria-label="Potwierdzenie operacji"
        >
          <h2>{labels[action]}</h2>
          <p className="muted">
            Potwierdź operację hasłem
            {security.data?.two_factor_enabled
              ? " oraz nowym kodem z aplikacji lub kodem odzyskiwania"
              : ""}
            . Użytego kodu TOTP nie można wykorzystać ponownie.
          </p>
          {action === "confirm" && setup && (
            <>
              <p>
                Zeskanuj kod QR w aplikacji uwierzytelniającej albo wpisz sekret
                ręcznie. Konfiguracja wygasa po 10 minutach.
              </p>
              <div data-private className="totp-provision">
                <img
                  src={setup.qr_data_url}
                  alt="Kod QR konfiguracji 2FA"
                  width="220"
                  height="220"
                />
                <label>
                  Sekret do ręcznego wpisania
                  <input readOnly value={setup.secret} autoComplete="off" />
                </label>
              </div>
              <p>
                2FA zostanie włączone dopiero po potwierdzeniu kodu. Zakończymy
                inne sesje i odnowimy bieżącą.
              </p>
            </>
          )}
          {action === "regenerate" && (
            <p>
              Poprzednie kody odzyskiwania i pozostałe sesje przestaną działać.
            </p>
          )}
          {action === "disable" && (
            <p>
              Wyłączenie usuwa sekret i kody odzyskiwania oraz kończy pozostałe
              sesje.
            </p>
          )}
          {action === "policy" && (
            <p>
              Wymóg obejmuje właściciela i administratorów. Osoby bez 2FA
              zachowają dostęp do konfiguracji bezpieczeństwa konta.
            </p>
          )}
          <form onSubmit={(e) => void perform(e)}>
            <label>
              Hasło do potwierdzenia
              <input
                type="password"
                data-private
                autoComplete="current-password"
                id="reauth-password"
                required
                maxLength={256}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {(action === "confirm" || security.data?.two_factor_enabled) && (
              <label>
                Kod potwierdzający
                <input
                  data-private
                  autoComplete="one-time-code"
                  id="factor-confirm"
                  required
                  maxLength={80}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
              </label>
            )}
            <div className="actions">
              <Button disabled={busy}>
                {busy ? "Zapisywanie…" : labels[action]}
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => start(null)}
              >
                Anuluj
              </Button>
            </div>
          </form>
        </section>
      )}
      {security.data?.can_manage_policy && (
        <section className="card">
          <h2>Polityka instalacji</h2>
          <p>
            Wymaganie 2FA dla właściciela i administratorów:{" "}
            <strong>
              {security.data.require_admin_totp ? "włączone" : "wyłączone"}
            </strong>
            .
          </p>
          <p className="muted">
            Najpierw aktywuj 2FA na swoim koncie i zachowaj kody odzyskiwania.
            Wymóg nie blokuje dostępu do konfiguracji drugiego składnika.
          </p>
          <Button
            variant="outline"
            disabled={busy || !!codes.length}
            onClick={() => start("policy")}
          >
            {labels.policy}
          </Button>
        </section>
      )}
      <section className="card">
        <div className="security-heading">
          <MonitorSmartphone size={22} />
          <h2>Aktywne sesje</h2>
        </div>
        <p className="muted">
          Nie rozpoznajesz urządzenia? Zakończ jego sesję i zmień hasło.
          Metadane starszych sesji mogą być niedostępne.
        </p>
        {sessions.isPending ? (
          <p role="status">Ładowanie…</p>
        ) : (
          <div className="session-list">
            {sessions.data?.map((s) => (
              <article key={s.id} className="session-row">
                <div>
                  <strong>
                    {s.current ? "Bieżąca sesja" : "Inne urządzenie"}
                  </strong>
                  <p data-private>
                    {s.user_agent || "Brak informacji o przeglądarce"}
                  </p>
                  <small data-private>
                    {s.client_ip || "Adres nieznany"} · Utworzona:{" "}
                    {s.created_at ? date(s.created_at) : "przed aktualizacją"} ·
                    Wygasa: {date(s.expires_at)}
                  </small>
                </div>
                <Button
                  variant="outline"
                  disabled={busy || !!codes.length}
                  onClick={() => setRevokeConfirm(s)}
                >
                  Zakończ sesję
                </Button>
              </article>
            ))}
          </div>
        )}
        <Button
          variant="outline"
          disabled={busy || !!codes.length}
          onClick={() => setLogoutConfirm(true)}
        >
          Wyloguj wszystkie urządzenia
        </Button>
        {(logoutConfirm || revokeConfirm) && (
          <div
            role="alertdialog"
            aria-label="Potwierdź zakończenie sesji"
            className="confirmation"
          >
            <p>
              {logoutConfirm
                ? "Czy wylogować wszystkie urządzenia?"
                : revokeConfirm?.current
                  ? "Czy zakończyć bieżącą sesję?"
                  : "Czy zakończyć wybraną sesję?"}
            </p>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                setLogoutConfirm(false);
                setRevokeConfirm(null);
              }}
            >
              Anuluj
            </Button>
            <Button
              disabled={busy}
              onClick={() =>
                void (logoutConfirm ? logoutAll() : revokeSession())
              }
            >
              Potwierdź wylogowanie
            </Button>
          </div>
        )}
      </section>
      <section className="card">
        <h2>Moje zdarzenia bezpieczeństwa</h2>
        <p className="muted">
          Dziennik zawiera wyłącznie zdarzenia przypisane do Twojego konta.
        </p>
        {events.isPending ? (
          <p role="status">Ładowanie…</p>
        ) : (
          <>
            <ul className="security-events">
              {events.data?.items.map((e) => (
                <li key={e.id}>
                  <span>{actions[e.action] || "Zdarzenie konta"}</span>
                  <time>{date(e.created_at)}</time>
                </li>
              ))}
            </ul>
            {events.data?.items.length === 0 && <p>Brak zdarzeń.</p>}
            <div className="actions">
              {before && (
                <Button variant="outline" onClick={() => setBefore(undefined)}>
                  Najnowsze zdarzenia
                </Button>
              )}
              {events.data?.next_before && (
                <Button
                  variant="outline"
                  onClick={() => setBefore(events.data!.next_before!)}
                >
                  Starsze zdarzenia
                </Button>
              )}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
