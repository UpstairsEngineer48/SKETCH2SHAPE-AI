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
  // slice(1): a leading '/' would make URL() discard the '/api' part of the base
  return new URL(normalizedPath.slice(1),`${API_BASE_URL}/`).toString();
}

const POLL_INTERVAL_MS=2000;
const MAX_WAIT_MS=30*60*1000;

async function readError(response,fallback){
  const raw=await response.text().catch(()=>'');
  try{
    const body=JSON.parse(raw);
    return body.error||body.detail||body.message||fallback;
  }catch{
    return raw?raw.slice(0,240):fallback;
  }
}

const sleep=(ms,signal)=>new Promise((resolve,reject)=>{
  const timer=setTimeout(resolve,ms);
  signal?.addEventListener('abort',()=>{clearTimeout(timer);reject(new DOMException('Cancelled','AbortError'));},{once:true});
});

export async function generateModel({image,prompt,inputType,signal,onProgress}){
  const formData=new FormData();
  formData.append('image',image,image.name||'sketch.png');
  formData.append('input_type',inputType);
  if(prompt?.trim())formData.append('prompt',prompt.trim());

  const submit=await fetch(joinApiPath(GENERATE_PATH),{method:'POST',body:formData,signal});
  if(!submit.ok)throw new Error(await readError(submit,`Generation request failed (${submit.status}).`));
  const {job_id:jobId}=await submit.json();
  if(!jobId)throw new Error('The API did not return a job id.');

  // The pipeline takes minutes, so poll a job instead of holding one request open.
  const deadline=Date.now()+MAX_WAIT_MS;
  while(Date.now()<deadline){
    await sleep(POLL_INTERVAL_MS,signal);
    const poll=await fetch(joinApiPath(`/jobs/${jobId}`),{signal});
    if(!poll.ok)throw new Error(await readError(poll,`Could not read job status (${poll.status}).`));
    const job=await poll.json();
    onProgress?.(job);

    if(job.status==='error')throw new Error(job.error||'Generation failed.');
    if(job.status==='done'){
      const format=(job.format||'glb').toLowerCase()==='obj'?'obj':'glb';
      return {
        modelUrl:resolveAssetUrl(job.model_url),
        format,
        filename:job.filename||`sketch2shape-output.${format}`,
        previewUrl:job.preview_url?resolveAssetUrl(job.preview_url):null,
        jobId,
        isObjectUrl:false,
      };
    }
  }
  throw new Error('Generation took longer than 30 minutes and was stopped.');
}

export async function checkApiHealth() {
  const response = await fetch(getHealthUrl(), { method: 'GET' });
  if (!response.ok) throw new Error(`Health check returned ${response.status}`);
  return response.json().catch(() => ({ status: 'ok' }));
}
