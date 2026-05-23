/* global React, Icon */
const { useState } = React;

const QUICK = [
  { v: 0.25, label: "15", sub: "min" },
  { v: 0.5,  label: "30", sub: "min" },
  { v: 1.0,  label: "1",  sub: "hour" },
];

function fmtToday(d) {
  const today = new Date();
  const isToday = d.toDateString() === today.toDateString();
  const isYest = (new Date(today.getTime() - 86400000)).toDateString() === d.toDateString();
  if (isToday) return "Today";
  if (isYest)  return "Yesterday";
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function LogTimeSheet({ promise: p, onClose, onConfirm }) {
  const [hours, setHours]   = useState(0.5);
  const [advanced, setAdv]  = useState(false);
  const [custom, setCustom] = useState(0.5);
  const [date, setDate]     = useState(new Date());
  const [time, setTime]     = useState(new Date());
  const [note, setNote]     = useState("");

  const dayOffsets = [0, -1, -2];

  const final = advanced ? Number(custom) : hours;

  return (
    <div className="scrim" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <div className="handle"/>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
          <div>
            <h3>Log time</h3>
            <p className="sheet-sub">{p.title}</p>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close" style={{ height: 32, width: 32, padding: 0 }}>
            <Icon name="x" size={18}/>
          </button>
        </div>

        <div className="body">
          {!advanced && (
            <div className="lt-quick">
              {QUICK.map(q => (
                <button key={q.v} className={q.v === hours ? "is-active" : ""} onClick={() => setHours(q.v)}>
                  <span>{q.label}</span>
                  <span className="lt-sub">{q.sub}</span>
                </button>
              ))}
            </div>
          )}

          <button className="lt-more" onClick={() => setAdv(a => !a)}>
            <Icon name={advanced ? "chevron-up" : "chevron-down"} size={14}/>
            {advanced ? "Hide details" : "More options"}
          </button>

          {advanced && (
            <div className="lt-advanced">
              <div className="field-row">
                <label>Duration</label>
                <div className="dur-input">
                  <input type="number" min="0" step="0.25" value={custom} onChange={e => setCustom(e.target.value)}/>
                  <span className="unit">hours</span>
                </div>
              </div>

              <div className="field-row">
                <label>Date</label>
                <div className="lt-grid2" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
                  {dayOffsets.map(off => {
                    const d = new Date();
                    d.setDate(d.getDate() + off);
                    const active = d.toDateString() === date.toDateString();
                    return (
                      <button key={off} className={`date-pill ${active ? "is-active" : ""}`} onClick={() => setDate(d)}>
                        <Icon name="calendar" size={13}/>{fmtToday(d)}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="field-row">
                <label>Time</label>
                <div className="date-pill">
                  <Icon name="clock" size={13}/>
                  {time.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}
                </div>
              </div>
            </div>
          )}

          <div className="field-row" style={{ marginTop: 14 }}>
            <label>Note <span style={{ color: "var(--fg-subtle)", fontWeight: 500 }}>(optional)</span></label>
            <textarea
              placeholder="What did you work on?"
              value={note}
              onChange={e => setNote(e.target.value)}
            />
          </div>

          <div className="divider"/>

          <button
            className="btn btn-primary btn-block"
            onClick={() => onConfirm({ hours: final, date, time, note })}
            disabled={!final}
          >
            <Icon name="check" size={16}/>Log {final}h
          </button>
        </div>
      </div>
    </div>
  );
}

window.LogTimeSheet = LogTimeSheet;
