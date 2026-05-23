/* global React, Icon */
const { useEffect, useState } = React;

function FocusSheet({ promise: p, onClose, onComplete }) {
  const total = 25 * 60; // 25 min default
  const [remaining, setRemaining] = useState(total);
  const [running, setRunning] = useState(true);

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => {
      setRemaining(r => {
        if (r <= 1) { clearInterval(id); setRunning(false); return 0; }
        return r - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [running]);

  const mm = String(Math.floor(remaining / 60)).padStart(2, "0");
  const ss = String(remaining % 60).padStart(2, "0");
  const pct = 1 - remaining / total;
  const R = 92;
  const C = 2 * Math.PI * R;

  return (
    <div className="scrim" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <div className="handle"/>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
          <div>
            <h3>Focus</h3>
            <p className="sheet-sub">{p ? p.title : "Deep work session"}</p>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close" style={{ height: 32, width: 32, padding: 0 }}>
            <Icon name="x" size={18}/>
          </button>
        </div>

        <div className="body">
          <div className="focus-ring">
            <svg width="220" height="220">
              <defs>
                <linearGradient id="ring" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0" stopColor="#67E8F9"/>
                  <stop offset="1" stopColor="#A78BFA"/>
                </linearGradient>
              </defs>
              <circle cx="110" cy="110" r={R} fill="none" stroke="rgba(230,234,245,0.07)" strokeWidth="6"/>
              <circle cx="110" cy="110" r={R} fill="none" stroke="url(#ring)" strokeWidth="6"
                      strokeDasharray={C} strokeDashoffset={C * (1 - pct)} strokeLinecap="round"
                      style={{ transition: "stroke-dashoffset 600ms cubic-bezier(0.2,0.7,0.2,1)" }}/>
            </svg>
            <div className="center">
              <div>
                <div className="time">{mm}:{ss}</div>
                <div className="label">{running ? "Focusing" : remaining === 0 ? "Complete" : "Paused"}</div>
              </div>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <button className="btn btn-secondary" onClick={() => setRunning(r => !r)}>
              <Icon name={running ? "pause" : "play"} size={14}/>
              {running ? "Pause" : remaining === 0 ? "Restart" : "Resume"}
            </button>
            <button className="btn btn-primary" onClick={() => onComplete(p)}>
              <Icon name="check" size={14}/>Finish &amp; log
            </button>
          </div>

          <div style={{ height: 8 }}/>
        </div>
      </div>
    </div>
  );
}

window.FocusSheet = FocusSheet;
