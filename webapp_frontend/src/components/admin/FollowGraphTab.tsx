/**
 * FollowGraphTab — admin-only interactive follow-graph visualisation.
 *
 * Uses React Flow (@xyflow/react) for pan/zoom/drag.
 * Nodes are laid out in a weighted circular arrangement (high-degree nodes
 * gravitate towards the centre ring).  No extra layout library required.
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeTypes,
  MarkerType,
  BackgroundVariant,
  useReactFlow,
  ReactFlowProvider,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { apiClient, ApiError } from '../../api/client';
import type { FollowGraphData, FollowGraphNode } from '../../types';

// ─── colour palette (consistent regardless of system theme) ──────────────────
const PALETTE = [
  '#6366f1', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b',
  '#ef4444', '#ec4899', '#3b82f6', '#84cc16', '#f97316',
];
function colorForId(id: string) {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

function initials(node: FollowGraphNode): string {
  const fn = node.first_name?.trim();
  const un = node.username?.trim();
  if (fn) return fn.slice(0, 2).toUpperCase();
  if (un) return un.slice(0, 2).toUpperCase();
  return node.id.slice(0, 2).toUpperCase();
}

function displayName(node: FollowGraphNode): string {
  if (node.first_name) return node.first_name;
  if (node.username) return `@${node.username}`;
  return node.id.slice(0, 8);
}

// ─── Custom node ─────────────────────────────────────────────────────────────
interface UserNodeData extends Record<string, unknown> {
  label: string;
  initials: string;
  color: string;
  highlighted: boolean;
  selected: boolean;
}

// Invisible handle style — edges need handles to connect but we don't want
// the default square connector dots to show on the avatar circle.
const HANDLE_STYLE: React.CSSProperties = {
  width: 1,
  height: 1,
  background: 'transparent',
  border: 'none',
  minWidth: 0,
  minHeight: 0,
};

function UserNodeComponent({ data }: { data: UserNodeData }) {
  const ring = data.highlighted
    ? '0 0 0 3px #facc15, 0 0 12px 4px rgba(250,204,21,0.6)'
    : data.selected
      ? '0 0 0 2px #6366f1'
      : 'none';

  return (
    <div
      title={data.label}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 4,
        cursor: 'pointer',
        userSelect: 'none',
        position: 'relative',
      }}
    >
      {/* Target handle — edges arrive here (this node is being followed) */}
      <Handle type="target" position={Position.Top} style={HANDLE_STYLE} />

      <div
        style={{
          width: 40,
          height: 40,
          borderRadius: '50%',
          background: data.color,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 13,
          fontWeight: 700,
          color: '#fff',
          boxShadow: ring,
          transition: 'box-shadow 0.2s',
          position: 'relative',
        }}
      >
        {data.initials}
      </div>
      <span
        style={{
          fontSize: 10,
          maxWidth: 72,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          color: 'var(--color-text-primary, #e2e8f0)',
          textAlign: 'center',
        }}
      >
        {data.label}
      </span>

      {/* Source handle — edges leave here (this node follows someone) */}
      <Handle type="source" position={Position.Bottom} style={HANDLE_STYLE} />
    </div>
  );
}

const nodeTypes: NodeTypes = {
  userNode: UserNodeComponent as unknown as NodeTypes['userNode'],
};

// ─── Radial layout ────────────────────────────────────────────────────────────
function computeLayout(
  graphNodes: FollowGraphNode[],
  highlightedId: string | null,
  selectedId: string | null,
): Node[] {
  if (graphNodes.length === 0) return [];

  const n = graphNodes.length;

  // Sort by degree descending — high-degree nodes to inner rings
  const sorted = [...graphNodes].sort(
    (a, b) => (b.follower_count + b.following_count) - (a.follower_count + a.following_count),
  );

  // Three rings: innermost (top ~10%), middle (~35%), outer (rest)
  const inner = Math.max(1, Math.ceil(n * 0.10));
  const mid   = Math.max(1, Math.ceil(n * 0.35));

  const R_INNER  = 160;
  const R_MIDDLE = 340;
  const R_OUTER  = 560;

  const placed: Node[] = [];

  sorted.forEach((gn, idx) => {
    let ring: number;
    let ringSize: number;
    let offset: number;

    if (idx < inner) {
      ring = R_INNER;
      ringSize = inner;
      offset = idx;
    } else if (idx < inner + mid) {
      ring = R_MIDDLE;
      ringSize = mid;
      offset = idx - inner;
    } else {
      ring = R_OUTER;
      ringSize = n - inner - mid;
      offset = idx - inner - mid;
    }

    const angle = (2 * Math.PI * offset) / ringSize;
    const x = ring * Math.cos(angle);
    const y = ring * Math.sin(angle);

    placed.push({
      id: gn.id,
      type: 'userNode',
      position: { x, y },
      data: {
        label: displayName(gn),
        initials: initials(gn),
        color: colorForId(gn.id),
        highlighted: gn.id === highlightedId,
        selected: gn.id === selectedId,
      },
    });
  });

  return placed;
}

