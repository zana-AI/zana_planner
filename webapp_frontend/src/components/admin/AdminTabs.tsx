export type TabType =
  | 'stats'
  | 'followgraph'
  | 'compose'
  | 'scheduled'
  | 'templates'
  | 'clubs'
  | 'promote'
  | 'devtools'
  | 'createPromise'
  | 'conversations'
  | 'tests'
  | 'users';

interface AdminTabsProps {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
  scheduledCount: number;
}

interface AdminTabGroup {
  label: string;
  items: Array<{ key: TabType; label: string }>;
}

export function AdminTabs({ activeTab, onTabChange, scheduledCount }: AdminTabsProps) {
  const groups: AdminTabGroup[] = [
    {
      label: 'Overview',
      items: [
        { key: 'stats', label: 'Metrics' },
        { key: 'followgraph', label: 'Follow Graph' },
        { key: 'users', label: 'Users' },
      ],
    },
    {
      label: 'Messaging',
      items: [
        { key: 'compose', label: 'Compose' },
        { key: 'scheduled', label: `Queue (${scheduledCount})` },
        { key: 'conversations', label: 'Conversations' },
      ],
    },
    {
      label: 'Promise Ops',
      items: [
        { key: 'templates', label: 'Template Library' },
        { key: 'createPromise', label: 'Create Promise' },
        { key: 'clubs', label: 'Club Setup' },
      ],
    },
    {
      label: 'System',
      items: [
        { key: 'tests', label: 'Test Runner' },
        { key: 'devtools', label: 'Dev Tools' },
        { key: 'promote', label: 'Promote' },
      ],
    },
  ];

  return (
    <div className="admin-tabs-groups">
      {groups.map((group) => (
        <section key={group.label} className="admin-tabs-group">
          <div className="admin-tabs-group-label">{group.label}</div>
          <div className="admin-tabs-group-items">
            {group.items.map((item) => (
              <button
                key={item.key}
                className={`admin-tab ${activeTab === item.key ? 'active' : ''}`}
                onClick={() => onTabChange(item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
