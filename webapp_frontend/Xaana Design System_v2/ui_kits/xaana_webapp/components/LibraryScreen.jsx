/* global React, Icon */
const { useState } = React;

const TYPE_ICON = {
  pdf: "file-text", book: "book-open",
  video: "video", audio: "headphones", article: "file-text",
};

function ContentRow({ item, promises, onOpen }) {
  const p = promises.find(x => x.id === item.promiseId);
  const cls = `content-row is-${item.type}`;
  const pct = Math.round((item.progress || 0) * 100);
  return (
    <div className={cls} onClick={() => onOpen(item)}>
      <div className="ic"><Icon name={TYPE_ICON[item.type] || "file-text"} size={18}/></div>
      <div className="info">
        <div className="t">{item.title}</div>
        <div className="s">
          <span>{item.source}</span>
          {p && <><span style={{ color: "var(--fg-subtle)" }}>·</span><span className="promise-tag">{p.title}</span></>}
        </div>
      </div>
      {pct > 0 ? (
        <div className="pbar" title={`${pct}%`}><div className={`fill ${pct >= 100 ? "done" : ""}`} style={{ width: `${pct}%` }}/></div>
      ) : (
        <span style={{ fontSize: 10, color: "var(--fg-subtle)", fontWeight: 700, fontFamily: "var(--font-mono)" }}>NEW</span>
      )}
    </div>
  );
}

function LibraryScreen({ promises, onOpen, filterPromiseId }) {
  const [seg, setSeg] = useState("content");  // content | templates
  const allContent = window.DATA.CONTENT;
  const templates  = window.DATA.TEMPLATES;

  // Group content by promise
  const byPromise = {};
  for (const c of allContent) {
    if (filterPromiseId && c.promiseId !== filterPromiseId) continue;
    (byPromise[c.promiseId] = byPromise[c.promiseId] || []).push(c);
  }

  return (
    <>
      {!filterPromiseId && (
        <div className="lib-segment">
          <button className={seg === "content"   ? "is-active" : ""} onClick={() => setSeg("content")}>My content</button>
          <button className={seg === "templates" ? "is-active" : ""} onClick={() => setSeg("templates")}>Templates</button>
        </div>
      )}

      {(seg === "content" || filterPromiseId) && (
        <>
          {Object.keys(byPromise).length === 0 && (
            <div className="empty">
              <h3>Nothing saved yet</h3>
              <p>Add a PDF, video, or article and link it to a promise. Time you spend reading or watching it gets logged automatically.</p>
              <button className="btn btn-primary btn-sm" style={{ marginTop: 6 }}>
                <Icon name="plus" size={14}/>Add content
              </button>
            </div>
          )}

          {Object.entries(byPromise).map(([pid, items]) => {
            const p = promises.find(x => x.id === pid);
            return (
              <div key={pid}>
                <div className="lib-group-head">
                  <span className="h">{p ? p.title : "Unfiled"}</span>
                  <span className="m">{items.length} item{items.length === 1 ? "" : "s"}</span>
                </div>
                <div className="list">
                  {items.map(c => <ContentRow key={c.id} item={c} promises={promises} onOpen={onOpen}/>)}
                </div>
              </div>
            );
          })}
        </>
      )}

      {seg === "templates" && !filterPromiseId && (
        <>
          <div style={{ display: "grid", gap: 10, marginBottom: 14 }}>
            {/* Compact templates */}
          </div>
          <div className="list">
            {templates.map(t => (
              <div key={t.id} className="tpl-row">
                <div className="info">
                  <div className="t">{t.title}</div>
                  <div className="meta">
                    <span>{t.category}</span>
                    <span className="dot"/>
                    <span>{t.users.toLocaleString()} using</span>
                  </div>
                </div>
                <button className="add" aria-label="Add"><Icon name="plus" size={14}/></button>
              </div>
            ))}
          </div>
        </>
      )}

      <div style={{ height: 80 }}/>
    </>
  );
}

window.LibraryScreen = LibraryScreen;
