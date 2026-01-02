import { NewYearBanner } from './NewYearBanner';

export function HomePage() {
  return (
    <div className="home-page">
      <NewYearBanner />
      
      {/* Hero Section */}
      <section className="home-hero">
        <div className="home-hero-content">
          <h1 className="home-hero-title">
            Zana AI
          </h1>
          <p className="home-hero-subtitle">
            Your AI-powered assistant for productivity and goal achievement
          </p>
          <p className="home-hero-description">
            Take control of your time, track your promises, and achieve your goals with intelligent insights and personalized recommendations.
          </p>
          <a 
            href="https://t.me/zana_planner_bot" 
            className="home-cta-button"
            target="_blank"
            rel="noopener noreferrer"
          >
            Start with Zana AI
          </a>
        </div>
      </section>

      {/* Three Key Features Section */}
      <section className="home-features">
        <h2 className="home-section-title">Why Choose Zana AI?</h2>
        <div className="home-features-grid">
          <div className="home-feature-card">
            <div className="home-feature-icon">🎯</div>
            <h3 className="home-feature-title">Goal Tracking</h3>
            <p className="home-feature-description">
              Track your promises (goals) and log time spent on them. Stay organized and focused on what matters most.
            </p>
          </div>
          
          <div className="home-feature-card">
            <div className="home-feature-icon">🧠</div>
            <h3 className="home-feature-title">AI Insights</h3>
            <p className="home-feature-description">
              Get personalized recommendations and daily focus areas powered by advanced AI. Know exactly what to work on today.
            </p>
          </div>
          
          <div className="home-feature-card">
            <div className="home-feature-icon">📊</div>
            <h3 className="home-feature-title">Progress Visualization</h3>
            <p className="home-feature-description">
              Visualize your progress with weekly reports and detailed analytics. See how you're advancing toward your goals.
            </p>
          </div>
        </div>
      </section>

      {/* Additional Features Section */}
      <section className="home-additional-features">
        <h2 className="home-section-title">More Features</h2>
        <div className="home-additional-grid">
          <div className="home-additional-item">
            <span className="home-additional-icon">🎤</span>
            <span className="home-additional-text">Voice & Image Input</span>
          </div>
          <div className="home-additional-item">
            <span className="home-additional-icon">🌍</span>
            <span className="home-additional-text">Multi-language Support</span>
          </div>
          <div className="home-additional-item">
            <span className="home-additional-icon">⏱️</span>
            <span className="home-additional-text">Pomodoro Sessions</span>
          </div>
          <div className="home-additional-item">
            <span className="home-additional-icon">🔔</span>
            <span className="home-additional-text">Smart Reminders</span>
          </div>
        </div>
      </section>

      {/* Community Preview Section */}
      <section className="home-community">
        <div className="home-community-card">
          <div className="home-community-icon">👥</div>
          <h3 className="home-community-title">Join the Community</h3>
          <p className="home-community-description">
            Connect with other goal-achievers, share your progress, and stay motivated together.
          </p>
          <a 
            href="?startapp=community" 
            className="home-cta-button"
            style={{ marginTop: '1rem', display: 'inline-block' }}
          >
            View Community
          </a>
        </div>
      </section>

      {/* Final CTA Section */}
      <section className="home-final-cta">
        <h2 className="home-cta-title">Ready to Achieve Your Goals?</h2>
        <p className="home-cta-subtitle">
          Start your productivity journey with Zana AI today
        </p>
        <a 
          href="https://t.me/zana_planner_bot" 
          className="home-cta-button home-cta-button-large"
          target="_blank"
          rel="noopener noreferrer"
        >
          Get Started on Telegram
        </a>
      </section>
    </div>
  );
}

