import React from 'react';
import Icon from '../components/Icon.jsx';

// Real outputs from public/examples/car/ (same files the landing page shows).
const BASE = import.meta.env.BASE_URL || '/';
const ex = (file) => `${BASE}examples/car/${file}`.replace(/\/{2,}/g, '/');
const hideOnError = (e) => { e.currentTarget.style.display = 'none'; };

// Small preview of what a stage produces. The mesh stage has no image, so it
// gets a dark viewer-style tile with the cutout faded behind a cube icon.
function StageThumb({ out }) {
  if (!out.endsWith('.png')) {
    return (
      <span className="stage-thumb mesh">
        <img src={ex('foreground.png')} alt="" loading="lazy" onError={hideOnError} />
        <Icon name="cube" size={22} />
      </span>
    );
  }
  const kind = out.replace('.png', '');
  const tone = kind === 'control' ? 'dark' : kind === 'foreground' ? 'checker' : '';
  return (
    <span className={`stage-thumb ${tone}`}>
      <img src={ex(out)} alt="" loading="lazy" onError={hideOnError} />
    </span>
  );
}

// One run, end to end. Dashed lines animate in the direction of travel.
function FlowDiagram() {
  const Node = ({ x, title, sub, lines }) => (
    <g>
      <rect className="fd-box" x={x} y={70} width={200} height={150} rx={14} />
      <text className="fd-title" x={x + 20} y={104}>{title}</text>
      <text className="fd-sub" x={x + 20} y={124}>{sub}</text>
      {lines.map((l, i) => <text key={l} className="fd-item" x={x + 20} y={152 + i * 18}>{l}</text>)}
    </g>
  );
  return (
    <div className="panel fd-panel">
      <div className="fd-head"><span>REQUEST FLOW</span><small>one run, end to end</small></div>
      <div className="table-scroll">
        <svg className="fd-svg" viewBox="0 52 960 238" role="img" aria-label="The browser submits a sketch to the Flask API, receives a job id, then polls for status while the API runs the model workers and serves the finished files back.">
          <defs>
            <marker id="fd-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M1 1 L9 5 L1 9 z" className="fd-tip" />
            </marker>
            <marker id="fd-arrow-back" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M1 1 L9 5 L1 9 z" className="fd-tip back" />
            </marker>
          </defs>

          <Node x={10} title="Browser" sub="React · three.js" lines={['sketch canvas / upload', 'live stage previews', 'GLB viewer + export']} />
          <Node x={380} title="Flask API" sub="127.0.0.1:8000 · /api" lines={['validate upload', 'job thread + GPU lock', 'serves generated files']} />
          <Node x={750} title="Model workers" sub="in-process + isolated" lines={['preprocess + ControlNet', 'cutout (rembg)', 'image → 3D mesh']} />

          {/* browser <-> API */}
          <text className="fd-label" x={295} y={102} textAnchor="middle">POST /generate</text>
          <path className="fd-line" d="M214 110 H374" markerEnd="url(#fd-arrow)" />
          <text className="fd-label back" x={295} y={142} textAnchor="middle">202 · job_id</text>
          <path className="fd-line back" d="M376 150 H216" markerEnd="url(#fd-arrow-back)" />
          <text className="fd-label" x={295} y={182} textAnchor="middle">poll /jobs/:id · 2 s</text>
          <path className="fd-line" d="M214 190 H374" markerStart="url(#fd-arrow)" markerEnd="url(#fd-arrow)" />

          {/* API <-> workers */}
          <text className="fd-label" x={665} y={117} textAnchor="middle">run steps 1 to 4</text>
          <path className="fd-line" d="M584 125 H744" markerEnd="url(#fd-arrow)" />
          <text className="fd-label back" x={665} y={167} textAnchor="middle">files on disk</text>
          <path className="fd-line back" d="M746 175 H586" markerEnd="url(#fd-arrow-back)" />

          {/* finished model back to the viewer */}
          <path className="fd-line back" d="M480 226 V272 H110 V228" markerEnd="url(#fd-arrow-back)" />
          <text className="fd-label back" x={295} y={264} textAnchor="middle">GET /files/:id/model.glb · into the viewer</text>
        </svg>
      </div>
      <p className="fd-caption">The browser never holds a request open for the minutes a run takes. It submits once, then polls the job.</p>
    </div>
  );
}

