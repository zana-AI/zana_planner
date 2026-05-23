/* global React, Icon */

function PromiseCard({ promise: p, onOpen }) {
  const isCheckin = p.logType === "checkin";
  const isBudget  = p.kind === "budget";
  const pct = Math.min(100, Math.round((p.spent / p.promised) * 100));
  const klass = p.status === "good" ? "good" : p.status === "warn" ? "warn" : p.status === "bad" ? "bad" : "";

  const typeIcon = isCheckin ? "check" : isBudget ? "trending-down" : p.kind === "task" ? "bookmark" : "target";
  const typeLabel = isCheckin ? "Check-in" : isBudget ? "Budget" : p.kind === "task" ? "Task" : "Promise";

  return (
    <div className={`pcard ${klass}`} onClick={() => onOpen(p)} role="button" tabIndex={0}>
      <div className="top">
        <div className="title">
          <span className="type-mark"><Icon name={typeIcon} size={11}/></span>
          {p.title}
        </div>
        {p.status === "good" && <span className="pill good"><span className="dot"/>On track</span>}
        {p.status === "warn" && <span className="pill warn"><span className="dot"/>Behind</span>}
        {p.status === "bad"  && <span className="pill bad"><span className="dot"/>Over</span>}
        {p.status === "idle" && <span className="pill"><span className="dot"/>Idle</span>}
      </div>

      {isCheckin ? (
        <div className="checkin-dots" aria-label="Daily check-ins this week">
          {p.sessions.map((s, i) => (
            <div key={i} className={`d ${s ? "done" : ""}`}>
              {s ? <Icon name="check" size={10}/> : null}
            </div>
          ))}
        </div>
      ) : (
        <div className="progress"><div className="fill" style={{ width: `${pct}%` }}/></div>
      )}

      <div className="row">
        <div className="footline">
          <span>{typeLabel}</span>
          {!isCheckin && <span className="meta">{p.spent.toFixed(1)}h / {p.promised.toFixed(1)}h</span>}
          {isCheckin && <span className="meta">{p.sessions.filter(s => s).length} / 7 days</span>}
          {p.linkedContentIds && p.linkedContentIds.length > 0 && (
            <span title="Linked content"><Icon name="link" size={11}/>{p.linkedContentIds.length}</span>
          )}
          {p.nextPlanned && (
            <span className="schedule"><Icon name="calendar" size={11}/>{p.nextPlanned}</span>
          )}
        </div>
      </div>
    </div>
  );
}

window.PromiseCard = PromiseCard;
