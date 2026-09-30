export function PrivacyPage() {
  return (
    <main className="page-container" dir="ltr" style={{ maxWidth: 760, margin: '2rem auto', lineHeight: 1.6 }}>
      <h1>Xaana Privacy Policy</h1>
      <p>Effective September 2026. Xaana is a planning and accountability app available at xaana.club and through the Xaana Telegram bot.</p>

      <h2>Information used by Xaana</h2>
      <p>Xaana uses your Telegram account identifier and profile information to sign you in. It stores the promises, sessions, check-ins, messages, clubs, and learning content you choose to create or share so it can provide planning, reminders, progress views, and related features. Some features use third-party AI services to process the content you provide. Xaana also uses technical logs to operate and protect the service.</p>

      <h2>Google Calendar</h2>
      <p>Google Calendar access is optional. When you choose “Add directly to Google Calendar” for a scheduled session, Xaana asks for permission to manage events on calendars you own. Xaana uses that permission only to create or update the selected Xaana session event in your primary Google Calendar. It sends the session title, optional notes, start and end time, and reminder setting to Google. Xaana does not list or read your existing calendar events.</p>
      <p>Xaana uses the Google authorization code and access token only while completing that requested action. It does not store a Google refresh token or keep ongoing Calendar access. Xaana receives the result of the event creation or update to tell you whether it succeeded. The session details you entered remain in Xaana independently of Google Calendar. Changing or deleting a Xaana session does not automatically change or delete its Google Calendar event; choose the add action again to update it.</p>
      <p>Xaana does not use Google Calendar data for advertising, sell it, or send it to AI models for training. Xaana’s use of information received from Google Workspace APIs follows the <a href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noopener noreferrer">Google API Services User Data Policy</a>, including its Limited Use requirements.</p>

      <h2>Sharing and your choices</h2>
      <p>Xaana shares information with service providers only as needed to run the features you use, including Telegram for bot and Mini App delivery and Google when you choose a Calendar action. Information you choose to share with a club or in Explore can be visible to other users according to that feature’s settings. You can revoke Xaana’s Google permission in your <a href="https://myaccount.google.com/permissions" target="_blank" rel="noopener noreferrer">Google Account</a>. Revoking access does not remove events already added to Google Calendar.</p>

      <h2>Questions and deletion requests</h2>
      <p>For questions about this policy or requests to access or delete your Xaana data, contact the <a href="https://t.me/xaana_bot" target="_blank" rel="noopener noreferrer">Xaana bot on Telegram</a>. You can also remove individual sessions and other content in the app where those controls are available.</p>
      <p><a href="/terms">Terms of Service</a> · <a href="/">Back to Xaana</a></p>
    </main>
  );
}