const TIERS = [
  {
    icon: 'monitor', tag: 'CLIENT', title: 'Browser', sub: 'React 18 · Vite · three.js',
    items: ['Sketch canvas: brush, eraser, reset', 'Image upload + optional prompt', '3D engine picker', 'Job polling and live progress', 'GLB viewer: orbit, zoom, fullscreen'],
  },
  {
    icon: 'server', tag: 'API', title: 'Flask backend', sub: '127.0.0.1:8000 · proxied at /api',
    items: ['Validates the upload', 'Starts a background job thread', 'One GPU pipeline at a time (lock)', 'Reports step, label and elapsed time', 'Serves the generated files'],
  },
  {
    icon: 'cpu', tag: 'MODELS', title: 'Model workers', sub: 'In-process and isolated',
    items: ['SD 1.5 + ControlNet (diffusers)', 'rembg background removal', 'Hunyuan3D-2mini in its own env', 'InstantMesh in its own env', 'InstantMesh Hugging Face Space'],
  },
];

const STAGES = [
  {
    n: '01', title: 'Preprocess', file: 'base/preprocessing.py', icon: 'sliders',
    points: [
      'Flattens transparency onto white and pads to a square without stretching.',
      'Classifies the input as a sketch or a photo from its colour and tone distribution. Drawings from the canvas skip the guess.',
      'Sketch: Otsu threshold, thicken thin lines, crop to the drawing and re-frame it. Photo: Canny edges with a relaxing threshold ladder.',
      'Rejects an empty sketch with a clear message.',
    ],
    out: 'control.png', outNote: '512 px, white lines on black',
  },
  {
    n: '02', title: 'Sketch-guided render', file: 'base/controlnet.py', icon: 'pen',
    points: [
      'Stable Diffusion 1.5 with a ControlNet: Scribble for hand drawings, Canny for photo edges.',
      'Prompt plus a studio-render style suffix and a negative prompt that keeps one centred object on a plain background.',
      'CUDA: fp16, 20 steps. CPU: LCM-LoRA, 6 steps. Optional CPU offload for small GPUs.',
      'Photos skip this stage by default, since re-rendering a real picture only degrades it.',
    ],
    out: 'rendered.png', outNote: 'refined product-style image',
  },
  {
    n: '03', title: 'Cutout', file: 'base/background_removal.py', icon: 'scissors',
    points: [
      'rembg with BiRefNet, falling back to ISNet and then U2Net if a model is unavailable.',
      'Alpha matting, mask clean-up, hole filling and colour de-fringing, each with a safe fallback.',
      'Keeps the main object, centres it and scales it to fill about 85% of a square frame.',
    ],
    out: 'foreground.png', outNote: 'RGBA, square, centred',
  },
  {
    n: '04', title: 'Image to 3D', file: 'base/mesh.py', icon: 'cube',
    points: [
      'The render model is parked on the CPU first, so the mesh model gets the whole GPU.',
      'Tries the selected engine, or the whole fallback chain in Auto mode.',
      'Returns the first working .glb (or .obj) and records which engine produced it.',
    ],
    out: 'model.glb', outNote: 'served to the viewer and download',
  },
];

const CHAIN = [
  { name: 'Hunyuan3D-2mini', where: 'Local GPU · separate process', note: 'Shape only, fastest to set up' },
  { name: 'InstantMesh (local)', where: 'Local GPU · own environment', note: 'Needs S2S_IM_DIR' },
  { name: 'InstantMesh (API)', where: 'Hugging Face Space', note: 'Needs internet, HF_TOKEN recommended' },
];

const API = [
  ['POST', '/api/generate', 'Multipart image, optional prompt, input_type and backend. Returns a job_id with 202.'],
  ['GET', '/api/jobs/<id>', 'Status, step, label, elapsed time, and model_url once finished.'],
  ['GET', '/api/files/<id>/<name>', 'Generated files: model.glb, rendered.png and so on.'],
  ['GET', '/api/health', 'Model loaded, device and fast-mode flags for the status light.'],
  ['GET', '/api/backends', 'Available 3D engines and why one is unavailable.'],
  ['POST', '/api/client-log', 'Batched browser log events, written to frontend.log.'],
];

