
export type TabType = 'stats' | 'compose' | 'scheduled' | 'templates' | 'promote' | 'devtools' | 'createPromise' | 'conversations' | 'tests';

interface AdminTabsProps {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
  scheduledCount: number;
}

export function AdminTabs({ activeTab, onTabChange, scheduledCount }: AdminTabsProps) {
  return (
    <div className="admin-panel-tabs">
      <button
        className={`admin-tab ${activeTab === 'stats' ? 'active' : ''}`}
        onClick={() => onTabChange('stats')}
      >
        Stats
      </button>
      <button
        className={`admin-tab ${activeTab === 'compose' ? 'active' : ''}`}
        onClick={() => onTabChange('compose')}
      >
        Broadcast
      </button>
      <button
        className={`admin-tab ${activeTab === 'scheduled' ? 'active' : ''}`}
        onClick={() => onTabChange('scheduled')}
      >
        Scheduled ({scheduledCount})
      </button>
      <button
        className={`admin-tab ${activeTab === 'templates' ? 'active' : ''}`}
        onClick={() => onTabChange('templates')}
      >
        Promise Marketplace
      </button>
      <button
        className={`admin-tab ${activeTab === 'promote' ? 'active' : ''}`}
        onClick={() => onTabChange('promote')}
      >
        Promote
      </button>
      <button
        className={`admin-tab ${activeTab === 'devtools' ? 'active' : ''}`}
        onClick={() => onTabChange('devtools')}
      >
        Dev Tools
      </button>
      <button
        className={`admin-tab ${activeTab === 'createPromise' ? 'active' : ''}`}
        onClick={() => onTabChange('createPromise')}
      >
        Create Promise
      </button>
      <button
        className={`admin-tab ${activeTab === 'conversations' ? 'active' : ''}`}
        onClick={() => onTabChange('conversations')}
      >
        Conversations
      </button>
      <button
        className={`admin-tab ${activeTab === 'tests' ? 'active' : ''}`}
        onClick={() => onTabChange('tests')}
      >
        Tests
      </button>
    </div>
  );
}
