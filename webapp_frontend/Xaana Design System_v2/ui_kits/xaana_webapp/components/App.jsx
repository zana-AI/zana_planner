/* global React, ReactDOM */
const { useState } = React;

function App() {
  const [tab, setTab] = useState("week");
  const [weekOffset, setWeekOffset] = useState(0);
  const [promises, setPromises] = useState(window.DATA.PROMISES);

  // Sheets
  const [openPromise, setOpenPromise] = useState(null);   // promise detail
  const [logFor, setLogFor]           = useState(null);   // log time
  const [checkinFor, setCheckinFor]   = useState(null);   // check in
  const [scheduleFor, setScheduleFor] = useState(null);   // schedule next session
  const [focusPick, setFocusPick]     = useState(false);  // focus picker visible
  const [focusFor, setFocusFor]       = useState(null);   // focus timer running
  const [libraryFilter, setLibraryFilter] = useState(null);

  // Toast
  const [toast, setToast] = useState(null);
  const flashToast = (text) => { setToast(text); setTimeout(() => setToast(null), 1800); };

  // Titles
  const META = {
    week:    { title: "My week",  subtitle: "Your weekly promises and progress" },
    library: { title: "Library",  subtitle: "Content and templates linked to your promises" },
    clubs:   { title: "Clubs",    subtitle: "Where people work toward something together" },
    explore: { title: "Explore",  subtitle: "Curated promise templates" },
  };
  const meta = META[tab];

  // Handlers
  const openDetail = (p) => setOpenPromise(p);
  const beginLog = (p) => { setOpenPromise(null); setLogFor(p); };
  const beginCheckin = (p) => { setOpenPromise(null); setCheckinFor(p); };

  const confirmLog = ({ hours, date, note }) => {
    setPromises(prev => prev.map(x => x.id === logFor.id
      ? { ...x,
          spent: x.spent + hours,
          activity: [...(x.activity || []), {
            id: `a-${Date.now()}`,
            date: date.toLocaleDateString("en-US", { weekday: "short" }),
            time: new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }),
            hours, note,
          }],
        }
      : x));
    flashToast(`Logged ${hours}h for ${logFor.title}`);
    setLogFor(null);
  };

  const confirmCheckin = ({ note }) => {
    const today = new Date().getDay(); // 0=Sun..6=Sat
    const mIdx  = (today + 6) % 7;     // 0=Mon..6=Sun
    setPromises(prev => prev.map(x => x.id === checkinFor.id
      ? { ...x,
          sessions: x.sessions.map((s, i) => i === mIdx ? 1 : s),
          spent: x.spent + 1,
          activity: [...(x.activity || []), {
            id: `a-${Date.now()}`,
            date: new Date().toLocaleDateString("en-US", { weekday: "short" }),
            time: new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }),
            note,
          }],
        }
      : x));
    flashToast(`Checked in for ${checkinFor.title}`);
    setCheckinFor(null);
  };

  const confirmSchedule = (label) => {
    setPromises(prev => prev.map(x => x.id === scheduleFor.id ? { ...x, nextPlanned: label } : x));
    flashToast(label ? `Reminder set · ${label}` : "Reminder cleared");
    setScheduleFor(null);
    // re-open the detail so the user sees the result
    setOpenPromise(prev => prev || promises.find(p => p.id === scheduleFor.id));
  };

  const startFocusFlow = () => setFocusPick(true);
  const pickFocusTarget = (p) => { setFocusPick(false); setFocusFor(p); };
  const finishFocus = (p) => { setFocusFor(null); if (p) setLogFor(p); };

  const openLibraryFor = (p) => { setOpenPromise(null); setLibraryFilter(p.id); setTab("library"); };
  const adoptTemplate = (t) => { flashToast(`${t.title} added`); setTab("week"); };

  return (
    <div className="stage">
      <div className="phone">
        <Chrome title={meta.title} subtitle={meta.subtitle}/>

        <div className="scroll">
          {tab === "week" && (
            <MyWeekScreen
              promises={promises}
              onOpen={openDetail}
              onStartFocus={startFocusFlow}
              weekOffset={weekOffset}
              setWeekOffset={setWeekOffset}
            />
          )}
          {tab === "library" && (
            <LibraryScreen
              promises={promises}
              filterPromiseId={libraryFilter}
              onOpen={(c) => flashToast(`Open ${c.title}`)}
            />
          )}
          {tab === "clubs"   && <ClubsScreen onPick={() => flashToast("Club opened")}/>}
          {tab === "explore" && <ExploreScreen onAdopt={adoptTemplate}/>}
        </div>

        {tab === "week" && (
          <button className="fab" onClick={() => flashToast("New promise — coming soon")} aria-label="New promise">
            <Icon name="plus" size={22}/>
          </button>
        )}

        {tab === "library" && libraryFilter && (
          <button
            className="fab"
            style={{ background: "var(--surface)", color: "var(--fg)", border: "1px solid var(--border-strong)", boxShadow: "none", right: 16, bottom: 80, width: "auto", height: 36, borderRadius: 999, padding: "0 14px" }}
            onClick={() => setLibraryFilter(null)}>
            <Icon name="x" size={14}/>
            <span style={{ marginLeft: 6, fontSize: 12, fontWeight: 700 }}>Clear filter</span>
          </button>
        )}

        <TabBar tab={tab} onTab={(t) => { setTab(t); if (t !== "library") setLibraryFilter(null); }}/>

        {/* Modal stack */}
        {openPromise && (
          <PromiseDetailSheet
            promise={promises.find(x => x.id === openPromise.id) || openPromise}
            onClose={() => setOpenPromise(null)}
            onLogTime={() => beginLog(openPromise)}
            onCheckin={() => beginCheckin(openPromise)}
            onSchedule={() => setScheduleFor(openPromise)}
            onClearSchedule={() => {
              setPromises(prev => prev.map(x => x.id === openPromise.id ? { ...x, nextPlanned: null } : x));
              flashToast("Reminder cleared");
            }}
            onOpenContent={openLibraryFor}
          />
        )}
        {logFor && (
          <LogTimeSheet promise={logFor} onClose={() => setLogFor(null)} onConfirm={confirmLog}/>
        )}
        {checkinFor && (
          <CheckinSheet promise={checkinFor} onClose={() => setCheckinFor(null)} onConfirm={confirmCheckin}/>
        )}
        {scheduleFor && (
          <ScheduleSheet promise={scheduleFor} onClose={() => setScheduleFor(null)} onConfirm={confirmSchedule}/>
        )}
        {focusPick && (
          <FocusPickerSheet promises={promises} onClose={() => setFocusPick(false)} onPick={pickFocusTarget}/>
        )}
        {focusFor && (
          <FocusSheet promise={focusFor} onClose={() => setFocusFor(null)} onComplete={finishFocus}/>
        )}

        {toast && (
          <div style={{
            position: "absolute", bottom: 88, left: "50%", transform: "translateX(-50%)",
            background: "var(--bg-elevated)", color: "var(--fg)",
            border: "1px solid var(--border-strong)", borderRadius: 999,
            padding: "8px 14px", fontSize: 12, fontWeight: 700,
            boxShadow: "var(--shadow-2)", zIndex: 30,
            whiteSpace: "nowrap",
          }}>{toast}</div>
        )}
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
