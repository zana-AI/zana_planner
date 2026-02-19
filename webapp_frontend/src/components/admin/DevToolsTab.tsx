import { BarChart3, Database, ExternalLink, Github, Settings2 } from 'lucide-react';
import type { ReactNode } from 'react';

interface DevToolLinkProps {
  name: string;
  description: string;
  url: string;
  icon: ReactNode;
}

function DevToolLink({ name, description, url, icon }: DevToolLinkProps) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      style={{
        display: 'block',
        background: 'rgba(15, 23, 48, 0.6)',
        border: '1px solid rgba(232, 238, 252, 0.1)',
        borderRadius: '8px',
        padding: '1.5rem',
        textDecoration: 'none',
        color: 'inherit',
        transition: 'all 0.2s',
        cursor: 'pointer',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = 'rgba(15, 23, 48, 0.8)';
        e.currentTarget.style.borderColor = 'rgba(91, 163, 245, 0.4)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = 'rgba(15, 23, 48, 0.6)';
        e.currentTarget.style.borderColor = 'rgba(232, 238, 252, 0.1)';
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <div style={{ color: '#9ec7ff' }}>{icon}</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '1.1rem', fontWeight: '600', color: '#fff', marginBottom: '0.25rem' }}>{name}</div>
          <div style={{ fontSize: '0.85rem', color: 'rgba(232, 238, 252, 0.6)' }}>{description}</div>
        </div>
        <ExternalLink size={16} color="rgba(91, 163, 245, 0.8)" />
      </div>
    </a>
  );
}

export function DevToolsTab() {
  return (
    <div className="admin-panel-devtools">
      <h2 style={{ marginBottom: '1.5rem', color: '#fff' }}>Dev Tools</h2>
      <div style={{ display: 'grid', gap: '1rem' }}>
        <DevToolLink
          name="Better Stack"
          description="Monitoring and observability"
          url="https://telemetry.betterstack.com/team/t480691/tail?s=1619692"
          icon={<BarChart3 size={24} />}
        />
        <DevToolLink
          name="Neon Database"
          description="PostgreSQL database management"
          url="https://console.neon.tech/app/projects/royal-shape-47999151"
          icon={<Database size={24} />}
        />
        <DevToolLink
          name="GitHub"
          description="Source code repository"
          url="https://github.com/zana-AI/zana_planner"
          icon={<Github size={24} />}
        />
        <DevToolLink
          name="GitHub Actions"
          description="CI/CD workflows"
          url="https://github.com/zana-AI/zana_planner/actions"
          icon={<Settings2 size={24} />}
        />
      </div>
    </div>
  );
}
