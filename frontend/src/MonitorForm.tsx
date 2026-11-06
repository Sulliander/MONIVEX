import { useTranslation } from "react-i18next";
import { useFieldArray, useForm, useWatch } from "react-hook-form";
import { useEffect, useState } from "react";
import { api } from "./api";
import { Button } from "./components/ui/button";
import type { Monitor } from "./Monitoring";
import {
  groupLabel,
  type Group,
  type Resource,
  type Tag,
} from "./infrastructure";

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
  group_id: string;
  resource_id: string;
  tag_ids: string[];
  priority: string;
  credentialAction: string;
  authType: string;
  username: string;
  password: string;
  bearer: string;
  body: string;
  headers: { name: string; value: string }[];
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
export default function MonitorForm({
  initial,
  groups,
  tags,
  resources,
  onCancel,
  onSaved,
}: {
  initial: Monitor | null;
  groups: Group[];
  tags: Tag[];
  resources: Resource[];
  onCancel: () => void;
  onSaved: (result: Monitor & { heartbeat_token?: string }) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [error, setError] = useState("");
  const c = initial?.config || {};
  const {
    register,
    control,
    setValue,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<Fields>({
    defaultValues: {
      name: initial?.name || "",
      kind: initial?.kind || "http",
      host: String(c.host || ""),
      port: Number(c.port || 443),
      url: String(c.url || ""),
      interval: initial?.interval || 60,
      timeout: initial?.timeout || 5,
      failure_threshold: initial?.failure_threshold || 3,
      recovery_threshold: initial?.recovery_threshold || 2,
      domain: String(c.domain || ""),
      record_type: String(c.record_type || "A"),
      expected_answer: String(c.expected_answer || ""),
      contains: String(c.contains || ""),
      method: String(c.method || "GET"),
      expected_codes: ((c.expected_codes as number[]) || [200]).join(","),
      json_path: JSON.stringify(c.json_path || []),
      expected_value: JSON.stringify(c.expected_value ?? null),
      expiry_warning_days: Number(c.expiry_warning_days ?? 30),
      grace_seconds: Number(c.grace_seconds ?? 30),
      follow_redirects: !!c.follow_redirects,
      starttls: !!c.starttls,
      warning_ms: Number(c.warning_ms || 0),
      group_id: String(initial?.group_id || ""),
      resource_id: String(initial?.resource_id || ""),
      tag_ids: initial?.tag_ids?.map(String) || [],
      priority: initial?.priority || "normal",
      credentialAction: "preserve",
      authType: "none",
      username: "",
      password: "",
      bearer: "",
      body: "",
      headers: [],
    },
  });
  const kind = useWatch({ control, name: "kind" });
  const credentialAction = useWatch({ control, name: "credentialAction" });
  const authType = useWatch({ control, name: "authType" });
  const method = useWatch({ control, name: "method" });
  const { fields, append, remove } = useFieldArray({
    control,
    name: "headers",
  });
  useEffect(() => {
    if (!initial)
      setValue("port", kind === "dns" ? 53 : kind === "smtp" ? 25 : 443);
  }, [kind, setValue, initial]);
  const http = ["http", "http_json"].includes(kind);
  async function submit(d: Fields) {
    setError("");
    try {
      let expected: unknown = null;
      let path: unknown = [];
      if (d.kind === "http_json") {
        try {
          expected = JSON.parse(d.expected_value);
          path = d.json_path.trim().startsWith("[")
            ? JSON.parse(d.json_path)
            : (d.json_path || "")
                .split(".")
                .filter(Boolean)
                .map((x) => (/^\d+$/.test(x) ? Number(x) : x));
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
            ...(kind === "http_json"
              ? { json_path: path, expected_value: expected }
              : {}),
          }
        : kind === "heartbeat"
          ? { grace_seconds: d.grace_seconds }
          : {
              host: d.host,
              port: d.port,
              ...(kind === "dns"
                ? {
                    domain: d.domain,
                    record_type: d.record_type,
                    expected_answer: d.expected_answer || "",
                  }
                : {}),
              ...(kind === "tls"
                ? { expiry_warning_days: d.expiry_warning_days }
                : {}),
              ...(kind === "smtp" ? { starttls: !!d.starttls } : {}),
            };
      let credentials: object = {};
      if (d.credentialAction === "replace") {
        const names = d.headers.map((h) => h.name.toLowerCase());
        if (new Set(names).size !== names.length)
          throw new Error(t("duplicateHeaders"));
        credentials = {
          secrets: {
            username: d.authType === "basic" ? d.username : "",
            password: d.authType === "basic" ? d.password : "",
            bearer: d.authType === "bearer" ? d.bearer : "",
            body: d.method === "POST" ? d.body : "",
            headers: Object.fromEntries(
              d.headers.map((h) => [h.name, h.value]),
            ),
          },
        };
      } else if (initial && d.credentialAction === "clear")
        credentials = { clear_credentials: true };
      const result = await api<Monitor & { heartbeat_token?: string }>(
        initial ? `/monitors/${initial.id}` : "/monitors",
        initial ? "PUT" : "POST",
        {
          name: d.name,
          kind: d.kind,
          interval: d.interval,
          timeout: d.timeout,
          failure_threshold: d.failure_threshold,
          recovery_threshold: d.recovery_threshold,
          config,
          group_id: d.group_id ? Number(d.group_id) : null,
          resource_id: d.resource_id ? Number(d.resource_id) : null,
          tag_ids: (d.tag_ids || []).map(Number),
          priority: d.priority,
          ...credentials,
          ...(initial ? { revision: initial.revision } : {}),
        },
      );
      await onSaved(result);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <section className="card editor-card">
      <h2>{t(initial ? "editMonitor" : "addMonitor")}</h2>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <form onSubmit={handleSubmit(submit)}>
        <fieldset className="monitor-form">
          <legend>{t("sectionBasic")}</legend>
          <label>
            {t("monitorName")}
            <input required maxLength={100} {...register("name")} />
          </label>
          <label>
            {t("type")}
            <select disabled={!!initial} {...register("kind")}>
              {kinds.map((x) => (
                <option key={x} value={x}>
                  {t(`kind_${x}`)}
                </option>
              ))}
            </select>
          </label>
          {http ? (
            <label className="full">
              {t("url")}
              <input
                type="url"
                required
                maxLength={2048}
                {...register("url")}
              />
            </label>
          ) : kind !== "heartbeat" ? (
            <>
              <label>
                {t("host")}
                <input required maxLength={253} {...register("host")} />
              </label>
              {kind !== "icmp" && (
                <label>
                  {t("port")}
                  <input
                    type="number"
                    required
                    min={1}
                    max={65535}
                    {...register("port", { valueAsNumber: true })}
                  />
                </label>
              )}
            </>
          ) : null}
          <label>
            {t("priority")}
            <select {...register("priority")}>
              {["low", "normal", "high", "critical"].map((x) => (
                <option key={x} value={x}>
                  {t(`priority_${x}`)}
                </option>
              ))}
            </select>
          </label>
        </fieldset>
        <fieldset className="monitor-form">
          <legend>{t("sectionConditions")}</legend>
          {http && (
            <>
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
                <input maxLength={1024} {...register("contains")} />
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
          )}
          {kind === "http_json" && (
            <>
              <label>
                {t("jsonPath")}
                <input {...register("json_path")} />
                <small>{t("jsonPathHint")}</small>
              </label>
              <label>
                {t("expectedValue")}
                <input required {...register("expected_value")} />
              </label>
            </>
          )}
          {kind === "dns" && (
            <>
              <label>
                {t("domain")}
                <input required maxLength={253} {...register("domain")} />
              </label>
              <label>
                {t("recordType")}
                <select {...register("record_type")}>
                  {["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SOA", "SRV"].map(
                    (x) => (
                      <option key={x}>{x}</option>
                    ),
                  )}
                </select>
              </label>
              <label>
                {t("expectedAnswer")}
                <input maxLength={512} {...register("expected_answer")} />
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
        </fieldset>
        <fieldset className="monitor-form">
          <legend>{t("sectionAdvanced")}</legend>
          {http && (
            <>
              <label className="check-label">
                <input type="checkbox" {...register("follow_redirects")} />
                {t("followRedirects")}
              </label>
              <p className="hint">{t("tlsAlwaysVerified")}</p>
              <label>
                {t("credentials")}
                <select {...register("credentialAction")}>
                  <option value="preserve">
                    {t(
                      initial?.has_credentials
                        ? "preserveSecrets"
                        : "noCredentials",
                    )}
                  </option>
                  <option value="replace">{t("replaceSecrets")}</option>
                  {initial && (
                    <option value="clear">{t("clearSecrets")}</option>
                  )}
                </select>
              </label>
              {credentialAction === "replace" && (
                <div className="full secret-section" data-private="true">
                  <p className="hint">{t("secretReplaceHint")}</p>
                  <label>
                    {t("authType")}
                    <select {...register("authType")}>
                      <option value="none">{t("noAuth")}</option>
                      <option value="basic">{t("basicAuth")}</option>
                      <option value="bearer">{t("bearerAuth")}</option>
                    </select>
                  </label>
                  {authType === "basic" && (
                    <>
                      <label>
                        {t("authUsername")}
                        <input
                          autoComplete="off"
                          maxLength={4096}
                          {...register("username")}
                        />
                      </label>
                      <label>
                        {t("authPassword")}
                        <input
                          type="password"
                          autoComplete="new-password"
                          maxLength={4096}
                          {...register("password")}
                        />
                      </label>
                    </>
                  )}
                  {authType === "bearer" && (
                    <label>
                      {t("bearerToken")}
                      <input
                        type="password"
                        autoComplete="off"
                        maxLength={4096}
                        {...register("bearer")}
                      />
                    </label>
                  )}
                  {method === "POST" && (
                    <label>
                      {t("requestBody")}
                      <textarea maxLength={65536} {...register("body")} />
                    </label>
                  )}
                  <h3>{t("headers")}</h3>
                  {fields.map((field, index) => (
                    <div className="header-row" key={field.id}>
                      <label>
                        {t("headerName")}
                        <input
                          required
                          maxLength={64}
                          {...register(`headers.${index}.name`)}
                        />
                      </label>
                      <label>
                        {t("headerValue")}
                        <input
                          required
                          type="password"
                          maxLength={4096}
                          {...register(`headers.${index}.value`)}
                        />
                      </label>
                      <Button
                        variant="ghost"
                        type="button"
                        onClick={() => remove(index)}
                      >
                        {t("removeHeader")}
                      </Button>
                    </div>
                  ))}
                  <Button
                    type="button"
                    variant="outline"
                    disabled={fields.length >= 20}
                    onClick={() => append({ name: "", value: "" })}
                  >
                    {t("addHeader")}
                  </Button>
                </div>
              )}
            </>
          )}
          {kind === "smtp" && (
            <label className="check-label">
              <input type="checkbox" {...register("starttls")} />
              {t("starttls")}
            </label>
          )}
          <p className="hint full">{t("targetPolicyHint")}</p>
        </fieldset>
        <fieldset className="monitor-form">
          <legend>{t("sectionLinks")}</legend>
          <label>
            {t("group")}
            <select {...register("group_id")}>
              <option value="">{t("unassigned")}</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {groupLabel(g.id, groups)}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("resource")}
            <select {...register("resource_id")}>
              <option value="">{t("unassigned")}</option>
              {resources.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("tags")}
            <select multiple {...register("tag_ids")}>
              {tags.map((tag) => (
                <option key={tag.id} value={tag.id}>
                  {tag.name}
                </option>
              ))}
            </select>
            <small>{t("multiSelectHint")}</small>
          </label>
          <p className="hint">{t("notificationsFuture")}</p>
        </fieldset>
        <div className="actions">
          <Button type="button" variant="outline" onClick={onCancel}>
            {t("cancel")}
          </Button>
          <Button disabled={isSubmitting}>
            {t(isSubmitting ? "loading" : "saveMonitor")}
          </Button>
        </div>
      </form>
    </section>
  );
}
