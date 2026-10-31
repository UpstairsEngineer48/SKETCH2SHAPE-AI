import React, { useState } from 'react';
import Icon from '../components/Icon.jsx';
import ModelViewer from '../components/ModelViewer.jsx';

const BASE = import.meta.env.BASE_URL || '/';
const ex = (name, file) => `${BASE}examples/${name}/${file}`.replace(/\/{2,}/g, '/');

// Real outputs of this pipeline (copied from backend/base/outputs/<job_id>/).
const EXAMPLES = {
  heart: { label: 'Apples', job: '0dcebb7e35bf', prompt: 'Apples' },
  car: { label: 'Car', job: '583e17253c09', prompt: 'no prompt' },
};

const STEPS = [
  { key: 'sketch', n: '01', title: 'Your sketch', text: 'Drawn in the app or uploaded as an image.' },
  { key: 'control', n: '02', title: 'Control map', text: 'Strokes cleaned into one thin white line each.' },
  { key: 'rendered', n: '03', title: 'Rendered object', text: 'ControlNet + Stable Diffusion paint the object.' },
  { key: 'foreground', n: '04', title: 'Clean cutout', text: 'Background removed, object centred for 3D.' },
];

const FEATURES = [
  { icon: 'pen', title: 'Draw or upload', text: 'Sketch on the built-in canvas with brush, eraser and reset, or drop in an existing image.' },
  { icon: 'sparkles', title: 'Prompt is optional', text: 'Add a colour or style hint if you like. It guides the render step, and a sketch alone is always enough.' },
  { icon: 'layers', title: 'Sketch stays in charge', text: 'ControlNet follows your strokes, so the result is your object, not whatever the prompt imagines.' },
  { icon: 'branch', title: 'Three 3D engines', text: 'Hunyuan3D, local InstantMesh, or the InstantMesh API. Auto mode falls back to the next one on failure.' },
  { icon: 'cube', title: 'Real geometry', text: 'The output is a mesh with depth and volume, not a flat image or a textured plane.' },
  { icon: 'download', title: 'Inspect and export', text: 'Orbit, zoom and go fullscreen in the browser, then download a .glb for Blender or any 3D tool.' },
];

const USES = ['Product design', 'Architecture & interiors', 'Games & VFX', '3D printing prep', 'Education'];