const MODELS = [
  ['Stable Diffusion 1.5', 'Image generation', 'stable-diffusion-v1-5', 'Local'],
  ['ControlNet Scribble and Canny', 'Follow the sketch or edges', 'lllyasviel/sd-controlnet-*', 'Local'],
  ['LCM-LoRA SD1.5', '6-step sampler on CPU', 'latent-consistency', 'Local'],
  ['rembg (BiRefNet, ISNet, U2Net)', 'Background removal', 'rembg', 'Local'],
  ['Hunyuan3D-2mini', 'Image to 3D shape', 'tencent/Hunyuan3D-2mini', 'Local'],
  ['InstantMesh', 'Image to 3D mesh', 'TencentARC/InstantMesh', 'Local or HF Space'],
  ['OpenCV, Pillow, NumPy', 'Pre-processing', 'open source libraries', 'Local'],
  ['Flask, diffusers, trimesh', 'API, pipeline, mesh I/O', 'open source libraries', 'Local'],
];

const DECISIONS = [
  { t: 'Job polling, not one long request', d: 'A run takes minutes. The client gets a job id and polls, so progress is visible and nothing times out.' },
  { t: 'Heavy models in subprocesses', d: 'Hunyuan3D and InstantMesh pin their own library versions. Running them in separate processes keeps the backend env clean and frees all VRAM on exit.' },
  { t: 'Fallback chain for the mesh step', d: 'A missing install, a full GPU or an API quota error moves on to the next engine instead of failing the job.' },
  { t: 'Sketch stays the source of truth', d: 'ControlNet conditions on your strokes, so the prompt styles the object rather than replacing it.' },
  { t: 'One GPU job at a time', d: 'A lock queues requests, which avoids out-of-memory crashes on a single GPU.' },
  { t: 'Studio stays mounted', d: 'Switching pages does not cancel a running job or lose the finished model.' },
];

