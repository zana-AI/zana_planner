/* global React */
// Seeded demo data for the prototype.

const TODAY = new Date();
const fmtMD = (d) => d.toLocaleDateString("en-US", { month: "short", day: "numeric" });

function weekRange(offset = 0) {
  const d = new Date(TODAY);
  const day = d.getDay(); // 0 = Sun
  const monOff = (day === 0 ? -6 : 1) - day;
  const monday = new Date(d);
  monday.setDate(d.getDate() + monOff + offset * 7);
  monday.setHours(0, 0, 0, 0);
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  return { start: monday, end: sunday, label: `${fmtMD(monday)} – ${fmtMD(sunday)}` };
}

// Activity log: an array of session entries per promise.
// type = "log" (duration) | "checkin" (just a tap, no hours)
const PROMISES = [
  {
    id: "p1",
    title: "Learn Rust",
    promised: 6, spent: 4.0,
    kind: "recurring", logType: "duration",
    sessions: [0, 1.5, 0, 0.5, 2.0, 0, 0],
    status: "good",
    nextPlanned: "Wed · 7:00pm",
    activity: [
      { id: "a1", date: "Mon", time: "8:12am", hours: 1.5, note: "Finished ownership chapter — borrow checker still confusing." },
      { id: "a2", date: "Wed", time: "9:40pm", hours: 0.5, note: "Quick review of yesterday's notes." },
      { id: "a3", date: "Fri", time: "7:30am", hours: 2.0, note: "Built a tiny CLI tool to practice lifetimes." },
    ],
    linkedContentIds: ["c1", "c2", "c3"],
  },
  {
    id: "p2",
    title: "Morning run",
    promised: 3, spent: 1.0,
    kind: "recurring", logType: "duration",
    sessions: [1.0, 0, 0, 0, 0, 0, 0],
    status: "warn",
    nextPlanned: null,
    activity: [
      { id: "a4", date: "Mon", time: "6:40am", hours: 1.0, note: "" },
    ],
    linkedContentIds: [],
  },
  {
    id: "p3",
    title: "Take vitamins",
    promised: 7, spent: 4,
    kind: "recurring", logType: "checkin",
    sessions: [1, 1, 0, 1, 1, 0, 0],
    status: "good",
    nextPlanned: null,
    activity: [
      { id: "a5", date: "Mon", time: "8:00am", note: "" },
      { id: "a6", date: "Tue", time: "8:14am", note: "" },
      { id: "a7", date: "Thu", time: "7:55am", note: "Almost forgot." },
      { id: "a8", date: "Fri", time: "8:02am", note: "" },
    ],
    linkedContentIds: [],
  },
  {
    id: "p4",
    title: "Finish design system handoff",
    promised: 4, spent: 2.5,
    kind: "task", logType: "duration",
    sessions: [0, 0, 1.0, 1.5, 0, 0, 0],
    status: "good",
    nextPlanned: "Sat · 10:00am",
    activity: [
      { id: "a9", date: "Wed", time: "2:10pm", hours: 1.0, note: "Drafted the token file and README." },
      { id: "a10", date: "Thu", time: "9:30am", hours: 1.5, note: "Built the preview cards." },
    ],
    linkedContentIds: [],
  },
  {
    id: "p5",
    title: "Social media",
    promised: 5, spent: 5.6,
    kind: "budget", logType: "duration",
    sessions: [0.8, 1.2, 0.4, 1.0, 1.2, 0.6, 0.4],
    status: "bad",
    nextPlanned: null,
    activity: [],
    linkedContentIds: [],
  },
];

const CONTENT = [
  { id: "c1", title: "The Rust Programming Language",     type: "book",  source: "doc.rust-lang.org", progress: 0.42, promiseId: "p1" },
  { id: "c2", title: "Crust of Rust: Lifetime Annotations", type: "video", source: "YouTube · 1h 31m", progress: 0.18, promiseId: "p1" },
  { id: "c3", title: "Why Rust's borrow checker matters",  type: "article", source: "fasterthanli.me", progress: 1.0,  promiseId: "p1" },
  { id: "c4", title: "Couch to 5K — Week 3",                type: "audio", source: "NHS · 25m",        progress: 0.0,  promiseId: "p2" },
];

const CLUBS = [
  { id: "cl1", name: "Rust beginners",   members: 84,  active: "12 active today",  badge: "RB" },
  { id: "cl2", name: "Morning routines", members: 213, active: "37 active today",  badge: "MR" },
  { id: "cl3", name: "Designers at work", members: 56,  active: "8 active today",   badge: "DW" },
];

const COMMUNITY = [
  { id: "u1", name: "Mira Asadova",   handle: "@mira",     activity: "On track, 4 promises" },
  { id: "u2", name: "Daniel Karimi",  handle: "@dkarimi",  activity: "Logged 7h this week" },
  { id: "u3", name: "Saba Niknam",    handle: "@saba",     activity: "Just kept a promise" },
  { id: "u4", name: "Leo Park",       handle: "@leo",      activity: "Public · 2 promises" },
];

const TEMPLATES = [
  { id: "t1", icon: "book",     title: "Read 30 min/day",      desc: "Build a steady habit of reading non-fiction.", users: 1240, category: "Learning" },
  { id: "t2", icon: "dumbbell", title: "Strength training 3x", desc: "Three full-body sessions per week.",            users: 980,  category: "Health" },
  { id: "t3", icon: "pencil",   title: "Daily journal",        desc: "5 minutes of evening reflection.",              users: 720,  category: "Mindset" },
  { id: "t4", icon: "trending-down", title: "Social media budget", desc: "Cap weekly screen time on one app.",        users: 1660, category: "Distraction" },
];

window.DATA = { weekRange, PROMISES, COMMUNITY, TEMPLATES, CONTENT, CLUBS };
