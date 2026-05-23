/* global React, Icon */
const { useState } = React;

const WEEK_LABELS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
const TIME_SLOTS = ["7:00am","9:00am","12:30pm","6:00pm","7:00pm","8:30pm","10:00pm"];

function ScheduleSheet({ promise: p, onClose, onConfirm }) {
  const [day, setDay]   = useState(2);   // Wed
  const [slot, setSlot] = useState("7:00pm");

  // Generate 7 upcoming days (today first)
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() + i);
    return d;
  });

  return (
    <div className="scrim" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <div className="handle"/>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
          <div>
            <h3>Schedule next session</h3>
            <p className="sheet-sub">{p.title}</p>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close" style={{ height: 32, width: 32, padding: 0 }}>
            <Icon name="x" size={18}/>
          </button>
        </div>

        <div className="body">
          <div className="sched-grid">
            {days.map((d, i) => (
              <button key={i} className={`sched-day ${i === day ? "is-active" : ""}`} onClick={() => setDay(i)}>
                <span>{d.toLocaleDateString("en-US", { weekday: "short" }).slice(0,3)}</span>
                <span className="num">{d.getDate()}</span>
              </button>
            ))}
          </div>

          <div style={{ marginTop: 18, fontSize: 12, color: "var(--fg-muted)", fontWeight: 600 }}>Time</div>
          <div className="time-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
            {TIME_SLOTS.slice(0,4).map(t => (
              <button key={t} className={t === slot ? "is-active" : ""} onClick={() => setSlot(t)}>{t}</button>
            ))}
          </div>
          <div className="time-row" style={{ gridTemplateColumns: "repeat(3, 1fr)", marginTop: 8 }}>
            {TIME_SLOTS.slice(4).map(t => (
              <button key={t} className={t === slot ? "is-active" : ""} onClick={() => setSlot(t)}>{t}</button>
            ))}
          </div>

          <div className="divider"/>

          <div style={{ display: "grid", gap: 8 }}>
            <button className="btn btn-primary btn-block" onClick={() => {
              const d = days[day];
              const label = `${d.toLocaleDateString("en-US", { weekday: "short" })} · ${slot}`;
              onConfirm(label);
            }}>
              <Icon name="bell" size={16}/>Set reminder
            </button>
            <button className="btn btn-ghost btn-block" onClick={() => onConfirm(null)}>
              {p.nextPlanned ? "Clear reminder" : "Not now"}
            </button>
          </div>

          <div style={{ height: 8 }}/>
        </div>
      </div>
    </div>
  );
}

window.ScheduleSheet = ScheduleSheet;
