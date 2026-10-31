import { useEffect, useState } from 'react';

// Tiny hash router: #/  (landing)  #/studio  #/architecture.
// No dependency, and it works on any static host or the Vite dev server.
export const ROUTES = ['/', '/studio', '/architecture'];

const parse = () => {
  const raw = window.location.hash.replace(/^#/, '').split('?')[0] || '/';
  return ROUTES.includes(raw) ? raw : '/';
};

export function navigate(path) {
  window.location.hash = path;
}

export default function useHashRoute() {
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const onChange = () => {
      setRoute(parse());
      window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
    };
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}
