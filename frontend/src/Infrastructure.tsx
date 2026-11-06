import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { api } from "./api";
import { Button } from "./components/ui/button";
import {
  groupLabel,
  isDescendant,
  type Group,
  type Resource,
  type Tag,
} from "./infrastructure";

type Fields = {
  name: string;
  parent_id: string;
  group_id: string;
  description: string;
  address: string;
  kind: string;
  operating_system: string;
  environment: string;
  tag_ids: string[];
};
type Row = Group | Resource | Tag;
export default function Infrastructure({
  kind,
  canEdit,
}: {
  kind: "resources" | "groups" | "tags";
  canEdit: boolean;
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [editing, setEditing] = useState<Row | null | undefined>(undefined);
  const [removing, setRemoving] = useState<Row | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [groupFilter, setGroupFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [sort, setSort] = useState("name");
  const rows = useQuery({
    queryKey: [kind],
    queryFn: () => api<Row[]>(`/${kind}`),
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
  const {
    register,
    reset,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<Fields>();
  const title = kind === "resources" ? "devices" : kind;
  const visible = useMemo(() => {
    let result = (rows.data || []).filter(
      (row) =>
        ("name" in row &&
          row.name
            .toLocaleLowerCase("pl")
            .includes(query.toLocaleLowerCase("pl"))) ||
        ("address" in row &&
          row.address
            .toLocaleLowerCase("pl")
            .includes(query.toLocaleLowerCase("pl"))),
    );
    if (kind === "resources") {
      result = result.filter((row) => {
        const r = row as Resource;
        return (
          (!groupFilter ||
            (r.group_id !== null &&
              isDescendant(
                r.group_id,
                Number(groupFilter),
                groups.data || [],
              ))) &&
          (!tagFilter || r.tag_ids.includes(Number(tagFilter)))
        );
      });
    }
    return [...result].sort((a, b) =>
      sort === "state" && "state" in a && "state" in b
        ? a.state.localeCompare(b.state)
        : kind === "groups"
          ? groupLabel(a.id, groups.data || []).localeCompare(
              groupLabel(b.id, groups.data || []),
              "pl",
            )
          : a.name.localeCompare(b.name, "pl"),
    );
  }, [rows.data, query, groupFilter, tagFilter, kind, groups.data, sort]);
  function open(row: Row | null) {
    setMessage("");
    setEditing(row);
    const r = row as Resource | undefined;
    reset({
      name: row?.name || "",
      parent_id: row && "parent_id" in row ? String(row.parent_id || "") : "",
      group_id: r && "group_id" in r ? String(r.group_id || "") : "",
      description: r?.description || "",
      address: r?.address || "",
      kind: r?.kind || "server",
      operating_system: r?.operating_system || "",
      environment: r?.environment || "",
      tag_ids: r?.tag_ids?.map(String) || [],
    });
  }
  async function refresh() {
    await Promise.all(
      ["groups", "tags", "resources", "monitors", "dashboard"].map((key) =>
        client.invalidateQueries({ queryKey: [key] }),
      ),
    );
  }
  async function save(d: Fields) {
    setMessage("");
    try {
      const payload =
        kind === "groups"
          ? {
              name: d.name,
              parent_id: d.parent_id ? Number(d.parent_id) : null,
            }
          : kind === "tags"
            ? { name: d.name }
            : {
                name: d.name,
                description: d.description,
                address: d.address,
                kind: d.kind,
                operating_system: d.operating_system,
                environment: d.environment,
                group_id: d.group_id ? Number(d.group_id) : null,
                tag_ids: (d.tag_ids || []).map(Number),
              };
      await api(
        `/${kind}${editing ? `/${editing.id}` : ""}`,
        editing ? "PUT" : "POST",
        { ...payload, ...(editing ? { revision: editing.revision } : {}) },
      );
      setEditing(undefined);
      await refresh();
      setMessage(t("saved"));
    } catch (e) {
      setMessage((e as Error).message);
    }
  }
  async function remove() {
    if (!removing) return;
    setBusy(true);
    try {
      await api(
        `/${kind}/${removing.id}?revision=${removing.revision}`,
        "DELETE",
      );
      setRemoving(null);
      await refresh();
      setMessage(t("deleted"));
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">{t("infrastructure")}</p>
          <h1>{t(title)}</h1>
        </div>
        {canEdit && (
          <Button onClick={() => open(null)}>{t(`add_${kind}`)}</Button>
        )}
      </div>
      {message && (
        <p role="status" className="notice">
          {message}
        </p>
      )}
      {[rows.error, groups.error, tags.error].some(Boolean) && (
        <p role="alert" className="error">
          {rows.error?.message || groups.error?.message || tags.error?.message}
        </p>
      )}
      {editing !== undefined && (
        <section className="card editor-card">
          <h2>{t(editing ? "edit" : "create")}</h2>
          <form onSubmit={handleSubmit(save)} className="monitor-form">
            <label>
              {t("name")}
              <input
                required
                maxLength={kind === "tags" ? 50 : 100}
                {...register("name")}
              />
            </label>
            {kind === "groups" && (
              <label>
                {t("parentGroup")}
                <select {...register("parent_id")}>
                  <option value="">{t("noParent")}</option>
                  {(groups.data || [])
                    .filter(
                      (g) =>
                        !editing ||
                        !isDescendant(g.id, editing.id, groups.data || []),
                    )
                    .map((g) => (
                      <option key={g.id} value={g.id}>
                        {groupLabel(g.id, groups.data || [])}
                      </option>
                    ))}
                </select>
              </label>
            )}
            {kind === "resources" && (
              <>
                <label>
                  {t("address")}
                  <input maxLength={253} {...register("address")} />
                </label>
                <label>
                  {t("deviceKind")}
                  <select {...register("kind")}>
                    {["server", "network", "website", "service", "other"].map(
                      (k) => (
                        <option key={k} value={k}>
                          {t(`device_${k}`)}
                        </option>
                      ),
                    )}
                  </select>
                </label>
                <label>
                  {t("operatingSystem")}
                  <input maxLength={100} {...register("operating_system")} />
                </label>
                <label>
                  {t("environment")}
                  <input maxLength={50} {...register("environment")} />
                </label>
                <label>
                  {t("group")}
                  <select {...register("group_id")}>
                    <option value="">{t("unassigned")}</option>
                    {(groups.data || []).map((g) => (
                      <option key={g.id} value={g.id}>
                        {groupLabel(g.id, groups.data || [])}
                      </option>
                    ))}
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
                  <small>{t("multiSelectHint")}</small>
                </label>
                <label className="full">
                  {t("description")}
                  <textarea maxLength={2000} {...register("description")} />
                </label>
              </>
            )}
            <div className="actions full">
              <Button
                type="button"
                variant="outline"
                onClick={() => setEditing(undefined)}
              >
                {t("cancel")}
              </Button>
              <Button disabled={isSubmitting}>
                {t(isSubmitting ? "loading" : "save")}
              </Button>
            </div>
          </form>
        </section>
      )}
      <section className="toolbar">
        <label>
          {t("search")}
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        {kind === "resources" && (
          <>
            <label>
              {t("group")}
              <select
                value={groupFilter}
                onChange={(e) => setGroupFilter(e.target.value)}
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
              <select
                value={tagFilter}
                onChange={(e) => setTagFilter(e.target.value)}
              >
                <option value="">{t("allTags")}</option>
                {(tags.data || []).map((tag) => (
                  <option key={tag.id} value={tag.id}>
                    {tag.name}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
        <label>
          {t("sort")}
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="name">{t("name")}</option>
            {kind === "resources" && (
              <option value="state">{t("state")}</option>
            )}
          </select>
        </label>
      </section>
      {rows.isPending ? (
        <p role="status">{t("loading")}</p>
      ) : !visible.length ? (
        <div className="empty">
          <h2>{t(rows.data?.length ? "noMatches" : `empty_${kind}`)}</h2>
          <p>{t(`hint_${kind}`)}</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t("name")}</th>
                {kind === "groups" && <th>{t("parentGroup")}</th>}
                {kind === "resources" && (
                  <>
                    <th>{t("address")}</th>
                    <th>{t("group")}</th>
                    <th>{t("tags")}</th>
                    <th>{t("state")}</th>
                    <th>{t("monitors")}</th>
                  </>
                )}
                {canEdit && <th>{t("actions")}</th>}
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr key={row.id}>
                  <td>
                    <strong>{row.name}</strong>
                    {kind === "resources" && (
                      <small className="subline">
                        {t(`device_${(row as Resource).kind}`)} ·{" "}
                        {(row as Resource).operating_system} ·{" "}
                        {(row as Resource).environment}
                      </small>
                    )}
                  </td>
                  {kind === "groups" && (
                    <td>
                      {(row as Group).parent_id
                        ? groupLabel(
                            (row as Group).parent_id!,
                            groups.data || [],
                          )
                        : t("noParent")}
                    </td>
                  )}
                  {kind === "resources" && (
                    <>
                      <td>{(row as Resource).address || t("unassigned")}</td>
                      <td>
                        {(row as Resource).group_id
                          ? groupLabel(
                              (row as Resource).group_id!,
                              groups.data || [],
                            )
                          : t("unassigned")}
                      </td>
                      <td>
                        {(row as Resource).tag_ids.map((id) => (
                          <span className="tag" key={id}>
                            {tags.data?.find((tag) => tag.id === id)?.name}
                          </span>
                        ))}
                      </td>
                      <td>
                        <span
                          className={`state state-${(row as Resource).state}`}
                        >
                          {t((row as Resource).state)}
                        </span>
                        {(row as Resource).paused_count > 0 && (
                          <small className="subline">
                            {t("pausedCount", {
                              count: (row as Resource).paused_count,
                            })}
                          </small>
                        )}
                      </td>
                      <td>
                        <Link to={`/monitors?resource=${row.id}`}>
                          {(row as Resource).monitor_count} ·{" "}
                          {t("viewMonitors")}
                        </Link>
                      </td>
                    </>
                  )}
                  {canEdit && (
                    <td>
                      <Button variant="ghost" onClick={() => open(row)}>
                        {t("edit")}
                      </Button>
                      <Button variant="ghost" onClick={() => setRemoving(row)}>
                        {t("delete")}
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {removing && (
        <div className="modal-backdrop">
          <section
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="remove-title"
            className="card dialog"
          >
            <h2 id="remove-title">{t("confirmDelete")}</h2>
            <p>{removing.name}</p>
            <p>{t(`deleteHint_${kind}`)}</p>
            <div className="actions">
              <Button variant="outline" onClick={() => setRemoving(null)}>
                {t("cancel")}
              </Button>
              <Button disabled={busy} onClick={() => void remove()}>
                {t("delete")}
              </Button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
