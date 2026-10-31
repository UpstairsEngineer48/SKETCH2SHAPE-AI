import React from 'react';
import Icon from './Icon.jsx';

export default function SiteFooter() {
  return (
    <footer className="footer">
      <a className="footer-brand" href="#/">
        <span className="brand-mark small-mark"><Icon name="cube" size={16} /></span>
        sketch<span>2</span>shape <i>AI</i>
      </a>
      <p className="footer-credit">
        Built for creative prototyping
        <span className="footer-separator">·</span>
        TeamTabahi
        <span className="footer-separator">·</span>
        TechZephyr 4.0
        <span className="footer-separator">·</span>
        <span className="footer-year">2026</span>
      </p>
      <nav className="footer-links" aria-label="Footer">
        <a href="#/">Home</a>
        <a href="#/studio">Studio</a>
        <a href="#/architecture">Architecture</a>
      </nav>
    </footer>
  );
}
