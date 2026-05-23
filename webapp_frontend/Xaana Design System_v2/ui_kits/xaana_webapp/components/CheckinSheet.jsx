/* global React, Icon */
const { useState } = React;

// Minimal sheet for check-in style promises (no duration).
function CheckinSheet({ promise: p, onClose, onConfirm }) {
  const [note, setNote] = useState("");
  return (
    <div className="scrim" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <div className="handle"/>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
          <div>
            <h3>Check in</h3>
            <p className="sheet-sub">{p.title} · {new Date().toLocaleDateString("en-US", { weekday: "long" })}</p>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close" style={{ height: 32, width: 32, padding: 0 }}>
            <Icon name="x" size={18}/>
          </button>
        </div>

        <div className="body">
          <button className="btn-checkin" onClick={() => onConfirm({ note })}>
            <span className="circle"><Icon name="check" size={18}/></span>
            <span>
              <div style={{ fontSize: 14, fontWeight: 700 }}>Mark done for today</div>
              <div style={{ fontSize: 11, color: "var(--fg-muted)", fontWeight: 500, marginTop: 2 }}>
                {new Date().toLocaleDateString("en-US", { month: "short", day: "numeric" })} · {new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}
              </div>
            </span>
          </button>

          <div className="field-row" style={{ marginTop: 16 }}>
            <label>Note <span style={{ color: "var(--fg-subtle)", fontWeight: 500 }}>(optional)</span></label>
            <textarea
              placeholder="A line of reflection"
              value={note}
              onChange={e => setNote(e.target.value)}
            />
          </div>

          <p style={{ fontSize: 11, color: "var(--fg-subtle)", marginTop: 12, textAlign: "center" }}>
            Need to log a different day? Tap <strong style={{ color: "var(--fg-muted)" }}>More</strong> below.
          </p>
          <button className="lt-more" style={{ margin: "0 auto", display: "flex" }}>
            <Icon name="chevron-down" size={14}/>More options
          </button>
        </div>
      </div>
    </div>
  );
}

window.CheckinSheet = CheckinSheet;
