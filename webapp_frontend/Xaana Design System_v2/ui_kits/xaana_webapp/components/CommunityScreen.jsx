/* global React, Icon */

function CommunityScreen({ onSuggest }) {
  const users = window.DATA.COMMUNITY;
  return (
    <>
      <div className="section-head">
        <h2>People you might follow</h2>
        <span className="meta">{users.length} active</span>
      </div>
      <div className="list">
        {users.map(u => (
          <div className="user-row" key={u.id}>
            <div className="av">{u.name[0]}</div>
            <div className="info">
              <div className="name">{u.name}</div>
              <div className="sub">{u.activity}</div>
            </div>
            <button className="btn btn-sm btn-secondary" onClick={() => onSuggest(u)}>
              <Icon name="user-plus" size={14}/>Follow
            </button>
          </div>
        ))}
      </div>
    </>
  );
}

window.CommunityScreen = CommunityScreen;
