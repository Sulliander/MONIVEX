import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { api } from "./api";
import { Button } from "./components/ui/button";
import { MonitorTable, type Monitor } from "./Monitoring";
import MonitorForm from "./MonitorForm";
import {
  groupLabel,
  type Group,
  type Resource,
  type Tag,
} from "./infrastructure";

type BulkFields = {
  interval: string;
  timeout: string;
  failure_threshold: string;
  recovery_threshold: string;
  group_id: string;
  resource_id: string;
  priority: string;
  tagAction: string;
  tag_ids: string[];
};
export default function MonitorManager({ canEdit }: { canEdit: boolean }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [url, setUrl] = useSearchParams();
  const [editing, setEditing] = useState<Monitor | null | undefined>(undefined);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState<{ id: number; value: string } | null>(
    null,
  );
  const [selected, setSelected] = useState<number[]>([]);
  const [confirm, setConfirm] = useState<{
    kind: "delete" | "duplicate" | "bulkDelete";
    row?: Monitor;
  } | null>(null);
  const [copyCredentials, setCopyCredentials] = useState(false);
  const [duplicateName, setDuplicateName] = useState("");
  const [bulkOpen, setBulkOpen] = useState(false);
  const [q, setQ] = useState("");
  const [group, setGroup] = useState("");
  const [tag, setTag] = useState("");
  const [kind, setKind] = useState("");
  const [state, setState] = useState("");
  const [sort, setSort] = useState("name");
  const [offset, setOffset] = useState(0);
  const resource = url.get("resource") || "";
  const params = new URLSearchParams({
    q,
    sort,
    offset: String(offset),
    limit: "50",
  });
  if (group) params.set("group_id", group);
  if (tag) params.set("tag_id", tag);
  if (kind) params.set("kind", kind);
  if (state) params.set("state", state);
  if (resource) params.set("resource_id", resource);
  const rows = useQuery({
    queryKey: ["monitors", params.toString()],
    queryFn: () =>
      api<{ items: Monitor[]; total: number; offset: number; limit: number }>(
        `/monitors/search?${params}`,
      ),
    refetchInterval: 5000,
    refetchIntervalInBackground: true,
  });
  const groups = useQuery({
    queryKey: ["groups"],
    queryFn: () => api<Group[]>("/groups"),
  });
  const tags = useQuery({
    queryKey: ["tags"],
    queryFn: () => api<Tag[]>("/tags"),
  });
  const resources = useQuery({
    queryKey: ["resources"],
    queryFn: () => api<Resource[]>("/resources"),
  });
  const {
    register,
    handleSubmit,
    reset: resetBulk,
  } = useForm<BulkFields>({
    defaultValues: {
      group_id: "keep",
      resource_id: "keep",
      priority: "keep",
      tagAction: "keep",
      tag_ids: [],
    },
  });
  const selectedRows = (rows.data?.items || []).filter((row) =>
    selected.includes(row.id),
  );
  function changed(setter: (s: string) => void, value: string) {
    setter(value);
    setOffset(0);
    setSelected([]);
  }
  async function refresh() {
    await Promise.all(
      ["monitors", "dashboard", "resources", "results"].map((key) =>
        client.invalidateQueries({ queryKey: [key] }),
      ),
    );
  }
  async function saved(result: Monitor & { heartbeat_token?: string }) {
    if (result.heartbeat_token)
      setToken({ id: result.id, value: result.heartbeat_token });
    setEditing(undefined);
    await refresh();
    setMessage(t("saved"));
  }
  async function perform(
    kind: "pause" | "resume" | "delete" | "configure",
    settings: object = {},
  ) {
    setBusy(true);
    setMessage("");
    try {
      await api("/monitors/bulk", "POST", {
        monitor_ids: selectedRows.map((row) => row.id),
        revisions: Object.fromEntries(
          selectedRows.map((row) => [row.id, row.revision]),
        ),
        operation: kind,
        ...settings,
      });
      setSelected([]);
      setBulkOpen(false);
      setConfirm(null);
      resetBulk();
      await refresh();
      setMessage(t("bulkSaved"));
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function bulkSave(d: BulkFields) {
    const settings: Record<string, unknown> = {};
    for (const key of [
      "interval",
      "timeout",
      "failure_threshold",
      "recovery_threshold",
    ] as const) {
      if (d[key]) settings[key] = Number(d[key]);
    }
    for (const key of ["group_id", "resource_id"] as const) {
      if (d[key] !== "keep") settings[key] = d[key] ? Number(d[key]) : null;
    }
    if (d.priority !== "keep") settings.priority = d.priority;
    if (d.tagAction === "replace")
      settings.tag_ids = (d.tag_ids || []).map(Number);
    if (d.tagAction === "clear") settings.tag_ids = [];
    if (!Object.keys(settings).length) {
      setMessage(t("chooseBulkChanges"));
      return;
    }
    await perform("configure", settings);
  }
  async function confirmAction() {
    if (!confirm) return;
    if (confirm.kind === "bulkDelete") {
      await perform("delete");
      return;
    }
    const row = confirm.row!;
    setBusy(true);
    setMessage("");
    try {
      if (confirm.kind === "delete")
        await api(`/monitors/${row.id}?revision=${row.revision}`, "DELETE");
      else {
        const result = await api<Monitor & { heartbeat_token?: string }>(
          `/monitors/${row.id}/duplicate`,
          "POST",
          {
            name: duplicateName,
            revision: row.revision,
            copy_credentials: copyCredentials,
          },
        );
        if (result.heartbeat_token)
          setToken({ id: result.id, value: result.heartbeat_token });
      }
      setConfirm(null);
      setSelected([]);
      await refresh();
      setMessage(t("saved"));
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function duplicate(row: Monitor) {
    setConfirm({ kind: "duplicate", row });
    setDuplicateName(`${row.name.slice(0, 80)} ${t("copySuffix")}`);
    setCopyCredentials(false);
  }
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">{t("infrastructure")}</p>
          <h1>{t("monitors")}</h1>
        </div>
        {canEdit && (
          <Button
            onClick={() => {
              setEditing(editing === undefined ? null : undefined);
              setMessage("");
            }}
          >
            {t(editing === undefined ? "addMonitor" : "cancel")}
          </Button>
        )}
      </div>
      {message && (
        <p role="status" className="notice">
          {message}
        </p>
      )}
      {[groups.error, tags.error, resources.error].some(Boolean) && (
        <p role="alert" className="error">
          {groups.error?.message ||
            tags.error?.message ||
            resources.error?.message}
        </p>
      )}
      {token && (
        <section className="card" data-private="true">
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
      {editing !== undefined && (
        <MonitorForm
          key={editing?.id || "new"}
          initial={editing}
          groups={groups.data || []}
          tags={tags.data || []}
          resources={resources.data || []}
          onCancel={() => setEditing(undefined)}
          onSaved={saved}
        />
      )}
      <section className="toolbar">
        <label>
          {t("search")}
          <input
            type="search"
            value={q}
            onChange={(e) => changed(setQ, e.target.value)}
          />
        </label>
        <label>
          {t("group")}
          <select
            value={group}
            onChange={(e) => changed(setGroup, e.target.value)}
          >
            <option value="">{t("allGroups")}</option>
            {(groups.data || []).map((g) => (
              <option key={g.id} value={g.id}>
                {groupLabel(g.id, groups.data || [])}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("tag")}
          <select value={tag} onChange={(e) => changed(setTag, e.target.value)}>
            <option value="">{t("allTags")}</option>
            {(tags.data || []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("resource")}
          <select
            value={resource}
            onChange={(e) => {
              setUrl(e.target.value ? { resource: e.target.value } : {});
              setOffset(0);
              setSelected([]);
            }}
          >
            <option value="">{t("allResources")}</option>
            {(resources.data || []).map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("type")}
          <select
            value={kind}
            onChange={(e) => changed(setKind, e.target.value)}
          >
            <option value="">{t("allTypes")}</option>
            {[
              "http",
              "tcp",
              "icmp",
              "dns",
              "tls",
              "smtp",
              "http_json",
              "heartbeat",
            ].map((x) => (
              <option key={x} value={x}>
                {t(`kind_${x}`)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("state")}
          <select
            value={state}
            onChange={(e) => changed(setState, e.target.value)}
          >
            <option value="">{t("allStates")}</option>
            {["UP", "DEGRADED", "DOWN", "PENDING", "UNKNOWN", "PAUSED"].map(
              (x) => (
                <option key={x} value={x}>
                  {t(x)}
                </option>
              ),
            )}
          </select>
        </label>
        <label>
          {t("sort")}
          <select
            value={sort}
            onChange={(e) => changed(setSort, e.target.value)}
          >
            {["name", "priority", "state", "id"].map((x) => (
              <option key={x} value={x}>
                {t(`sort_${x}`)}
              </option>
            ))}
          </select>
        </label>
      </section>
      {canEdit && selectedRows.length > 0 && (
        <section className="bulk-bar">
          <strong>{t("selectedCount", { count: selectedRows.length })}</strong>
          <Button
            disabled={busy}
            variant="outline"
            onClick={() => void perform("pause")}
          >
            {t("pauseSelected")}
          </Button>
          <Button
            disabled={busy}
            variant="outline"
            onClick={() => void perform("resume")}
          >
            {t("resumeSelected")}
          </Button>
          <Button
            disabled={busy}
            variant="outline"
            onClick={() => setBulkOpen(!bulkOpen)}
          >
            {t("configureSelected")}
          </Button>
          <Button
            disabled={busy}
            variant="outline"
            onClick={() => setConfirm({ kind: "bulkDelete" })}
          >
            {t("deleteSelected")}
          </Button>
        </section>
      )}
      {bulkOpen && selectedRows.length > 0 && (
        <section className="card editor-card">
          <h2>{t("configureSelected")}</h2>
          <form className="monitor-form" onSubmit={handleSubmit(bulkSave)}>
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
                  placeholder={t("keepCurrent")}
                  step={key === "timeout" ? 0.1 : 1}
                  min={key === "timeout" ? 0.1 : key === "interval" ? 10 : 1}
                  max={key === "timeout" ? 30 : key === "interval" ? 86400 : 20}
                  {...register(key)}
                />
              </label>
            ))}
            <label>
              {t("priority")}
              <select {...register("priority")}>
                <option value="keep">{t("keepCurrent")}</option>
                {["low", "normal", "high", "critical"].map((x) => (
                  <option key={x} value={x}>
                    {t(`priority_${x}`)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("group")}
              <select {...register("group_id")}>
                <option value="keep">{t("keepCurrent")}</option>
                <option value="">{t("unassigned")}</option>
                {(groups.data || []).map((g) => (
                  <option key={g.id} value={g.id}>
                    {groupLabel(g.id, groups.data || [])}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("resource")}
              <select {...register("resource_id")}>
                <option value="keep">{t("keepCurrent")}</option>
                <option value="">{t("unassigned")}</option>
                {(resources.data || []).map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("tagAction")}
              <select {...register("tagAction")}>
                <option value="keep">{t("keepCurrent")}</option>
                <option value="replace">{t("replaceTags")}</option>
                <option value="clear">{t("clearTags")}</option>
              </select>
            </label>
            <label>
              {t("tags")}
              <select multiple {...register("tag_ids")}>
                {(tags.data || []).map((tag) => (
                  <option key={tag.id} value={tag.id}>
                    {tag.name}
                  </option>
                ))}
              </select>
            </label>
            <p className="hint full">{t("atomicBulkHint")}</p>
            <Button disabled={busy}>{t("applyChanges")}</Button>
          </form>
        </section>
      )}
      {rows.isPending ? (
        <p role="status">{t("loading")}</p>
      ) : rows.isError ? (
        <p role="alert" className="error">
          {rows.error.message}
        </p>
      ) : rows.data.items.length ? (
        <>
          <MonitorTable
            rows={rows.data.items}
            actions={canEdit}
            selectedIds={selected}
            onSelect={canEdit ? setSelected : undefined}
            onEdit={setEditing}
            onDuplicate={duplicate}
            onDelete={(row) => setConfirm({ kind: "delete", row })}
          />
          <div className="pagination">
            <span>{t("resultCount", { count: rows.data.total })}</span>
            <Button
              variant="outline"
              disabled={offset === 0}
              onClick={() => {
                setOffset(Math.max(0, offset - 50));
                setSelected([]);
              }}
            >
              {t("previousPage")}
            </Button>
            <Button
              variant="outline"
              disabled={offset + 50 >= rows.data.total}
              onClick={() => {
                setOffset(offset + 50);
                setSelected([]);
              }}
            >
              {t("nextPage")}
            </Button>
          </div>
        </>
      ) : (
        <div className="empty">
          <h2>
            {t(
              q || group || tag || kind || state || resource
                ? "noMatches"
                : "noMonitors",
            )}
          </h2>
          <p>{t("noMonitorsText")}</p>
        </div>
      )}
      {confirm && (
        <div className="modal-backdrop">
          <section
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="monitor-confirm"
            className="card dialog"
          >
            <h2 id="monitor-confirm">
              {t(
                confirm.kind === "duplicate"
                  ? "duplicateMonitor"
                  : "confirmDelete",
              )}
            </h2>
            {confirm.kind === "duplicate" ? (
              <>
                <label>
                  {t("monitorName")}
                  <input
                    required
                    maxLength={100}
                    value={duplicateName}
                    onChange={(e) => setDuplicateName(e.target.value)}
                  />
                </label>
                {confirm.row?.has_credentials && (
                  <label className="check-label">
                    <input
                      type="checkbox"
                      checked={copyCredentials}
                      onChange={(e) => setCopyCredentials(e.target.checked)}
                    />
                    {t("copyCredentials")}
                  </label>
                )}
                <p className="hint">{t("duplicateHint")}</p>
              </>
            ) : (
              <>
                <p>
                  {confirm.row?.name ||
                    t("selectedCount", { count: selectedRows.length })}
                </p>
                <p>{t("deleteMonitorHint")}</p>
              </>
            )}
            <div className="actions">
              <Button variant="outline" onClick={() => setConfirm(null)}>
                {t("cancel")}
              </Button>
              <Button
                disabled={
                  busy ||
                  (confirm.kind === "duplicate" && !duplicateName.trim())
                }
                onClick={() => void confirmAction()}
              >
                {t(confirm.kind === "duplicate" ? "duplicate" : "delete")}
              </Button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
