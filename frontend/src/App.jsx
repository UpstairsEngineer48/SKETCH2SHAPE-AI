import React from 'react';
import SiteHeader from './components/SiteHeader.jsx';
import SiteFooter from './components/SiteFooter.jsx';
import Landing from './pages/Landing.jsx';
import Studio from './pages/Studio.jsx';
import Architecture from './pages/Architecture.jsx';
import useHashRoute from './lib/useHashRoute.js';
import useTheme from './lib/useTheme.js';
import useApiHealth from './lib/useApiHealth.js';

export default function App() {
  const route = useHashRoute();
  const { theme, toggleTheme } = useTheme();
  const api = useApiHealth();

  return (
    <div className="app-shell">
      <SiteHeader route={route} theme={theme} onToggleTheme={toggleTheme} apiState={api.apiState} apiDetail={api.apiDetail} />
      {route === '/' && <Landing />}
      {route === '/architecture' && <Architecture />}
      {/* The studio stays mounted (just hidden) so a running job and its result
          survive a trip to the other pages. */}
      <div hidden={route !== '/studio'}><Studio api={api} /></div>
      <SiteFooter />
    </div>
  );
}
