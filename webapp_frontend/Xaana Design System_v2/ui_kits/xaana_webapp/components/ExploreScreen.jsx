/* global React, Icon */
const { useState } = React;

function ExploreScreen({ onAdopt }) {
  const cats = ["All", "Health", "Learning", "Mindset", "Distraction"];
  const [cat, setCat] = useState("All");
  const items = window.DATA.TEMPLATES.filter(t => cat === "All" || t.category === cat);
  return (
    <>
      <div className="cat-chips">
        {cats.map(c => (
          <button key={c} className={c === cat ? "is-active" : ""} onClick={() => setCat(c)}>{c}</button>
        ))}
      </div>
      <div className="list">
        {items.map(t => (
          <div className="tpl-row" key={t.id} onClick={() => onAdopt(t)}>
            <div className="info">
              <div className="t">{t.title}</div>
              <div className="meta">
                <span>{t.category}</span>
                <span className="dot"/>
                <span>{t.users.toLocaleString()} using</span>
              </div>
            </div>
            <button className="add" aria-label="Add" onClick={(e) => { e.stopPropagation(); onAdopt(t); }}>
              <Icon name="plus" size={14}/>
            </button>
          </div>
        ))}
      </div>
      <div style={{ height: 80 }}/>
    </>
  );
}

window.ExploreScreen = ExploreScreen;