export default function Landing() {
  const [sel, setSel] = useState('heart');
  const [loaded3d, setLoaded3d] = useState({});
  const cur = EXAMPLES[sel];
  const show3d = Boolean(loaded3d[sel]);

  return (
    <main className="page-content lp">
      {/* HERO */}
      <section className="lp-hero">
        <div className="lp-hero-copy">
          <div className="eyebrow"><span className="eyebrow-line" /> GENERATIVE 3D WORKSPACE</div>
          <h1>From a sketch<br /><span>to a shape.</span></h1>
          <p>Draw a rough idea or upload one. Sketch2Shape reads your outlines, renders the object, and reconstructs it as a 3D asset you can rotate, inspect and export.</p>
          <div className="lp-cta-row">
            <a className="btn-primary" href="#/studio"><Icon name="sparkles" size={17} /> Start creating <Icon name="arrow" size={15} /></a>
            <a className="btn-ghost" href="#/architecture">See how it works</a>
          </div>
          <ul className="lp-meta">
            <li><Icon name="check" size={13} /> One view is enough</li>
            <li><Icon name="check" size={13} /> Exports .glb</li>
            <li><Icon name="check" size={13} /> Runs on your own GPU</li>
          </ul>
        </div>

        <div className="lp-hero-stage" aria-hidden="true">
          <div className="stage-glow" />
          <figure className="stage-card stage-sketch">
            <img src={ex('car', 'sketch.png')} alt="" />
            <figcaption>SKETCH</figcaption>
          </figure>
          <div className="stage-arrow"><Icon name="arrow" size={18} /></div>
          <figure className="stage-card stage-model">
            <img src={ex('car', 'foreground.png')} alt="" />
            <figcaption><span className="live-dot" /> 3D · GLB</figcaption>
          </figure>
          <span className="stage-chip chip-a">ControlNet</span>
          <span className="stage-chip chip-b">Image-to-3D</span>
        </div>
      </section>

      {/* REAL RUN */}
      <section className="lp-section" aria-labelledby="run-h">
        <div className="lp-section-head">
          <div>
            <div className="section-kicker"><span>01</span> REAL OUTPUT</div>
            <h2 id="run-h">One sketch, four stages</h2>
            <p>These are untouched results from this project&apos;s own pipeline.</p>
          </div>
          <div className="seg" role="tablist" aria-label="Choose an example">
            {Object.entries(EXAMPLES).map(([k, v]) => (
              <button key={k} type="button" role="tab" aria-selected={sel === k} className={sel === k ? 'selected' : ''} onClick={() => setSel(k)}>{v.label}</button>
            ))}
          </div>
        </div>

        <div className="lp-run">
          <div className="lp-run-steps">
            {STEPS.map((s) => (
              <figure key={s.key} className="run-step">
                <div className={`run-thumb ${s.key === 'foreground' ? 'checker' : ''} ${s.key === 'control' ? 'dark' : ''}`}>
                  <img src={ex(sel, `${s.key}.png`)} alt={`${cur.label} ${s.title.toLowerCase()}`} loading="lazy" />
                </div>
                <figcaption><span>{s.n}</span><strong>{s.title}</strong><small>{s.text}</small></figcaption>
              </figure>
            ))}
          </div>

          <div className="lp-run-viewer">
            {show3d ? (
              <ModelViewer modelUrl={ex(sel, 'model.glb')} format="glb" isGenerating={false} />
            ) : (
              <div className="viewer-shell lp-viewer-idle">
                <img className="idle-bg" src={ex(sel, 'foreground.webp')} alt="" />
                <div className="idle-overlay">
                  <button type="button" className="btn-primary" onClick={() => setLoaded3d((p) => ({ ...p, [sel]: true }))}>
                    <Icon name="cube" size={17} /> Load interactive 3D
                  </button>
                  <small>Opens the exported .glb, about {sel === 'heart' ? '4.7' : '3.2'} MB</small>
                </div>
              </div>
            )}
            <div className="run-meta">
              <span><Icon name="file" size={13} /> model.glb</span>
              <span>prompt: <code>{cur.prompt}</code></span>
              <span>job <code>{cur.job}</code></span>
              <a href={ex(sel, 'model.glb')} download={`sketch2shape_${cur.job}.glb`}><Icon name="download" size={13} /> Download</a>
            </div>
          </div>
        </div>
      </section>

      {/* FEATURES */}
      <section className="lp-section" aria-labelledby="feat-h">
        <div className="lp-section-head">
          <div>
            <div className="section-kicker"><span>02</span> WHAT IT DOES</div>
            <h2 id="feat-h">Built to get you from idea to asset</h2>
          </div>
        </div>
        <div className="lp-features">
          {FEATURES.map((f) => (
            <article key={f.title} className="feature-card">
              <span className="feature-icon"><Icon name={f.icon} size={18} /></span>
              <h3>{f.title}</h3>
              <p>{f.text}</p>
            </article>
          ))}
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="lp-section" aria-labelledby="how-h">
        <div className="lp-how panel">
          <div className="lp-section-head tight">
            <div>
              <div className="section-kicker"><span>03</span> HOW IT WORKS</div>
              <h2 id="how-h">Three steps for you, four stages for the machine</h2>
            </div>
            <a className="text-link" href="#/architecture">Full architecture <Icon name="arrow" size={13} /></a>
          </div>
          <ol className="lp-how-steps">
            <li><span className="workflow-number">01</span><div><strong>Give it a sketch</strong><p>Draw on the canvas or upload an image. Add a short description if you want to steer colour or material.</p></div></li>
            <li><span className="workflow-number">02</span><div><strong>Generate</strong><p>The app cleans the strokes, renders the object, cuts it out and reconstructs the mesh. Progress is shown live.</p></div></li>
            <li><span className="workflow-number">03</span><div><strong>Inspect and export</strong><p>Spin the model in the viewer, then download the .glb to refine in your own 3D software.</p></div></li>
          </ol>
        </div>
      </section>

      {/* USE CASES + CTA */}
      <section className="lp-cta panel">
        <div>
          <div className="section-kicker"><span>04</span> USE IT FOR</div>
          <h2>Start with a rough outline.</h2>
          <div className="lp-uses">{USES.map((u) => <span key={u}>{u}</span>)}</div>
        </div>
        <a className="btn-primary big" href="#/studio"><Icon name="sparkles" size={18} /> Open the studio <Icon name="arrow" size={16} /></a>
      </section>
    </main>
  );
}