import React from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource/manrope/400.css'
import '@fontsource/manrope/500.css'
import '@fontsource/manrope/600.css'
import '@fontsource/manrope/700.css'
import App from './App'
import { ErrorBoundary } from './components/ErrorBoundary'
import './styles/design-system.css'
import './styles/tokens.css'
import './styles/sheets.css'
import './styles/shell-v2.css'
import './styles/index.css'
import './components/ui/ui.css'
import './components/home/home.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
)
