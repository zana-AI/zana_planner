import { BarChart3, Bell, CalendarClock, CheckCircle2, Flame, MessageCircle, Sparkles, Users } from 'lucide-react';
import type { ReactNode } from 'react';

export type HomeMockupId = 'my-week' | 'community-clubs' | 'planned-sessions' | 'telegram-chat';

export const HOME_MOCKUPS: Array<{
  id: HomeMockupId;
  title: string;
  alt: string;
  src: string;
}> = [
  {
    id: 'my-week',
    title: 'My Week',
    alt: 'Xaana weekly progress screen showing promises, progress bars, and next actions',
    src: '/assets/home/my-week.png',
  },
  {
    id: 'community-clubs',
    title: 'Community Clubs',
    alt: 'Xaana community clubs screen showing friends working toward shared routines',
    src: '/assets/home/community-clubs.png',
  },
  {
    id: 'planned-sessions',
    title: 'Planned Sessions',
    alt: 'Xaana planned sessions screen showing upcoming routine blocks for the week',
    src: '/assets/home/planned-sessions.png',
  },
  {
    id: 'telegram-chat',
    title: 'Telegram Check-ins',
    alt: 'Telegram-style Xaana chat showing routine reminders and friend check-ins',
    src: '/assets/home/telegram-chat.png',
  },
];

type MockupFrameProps = {
  eyebrow: string;
  title: string;
  children: ReactNode;
};

function StatusBar() {
  return (
    <div className="home-shot-statusbar">
      <span>9:41</span>
      <span className="home-shot-statusbar-icons">5G 100%</span>
    </div>
  );
}

function MockupFrame({ eyebrow, title, children }: MockupFrameProps) {
  return (
    <div className="home-shot-capture">
      <div className="home-shot-phone">
        <StatusBar />
        <header className="home-shot-header">
          <div className="home-shot-mark">X</div>
          <div>
            <p>{eyebrow}</p>
            <h1>{title}</h1>
          </div>
        </header>
        <main className="home-shot-body">{children}</main>
      </div>
    </div>
  );
}

function ProgressRow({ title, meta, value, tone }: { title: string; meta: string; value: number; tone?: 'good' | 'warn' }) {
  return (
    <div className="home-shot-progress-row">
      <div className="home-shot-progress-top">
        <span>{title}</span>
        <strong>{value}%</strong>
      </div>
      <div className="home-shot-progress-track">
        <div className={tone ? `is-${tone}` : ''} style={{ width: `${value}%` }} />
      </div>
      <p>{meta}</p>
    </div>
  );
}

function MyWeekMockup() {
  return (
    <MockupFrame eyebrow="My Week" title="May 31 - Jun 6">
      <section className="home-shot-overview">
        <div>
          <span>Weekly progress</span>
          <strong>72%</strong>
        </div>
        <p>Three routines are moving. Xaana suggests protecting tomorrow morning for the writing block.</p>
      </section>
      <div className="home-shot-week-grid">
        {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((day, index) => (
          <div key={`${day}-${index}`} className={index < 5 ? 'is-active' : ''}>
            <span>{day}</span>
            <b />
          </div>
        ))}
      </div>
      <div className="home-shot-list">
        <ProgressRow title="Run before work" meta="4 of 5 check-ins" value={80} tone="good" />
        <ProgressRow title="Deep work sprint" meta="3h 45m logged" value={63} />
        <ProgressRow title="Spanish practice" meta="Needs a plan this weekend" value={40} tone="warn" />
      </div>
      <section className="home-shot-ai-card">
        <Sparkles size={18} />
        <span>Move Spanish to Saturday 10:00. Your club is usually active then.</span>
      </section>
    </MockupFrame>
  );
}

