/* global React, Icon */
const { useMemo, useState } = React;

function MyWeekScreen({ promises, onOpen, onCreate, onStartFocus, weekOffset, setWeekOffset }) {
  const week = window.DATA.weekRange(weekOffset);
  const recurring = promises.filter(p => p.kind === "recurring");
  const tasks     = promises.filter(p => p.kind === "task");
  const budgets   = promises.filter(p => p.kind === "budget");

  const totalPromised = recurring.reduce((a, p) => a + p.promised, 0) +
                        tasks.reduce((a, p) => a + p.promised, 0);
  const totalSpent    = recurring.reduce((a, p) => a + Math.min(p.spent, p.promised), 0) +
                        tasks.reduce((a, p) => a + Math.min(p.spent, p.promised), 0);
  const pct = totalPromised > 0 ? Math.round((totalSpent / totalPromised) * 100) : 0;

  return (
    <>
      <div className="week-strip">
        <button onClick={() => setWeekOffset(weekOffset - 1)} aria-label="Previous week">
          <Icon name="chevron-left" size={16}/>
        </button>
        <div className="range">{week.label}</div>
        <button onClick={() => setWeekOffset(weekOffset + 1)} disabled={weekOffset >= 0} aria-label="Next week">
          <Icon name="chevron-right" size={16}/>
        </button>
      </div>

      <div className="overall">
        <div className="row">
          <span className="label">Overall progress</span>
          <span className="sub">{totalSpent.toFixed(1)}h / {totalPromised.toFixed(1)}h</span>
        </div>
        <div className="row" style={{ marginTop: 4 }}>
          <span className="value">{pct}%</span>
          <button className="btn btn-sm btn-secondary" onClick={onStartFocus}>
            <Icon name="timer" size={14}/>Start focus
          </button>
        </div>
        <div className="track"><div className="fill" style={{ width: `${pct}%` }}/></div>
      </div>

      {recurring.length > 0 && (
        <>
          <div className="section-head">
            <h2>Promises</h2>
            <span className="meta">{recurring.length} active</span>
          </div>
          <div className="list">
            {recurring.map(p => <PromiseCard key={p.id} promise={p} onOpen={onOpen}/>)}
          </div>
        </>
      )}

      {tasks.length > 0 && (
        <>
          <div className="section-head">
            <h2>One-time tasks</h2>
            <span className="meta">{tasks.length} this week</span>
          </div>
          <div className="list">
            {tasks.map(p => <PromiseCard key={p.id} promise={p} onOpen={onOpen}/>)}
          </div>
        </>
      )}

      {budgets.length > 0 && (
        <>
          <div className="section-head">
            <h2>Distractions</h2>
            <span className="meta">Stay under budget</span>
          </div>
          <div className="list">
            {budgets.map(p => <PromiseCard key={p.id} promise={p} onOpen={onOpen}/>)}
          </div>
        </>
      )}

      <div style={{ height: 80 }}/>
    </>
  );
}

window.MyWeekScreen = MyWeekScreen;
