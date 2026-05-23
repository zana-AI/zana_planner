/* global React, Icon */
const { useState } = React;

function FocusPickerSheet({ promises, onClose, onPick }) {
  const eligible = promises.filter(p => p.kind !== "budget");
  const [picked, setPicked] = useState(eligible[0]?.id || null);

  return (
    <div className="scrim" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <div className="handle"/>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
          <div>
            <h3>Focus on…</h3>
            <p className="sheet-sub">Pick a promise to work on this session</p>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close" style={{ height: 32, width: 32, padding: 0 }}>
            <Icon name="x" size={18}/>
          </button>
        </div>

        <div className="body">
          <div className="list">
            {eligible.map(p => {
              const selected = p.id === picked;
              const remaining = Math.max(0, p.promised - p.spent);
              return (
                <div key={p.id}
                     className={`focus-pick-row ${selected ? "is-selected" : ""}`}
                     onClick={() => setPicked(p.id)}>
                  <span className="radio"/>
                  <div>
                    <div className="t">{p.title}</div>
                    <div className="m">{p.logType === "checkin" ? "Daily check-in" : `${remaining.toFixed(1)}h left this week`}</div>
                  </div>
                  <span className="right">{p.logType === "checkin" ? `${p.sessions.filter(s=>s).length}/7` : `${p.spent.toFixed(1)}/${p.promised.toFixed(1)}h`}</span>
                </div>
              );
            })}
          </div>

          <div className="divider"/>

          <button className="btn btn-primary btn-block"
                  disabled={!picked}
                  onClick={() => onPick(promises.find(p => p.id === picked))}>
            <Icon name="timer" size={16}/>Start 25-min focus
          </button>

          <div style={{ height: 8 }}/>
        </div>
      </div>
    </div>
  );
}

window.FocusPickerSheet = FocusPickerSheet;