// ─── Inner graph (needs ReactFlowProvider context for fitView / viewport) ──────
interface InnerGraphProps {
  graphData: FollowGraphData;
  searchQuery: string;
  selectedNodeId: string | null;
  onSelectNode: (id: string | null) => void;
}

function InnerGraph({ graphData, searchQuery, selectedNodeId, onSelectNode }: InnerGraphProps) {
  const { fitView, setCenter } = useReactFlow();
  const fittedRef = useRef(false);

  // Compute highlighted node id from search
  const highlightedId = useMemo(() => {
    if (!searchQuery.trim()) return null;
    const q = searchQuery.toLowerCase();
    const match = graphData.nodes.find(
      (n) =>
        n.first_name?.toLowerCase().includes(q) ||
        n.username?.toLowerCase().includes(q) ||
        n.id.toLowerCase().includes(q),
    );
    return match?.id ?? null;
  }, [searchQuery, graphData.nodes]);

  // Build React Flow nodes
  const rfNodes = useMemo<Node[]>(
    () => computeLayout(graphData.nodes, highlightedId, selectedNodeId),
    [graphData.nodes, highlightedId, selectedNodeId],
  );

  // Build React Flow edges
  const rfEdges = useMemo<Edge[]>(
    () =>
      graphData.edges.map((e, i) => ({
        id: `e-${i}`,
        source: e.source,
        target: e.target,
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: '#6366f1' },
        style: { stroke: '#6366f180', strokeWidth: 1.2 },
        animated: false,
      })),
    [graphData.edges],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(rfNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(rfEdges);

  // Sync nodes whenever highlighted/selected state or graph data changes
  useEffect(() => { setNodes(rfNodes); }, [rfNodes, setNodes]);
  // Sync edges whenever graph data changes
  useEffect(() => { setEdges(rfEdges); }, [rfEdges, setEdges]);

  // Fit on first load
  useEffect(() => {
    if (!fittedRef.current && nodes.length > 0) {
      setTimeout(() => {
        fitView({ padding: 0.15, duration: 600 });
        fittedRef.current = true;
      }, 100);
    }
  }, [nodes.length, fitView]);

  // Pan to highlighted node when search changes
  useEffect(() => {
    if (!highlightedId) return;
    const node = nodes.find((n) => n.id === highlightedId);
    if (node) {
      setCenter(node.position.x, node.position.y, { zoom: 1.6, duration: 600 });
    }
  }, [highlightedId, nodes, setCenter]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onSelectNode(node.id === selectedNodeId ? null : node.id);
    },
    [selectedNodeId, onSelectNode],
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={handleNodeClick}
      onPaneClick={() => onSelectNode(null)}
      fitView
      minZoom={0.05}
      maxZoom={4}
      style={{ background: 'var(--color-bg-secondary, #1e2433)' }}
    >
      <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#334155" />
      <Controls showInteractive={false} style={{ bottom: 60, left: 12, top: 'auto' }} />
      <MiniMap
        nodeColor={(n) => (n.data as UserNodeData).color as string}
        style={{ background: '#0f172a', border: '1px solid #334155' }}
        maskColor="rgba(0,0,0,0.5)"
      />
    </ReactFlow>
  );
}

