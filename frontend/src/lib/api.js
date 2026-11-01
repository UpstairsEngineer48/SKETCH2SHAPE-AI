import { log } from './logger.js';

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

// fetch + timing + log line. Polling calls pass quiet=true so they only log on failure.
async function loggedFetch(url,options={},{quiet=false}={}){
  const method=options.method||'GET';
  const started=performance.now();
  try{
    const response=await fetch(url,options);
    const ms=Math.round(performance.now()-started);
    if(!response.ok)log.warn(`${method} ${url} -> ${response.status}`,{ms});
    else if(!quiet)log.info(`${method} ${url} -> ${response.status}`,{ms});
    return response;
  }catch(error){
    if(error?.name==='AbortError'){log.info(`${method} ${url} aborted`);throw error;}
    log.error(`${method} ${url} failed (network)`,{ms:Math.round(performance.now()-started),message:error.message});
    throw error;
  }
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

export async function getBackends(){
  const response=await loggedFetch(joinApiPath('/backends'),{},{quiet:true});
  if(!response.ok)throw new Error(`Backends request returned ${response.status}`);
  return (await response.json()).backends||[];
}

export async function generateModel({image,prompt,inputType,backend,signal,onProgress}){
  const formData=new FormData();
  formData.append('image',image,image.name||'sketch.png');
  formData.append('input_type',inputType);
  formData.append('backend',backend||'auto');
  if(prompt?.trim())formData.append('prompt',prompt.trim());

  log.info('Generate: submitting',{inputType,backend:backend||'auto',promptLength:prompt?.trim().length||0,imageBytes:image.size});
  const submit=await loggedFetch(joinApiPath(GENERATE_PATH),{method:'POST',body:formData,signal});
  if(!submit.ok)throw new Error(await readError(submit,`Generation request failed (${submit.status}).`));
  const {job_id:jobId}=await submit.json();
  if(!jobId)throw new Error('The API did not return a job id.');
  log.info('Generate: job accepted',{jobId});
  const startedAt=performance.now();
  let lastStep=null;
  let lastLabel=null;

  // The pipeline takes minutes, so poll a job instead of holding one request open.
  const deadline=Date.now()+MAX_WAIT_MS;
  while(Date.now()<deadline){
    await sleep(POLL_INTERVAL_MS,signal);
    const poll=await loggedFetch(joinApiPath(`/jobs/${jobId}`),{signal},{quiet:true});
    if(!poll.ok)throw new Error(await readError(poll,`Could not read job status (${poll.status}).`));
    const job=await poll.json();
    onProgress?.(job);
    // log only when something changed, not every 2 s
    if(job.step!==lastStep||job.label!==lastLabel){
      log.info(`Job ${jobId}: ${job.label||job.status}`,{status:job.status,step:`${job.step}/${job.total_steps}`,elapsed:job.elapsed});
      lastStep=job.step;lastLabel=job.label;
    }

    if(job.status==='error'){
      log.error(`Job ${jobId}: failed`,{error:job.error,elapsed:job.elapsed});
      throw new Error(job.error||'Generation failed.');
    }
    if(job.status==='done'){
      const format=(job.format||'glb').toLowerCase()==='obj'?'obj':'glb';
      log.info(`Job ${jobId}: done`,{backend:job.backend,format,totalSeconds:Math.round((performance.now()-startedAt)/1000)});
      return {
        modelUrl:resolveAssetUrl(job.model_url),
        format,
        filename:job.filename||`sketch2shape-output.${format}`,
        previewUrl:job.preview_url?resolveAssetUrl(job.preview_url):null,
        jobId,
        backend:job.backend||null,
        isObjectUrl:false,
      };
    }
  }
  log.error(`Job ${jobId}: gave up after 30 minutes`);
  throw new Error('Generation took longer than 30 minutes and was stopped.');
}

export async function checkApiHealth() {
  const response = await loggedFetch(getHealthUrl(), { method: 'GET' }, { quiet: true });
  if (!response.ok) throw new Error(`Health check returned ${response.status}`);
  return response.json().catch(() => ({ status: 'ok' }));
}