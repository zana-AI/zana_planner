/* global React, Icon */

function Chrome({ title, subtitle }) {
  return (
    <>
      <div className="statusbar">
        <span>9:41</span>
        <span className="right">
          <svg width="16" height="11" viewBox="0 0 16 11" fill="none" stroke="currentColor" strokeWidth="1.2">
            <path d="M1 8 a 7 7 0 0 1 14 0"/><path d="M3.5 8 a 4.5 4.5 0 0 1 9 0"/><circle cx="8" cy="8" r="1" fill="currentColor"/>
          </svg>
          <svg width="20" height="11" viewBox="0 0 20 11" fill="none" stroke="currentColor" strokeWidth="1.2">
            <rect x="1" y="1" width="16" height="9" rx="2"/><rect x="2.5" y="2.5" width="12" height="6" rx="1" fill="currentColor"/><path d="M18 4v3"/>
          </svg>
        </span>
      </div>
      <div className="app-header">
        <div className="brand" aria-label="Xaana logo"/>
        <div className="titles">
          <h1>{title}</h1>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        <button className="icon-btn" aria-label="Notifications"><Icon name="bell" size={18}/></button>
        <div className="avatar">A</div>
      </div>
    </>
  );
}

function TabBar({ tab, onTab }) {
  const tabs = [
    { id: "week",    label: "My week",  icon: "calendar-check" },
    { id: "library", label: "Library",  icon: "book-open" },
    { id: "clubs",   label: "Clubs",    icon: "shield" },
    { id: "explore", label: "Explore",  icon: "compass" },
  ];
  return (
    <div className="tabbar">
      {tabs.map(t => (
        <button key={t.id} className={t.id === tab ? "is-active" : ""} onClick={() => onTab(t.id)}>
          <Icon name={t.icon} size={20}/>{t.label}
        </button>
      ))}
    </div>
  );
}

window.Chrome = Chrome;
window.TabBar = TabBar;
