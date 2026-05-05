import { useEffect, useMemo, useState } from 'react';
import {
  apiClient,
  type AdminLLMBackendTestResponse,
  type AdminLLMBackendsResponse,
  type AdminLLMRateLimitInfo,
  type AdminLLMUsageResponse,
} from '../../api/client';

const WINDOW_OPTIONS: Array<{ label: string; hours: number }> = [
  { label: '1h', hours: 1 },
  { label: '24h', hours: 24 },
  { label: '7d', hours: 24 * 7 },
  { label: '30d', hours: 24 * 30 },
];

const LLM_ROLES = ['router', 'planner', 'responder'] as const;
type LLMRole = (typeof LLM_ROLES)[number];

function formatTokens(n: number): string {
  if (!n) return '0';
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(2)}M`;
}

function formatCost(usd: number | null): string {
  if (usd == null) return '-';
  if (usd < 0.01) return '<$0.01';
  return `$${usd.toFixed(2)}`;
}

function shortModel(name: string): string {
  const idx = name.indexOf('/');
  return idx > -1 ? name.slice(idx + 1) : name;
}

function formatLimitValue(value: number | null | undefined): string {
  return value == null ? '-' : value.toLocaleString();
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function rateLimitLabel(rateLimit?: AdminLLMRateLimitInfo): string {
  if (!rateLimit) return 'Unknown';
  if (rateLimit.status === 'blocked') return 'Limited';
  if (rateLimit.status === 'observed') return 'Observed';
  return Object.keys(rateLimit.announced || {}).length ? 'Published' : 'Unknown';
}

function resultSummary(result: AdminLLMBackendTestResponse): string {
  if (result.parallel_count && result.parallel_count > 1) {
    return `${result.successes ?? 0}/${result.parallel_count} OK in ${result.latency_ms ?? '?'} ms`;
  }
  if (result.status === 'ok') {
    return `OK in ${result.latency_ms ?? '?'} ms: ${result.response_preview || 'No preview'}`;
  }
  return result.error || 'Smoke test failed';
}

function RateLimitDetails({ rateLimit }: { rateLimit?: AdminLLMRateLimitInfo }) {
  const observed = rateLimit?.observed;
  const announced = rateLimit?.announced || {};
  const hasPublished = Object.keys(announced).length > 0;

  return (
    <div className="admin-llm-rate-details">
      <span className={`admin-llm-rate-status ${rateLimit?.status || 'unknown'}`}>
        {rateLimitLabel(rateLimit)}
      </span>
      {observed?.remaining_requests != null || observed?.limit_requests != null ? (
        <span>
          Req {formatLimitValue(observed.remaining_requests)} / {formatLimitValue(observed.limit_requests)}
        </span>
      ) : null}
      {observed?.remaining_tokens != null || observed?.limit_tokens != null ? (
        <span>
          Tok {formatLimitValue(observed.remaining_tokens)} / {formatLimitValue(observed.limit_tokens)}
        </span>
      ) : null}
      {observed?.blocked_until ? <span>Blocked until {formatDateTime(observed.blocked_until)}</span> : null}
      {!observed?.blocked_until && observed?.reset_requests_at ? (
        <span>Req reset {formatDateTime(observed.reset_requests_at)}</span>
      ) : null}
      {!observed?.blocked_until && observed?.reset_tokens_at ? (
        <span>Tok reset {formatDateTime(observed.reset_tokens_at)}</span>
      ) : null}
      {observed?.last_error ? <span>Last error: {observed.last_error}</span> : null}
      {hasPublished ? (
        <span>
          Published{' '}
          {Object.entries(announced)
            .map(([key, value]) => `${key}: ${formatLimitValue(value)}`)
            .join(', ')}
        </span>
      ) : null}
    </div>
  );
}

function LLMUsageSection() {
  const [hours, setHours] = useState<number>(24);
  const [data, setData] = useState<AdminLLMUsageResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    apiClient
      .getAdminLLMUsage(hours)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || 'Failed to load LLM usage');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [hours]);

  const totals = data?.totals;
  const rows = useMemo(() => data?.per_model ?? [], [data]);

  return (
    <div className="admin-llm-usage">
      <div className="admin-llm-usage-header">
        <h3>Usage</h3>
        <div className="admin-llm-usage-windows">
          {WINDOW_OPTIONS.map((opt) => (
            <button
              key={opt.hours}
              className={`admin-llm-usage-window-btn${hours === opt.hours ? ' active' : ''}`}
              onClick={() => setHours(opt.hours)}
              type="button"
            >
              {opt.label}
            </button>
          ))}
          {data?.langfuse_url && (
            <a
              href={data.langfuse_url}
              target="_blank"
              rel="noreferrer noopener"
              className="admin-llm-usage-langfuse-link"
              title="Open Langfuse dashboard for trace exploration"
            >
              Open Langfuse
            </a>
          )}
        </div>
      </div>

      {loading && <div className="admin-llm-usage-loading">Loading...</div>}
      {!loading && error && <div className="admin-llm-usage-error">{error}</div>}

      {!loading && !error && totals && (
        <>
          <div className="admin-metrics-grid">
            <div className="admin-metric-card">
              <div className="admin-metric-label">Calls</div>
              <div className="admin-metric-value">{totals.calls.toLocaleString()}</div>
            </div>
            <div className="admin-metric-card">
              <div className="admin-metric-label">Input tokens</div>
              <div className="admin-metric-value">{formatTokens(totals.input_tokens)}</div>
            </div>
            <div className="admin-metric-card">
              <div className="admin-metric-label">Output tokens</div>
              <div className="admin-metric-value">{formatTokens(totals.output_tokens)}</div>
            </div>
            <div className="admin-metric-card">
              <div className="admin-metric-label">Est. cost</div>
              <div className="admin-metric-value">{formatCost(totals.estimated_cost_usd)}</div>
            </div>
          </div>

          {rows.length === 0 ? (
            <div className="admin-llm-usage-empty">No LLM calls recorded in this window yet.</div>
          ) : (
            <div className="admin-llm-usage-table-wrap">
              <table className="admin-llm-usage-table">
                <thead>
                  <tr>
                    <th>Provider</th>
                    <th>Model</th>
                    <th>Role</th>
                    <th style={{ textAlign: 'right' }}>Calls</th>
                    <th style={{ textAlign: 'right' }}>In tokens</th>
                    <th style={{ textAlign: 'right' }}>Out tokens</th>
                    <th style={{ textAlign: 'right' }}>Avg latency</th>
                    <th style={{ textAlign: 'right' }}>Errors</th>
                    <th style={{ textAlign: 'right' }}>Est. cost</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, idx) => (
                    <tr key={`${row.provider}|${row.model_name}|${row.role ?? ''}|${idx}`}>
                      <td>{row.provider}</td>
                      <td title={row.model_name}>{shortModel(row.model_name)}</td>
                      <td>{row.role ?? '-'}</td>
                      <td style={{ textAlign: 'right' }}>{row.calls.toLocaleString()}</td>
                      <td style={{ textAlign: 'right' }}>{formatTokens(row.input_tokens)}</td>
                      <td style={{ textAlign: 'right' }}>{formatTokens(row.output_tokens)}</td>
                      <td style={{ textAlign: 'right' }}>{row.avg_latency_ms} ms</td>
                      <td style={{ textAlign: 'right' }}>{row.errors}</td>
                      <td style={{ textAlign: 'right' }}>{formatCost(row.estimated_cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function LLMBackendsSection() {
  const [data, setData] = useState<AdminLLMBackendsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [testingKey, setTestingKey] = useState<string>('');
  const [testResults, setTestResults] = useState<Record<string, AdminLLMBackendTestResponse>>({});
  const [parallelCounts, setParallelCounts] = useState<Record<string, number>>({});

  const loadBackends = () => {
    setLoading(true);
    setError('');
    apiClient
      .getAdminLLMBackends()
      .then(setData)
      .catch((err) => setError(err?.message || 'Failed to load LLM backends'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadBackends();
  }, []);

  const testBackend = async (provider: string, role: LLMRole, model: string, parallelCount = 1) => {
    const key = `${provider}:${role}`;
    setTestingKey(key);
    setTestResults((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    try {
      const result = await apiClient.testAdminLLMBackend({
        provider,
        model,
        role,
        parallel_count: Math.max(1, Math.min(50, Math.floor(parallelCount || 1))),
      });
      setTestResults((prev) => ({ ...prev, [key]: result }));
      const rateLimit = result.rate_limit;
      if (rateLimit) {
        setData((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            rate_limits: {
              ...prev.rate_limits,
              [provider]: {
                ...(prev.rate_limits[provider] || {}),
                [model]: rateLimit,
              },
            },
          };
        });
      }
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [key]: {
          status: 'error',
          provider,
          model,
          role,
          response_preview: '',
          error: err instanceof Error ? err.message : 'Smoke test failed',
        },
      }));
    } finally {
      setTestingKey('');
    }
  };

  return (
    <div className="admin-llm-backends">
      <div className="admin-llm-usage-header">
        <div>
          <h3>Backends & Limits</h3>
          <p className="admin-llm-backends-note">
            Read-only smoke tests check credentials, model access, latency, and any observed rate-limit state.
          </p>
        </div>
        <button type="button" className="admin-llm-backends-refresh" onClick={loadBackends} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {loading && <div className="admin-llm-usage-loading">Loading backends...</div>}
      {!loading && error && <div className="admin-llm-usage-error">{error}</div>}

      {!loading && data && (
        <>
          <div className="admin-llm-backends-summary">
            <span>Active: {data.active_provider || 'not configured'}</span>
            <span>Requested: {data.requested_provider || 'default'}</span>
            <span>
              Fallback:{' '}
              {data.fallback.enabled
                ? `${data.fallback.provider || 'configured'} responder ${data.fallback.models.responder || 'default'}`
                : 'disabled'}
            </span>
          </div>

          {data.config_error ? <div className="admin-llm-usage-error">{data.config_error}</div> : null}

          <div className="admin-llm-backends-grid">
            {data.available_providers.map((provider) => {
              const hasCredentials = !!data.credentials[provider];
              const roleModels = data.provider_models[provider] || {};
              return (
                <article key={provider} className="admin-llm-backend-card">
                  <div className="admin-llm-backend-card-header">
                    <h4>{provider}</h4>
                    <span className={`admin-llm-backend-credential ${hasCredentials ? 'ready' : 'missing'}`}>
                      {hasCredentials ? 'Credentials available' : 'Credentials missing'}
                    </span>
                  </div>

                  <div className="admin-llm-backend-roles">
                    {LLM_ROLES.map((role) => {
                      const model = roleModels[role] || data.role_models[role] || '';
                      const knownModels = data.model_catalog[provider]?.known || [];
                      const supported = !!model && knownModels.includes(model);
                      const key = `${provider}:${role}`;
                      const result = testResults[key];
                      const disabled = !hasCredentials || !supported || testingKey === key;
                      const parallelCount = parallelCounts[key] ?? 5;
                      const rateLimit = model ? data.rate_limits[provider]?.[model] : undefined;
                      return (
                        <div key={role} className="admin-llm-backend-role">
                          <div>
                            <div className="admin-llm-backend-role-name">{role}</div>
                            <div className="admin-llm-backend-model" title={model || 'No model configured'}>
                              {model ? shortModel(model) : 'No model configured'}
                            </div>
                            {!supported && model ? (
                              <div className="admin-llm-backend-warning">Unsupported by local model catalog</div>
                            ) : null}
                            <RateLimitDetails rateLimit={rateLimit} />
                          </div>
                          <div className="admin-llm-backend-actions">
                            <button
                              type="button"
                              className="admin-select-all-btn admin-llm-backend-test-btn"
                              disabled={disabled}
                              onClick={() => testBackend(provider, role, model)}
                              title={
                                !hasCredentials
                                  ? 'Credentials are not configured'
                                  : !supported
                                    ? 'Model is not supported by the local catalog'
                                    : 'Run one read-only smoke test'
                              }
                            >
                              {testingKey === key ? 'Testing...' : 'Test'}
                            </button>
                            <div className="admin-llm-parallel-control">
                              <input
                                type="number"
                                min={1}
                                max={50}
                                value={parallelCount}
                                disabled={disabled}
                                onChange={(event) => {
                                  const value = Number(event.target.value);
                                  setParallelCounts((prev) => ({
                                    ...prev,
                                    [key]: Number.isFinite(value)
                                      ? Math.max(1, Math.min(50, Math.floor(value)))
                                      : 1,
                                  }));
                                }}
                                title="Parallel request count"
                              />
                              <button
                                type="button"
                                className="admin-select-all-btn admin-llm-backend-test-btn"
                                disabled={disabled}
                                onClick={() => testBackend(provider, role, model, parallelCount)}
                                title="Run N read-only smoke tests in parallel"
                              >
                                Run N
                              </button>
                            </div>
                          </div>
                          {result ? (
                            <div className={`admin-llm-backend-result ${result.status}`}>
                              <div>{resultSummary(result)}</div>
                              {result.error ? <div>{result.error}</div> : null}
                              {result.attempts?.length ? (
                                <div className="admin-llm-attempts">
                                  {result.attempts.map((attempt) => (
                                    <span
                                      key={attempt.attempt}
                                      className={`admin-llm-attempt ${attempt.status}`}
                                      title={attempt.error || attempt.response_preview || ''}
                                    >
                                      #{attempt.attempt}: {attempt.status === 'ok' ? `${attempt.latency_ms} ms` : attempt.error || 'error'}
                                    </span>
                                  ))}
                                </div>
                              ) : null}
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                </article>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

export function LLMTab() {
  return (
    <div className="admin-panel-stats admin-llm-tab">
      <LLMUsageSection />
      <LLMBackendsSection />
    </div>
  );
}