// ─── Sidebar detail panel ──────────────────────────────────────────────────────
function NodeDetailPanel({
  node,
  onClose,
}: {
  node: FollowGraphNode;
  onClose: () => void;
}) {
  return (
    <div
      style={{
        position: 'absolute',
        top: 12,
        right: 12,
        width: 220,
        background: 'var(--color-bg-primary, #0f172a)',
        border: '1px solid var(--color-border, #334155)',
        borderRadius: 12,
        padding: '16px',
        zIndex: 10,
        boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <div
          style={{
            width: 44,
            height: 44,
            borderRadius: '50%',
            background: colorForId(node.id),
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 16,
            fontWeight: 700,
            color: '#fff',
            flexShrink: 0,
          }}
        >
          {initials(node)}
        </div>
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              fontWeight: 600,
              fontSize: 14,
              color: 'var(--color-text-primary, #e2e8f0)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {node.first_name || node.username || node.id}
          </div>
          {node.username && (
            <div style={{ fontSize: 12, color: 'var(--color-text-muted, #94a3b8)' }}>
              @{node.username}
            </div>
          )}
        </div>
        <button
          onClick={onClose}
          style={{
            marginLeft: 'auto',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--color-text-muted, #94a3b8)',
            fontSize: 16,
            lineHeight: 1,
            padding: 2,
            flexShrink: 0,
          }}
        >
          ×
        </button>
      </div>
      <div style={{ fontSize: 12, color: 'var(--color-text-muted, #94a3b8)', marginBottom: 6 }}>
        ID: <code style={{ fontSize: 11 }}>{node.id}</code>
      </div>
      <div
        style={{
          display: 'flex',
          gap: 8,
          marginTop: 8,
        }}
      >
        <StatPill label="Followers" value={node.follower_count} />
        <StatPill label="Following" value={node.following_count} />
      </div>
    </div>
  );
}

function StatPill({ label, value }: { label: string; value: number }) {
  return (
    <div
      style={{
        flex: 1,
        background: 'var(--color-bg-secondary, #1e2433)',
        border: '1px solid var(--color-border, #334155)',
        borderRadius: 8,
        padding: '8px 6px',
        textAlign: 'center',
      }}
    >
      <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--color-text-primary, #e2e8f0)' }}>
        {value}
      </div>
      <div style={{ fontSize: 11, color: 'var(--color-text-muted, #94a3b8)', marginTop: 2 }}>
        {label}
      </div>
    </div>
  );
}

// ─── Public tab component ──────────────────────────────────────────────────────
export function FollowGraphTab() {
  const [graphData, setGraphData] = useState<FollowGraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetch = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await apiClient.getFollowGraph(2000);
        if (!cancelled) setGraphData(data);
      } catch (err) {
        if (!cancelled) {
          if (err instanceof ApiError) {
            setError(err.message || 'Failed to load follow graph');
          } else {
            setError('Failed to load follow graph');
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetch();
    return () => { cancelled = true; };
  }, []);

  const selectedNode = useMemo(
    () => (selectedNodeId ? graphData?.nodes.find((n) => n.id === selectedNodeId) ?? null : null),
    [selectedNodeId, graphData],
  );

  if (loading) {
    return (
      <div className="admin-tab-content" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 320 }}>
        <div className="loading-spinner" />
        <span style={{ marginLeft: 12, color: 'var(--color-text-muted, #94a3b8)' }}>Loading follow graph…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="admin-tab-content" style={{ padding: 24 }}>
        <div className="admin-panel-error-banner" style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <span>⚠ {error}</span>
          <button className="admin-btn admin-btn-sm" onClick={() => { setError(null); setLoading(true); }}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!graphData || graphData.total_nodes === 0) {
    return (
      <div className="admin-tab-content" style={{ padding: 24, textAlign: 'center', color: 'var(--color-text-muted, #94a3b8)' }}>
        <p style={{ fontSize: 16 }}>No follow relationships found.</p>
        <p style={{ fontSize: 13 }}>Follow some users first, then come back here.</p>
      </div>
    );
  }

  return (
    <div className="admin-tab-content" style={{ padding: 0 }}>
      {/* Toolbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '10px 16px',
          borderBottom: '1px solid var(--color-border, #334155)',
          background: 'var(--color-bg-primary, #0f172a)',
          flexWrap: 'wrap',
        }}
      >
        <input
          type="search"
          placeholder="Search user…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            background: 'var(--color-bg-secondary, #1e2433)',
            border: '1px solid var(--color-border, #334155)',
            borderRadius: 8,
            padding: '6px 12px',
            color: 'var(--color-text-primary, #e2e8f0)',
            fontSize: 13,
            width: 200,
            outline: 'none',
          }}
        />
        <span style={{ fontSize: 12, color: 'var(--color-text-muted, #94a3b8)', display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <svg width="28" height="10" viewBox="0 0 28 10">
              <line x1="2" y1="5" x2="22" y2="5" stroke="#6366f1" strokeWidth="1.5"/>
              <polygon points="22,2 28,5 22,8" fill="#6366f1"/>
            </svg>
            <span>A follows B</span>
          </span>
          <span style={{ color: 'var(--color-border, #334155)' }}>·</span>
          <span>{graphData.total_nodes} users</span>
          <span style={{ color: 'var(--color-border, #334155)' }}>·</span>
          <span>{graphData.total_edges} edges</span>
        </span>
      </div>

      {/* Graph canvas */}
      <div style={{ height: 'calc(100vh - 230px)', minHeight: 420, position: 'relative' }}>
        <ReactFlowProvider>
          <InnerGraph
            graphData={graphData}
            searchQuery={searchQuery}
            selectedNodeId={selectedNodeId}
            onSelectNode={setSelectedNodeId}
          />
          {selectedNode && (
            <NodeDetailPanel node={selectedNode} onClose={() => setSelectedNodeId(null)} />
          )}
        </ReactFlowProvider>
      </div>
    </div>
  );
}
