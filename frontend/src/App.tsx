import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { NavLink, Route, Routes, useNavigate } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  Check,
  ChevronRight,
  CircleHelp,
  LayoutDashboard,
  LogOut,
  Menu,
  Server,
  Settings,
  ShieldCheck,
} from "lucide-react";
import { api, ApiError } from "./api";
import {
  Monitors,
  Engine,
  MonitorTable,
  type DashboardData,
} from "./Monitoring";
import { Button } from "./components/ui/button";

const schema = z.object({
  username: z.string().regex(/^[a-zA-Z0-9_.-]{3,64}$/),
  password: z.string().min(12).max(256),
  installation_name: z.string().min(1).max(100),
  timezone: z.string().min(1).max(64),
  token: z.string().min(32),
});
type Setup = z.infer<typeof schema>;
type User = { id: number; username: string; role: string };
export default function App() {
  const { t } = useTranslation();
  const client = useQueryClient();
  useEffect(() => {
    const expired = () => {
      sessionStorage.removeItem("csrf");
      client.setQueryData(["me"], null);
      client.removeQueries({
        predicate: (q) => !["me", "setup"].includes(String(q.queryKey[0])),
      });
    };
    window.addEventListener("monivex:session-expired", expired);
    return () => window.removeEventListener("monivex:session-expired", expired);
  }, [client]);
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "dark");
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme =
        theme === "system" ? (media.matches ? "dark" : "light") : theme;
    };
    apply();
    media.addEventListener("change", apply);
    localStorage.setItem("theme", theme);
    return () => media.removeEventListener("change", apply);
  }, [theme]);
  const setup = useQuery({
    queryKey: ["setup"],
    queryFn: () => api<{ initialized: boolean }>("/setup/status"),
  });
  const user = useQuery({
    queryKey: ["me"],
    queryFn: () => api<User>("/auth/me"),
    enabled: setup.data?.initialized === true,
  });
  const refresh = async () => {
    await client.invalidateQueries();
  };
  const themeSelect = (
    <label className="theme">
      <span>{t("theme")}</span>
      <select
        aria-label={t("theme")}
        value={theme}
        onChange={(e) => setTheme(e.target.value)}
      >
        {["dark", "light", "system"].map((x) => (
          <option key={x} value={x}>
            {t(x)}
          </option>
        ))}
      </select>
    </label>
  );
  if (setup.isPending || (setup.data?.initialized && user.isPending))
    return (
      <div role="status" className="center">
        {t("loading")}
      </div>
    );
  if (
    setup.isError ||
    (user.isError &&
      !(user.error instanceof ApiError && user.error.status === 401))
  )
    return (
      <div role="alert" className="center">
        {(setup.error || user.error)?.message}
        <Button onClick={() => void refresh()}>{t("retry")}</Button>
      </div>
    );
  return (
    <>
      {!setup.data?.initialized ? (
        <div className="auth-shell">
          {themeSelect}
          <Wizard done={refresh} />
        </div>
      ) : !user.data ? (
        <div className="auth-shell">
          {themeSelect}
          <Login done={refresh} />
        </div>
      ) : (
        <Panel user={user.data} themeSelect={themeSelect} />
      )}
    </>
  );
}
function Brand() {
  const { t } = useTranslation();
  return (
    <div className="brand">
      <Activity size={28} />
      <span>{t("brand")}</span>
    </div>
  );
}
function Wizard({ done }: { done: () => Promise<void> }) {
  const { t } = useTranslation();
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const {
    register,
    handleSubmit,
    trigger,
    formState: { isSubmitting, errors },
    getValues,
  } = useForm<Setup>({
    resolver: zodResolver(schema),
    defaultValues: { installation_name: "MONIVEX", timezone: "Europe/Warsaw" },
  });
  const steps = ["welcome", "owner", "general", "optional", "review"];
  async function next() {
    const fields: (keyof Setup)[] =
      step === 1
        ? ["username", "password", "token"]
        : step === 2
          ? ["installation_name", "timezone"]
          : [];
    if (await trigger(fields)) setStep(step + 1);
  }
  async function submit(data: Setup) {
    setError("");
    try {
      await api(
        "/setup",
        "POST",
        {
          username: data.username,
          password: data.password,
          installation_name: data.installation_name,
          timezone: data.timezone,
        },
        { "X-Setup-Token": data.token },
      );
      await done();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <main className="auth-card wizard">
      <Brand />
      <div className="steps">
        {steps.map((key, i) => (
          <span
            key={key}
            className={step === i ? "selected" : ""}
            aria-current={step === i ? "step" : undefined}
          >
            {i < step ? <Check size={14} /> : i + 1}
          </span>
        ))}
      </div>
      <p className="eyebrow">{t("foundation")}</p>
      <h1>{t(steps[step])}</h1>
      <form onSubmit={handleSubmit(submit)}>
        <div hidden={step !== 0}>
          <p>{t("intro")}</p>
          <div className="welcome-icon">
            <ShieldCheck size={64} />
          </div>
        </div>
        <div hidden={step !== 1}>
          <label>
            {t("username")}
            <input autoComplete="username" {...register("username")} />
          </label>
          <label>
            {t("password")}
            <input
              type="password"
              autoComplete="new-password"
              {...register("password")}
            />
          </label>
          <label>
            {t("setupToken")}
            <input type="password" autoComplete="off" {...register("token")} />
          </label>
          <p className="hint">{t("setupHint")}</p>
        </div>
        <div hidden={step !== 2}>
          <label>
            {t("installationName")}
            <input {...register("installation_name")} />
          </label>
          <label>
            {t("timezone")}
            <select {...register("timezone")}>
              {[
                "Europe/Warsaw",
                "Europe/London",
                "Europe/Berlin",
                "UTC",
                "America/New_York",
                "Asia/Tokyo",
              ].map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
        </div>
        <div hidden={step !== 3}>
          <p>{t("optionalInfo")}</p>
        </div>
        {step === 4 && (
          <dl>
            <dt>{t("username")}</dt>
            <dd>{getValues("username")}</dd>
            <dt>{t("installationName")}</dt>
            <dd>{getValues("installation_name")}</dd>
            <dt>{t("timezone")}</dt>
            <dd>{getValues("timezone")}</dd>
          </dl>
        )}
        {Object.keys(errors).length > 0 && (
          <p className="error" role="alert">
            {t("validation")}
          </p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="actions">
          {step > 0 && (
            <Button
              type="button"
              variant="outline"
              onClick={() => setStep(step - 1)}
            >
              {t("back")}
            </Button>
          )}
          {step < 4 ? (
            <Button key="next" type="button" onClick={() => void next()}>
              {t("next")}
              <ArrowRight size={16} />
            </Button>
          ) : (
            <Button key="submit" disabled={isSubmitting}>
              {isSubmitting ? t("loading") : t("finish")}
            </Button>
          )}
        </div>
      </form>
    </main>
  );
}
function Login({ done }: { done: () => Promise<void> }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<{ username: string; password: string }>();
  async function submit(data: { username: string; password: string }) {
    try {
      const result = await api<{ csrf_token: string }>(
        "/auth/login",
        "POST",
        data,
      );
      sessionStorage.setItem("csrf", result.csrf_token);
      navigate("/");
      await done();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <main className="auth-card">
      <Brand />
      <p className="eyebrow">{t("tagline")}</p>
      <h1>{t("login")}</h1>
      <form onSubmit={handleSubmit(submit)}>
        <label>
          {t("username")}
          <input autoComplete="username" required {...register("username")} />
        </label>
        <label>
          {t("password")}
          <input
            type="password"
            autoComplete="current-password"
            required
            {...register("password")}
          />
        </label>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <Button disabled={isSubmitting}>
          {isSubmitting ? t("loading") : t("login")}
          <ArrowRight size={16} />
        </Button>
      </form>
    </main>
  );
}
const sections = [
  { key: "dashboard", items: ["overview"] },
  { key: "infrastructure", items: ["devices", "monitors", "groups", "tags"] },
  {
    key: "events",
    items: ["incidents", "notifications", "maintenance", "reports"],
  },
  { key: "administration", items: ["users", "audit", "settings", "backups"] },
];
function Panel({
  user,
  themeSelect,
}: {
  user: User;
  themeSelect: React.ReactNode;
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [collapsed, setCollapsed] = useState(false);
  const [error, setError] = useState("");
  const installation = useQuery({
    queryKey: ["installation"],
    queryFn: () =>
      api<{ name: string; timezone: string; version: string }>("/installation"),
  });
  async function logout() {
    try {
      await api("/auth/logout", "POST");
      sessionStorage.removeItem("csrf");
      client.setQueryData(["me"], null);
      client.removeQueries({
        predicate: (q) => !["me", "setup"].includes(String(q.queryKey[0])),
      });
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <div className={`layout ${collapsed ? "collapsed" : ""}`}>
      <a className="skip" href="#content">
        {t("skip")}
      </a>
      <aside>
        <Brand />
        <nav>
          {sections.map((section) => (
            <section key={section.key}>
              <p>{t(section.key)}</p>
              {section.items.map((key) => (
                <NavLink
                  key={key}
                  to={key === "overview" ? "/" : `/${key}`}
                  end
                >
                  {key === "overview" ? (
                    <LayoutDashboard size={18} />
                  ) : key === "settings" ? (
                    <Settings size={18} />
                  ) : (
                    <Server size={18} />
                  )}
                  <span>{t(key)}</span>
                  {!["overview", "settings", "monitors"].includes(key) && (
                    <CircleHelp size={13} />
                  )}
                </NavLink>
              ))}
            </section>
          ))}
        </nav>
        <footer>
          <span className="avatar">
            {user.username.slice(0, 1).toUpperCase()}
          </span>
          <div>
            {user.username}
            <small>{t(user.role)}</small>
          </div>
          <button aria-label={t("logout")} onClick={() => void logout()}>
            <LogOut size={18} />
          </button>
        </footer>
      </aside>
      <div className="workspace">
        <header>
          <button
            aria-label={t("menu")}
            onClick={() => setCollapsed(!collapsed)}
          >
            <Menu size={20} />
          </button>
          <span>{installation.data?.name || t("brand")}</span>
          <ChevronRight size={14} />
          <span className="muted">{t("foundation")}</span>
          <div className="header-end">
            {themeSelect}
            <span className="version">
              {t("version")} {installation.data?.version}
            </span>
          </div>
        </header>
        <main id="content">
          {(error || installation.error) && (
            <p role="alert" className="error">
              {error || installation.error?.message}
            </p>
          )}
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/settings" element={<Account />} />
            <Route
              path="/monitors"
              element={
                <Monitors
                  canEdit={["owner", "administrator", "operator"].includes(
                    user.role,
                  )}
                />
              }
            />
            <Route
              path="*"
              element={
                <div className="empty">
                  <CircleHelp size={38} />
                  <h1>{t("future")}</h1>
                  <p>{t("foundation")}</p>
                </div>
              }
            />
          </Routes>
        </main>
      </div>
    </div>
  );
}
function Dashboard() {
  const { t } = useTranslation();
  const data = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<DashboardData>("/dashboard"),
    refetchInterval: 5000,
  });
  const rows = data.data?.monitors || [];
  const counts = [
    rows.length,
    ...["UP", "DEGRADED", "DOWN", "UNKNOWN"].map(
      (state) => rows.filter((r) => r.state === state).length,
    ),
  ];
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">{t("dashboard")}</p>
          <h1>{t("overview")}</h1>
        </div>
        <span className="badge">{t("foundation")}</span>
      </div>
      {data.isError ? (
        <p role="alert" className="error">
          {data.error.message}
        </p>
      ) : data.isPending ? (
        <p role="status">{t("loading")}</p>
      ) : (
        <>
          <div className="stats">
            {["all", "up", "warning", "down", "unknown"].map((key, i) => (
              <article key={key}>
                <div>
                  <span className={`dot dot-${i}`} />
                  {t(key)}
                </div>
                <strong>{counts[i]}</strong>
                <small>{t("currentState")}</small>
              </article>
            ))}
          </div>
          <Engine
            status={data.data.worker_status}
            last={data.data.last_cycle_at}
          />
          {rows.length ? (
            <MonitorTable rows={rows} />
          ) : (
            <div className="empty">
              <div className="orb">
                <Activity size={46} />
              </div>
              <h2>{t("noMonitors")}</h2>
              <p>{t("noMonitorsText")}</p>
              <Button asChild>
                <NavLink to="/monitors">{t("monitors")}</NavLink>
              </Button>
            </div>
          )}
          <section className="card">
            <h2>{t("activeIncidents")}</h2>
            {data.data.incidents.length ? (
              data.data.incidents.map((i) => (
                <p key={i.id}>
                  {rows.find((r) => r.id === i.monitor_id)?.name} ·{" "}
                  {new Date(i.started_at * 1000).toLocaleString("pl-PL")} ·{" "}
                  {i.cause}
                </p>
              ))
            ) : (
              <p className="muted">{t("noActiveIncidents")}</p>
            )}
          </section>
        </>
      )}
    </>
  );
}
function Account() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [message, setMessage] = useState("");
  const [confirm, setConfirm] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<{ current_password: string; new_password: string }>();
  async function invalidate() {
    sessionStorage.removeItem("csrf");
    client.setQueryData(["me"], null);
    client.removeQueries({
      predicate: (q) => !["me", "setup"].includes(String(q.queryKey[0])),
    });
  }
  async function password(data: {
    current_password: string;
    new_password: string;
  }) {
    try {
      await api("/auth/password", "POST", data);
      await invalidate();
    } catch (e) {
      setMessage((e as Error).message);
    }
  }
  async function all() {
    try {
      await api("/auth/logout-all", "POST");
      await invalidate();
    } catch (e) {
      setMessage((e as Error).message);
    }
  }
  return (
    <>
      <h1>{t("settings")}</h1>
      <section className="card account">
        <h2>{t("account")}</h2>
        <form onSubmit={handleSubmit(password)}>
          <label>
            {t("currentPassword")}
            <input
              type="password"
              autoComplete="current-password"
              required
              {...register("current_password")}
            />
          </label>
          <label>
            {t("newPassword")}
            <input
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={256}
              required
              {...register("new_password")}
            />
          </label>
          <Button disabled={isSubmitting}>{t("changePassword")}</Button>
        </form>
        {message && (
          <p role="alert" className="error">
            {message}
          </p>
        )}
        <hr />
        <Button variant="outline" onClick={() => setConfirm(true)}>
          {t("logoutAll")}
        </Button>
        {confirm && (
          <div
            role="alertdialog"
            aria-label={t("confirmAll")}
            className="confirmation"
          >
            <p>{t("confirmAll")}</p>
            <Button variant="outline" onClick={() => setConfirm(false)}>
              {t("cancel")}
            </Button>
            <Button onClick={() => void all()}>{t("logoutAll")}</Button>
          </div>
        )}
      </section>
    </>
  );
}
