/* global React, Icon */
const { useState } = React;

function ClubsScreen({ onPick }) {
  const [seg, setSeg] = useState("clubs"); // clubs | people
  const clubs  = window.DATA.CLUBS;
  const people = window.DATA.COMMUNITY;

  return (
    <>
      <div className="lib-segment">
        <button className={seg === "clubs"  ? "is-active" : ""} onClick={() => setSeg("clubs")}>Clubs</button>
        <button className={seg === "people" ? "is-active" : ""} onClick={() => setSeg("people")}>People</button>
      </div>

      {seg === "clubs" && (
        <>
          <div className="list">
            {clubs.map(c => (
              <div key={c.id} className="club-row" onClick={() => onPick && onPick(c)}>
                <div className="crest">{c.badge}</div>
                <div className="info">
                  <div className="n">{c.name}</div>
                  <div className="s">
                    <span>{c.members} members</span>
                    <span><span className="live"/>{c.active}</span>
                  </div>
                </div>
                <button className="btn btn-sm btn-secondary" onClick={(e) => { e.stopPropagation(); }}>Join</button>
              </div>
            ))}
          </div>

          <div className="lib-group-head" style={{ marginTop: 22 }}>
            <span className="h">Discover</span>
            <span className="m">Open clubs</span>
          </div>
          <div className="empty">
            <h3>No more open clubs near you</h3>
            <p>Start one for your team or friends — it's just a name and a description.</p>
            <button className="btn btn-secondary btn-sm" style={{ marginTop: 6 }}>
              <Icon name="plus" size={14}/>Start a club
            </button>
          </div>
        </>
      )}

      {seg === "people" && (
        <div className="list">
          {people.map(u => (
            <div className="user-row" key={u.id}>
              <div className="av">{u.name[0]}</div>
              <div className="info">
                <div className="name">{u.name}</div>
                <div className="sub">{u.activity}</div>
              </div>
              <button className="btn btn-sm btn-secondary">
                <Icon name="user-plus" size={14}/>Follow
              </button>
            </div>
          ))}
        </div>
      )}

      <div style={{ height: 80 }}/>
    </>
  );
}

window.ClubsScreen = ClubsScreen;