function CommunityClubsMockup() {
  return (
    <MockupFrame eyebrow="Community" title="Clubs">
      <section className="home-shot-club-hero">
        <Users size={22} />
        <div>
          <strong>Morning Run Club</strong>
          <span>5 friends · 4 check-ins/week</span>
        </div>
      </section>
      <div className="home-shot-club-members">
        {[
          ['N', 94],
          ['A', 82],
          ['L', 78],
          ['J', 65],
        ].map(([initial, score]) => (
          <div key={initial}>
            <span>{initial}</span>
            <b>{score}%</b>
          </div>
        ))}
      </div>
      <section className="home-shot-activity">
        <h2>Today</h2>
        <p><strong>Nora</strong> checked in after a 32 min run.</p>
        <p><strong>Amir</strong> scheduled tomorrow&apos;s route.</p>
        <p><strong>Xaana</strong> nudged the group before momentum dropped.</p>
      </section>
      <button className="home-shot-button" type="button">Open club</button>
    </MockupFrame>
  );
}

function PlannedSessionsMockup() {
  return (
    <MockupFrame eyebrow="Planner" title="Next sessions">
      <section className="home-shot-session-main">
        <CalendarClock size={24} />
        <div>
          <span>Tomorrow · 09:00</span>
          <strong>Deep work sprint</strong>
          <p>90 minutes · phone away · write product note</p>
        </div>
      </section>
      <div className="home-shot-session-list">
        <div>
          <span>Tue</span>
          <strong>Run before work</strong>
          <p>07:15 with Morning Run Club</p>
        </div>
        <div>
          <span>Thu</span>
          <strong>Spanish practice</strong>
          <p>20 minutes after dinner</p>
        </div>
        <div>
          <span>Fri</span>
          <strong>Weekly review</strong>
          <p>Xaana prepares the summary</p>
        </div>
      </div>
      <section className="home-shot-reminder">
        <Bell size={16} />
        <span>Reminder ready in Telegram</span>
      </section>
    </MockupFrame>
  );
}

function TelegramChatMockup() {
  return (
    <MockupFrame eyebrow="Telegram" title="Xaana chat">
      <div className="home-shot-chat">
        <div className="home-shot-message is-bot">
          <span>Xaana</span>
          <p>Your Morning Run Club is at 3/4 check-ins. Want a 7:15 reminder tomorrow?</p>
        </div>
        <div className="home-shot-message is-user">
          <p>Yes, and ask the group who&apos;s joining.</p>
        </div>
        <div className="home-shot-message is-bot">
          <span>Xaana</span>
          <p>Done. I also moved Spanish to Saturday because tonight is packed.</p>
        </div>
        <div className="home-shot-chat-card">
          <MessageCircle size={18} />
          <div>
            <strong>Leila checked in</strong>
            <span>Run before work · 28 min</span>
          </div>
          <CheckCircle2 size={18} />
        </div>
      </div>
    </MockupFrame>
  );
}

export function HomeMockupScreen({ id }: { id: HomeMockupId }) {
  if (id === 'community-clubs') return <CommunityClubsMockup />;
  if (id === 'planned-sessions') return <PlannedSessionsMockup />;
  if (id === 'telegram-chat') return <TelegramChatMockup />;
  return <MyWeekMockup />;
}

export function HomeMockupPreviewStack() {
  return (
    <div className="home-product-stack" aria-label="Xaana product previews">
      <div className="home-product-card home-product-card-main">
        <img src="/assets/home/my-week.png" alt={HOME_MOCKUPS[0].alt} width="520" height="888" />
      </div>
      <div className="home-product-card home-product-card-side">
        <img src="/assets/home/community-clubs.png" alt={HOME_MOCKUPS[1].alt} width="520" height="888" />
      </div>
    </div>
  );
}

export function HomeMockupGallery() {
  return (
    <div className="home-screenshot-grid">
      {HOME_MOCKUPS.map((mockup) => (
        <article key={mockup.id} className="home-screenshot-card">
          <img src={mockup.src} alt={mockup.alt} width="520" height="888" loading="lazy" />
          <h3>{mockup.title}</h3>
        </article>
      ))}
    </div>
  );
}

export const homeMockupIcons = {
  BarChart3,
  CalendarClock,
  Flame,
  Sparkles,
  Users,
};
