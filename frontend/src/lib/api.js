const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
const GENERATE_PATH = import.meta.env.VITE_GENERATE_PATH || '/generate';
const HEALTH_PATH = import.meta.env.VITE_HEALTH_PATH || '/health';

function joinApiPath(path) {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${cleanPath}`;
}

export function getHealthUrl() {
  return joinApiPath(HEALTH_PATH);
}

function resolveAssetUrl(url) {
  if (!url) return null;
  if (/^(https?:|blob:|data:)/i.test(url)) return url;
  // When using the Vite /api proxy, route backend-served assets through it too.
  const normalizedPath = url.startsWith('/') ? url : `/${url}`;
  if (API_BASE_URL.startsWith('/')) {
    return `${API_BASE_URL}${normalizedPath}`;
  }
  return new URL(normalizedPath, `${API_BASE_URL}/`).toString();
}

export async function generateModel({ image, prompt, inputType, signal }) {
  const formData = new FormData();
  formData.append('image', image, image.name || 'sketch.png');
  formData.append('input_type', inputType);
  if (prompt?.trim()) formData.append('prompt', prompt.trim());

  const response = await fetch(joinApiPath(GENERATE_PATH), {
    method: 'POST',
    body: formData,
    signal,
  });

  if (!response.ok) {
    let detail = `Generation request failed (${response.status}).`;
    try {
      const errorBody = await response.json();
      detail = errorBody.detail || errorBody.message || detail;
    } catch {
      // The server may return a plain-text error or an empty response.
      const text = await response.text().catch(() => '');
      if (text) detail = text.slice(0, 240);
    }
    throw new Error(detail);
  }

  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('model/gltf-binary') || contentType.includes('application/octet-stream')) {
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    return { modelUrl: url, format: 'glb', filename: 'sketch2shape-output.glb', isObjectUrl: true };
  }

  const payload = await response.json();
  const rawModelUrl = payload.model_url || payload.glb_url || payload.obj_url || payload.asset_url || payload.output_url;
  if (!rawModelUrl) {
    throw new Error('The API responded, but did not include a model URL. Return model_url, glb_url, obj_url, or asset_url.');
  }

  const resolvedModelUrl = resolveAssetUrl(rawModelUrl);
  const responseFormat = (payload.format || payload.file_format || '').toLowerCase();
  const extension = rawModelUrl.split('?')[0].split('.').pop()?.toLowerCase();
  const format = responseFormat.includes('obj') || extension === 'obj' ? 'obj' : 'glb';

  return {
    modelUrl: resolvedModelUrl,
    format,
    filename: payload.filename || payload.file_name || `sketch2shape-output.${format}`,
    previewUrl: payload.preview_url ? resolveAssetUrl(payload.preview_url) : null,
    jobId: payload.job_id || payload.id || null,
    note: payload.note || '',
    promptUsed: Boolean(payload.prompt_used),
    mesh: payload.mesh || null,
    isObjectUrl: false,
  };
}

export async function checkApiHealth() {
  const response = await fetch(getHealthUrl(), { method: 'GET' });
  if (!response.ok) throw new Error(`Health check returned ${response.status}`);
  return response.json().catch(() => ({ status: 'ok' }));
}
