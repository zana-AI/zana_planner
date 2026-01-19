import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { useTelegramWebApp, getDevInitData } from './hooks/useTelegramWebApp';
import { useTimezoneDetection } from './hooks/useTimezoneDetection';
import { DashboardPage } from './pages/DashboardPage';
import { TemplatesPage } from './pages/TemplatesPage';
import { TemplateDetailPage } from './pages/TemplateDetailPage';
import { TimezoneSelectorPage } from './pages/TimezoneSelectorPage';
import { UsersPage } from './components/UsersPage';
import { HomePage } from './components/HomePage';
import { AdminPanel } from './components/AdminPanel';
import { Navigation } from './components/Navigation';
import { apiClient } from './api/client';

function App() {
  const { initData, isReady } = useTelegramWebApp();
  const [hasSessionToken, setHasSessionToken] = useState(false);
  
  // Automatically detect and set timezone when Mini App loads (only if authenticated)
  const isAuthenticated = !!initData || !!getDevInitData() || hasSessionToken;
  useTimezoneDetection(isAuthenticated && isReady);
  
  // Check for session token on mount and listen for changes
  useEffect(() => {
    const checkToken = () => {
      const token = localStorage.getItem('telegram_auth_token');
      setHasSessionToken(!!token);
    };
    
    checkToken();
    
    // Listen for storage changes (e.g., logout)
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'telegram_auth_token') {
        checkToken();
      }
    };
    
    window.addEventListener('storage', handleStorageChange);
    
    // Listen for custom login event (browser login)
    const handleLogin = () => {
      checkToken();
    };
    
    // Also listen for custom logout event
    const handleLogout = () => {
      checkToken();
    };
    
    window.addEventListener('login', handleLogin);
    window.addEventListener('logout', handleLogout);
    
    return () => {
      window.removeEventListener('storage', handleStorageChange);
      window.removeEventListener('login', handleLogin);
      window.removeEventListener('logout', handleLogout);
    };
  }, []);

  // Check for Telegram Mini App initData or session token
  const authData = initData || getDevInitData();
  // Note: isAuthenticated is now defined above for useTimezoneDetection
  
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
        
        {/* Timezone Selector Page */}
        <Route 
          path="/timezone" 
          element={
            isAuthenticated ? (
              <TimezoneSelectorPage />
            ) : (
              <Navigate to="/" replace />
            )
          } 
        />
        
        {/* Home Page - shown when not authenticated */}
        <Route 
          path="/" 
          element={
            isAuthenticated ? (
              <Navigate to="/dashboard" replace />
            ) : (
              <HomePage />
            )
          } 
        />
        
        {/* Dashboard - default for authenticated users */}
        <Route 
          path="/dashboard" 
          element={
            isAuthenticated ? (
              <DashboardPage />
            ) : (
              <Navigate to="/" replace />
            )
          } 
        />
        
        {/* Legacy routes - redirect to dashboard */}
        <Route 
          path="/weekly" 
          element={<Navigate to="/dashboard" replace />}
        />
        
        <Route 
          path="/tasks" 
          element={<Navigate to="/dashboard" replace />}
        />
        
        {/* Catch-all: redirect to home */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
