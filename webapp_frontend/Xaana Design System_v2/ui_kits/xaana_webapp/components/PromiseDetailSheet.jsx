/* global React, Icon */
const { useState } = React;

function PromiseDetailSheet({ promise: p, onClose, onLogTime, onCheckin, onSchedule, onClearSchedule, onOpenContent }) {
  const isCheckin = p.logType === "checkin";
  const pct = Math.min(100, Math.round((p.spent / p.promised) * 100));
  const checkins = isCheckin ? p.sessions.filter(s => s).length : 0;
  const linked = (p.linkedContentIds || []).map(id => window.DATA.CONTENT.find(c => c.id === id)).filter(Boolean);

  return (
    <div className="scrim" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <div className="handle"/>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
          <div>
            <h3>{p.title}</h3>
            <p className="sheet-sub">
              {isCheckin ? "Daily check-in" :
               p.kind === "task" ? "One-time task" :
               p.kind === "budget" ? "Distraction budget" : "Recurring promise"}
            </p>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close" style={{ height: 32, width: 32, padding: 0 }}>
            <Icon name="x" size={18}/>
          </button>
        </div>

        <div className="body">
          {/* This week summary */}
          <div className="overall" style={{ marginTop: 4 }}>
            <div className="row">
              <span className="label">This week</span>
              {isCheckin ? (
                <span className="sub">{checkins} / 7 days</span>
              ) : (
                <span className="sub">{p.spent.toFixed(1)}h / {p.promised.toFixed(1)}h</span>
              )}
            </div>
            <div className="row" style={{ marginTop: 2 }}>
              <span className="value">{isCheckin ? `${Math.round(checkins/7*100)}%` : `${pct}%`}</span>
              {p.status === "good" && <span className="pill good"><span className="dot"/>On track</span>}
              {p.status === "warn" && <span className="pill warn"><span className="dot"/>Behind</span>}
              {p.status === "bad"  && <span className="pill bad"><span className="dot"/>Over</span>}
              {p.status === "idle" && <span className="pill"><span className="dot"/>Idle</span>}
            </div>
            {isCheckin ? (
              <div className="checkin-dots" style={{ marginTop: 10 }}>
                {p.sessions.map((s, i) => (
                  <div key={i} className={`d ${s ? "done" : ""}`} style={{ width: 24, height: 24, borderRadius: 6 }}>
                    {s ? <Icon name="check" size={12}/> : null}
                  </div>
                ))}
              </div>
            ) : (
              <div className="track" style={{ marginTop: 10 }}>
                <div className="fill" style={{ width: `${pct}%` }}/>
              </div>
            )}
          </div>

          {/* Action row: Log / Check in · Schedule · More */}
          <div className="action-row" style={{ marginTop: 14 }}>
            {isCheckin ? (
              <button className="btn btn-primary" onClick={onCheckin}>
                <Icon name="check" size={16}/>
                <span className="label">Check in</span>
              </button>
            ) : (
              <button className="btn btn-primary" onClick={onLogTime}>
                <Icon name="check" size={16}/>
                <span className="label">Log time</span>
              </button>
            )}
            <button
              className={`btn btn-secondary ${p.nextPlanned ? "scheduled" : ""}`}
              onClick={onSchedule}
            >
              <Icon name={p.nextPlanned ? "bell" : "calendar"} size={16}/>
              <span className="label">{p.nextPlanned ? "Scheduled" : "Schedule"}</span>
            </button>
            <button className="btn btn-secondary" aria-label="More">
              <Icon name="more-horizontal" size={16}/>
              <span className="label">More</span>
            </button>
          </div>

          {p.nextPlanned && (
            <div style={{
              marginTop: 8, padding: "8px 12px",
              background: "var(--accent-soft)", border: "1px solid var(--accent-border)",
              borderRadius: 8, fontSize: 12, color: "var(--accent)",
              display: "flex", alignItems: "center", gap: 8, justifyContent: "space-between",
            }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <Icon name="bell" size={12}/>Next session · {p.nextPlanned}
              </span>
              <button
                style={{ background: "none", border: "none", color: "var(--accent)", cursor: "pointer", padding: 2, display: "grid", placeItems: "center" }}
                onClick={onClearSchedule} aria-label="Clear">
                <Icon name="x" size={14}/>
              </button>
            </div>
          )}

          {/* Linked content — minimal collapsed view */}
          {linked.length > 0 && (
            <>
              <div className="section-head" style={{ marginTop: 16 }}>
                <h2>Linked content</h2>
                <span className="meta">{linked.length} item{linked.length === 1 ? "" : "s"}</span>
              </div>
              <div className="content-link-row" onClick={() => onOpenContent && onOpenContent(p)}>
                <div className="ic"><Icon name="link" size={16}/></div>
                <div className="info">
                  <div className="t">{linked.length === 1 ? linked[0].title : `${linked.length} items`}</div>
                  <div className="s">
                    {linked.length === 1
                      ? linked[0].source
                      : linked.slice(0,3).map(c => c.title).join(" · ")}
                  </div>
                </div>
                <Icon name="chevron-right" size={16}/>
              </div>
            </>
          )}

          {/* Activity log — where notes live */}
          <div className="section-head" style={{ marginTop: 18 }}>
            <h2>Activity</h2>
            <span className="meta">{p.activity?.length || 0} entries</span>
          </div>
          {(p.activity && p.activity.length > 0) ? (
            <div className="activity">
              {p.activity.slice().reverse().map(a => (
                <div className="activity-row" key={a.id}>
                  <div className="when">
                    <span className="d">{a.date}</span>
                    <span>{a.time}</span>
                  </div>
                  <div className="body">
                    <div className="first">
                      {isCheckin ? <><Icon name="check" size={12}/>Checked in</> : <>Logged</>}
                    </div>
                    {a.note ? <div className="note">{a.note}</div> : <div className="note" style={{ color: "var(--fg-subtle)", fontStyle: "italic" }}>No note</div>}
                  </div>
                  <div className="amount">
                    {!isCheckin && a.hours ? `${a.hours.toFixed(2).replace(/\.?0+$/, "")}h` : ""}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="activity"><div className="activity-empty">No activity yet this week.</div></div>
          )}

          <div className="divider"/>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <button className="btn btn-secondary"><Icon name="pencil" size={14}/>Edit promise</button>
            <button className="btn btn-secondary" style={{ color: "#F87171", borderColor: "rgba(248,113,113,0.32)" }}>
              <Icon name="trash" size={14}/>Delete
            </button>
          </div>

          <div style={{ height: 12 }}/>
        </div>
      </div>
    </div>
  );
}

window.PromiseDetailSheet = PromiseDetailSheet;
