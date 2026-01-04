import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { useTelegramWebApp, getDevInitData } from './hooks/useTelegramWebApp';
import { WeeklyReportPage } from './pages/WeeklyReportPage';
import { TemplatesPage } from './pages/TemplatesPage';
import { TemplateDetailPage } from './pages/TemplateDetailPage';
import { UsersPage } from './components/UsersPage';
import { HomePage } from './components/HomePage';
import { AdminPanel } from './components/AdminPanel';
import { Navigation } from './components/Navigation';
import { apiClient } from './api/client';

function App() {
  const { initData, isReady } = useTelegramWebApp();
  const [hasSessionToken, setHasSessionToken] = useState(false);
  
  // Check for session token on mount
  useEffect(() => {
    const token = localStorage.getItem('telegram_auth_token');
    setHasSessionToken(!!token);
  }, []);

  // Check for Telegram Mini App initData or session token
  const authData = initData || getDevInitData();
  const isAuthenticated = !!authData || hasSessionToken;
  
  // Update API client with initData if available
  useEffect(() => {
    if (authData) {
      apiClient.setInitData(authData);
    }
  }, [authData]);

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
      <Navigation />
      <Routes>
        {/* Admin Panel - accessible via /admin */}
        <Route path="/admin" element={<AdminPanel />} />
        
        {/* Community/Users Page - accessible via /community */}
        <Route path="/community" element={<UsersPage />} />
        
        {/* Templates Pages */}
        <Route path="/templates" element={<TemplatesPage />} />
        <Route path="/templates/:templateId" element={<TemplateDetailPage />} />
        
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
        
        {/* Tasks - one-time tasks only */}
        <Route 
          path="/tasks" 
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
