import { useEffect, useRef, useState } from 'react';
import { checkApiHealth } from './api.js';
import { log } from './logger.js';

// Polls /api/health until the image model is loaded. Lives at the app root so the
// status light works on every page and survives page switches.
export default function useApiHealth() {
  const [apiState, setApiState] = useState('checking');
  const [apiDetail, setApiDetail] = useState('Checking the generation API');
  const last = useRef(null);

  useEffect(() => {
    if (last.current === apiState) return;
    log[apiState === 'offline' ? 'warn' : 'info'](`API status: ${apiState}`, { detail: apiDetail });
    last.current = apiState;
  }, [apiState, apiDetail]);

  useEffect(() => {
    let active = true;
    let timer = null;
    const check = () => {
      checkApiHealth()
        .then((health) => {
          if (!active) return;
          if (health?.error) {
            setApiState('offline');
            setApiDetail(`Model failed to load: ${health.error}`);
          } else if (health?.model_loaded === false) {
            setApiState('warming');
            setApiDetail('API online · model weights are loading (first start downloads several GB)');
          } else {
            setApiState('online');
            setApiDetail(health?.device === 'cpu' ? 'Connected · running on CPU, expect slow generation' : 'Generation API is reachable');
            return;
          }
          timer = setTimeout(check, 4000);
        })
        .catch(() => {
          if (!active) return;
          setApiState('offline');
          setApiDetail('Could not reach the API at the configured address');
          timer = setTimeout(check, 4000);
        });
    };
    check();
    return () => { active = false; clearTimeout(timer); };
  }, []);

  return { apiState, apiDetail, setApiState, setApiDetail };
}
