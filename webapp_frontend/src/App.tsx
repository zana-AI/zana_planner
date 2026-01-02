import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useTelegramWebApp, getDevInitData } from './hooks/useTelegramWebApp';
import { WeeklyReportPage } from './pages/WeeklyReportPage';
import { UsersPage } from './components/UsersPage';
import { HomePage } from './components/HomePage';
import { AdminPanel } from './components/AdminPanel';

function App() {
  const { initData, isReady } = useTelegramWebApp();
  const authData = initData || getDevInitData();
  const isAuthenticated = !!authData;

  // Wait for Telegram WebApp to be ready
  if (!isReady) {
    return (
      <div className="app">
        <div className="loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        {/* Admin Panel - accessible via /admin */}
        <Route path="/admin" element={<AdminPanel />} />
        
        {/* Community/Users Page - accessible via /community */}
        <Route path="/community" element={<UsersPage />} />
        
        {/* Home Page - shown when not authenticated */}
        <Route 
          path="/" 
          element={
            isAuthenticated ? (
              <Navigate to="/weekly" replace />
            ) : (
              <HomePage />
            )
          } 
        />
        
        {/* Weekly Report - default for authenticated users */}
        <Route 
          path="/weekly" 
          element={
            isAuthenticated ? (
              <WeeklyReportPage />
            ) : (
              <Navigate to="/" replace />
            )
          } 
        />
        
        {/* Catch-all: redirect to home */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
