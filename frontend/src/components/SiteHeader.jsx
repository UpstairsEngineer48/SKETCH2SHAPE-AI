import React from 'react';
import Icon from './Icon.jsx';

const SunIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
  </svg>
);
const MoonIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
  </svg>
);

const LINKS = [
  { path: '/', label: 'Home' },
  { path: '/studio', label: 'Studio' },
  { path: '/architecture', label: 'Architecture' },
];

const STATUS_LABEL = { checking: 'Checking API', online: 'API connected', warming: 'Model loading', offline: 'API offline' };

export default function SiteHeader({ route, theme, onToggleTheme, apiState, apiDetail }) {
  const nextThemeLabel = `Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`;
  return (
    <header className="topbar">
      <a className="brand" href="#/" aria-label="Sketch2Shape AI home">
        <span className="brand-mark"><Icon name="cube" size={22} /></span>
        <span className="brand-name">sketch<span>2</span>shape</span>
        <span className="brand-ai">AI</span>
      </a>
      <nav className="top-nav" aria-label="Main navigation">
        {LINKS.map((l) => (
          <a key={l.path} href={`#${l.path}`} className={route === l.path ? 'nav-active' : ''} aria-current={route === l.path ? 'page' : undefined}>{l.label}</a>
        ))}
      </nav>
      <div className="topbar-right">
        {apiState && (
          <div className={`api-status api-${apiState}`} title={apiDetail}>
            <span className="api-status-dot" />
            <span>{STATUS_LABEL[apiState]}</span>
          </div>
        )}
        <button type="button" className="theme-toggle" onClick={onToggleTheme} aria-label={nextThemeLabel} title={nextThemeLabel}>
          {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
        </button>
        {route !== '/studio'
          ? <a className="nav-cta" href="#/studio">Open studio <Icon name="arrow" size={14} /></a>
          : <span className="version-tag"> Ver<span>·</span> 1.0</span>}
      </div>
    </header>
  );
}
