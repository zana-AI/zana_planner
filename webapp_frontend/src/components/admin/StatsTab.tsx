import { useEffect, useMemo, useState } from 'react';
import { apiClient, type AdminLLMUsageResponse } from '../../api/client';

interface StatsTabProps {
  stats: { total_users: number; active_users: number; total_promises: number } | null;
  loadingStats: boolean;
  statsError: string;
  onRetry: () => void;
}

const WINDOW_OPTIONS: Array<{ label: string; hours: number }> = [
  { label: '1h', hours: 1 },
  { label: '24h', hours: 24 },
  { label: '7d', hours: 24 * 7 },
  { label: '30d', hours: 24 * 30 },
];

function formatTokens(n: number): string {
  if (!n) return '0';
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(2)}M`;
}

function formatCost(usd: number | null): string {
  if (usd == null) return '—';
  if (usd < 0.01) return `<$0.01`;
  return `$${usd.toFixed(2)}`;
}

function shortModel(name: string): string {
  // Strip leading "openai/" / "moonshotai/" namespace for compactness.
  const idx = name.indexOf('/');
  return idx > -1 ? name.slice(idx + 1) : name;
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
        <h3>LLM Usage</h3>
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
              Open Langfuse →
            </a>
          )}
        </div>
      </div>

      {loading && <div className="admin-llm-usage-loading">Loading…</div>}

      {!loading && error && (
        <div className="admin-llm-usage-error">{error}</div>
      )}

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
            <div className="admin-llm-usage-empty">
              No LLM calls recorded in this window yet.
            </div>
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
                      <td>{row.role ?? '—'}</td>
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

export function StatsTab({ stats, loadingStats, statsError, onRetry }: StatsTabProps) {
  if (loadingStats) {
    return (
      <div className="admin-panel-stats">
        <div className="admin-loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading metrics...</div>
        </div>
      </div>
    );
  }

  if (statsError) {
    return (
      <div className="admin-panel-stats">
        <div className="admin-no-stats">
          <p>{statsError}</p>
          <button className="admin-select-all-btn" onClick={onRetry}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="admin-panel-stats">
        <div className="admin-no-stats">
          <p>No metrics available</p>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-panel-stats">
      <div className="admin-metrics-grid">
        <div className="admin-metric-card">
          <div className="admin-metric-label">Total Users</div>
          <div className="admin-metric-value">{stats.total_users.toLocaleString()}</div>
        </div>
        <div className="admin-metric-card">
          <div className="admin-metric-label">Active Users (7d)</div>
          <div className="admin-metric-value">{stats.active_users.toLocaleString()}</div>
        </div>
        <div className="admin-metric-card">
          <div className="admin-metric-label">Users With Promises</div>
          <div className="admin-metric-value">{stats.total_promises.toLocaleString()}</div>
        </div>
      </div>

      <LLMUsageSection />
    </div>
  );
}
