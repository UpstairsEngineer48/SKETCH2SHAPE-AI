const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
const CONDITIONER_PATH = import.meta.env.VITE_CONDITIONER_PATH || '/debug/conditioner';
const HEALTH_PATH = import.meta.env.VITE_HEALTH_PATH || '/health';

function joinApiPath(path) {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${cleanPath}`;
}

function resolveAssetUrl(url) {
  if (!url) return null;
  if (/^(https?:|blob:|data:)/i.test(url)) return url;
  const normalizedPath = url.startsWith('/') ? url : `/${url}`;
  if (API_BASE_URL.startsWith('/')) return `${API_BASE_URL}${normalizedPath}`;
  return new URL(normalizedPath, `${API_BASE_URL}/`).toString();
}

async function readError(response) {
  let detail = `Request failed (${response.status}).`;
  try {
    const body = await response.json();
    detail = body.detail || body.message || detail;
  } catch {
    const text = await response.text().catch(() => '');
    if (text) detail = text.slice(0, 300);
  }
  return detail;
}

export async function runConditioner({ image, prompt, inputType, signal }) {
  const formData = new FormData();
  formData.append('image', image, image.name || 'sketch.png');
  // A drawing made on the canvas should never be sent through semantic photo removal.
  formData.append('input_type', ['auto', 'photo', 'sketch'].includes(inputType) ? inputType : 'auto');
  formData.append('remove_background', 'true');
  if (prompt?.trim()) formData.append('prompt', prompt.trim());

  const response = await fetch(joinApiPath(CONDITIONER_PATH), {
    method: 'POST',
    body: formData,
    signal,
  });
  if (!response.ok) throw new Error(await readError(response));

  const payload = await response.json();
  if (payload.status !== 'conditioner_ok') {
    throw new Error('The backend response did not confirm successful image conditioning.');
  }

  const artifacts = Object.fromEntries(
    Object.entries(payload.artifact_urls || {}).map(([key, url]) => [key, resolveAssetUrl(url)]),
  );
  return { ...payload, artifacts };
}

export async function checkApiHealth() {
  const response = await fetch(joinApiPath(HEALTH_PATH), { method: 'GET' });
  if (!response.ok) throw new Error(`Health check returned ${response.status}`);
  return response.json().catch(() => ({ status: 'ok' }));
}