export default function Architecture() {
  return (
    <main className="page-content ar">
      <section className="ar-hero">
        <div className="eyebrow"><span className="eyebrow-line" /> SYSTEM ARCHITECTURE</div>
        <h1>How a sketch<br /><span>becomes a mesh.</span></h1>
        <p>A React front end, a small Flask API, and a chain of pretrained models. Every stage writes its result to disk, so each step can be inspected on its own.</p>
      </section>

      {/* OVERVIEW */}
      <section className="lp-section" aria-labelledby="ov-h">
        <div className="lp-section-head">
          <div>
            <div className="section-kicker"><span>01</span> OVERVIEW</div>
            <h2 id="ov-h">Three layers</h2>
          </div>
        </div>
        <FlowDiagram />
        <div className="ar-tiers">
          {TIERS.map((t, i) => (
            <React.Fragment key={t.tag}>
              <article className="tier-card">
                <header>
                  <span className="feature-icon"><Icon name={t.icon} size={18} /></span>
                  <div><span className="tier-tag">{t.tag}</span><h3>{t.title}</h3><small>{t.sub}</small></div>
                </header>
                <ul>{t.items.map((x) => <li key={x}>{x}</li>)}</ul>
              </article>
              {i < TIERS.length - 1 && (
                <div className="tier-link" aria-hidden="true">
                  <span>{i === 0 ? 'upload' : 'run'}</span>
                  <Icon name="arrow" size={16} />
                  <span>{i === 0 ? 'job status' : 'files'}</span>
                </div>
              )}
            </React.Fragment>
          ))}
        </div>
      </section>

      {/* PIPELINE */}
      <section className="lp-section" aria-labelledby="pl-h">
        <div className="lp-section-head">
          <div>
            <div className="section-kicker"><span>02</span> PIPELINE</div>
            <h2 id="pl-h">Four stages per job</h2>
            <p>Each job gets its own folder under <code>backend/base/outputs/&lt;job_id&gt;/</code>.</p>
          </div>
        </div>
        <ol className="ar-stages">
          {STAGES.map((s) => (
            <li key={s.n} className="stage-row">
              <div className="stage-rail"><span className="workflow-number">{s.n}</span><i /></div>
              <article className="panel stage-body">
                <header>
                  <span className="feature-icon"><Icon name={s.icon} size={18} /></span>
                  <div><h3>{s.title}</h3><code>{s.file}</code></div>
                  <div className="stage-out">
                    <StageThumb out={s.out} />
                    <div className="stage-out-text"><small>OUTPUT</small><strong>{s.out}</strong><em>{s.outNote}</em></div>
                  </div>
                </header>
                <ul>{s.points.map((p) => <li key={p}>{p}</li>)}</ul>
              </article>
            </li>
          ))}
        </ol>
      </section>

      {/* CHAIN */}
      <section className="lp-section" aria-labelledby="ch-h">
        <div className="lp-section-head">
          <div>
            <div className="section-kicker"><span>03</span> 3D ENGINES</div>
            <h2 id="ch-h">Fallback chain</h2>
            <p>Default order, set with <code>S2S_MESH</code>. Pick a single engine in the studio to switch the fallback off.</p>
          </div>
        </div>
        <div className="ar-chain">
          {CHAIN.map((c, i) => (
            <React.Fragment key={c.name}>
              <article className="chain-card">
                <span className="chain-n">{i + 1}</span>
                <h3>{c.name}</h3>
                <p>{c.where}</p>
                <small>{c.note}</small>
              </article>
              {i < CHAIN.length - 1 && <div className="chain-arrow" aria-hidden="true"><small>if it fails</small><Icon name="arrow" size={16} /></div>}
            </React.Fragment>
          ))}
        </div>
      </section>

      {/* API */}
      <section className="lp-section" aria-labelledby="api-h">
        <div className="lp-section-head">
          <div>
            <div className="section-kicker"><span>04</span> API</div>
            <h2 id="api-h">Endpoints</h2>
            <p>Job states: <code>queued</code> → <code>running</code> (steps 1 to 4) → <code>done</code> or <code>error</code>.</p>
          </div>
        </div>
        <div className="panel table-panel">
          <div className="table-scroll">
            <table className="ar-table">
              <thead><tr><th>Method</th><th>Route</th><th>Purpose</th></tr></thead>
              <tbody>
                {API.map(([m, r, d]) => (
                  <tr key={r}><td><span className={`verb verb-${m.toLowerCase()}`}>{m}</span></td><td><code>{r}</code></td><td>{d}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* MODELS */}
      <section className="lp-section" aria-labelledby="md-h">
        <div className="lp-section-head">
          <div>
            <div className="section-kicker"><span>05</span> DISCLOSURE</div>
            <h2 id="md-h">Models and components used</h2>
            <p>All models are pretrained. Nothing was trained for this project.</p>
          </div>
        </div>
        <div className="panel table-panel">
          <div className="table-scroll">
            <table className="ar-table">
              <thead><tr><th>Component</th><th>Used for</th><th>Source</th><th>Runs</th></tr></thead>
              <tbody>
                {MODELS.map(([a, b, c, d]) => (
                  <tr key={a}><td><strong>{a}</strong></td><td>{b}</td><td><code>{c}</code></td><td>{d}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* DECISIONS */}
      <section className="lp-section" aria-labelledby="dc-h">
        <div className="lp-section-head">
          <div>
            <div className="section-kicker"><span>06</span> DECISIONS</div>
            <h2 id="dc-h">Why it is built this way</h2>
          </div>
        </div>
        <div className="lp-features">
          {DECISIONS.map((d) => (
            <article key={d.t} className="feature-card">
              <h3>{d.t}</h3>
              <p>{d.d}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="lp-cta panel">
        <div>
          <div className="section-kicker"><span>07</span> TRY IT</div>
          <h2>See the pipeline run.</h2>
        </div>
        <a className="btn-primary big" href="#/studio"><Icon name="sparkles" size={18} /> Open the studio <Icon name="arrow" size={16} /></a>
      </section>
    </main>
  );
}