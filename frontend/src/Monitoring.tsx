import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { useDateFormatter } from "./dates";
import { api } from "./api";
import { Button } from "./components/ui/button";

export type Monitor = {
  id: number;
  name: string;
  kind: string;
  config: Record<string, unknown>;
  revision: number;
  group_id: number | null;
  resource_id: number | null;
  tag_ids: number[];
  priority: string;
  has_credentials: boolean;
  timeout: number;
  failure_threshold: number;
  recovery_threshold: number;
  state: string;
  recorded_state: string;
  stale: boolean;
  paused: boolean;
  interval: number;
  last_checked_at: number | null;
};
export type DashboardData = {
  counts?: Record<string, number>;
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
export function Engine({
  status,
  last,
}: {
  status: string;
  last: number | null;
}) {
  const { t } = useTranslation();
  const date = useDateFormatter();
  return (
    <section className={`engine engine-${status}`}>
      <Activity />
      <div>
        <h2>{t("workerTitle")}</h2>
        <p>
          {t(status === "running" ? "workerRunning" : "workerStale")}
          {last ? ` · ${date(last)}` : ""}
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
  selectedIds,
  onSelect,
  onEdit,
  onDuplicate,
  onDelete,
}: {
  rows: Monitor[];
  actions?: boolean;
  selectedIds?: number[];
  onSelect?: (ids: number[]) => void;
  onEdit?: (row: Monitor) => void;
  onDuplicate?: (row: Monitor) => void;
  onDelete?: (row: Monitor) => void;
}) {
  const { t } = useTranslation();
  const date = useDateFormatter();
  const client = useQueryClient();
  const [selected, setSelected] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const history = useQuery({
    queryKey: ["results", selected],
    queryFn: () => api<Result[]>(`/monitors/${selected}/results`),
    enabled: selected !== null,
    refetchInterval: 5000,
    refetchIntervalInBackground: true,
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
              {onSelect && (
                <th>
                  <input
                    type="checkbox"
                    aria-label={t("selectPage")}
                    checked={
                      rows.length > 0 &&
                      rows.every((row) => selectedIds?.includes(row.id))
                    }
                    onChange={(e) =>
                      onSelect(
                        e.target.checked ? rows.map((row) => row.id) : [],
                      )
                    }
                  />
                </th>
              )}
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
                {onSelect && (
                  <td>
                    <input
                      type="checkbox"
                      aria-label={t("selectMonitor", { name: row.name })}
                      checked={selectedIds?.includes(row.id) || false}
                      onChange={(e) =>
                        onSelect(
                          e.target.checked
                            ? [...(selectedIds || []), row.id]
                            : (selectedIds || []).filter((id) => id !== row.id),
                        )
                      }
                    />
                  </td>
                )}
                <td>
                  <strong>{row.name}</strong>
                  {actions && (
                    <small className="subline">
                      {t(`priority_${row.priority || "normal"}`)}
                    </small>
                  )}
                </td>
                <td>{t(`kind_${row.kind}`)}</td>
                <td>
                  <span className={`state state-${row.state}`}>
                    {t(row.state)}
                  </span>
                  {row.stale && <small> · {t("stale")}</small>}
                </td>
                <td>
                  {row.last_checked_at
                    ? date(row.last_checked_at)
                    : t("noResults")}
                </td>
                <td>
                  <Button variant="ghost" onClick={() => setSelected(row.id)}>
                    {t("history")}
                  </Button>
                  {actions && (
                    <>
                      {onEdit && (
                        <Button variant="ghost" onClick={() => onEdit(row)}>
                          {t("edit")}
                        </Button>
                      )}
                      {onDuplicate && (
                        <Button
                          variant="ghost"
                          onClick={() => onDuplicate(row)}
                        >
                          {t("duplicate")}
                        </Button>
                      )}
                      {onDelete && (
                        <Button variant="ghost" onClick={() => onDelete(row)}>
                          {t("delete")}
                        </Button>
                      )}
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
                      <td>{date(r.checked_at)}</td>
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

export { default as Monitors } from "./MonitorManager";
