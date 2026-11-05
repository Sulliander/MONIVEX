import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { Activity } from "lucide-react";
import { api } from "./api";
import { Button } from "./components/ui/button";

export type Monitor = {
  id: number;
  name: string;
  kind: string;
  state: string;
  recorded_state: string;
  stale: boolean;
  paused: boolean;
  interval: number;
  last_checked_at: number | null;
};
export type DashboardData = {
  monitoring_available: boolean;
  worker_status: string;
  last_cycle_at: number | null;
  monitors: Monitor[];
  incidents: {
    id: number;
    monitor_id: number;
    started_at: number;
    cause: string;
  }[];
};
type Result = {
  id: number;
  checked_at: number;
  status: string;
  state: string;
  duration_ms: number;
  message: string;
};
const kinds = [
  "http",
  "tcp",
  "icmp",
  "dns",
  "tls",
  "smtp",
  "http_json",
  "heartbeat",
];
export function Engine({
  status,
  last,
}: {
  status: string;
  last: number | null;
}) {
  const { t } = useTranslation();
  return (
    <section className="engine">
      <Activity />
      <div>
        <h2>{t("workerTitle")}</h2>
        <p>
          {t(status === "running" ? "workerRunning" : "workerStale")}
          {last ? ` · ${new Date(last * 1000).toLocaleString("pl-PL")}` : ""}
        </p>
      </div>
      <span className={`badge ${status === "running" ? "" : "amber"}`}>
        {t(status === "running" ? "running" : "stale")}
      </span>
    </section>
  );
}
export function MonitorTable({
  rows,
  actions = false,
}: {
  rows: Monitor[];
  actions?: boolean;
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [selected, setSelected] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const history = useQuery({
    queryKey: ["results", selected],
    queryFn: () => api<Result[]>(`/monitors/${selected}/results`),
    enabled: selected !== null,
    refetchInterval: 5000,
  });
  async function action(row: Monitor, kind: "pause" | "test") {
    setBusy(true);
    setMessage("");
    try {
      if (kind === "pause") {
        await api(`/monitors/${row.id}/pause`, "PATCH", {
          paused: !row.paused,
        });
        await client.invalidateQueries({ queryKey: ["monitors"] });
        await client.invalidateQueries({ queryKey: ["dashboard"] });
      } else {
        const result = await api<{
          status: string;
          duration_ms: number;
          message: string;
        }>(`/monitors/${row.id}/test`, "POST");
        setMessage(
          `${t(result.status)} · ${result.duration_ms} ms · ${result.message}`,
        );
      }
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {message && (
        <p role="status" className="card">
          {message}
        </p>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {["monitorName", "type", "state", "lastCheck", "actions"].map(
                (key) => (
                  <th key={key}>{t(key)}</th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.name}</td>
                <td>{t(`kind_${row.kind}`)}</td>
                <td>
                  <span className={`state state-${row.state}`}>
                    {t(row.state)}
                  </span>
                  {row.stale && <small> · {t("stale")}</small>}
                </td>
                <td>
                  {row.last_checked_at
                    ? new Date(row.last_checked_at * 1000).toLocaleString(
                        "pl-PL",
                      )
                    : t("noResults")}
                </td>
                <td>
                  <Button variant="ghost" onClick={() => setSelected(row.id)}>
                    {t("history")}
                  </Button>
                  {actions && (
                    <>
                      <Button
                        disabled={busy}
                        variant="ghost"
                        onClick={() => void action(row, "pause")}
                      >
                        {t(row.paused ? "resume" : "pause")}
                      </Button>
                      {row.kind !== "heartbeat" && (
                        <Button
                          disabled={busy}
                          variant="outline"
                          onClick={() => void action(row, "test")}
                        >
                          {t("runTest")}
                        </Button>
                      )}
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {selected !== null && (
        <section className="card history">
          <div className="page-title">
            <h2>
              {t("history")} · {rows.find((r) => r.id === selected)?.name}
            </h2>
            <Button variant="ghost" onClick={() => setSelected(null)}>
              {t("close")}
            </Button>
          </div>
          {history.isPending ? (
            <p>{t("loading")}</p>
          ) : history.isError ? (
            <p role="alert">{history.error.message}</p>
          ) : !history.data.length ? (
            <p>{t("noResults")}</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    {["lastCheck", "state", "duration", "details"].map((x) => (
                      <th key={x}>{t(x)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {history.data.map((r) => (
                    <tr key={r.id}>
                      <td>
                        {new Date(r.checked_at * 1000).toLocaleString("pl-PL")}
                      </td>
                      <td>
                        {t(r.status)} / {t(r.state)}
                      </td>
                      <td>{r.duration_ms} ms</td>
                      <td>{r.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </>
  );
}
type Fields = {
  name: string;
  kind: string;
  host: string;
  port: number;
  url: string;
  interval: number;
  timeout: number;
  failure_threshold: number;
  recovery_threshold: number;
  domain: string;
  record_type: string;
  expected_answer: string;
  contains: string;
  method: string;
  expected_codes: string;
  json_path: string;
  expected_value: string;
  expiry_warning_days: number;
  grace_seconds: number;
  follow_redirects: boolean;
  starttls: boolean;
  warning_ms: number;
};
export function Monitors({ canEdit }: { canEdit: boolean }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [token, setToken] = useState<{ id: number; value: string } | null>(
    null,
  );
  const rows = useQuery({
    queryKey: ["monitors"],
    queryFn: () => api<Monitor[]>("/monitors"),
    refetchInterval: 5000,
  });
  const {
    register,
    control,
    setValue,
    handleSubmit,
    reset,
    formState: { isSubmitting },
  } = useForm<Fields>({
    defaultValues: {
      kind: "http",
      port: 443,
      interval: 60,
      timeout: 5,
      failure_threshold: 3,
      recovery_threshold: 2,
      method: "GET",
      expected_codes: "200",
      record_type: "A",
      expiry_warning_days: 30,
      grace_seconds: 30,
      warning_ms: 0,
    },
  });
  const kind = useWatch({ control, name: "kind" });
  useEffect(() => {
    setValue("port", kind === "dns" ? 53 : kind === "smtp" ? 25 : 443);
  }, [kind, setValue]);
  const http = ["http", "http_json"].includes(kind);
  async function submit(d: Fields) {
    setMessage("");
    try {
      let expected: unknown = null;
      if (d.kind === "http_json") {
        try {
          expected = JSON.parse(d.expected_value);
        } catch {
          throw new Error(t("invalidJsonValue"));
        }
      }
      const config = http
        ? {
            url: d.url,
            method: d.method,
            expected_codes: d.expected_codes
              .split(",")
              .map((x) => Number(x.trim())),
            contains: d.contains || "",
            follow_redirects: !!d.follow_redirects,
            warning_ms: d.warning_ms || 0,
            ...(d.kind === "http_json"
              ? {
                  json_path: (d.json_path || "")
                    .split(".")
                    .filter(Boolean)
                    .map((x) => (/^\d+$/.test(x) ? Number(x) : x)),
                  expected_value: expected,
                }
              : {}),
          }
        : d.kind === "heartbeat"
          ? { grace_seconds: d.grace_seconds }
          : {
              host: d.host,
              port: d.port,
              ...(d.kind === "dns"
                ? {
                    domain: d.domain,
                    record_type: d.record_type,
                    expected_answer: d.expected_answer || "",
                  }
                : {}),
              ...(d.kind === "tls"
                ? { expiry_warning_days: d.expiry_warning_days }
                : {}),
              ...(d.kind === "smtp" ? { starttls: !!d.starttls } : {}),
            };
      const result = await api<{ id: number; heartbeat_token?: string }>(
        "/monitors",
        "POST",
        {
          name: d.name,
          kind: d.kind,
          interval: d.interval,
          timeout: d.timeout,
          failure_threshold: d.failure_threshold,
          recovery_threshold: d.recovery_threshold,
          config,
        },
      );
      if (result.heartbeat_token)
        setToken({ id: result.id, value: result.heartbeat_token });
      setOpen(false);
      reset();
      await client.invalidateQueries({ queryKey: ["monitors"] });
      await client.invalidateQueries({ queryKey: ["dashboard"] });
    } catch (e) {
      setMessage((e as Error).message);
    }
  }
  return (
    <>
      <div className="page-title">
        <h1>{t("monitors")}</h1>
        {canEdit && (
          <Button onClick={() => setOpen(!open)}>
            {t(open ? "cancel" : "addMonitor")}
          </Button>
        )}
      </div>
      {message && (
        <p role="alert" className="error">
          {message}
        </p>
      )}
      {token && (
        <section className="card">
          <h2>{t("heartbeatToken")}</h2>
          <p>{t("heartbeatHint")}</p>
          <p>
            {t("heartbeatEndpoint")}: <code>/api/heartbeats/{token.id}</code>
          </p>
          <label>
            {t("heartbeatToken")}
            <input
              readOnly
              value={token.value}
              onFocus={(e) => e.target.select()}
            />
          </label>
          <Button variant="outline" onClick={() => setToken(null)}>
            {t("hideToken")}
          </Button>
        </section>
      )}
      {open && (
        <section className="card">
          <form onSubmit={handleSubmit(submit)} className="monitor-form">
            <label>
              {t("monitorName")}
              <input required maxLength={100} {...register("name")} />
            </label>
            <label>
              {t("type")}
              <select {...register("kind")}>
                {kinds.map((x) => (
                  <option key={x} value={x}>
                    {t(`kind_${x}`)}
                  </option>
                ))}
              </select>
            </label>
            {http ? (
              <>
                <label>
                  {t("url")}
                  <input type="url" required {...register("url")} />
                </label>
                <label>
                  {t("method")}
                  <select {...register("method")}>
                    {["GET", "HEAD", "POST"].map((x) => (
                      <option key={x}>{x}</option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("expectedCodes")}
                  <input required {...register("expected_codes")} />
                </label>
                <label>
                  {t("contains")}
                  <input {...register("contains")} />
                </label>
                <label className="check-label">
                  <input type="checkbox" {...register("follow_redirects")} />
                  {t("followRedirects")}
                </label>
                <label>
                  {t("warningMs")}
                  <input
                    type="number"
                    min={0}
                    max={120000}
                    {...register("warning_ms", { valueAsNumber: true })}
                  />
                </label>
              </>
            ) : kind !== "heartbeat" ? (
              <>
                <label>
                  {t("host")}
                  <input required {...register("host")} />
                </label>
                {kind !== "icmp" && (
                  <label>
                    {t("port")}
                    <input
                      type="number"
                      min={1}
                      max={65535}
                      required
                      {...register("port", { valueAsNumber: true })}
                    />
                  </label>
                )}
              </>
            ) : null}
            {kind === "dns" && (
              <>
                <label>
                  {t("domain")}
                  <input required {...register("domain")} />
                </label>
                <label>
                  {t("recordType")}
                  <select {...register("record_type")}>
                    {[
                      "A",
                      "AAAA",
                      "CNAME",
                      "MX",
                      "TXT",
                      "NS",
                      "SOA",
                      "SRV",
                    ].map((x) => (
                      <option key={x}>{x}</option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("expectedAnswer")}
                  <input {...register("expected_answer")} />
                </label>
              </>
            )}
            {kind === "tls" && (
              <label>
                {t("expiryWarning")}
                <input
                  type="number"
                  min={0}
                  max={365}
                  {...register("expiry_warning_days", { valueAsNumber: true })}
                />
              </label>
            )}
            {kind === "smtp" && (
              <label className="check-label">
                <input type="checkbox" {...register("starttls")} />
                {t("starttls")}
              </label>
            )}
            {kind === "http_json" && (
              <>
                <label>
                  {t("jsonPath")}
                  <input {...register("json_path")} />
                </label>
                <label>
                  {t("expectedValue")}
                  <input required {...register("expected_value")} />
                </label>
              </>
            )}
            {kind === "heartbeat" && (
              <label>
                {t("graceSeconds")}
                <input
                  type="number"
                  min={0}
                  max={86400}
                  {...register("grace_seconds", { valueAsNumber: true })}
                />
              </label>
            )}
            {(
              [
                "interval",
                "timeout",
                "failure_threshold",
                "recovery_threshold",
              ] as const
            ).map((key) => (
              <label key={key}>
                {t(key)}
                <input
                  type="number"
                  required
                  min={key === "timeout" ? 0.1 : key === "interval" ? 10 : 1}
                  max={key === "timeout" ? 30 : key === "interval" ? 86400 : 20}
                  step={key === "timeout" ? 0.1 : 1}
                  {...register(key, { valueAsNumber: true })}
                />
              </label>
            ))}
            <p className="hint full">{t("targetPolicyHint")}</p>
            <Button disabled={isSubmitting}>
              {t(isSubmitting ? "loading" : "saveMonitor")}
            </Button>
          </form>
        </section>
      )}
      {rows.isPending ? (
        <p>{t("loading")}</p>
      ) : rows.isError ? (
        <p role="alert" className="error">
          {rows.error.message}
        </p>
      ) : rows.data.length ? (
        <MonitorTable rows={rows.data} actions={canEdit} />
      ) : (
        <div className="empty">
          <h2>{t("noMonitors")}</h2>
          <p>{t("noMonitorsText")}</p>
        </div>
      )}
    </>
  );
}
