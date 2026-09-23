import { useEffect, useState } from 'react';
import { apiClient } from '../../api/client';

export function CaptionRelayTab() {
  const [data, setData] = useState<Awaited<ReturnType<typeof apiClient.getCaptionRelays>> | null>(null);
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function refresh() {
    try { setData(await apiClient.getCaptionRelays()); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not load devices'); }
  }
  useEffect(() => { void refresh(); const timer = setInterval(refresh, 20000); return () => clearInterval(timer); }, []);
  useEffect(() => { if (!code) return; const timer = setTimeout(() => setCode(''), 600000); return () => clearTimeout(timer); }, [code]);
  async function create() {
    setBusy(true); setError(''); setCode('');
    try { setCode((await apiClient.createCaptionRelay(name.trim())).pairing_code); setName(''); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not pair device'); }
    finally { setBusy(false); }
  }
  async function revoke(id: string) {
    if (!window.confirm('Revoke this device? It will stop receiving and uploading captions.')) return;
    setBusy(true); setError('');
    try { await apiClient.revokeCaptionRelay(id); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not revoke device'); }
    finally { setBusy(false); }
  }
  return <section dir="ltr" style={{ padding: 20 }}>
    <h2>Xaana Caption Relay</h2>
    <p>Xaana tries the server first. Paired devices fetch captions when that attempt fails.</p>
    <p>Pair a trusted device once. It can only receive a video job and return its captions.</p>
    {error && <p role="alert">{error}</p>}
    <form onSubmit={e => { e.preventDefault(); void create(); }} style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
      <input aria-label="Device name" value={name} maxLength={80} onChange={e => setName(e.target.value)} placeholder="Living room Raspberry Pi" />
      <button type="submit" disabled={busy || !name.trim()}>Create pairing code</button>
    </form>
    {code && <div style={{ marginBlock: 16 }}>
      <p>On the device, run <code>xaana-caption-relay pair</code> and paste this code. It is valid for 10 minutes and can be used once.</p>
      <code style={{ overflowWrap: 'anywhere', userSelect: 'all' }}>{code}</code>
      <button onClick={() => setCode('')} style={{ marginInlineStart: 12 }}>Hide</button>
    </div>}
    <h3>Devices</h3>
    {data?.devices.length === 0 && <p>No devices paired yet.</p>}
    {data?.devices.map(d => <article key={d.id} style={{ paddingBlock: 12, borderBottom: '1px solid var(--app-border)' }}>
      <strong>{d.name}</strong> — {d.revoked_at ? 'Revoked' : d.activated_at ? 'Paired' : d.pairing_expires_at && new Date(d.pairing_expires_at) < new Date() ? 'Pairing expired' : 'Awaiting pairing'}
      <p>Last contact: {d.last_seen_at ? new Date(d.last_seen_at).toLocaleString() : 'Never'}</p>
      {!d.revoked_at && <button disabled={busy} onClick={() => void revoke(d.id)}>Revoke</button>}
    </article>)}
    <h3>Queue</h3>
    {data?.queue.map(q => <p key={q.fetch_stage + q.status}>{q.fetch_stage} · {q.status}: {q.count}</p>)}
  </section>;
}
