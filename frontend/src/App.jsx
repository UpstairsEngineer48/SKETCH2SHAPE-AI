import React, { useEffect, useRef, useState } from 'react';
import Icon from './components/Icon.jsx';
import SketchCanvas from './components/SketchCanvas.jsx';
import UploadPanel from './components/UploadPanel.jsx';
import ModelViewer from './components/ModelViewer.jsx';
import { checkApiHealth, runConditioner } from './lib/api.js';

const PROMPT_SUGGESTIONS = ['Product design', 'Matte ceramic', 'Soft rounded edges', 'Studio lighting'];

function formatLabel(format) {
  return (format || 'GLB').toUpperCase();
}

const getInitialTheme = () => {
  try {
    const saved = localStorage.getItem('theme');
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {}
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
};

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

export default function App() {
  const sketchRef = useRef(null);
  const [theme, setTheme] = useState(getInitialTheme);
  const [inputMode, setInputMode] = useState('draw');
  const [uploadInputType, setUploadInputType] = useState('auto');
  const [uploadedFile, setUploadedFile] = useState(null);
  const [canvasHasContent, setCanvasHasContent] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [generationState, setGenerationState] = useState('idle');
  const [output, setOutput] = useState(null);
  const [preprocessingResult, setPreprocessingResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [apiState, setApiState] = useState('checking');
  const [apiDetail, setApiDetail] = useState('Checking the local backend API');

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('theme', theme); } catch {}
  }, [theme]);

  useEffect(() => {
    let active = true;
    checkApiHealth()
      .then((health) => {
        if (!active) return;
        if (health?.conditioner_model_available === false) {
          setApiState('warming');
          setApiDetail('Backend online · DINOv2 ONNX file is missing; download it from the backend folder');
        } else {
          setApiState('online');
          setApiDetail('Backend connected · ONNX Runtime CPU');
        }
      })
      .catch(() => {
        if (!active) return;
        setApiState('offline');
        setApiDetail('Could not reach the API at the configured address');
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    return () => {
      if (output?.isObjectUrl && output.modelUrl) URL.revokeObjectURL(output.modelUrl);
    };
  }, [output]);

  const canGenerate = inputMode === 'draw' ? canvasHasContent : Boolean(uploadedFile);

  const toggleTheme = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'));
  const nextThemeLabel = `Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`;

  const appendPromptSuggestion = (suggestion) => {
    setPrompt((current) => {
      const clean = current.trim();
      return clean ? `${clean}, ${suggestion.toLowerCase()}` : suggestion;
    });
  };

  const handleGenerate = async () => {
    if (generationState === 'generating') return;
    setErrorMessage('');
    let imageFile = uploadedFile;

    try {
      if (inputMode === 'draw') {
        imageFile = await sketchRef.current?.toFile();
      }
      if (!imageFile) {
        setErrorMessage(inputMode === 'draw' ? 'Draw a sketch on the canvas before generating.' : 'Upload a sketch image before generating.');
        return;
      }

      setGenerationState('generating');
      setApiDetail('Preprocessing image and running DINOv2 on CPU');
      const controller = new AbortController();
      const result = await runConditioner({
        image: imageFile,
        prompt,
        inputType: inputMode === 'draw' ? 'sketch' : uploadInputType,
        signal: controller.signal,
      });

      setPreprocessingResult(result);
      setOutput(null);
      setGenerationState('complete');
      setApiState('online');
      setApiDetail('Backend connected · image conditioning completed');
    } catch (error) {
      console.error(error);
      setGenerationState('error');
      setErrorMessage(error.message || 'Something went wrong while preprocessing or conditioning the image.');
      setApiDetail('The preprocessing / conditioning request did not complete');
    }
  };

  const handleDownload = async () => {
    if (!output?.modelUrl) return;
    try {
      const response = await fetch(output.modelUrl);
      if (!response.ok) throw new Error('Download request failed');
      const blob = await response.blob();
      const temporaryUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = temporaryUrl;
      anchor.download = output.filename || `sketch2shape-output.${output.format || 'glb'}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(temporaryUrl);
    } catch (error) {
      console.error(error);
      window.open(output.modelUrl, '_blank', 'noopener,noreferrer');
    }
  };

  const resetOutput = () => {
    setOutput(null);
    setPreprocessingResult(null);
    setGenerationState('idle');
    setErrorMessage('');
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Sketch2Shape AI home">
          <span className="brand-mark"><Icon name="cube" size={22} /></span>
          <span className="brand-name">sketch<span>2</span>shape</span>
          <span className="brand-ai">AI</span>
        </a>
        <nav className="top-nav" aria-label="Main navigation">
          <a className="nav-active" href="#workspace">Workspace</a>
          <a href="#workflow">How it works</a>
        </nav>
        <div className="topbar-right">
          <div className={`api-status api-${apiState}`} title={apiDetail}>
            <span className="api-status-dot" />
            <span>{apiState === 'checking' ? 'Checking API' : apiState === 'online' ? 'API connected' : apiState === 'warming' ? 'DINOv2 missing' : 'API offline'}</span>
          </div>
          <button
            type="button"
            className="theme-toggle"
            onClick={toggleTheme}
            aria-label={nextThemeLabel}
            title={nextThemeLabel}
          >
            {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
          </button>
          <span className="version-tag">BETA <span>·</span> 0.1</span>
        </div>
      </header>

      <main id="top" className="page-content">
        <section className="intro-section">
          <div className="intro-copy">
            <div className="eyebrow"><span className="eyebrow-line" /> GENERATIVE 3D WORKSPACE</div>
            <h1>From a sketch<br /><span>to a shape.</span></h1>
            <p>Draw or upload a concept, isolate the subject, inspect the normalized image and verify CPU-based DINOv2 conditioning before the 3D reconstruction stage.</p>
          </div>
          <div className="intro-aside">
            <div className="aside-orbit"><span className="orbit-core" /><span className="orbit-ring ring-one" /><span className="orbit-ring ring-two" /><span className="orbit-spark spark-one" /><span className="orbit-spark spark-two" /></div>
            <div className="aside-copy"><strong>Build the pipeline one stage at a time.</strong><span>Local preprocessing and CPU ONNX conditioning.<br />Mesh generation is the next integration stage.</span></div>
          </div>
        </section>

        <section id="workspace" className="workspace-grid">
          <section className="panel input-panel" aria-labelledby="input-heading">
            <div className="panel-heading">
              <div>
                <div className="section-kicker"><span>01</span> INPUT</div>
                <h2 id="input-heading">Your starting point</h2>
                <p>Give your idea a visual form.</p>
              </div>
              <span className="required-note">SKETCH REQUIRED</span>
            </div>

            <div className="input-tabs" role="tablist" aria-label="Choose sketch input method">
              <button
                className={`input-tab ${inputMode === 'draw' ? 'selected' : ''}`}
                onClick={() => { setInputMode('draw'); setErrorMessage(''); }}
                role="tab"
                aria-selected={inputMode === 'draw'}
                type="button"
              >
                <Icon name="pen" size={16} /> Draw a sketch
              </button>
              <button
                className={`input-tab ${inputMode === 'upload' ? 'selected' : ''}`}
                onClick={() => { setInputMode('upload'); setErrorMessage(''); }}
                role="tab"
                aria-selected={inputMode === 'upload'}
                type="button"
              >
                <Icon name="upload" size={16} /> Upload image
              </button>
            </div>

            <div className="input-mode-heading">
              <div>
                <strong>{inputMode === 'draw' ? 'Sketch canvas' : 'Reference image'}</strong>
                <span>{inputMode === 'draw' ? 'A simple outline is all you need to start.' : 'Use a photo or a drawing saved on your device.'}</span>
              </div>
              <span className="mode-step">{inputMode === 'draw' ? 'LIVE CANVAS' : 'IMAGE INPUT'}</span>
            </div>

            {inputMode === 'draw' ? (
              <SketchCanvas ref={sketchRef} onContentChange={setCanvasHasContent} />
            ) : (
              <UploadPanel file={uploadedFile} onFileChange={setUploadedFile} inputType={uploadInputType} onInputTypeChange={setUploadInputType} />
            )}

            <div className="prompt-divider"><span /> <small>OPTIONAL GUIDANCE</small> <span /></div>
            <div className="prompt-heading">
              <label htmlFor="object-prompt">Describe your object</label>
              <span>FUTURE GENERATION INPUT</span>
            </div>
            <textarea
              id="object-prompt"
              className="prompt-input"
              maxLength={400}
              rows={3}
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="e.g. A compact desk lamp with a brushed aluminium finish, warm light and smooth rounded edges... (not used by the current DINOv2 stage)"
            />
            <div className="prompt-footer">
              <div className="prompt-suggestions">
                {PROMPT_SUGGESTIONS.map((suggestion) => (
                  <button type="button" key={suggestion} onClick={() => appendPromptSuggestion(suggestion)}>{suggestion}</button>
                ))}
              </div>
              <span className="character-count">{prompt.length}/400</span>
            </div>

            {errorMessage && (
              <div className="error-banner" role="alert"><Icon name="alert" size={17} /><span>{errorMessage}</span></div>
            )}

            <div className="generate-area">
              <button
                className="generate-button"
                type="button"
                onClick={handleGenerate}
                disabled={!canGenerate || generationState === 'generating'}
              >
                {generationState === 'generating' ? <><span className="button-spinner" /> Processing image...</> : <><Icon name="sparkles" size={18} /> Run image conditioning <Icon name="chevron" size={17} /></>}
              </button>
              <div className="generate-caption"><Icon name="file" size={13} /> Background removal + DINOv2 CPU check <span>·</span> No mesh is generated yet</div>
            </div>
          </section>

          <section className="panel output-panel" aria-labelledby="output-heading">
            <div className="panel-heading output-heading">
              <div>
                <div className="section-kicker"><span>02</span> CONDITIONING</div>
                <h2 id="output-heading">Pipeline diagnostics</h2>
                <p>Inspect the normalized input and conditioner result.</p>
              </div>
              <div className={`output-status ${preprocessingResult ? 'output-ready' : ''}`}><span /> {preprocessingResult ? 'CONDITIONER PASSED' : 'AWAITING INPUT'}</div>
            </div>

            <ModelViewer modelUrl={output?.modelUrl} format={output?.format} isGenerating={generationState === 'generating'} />

            {preprocessingResult && (
              <div className="preprocess-results" aria-live="polite">
                <div className="preprocess-results-heading">
                  <strong>Preprocessing artifacts</strong>
                  <span>{preprocessingResult.preprocessing?.method || 'Image processed'}</span>
                </div>
                <div className="preprocess-image-grid">
                  <figure>
                    <img src={preprocessingResult.artifacts?.model_input} alt="Normalized RGB image passed to DINOv2" />
                    <figcaption>MODEL INPUT · RGB</figcaption>
                  </figure>
                  <figure>
                    <img src={preprocessingResult.artifacts?.foreground} alt="Extracted foreground subject with transparency" />
                    <figcaption>FOREGROUND</figcaption>
                  </figure>
                  <figure>
                    <img src={preprocessingResult.artifacts?.mask} alt="Foreground alpha mask" />
                    <figcaption>ALPHA MASK</figcaption>
                  </figure>
                  <figure>
                    <img src={preprocessingResult.artifacts?.canny_edges} alt="Canny edge diagnostic map" />
                    <figcaption>CANNY · DIAGNOSTIC</figcaption>
                  </figure>
                </div>
                <div className="conditioner-metrics">
                  <div><span>Embedding</span><strong>{preprocessingResult.embedding_shape?.join(' × ') || 'Completed'}</strong></div>
                  <div><span>Data type</span><strong>{preprocessingResult.embedding_dtype || '—'}</strong></div>
                  <div><span>Inference</span><strong>{preprocessingResult.inference_seconds ?? '—'} s</strong></div>
                  <div><span>Background</span><strong>{preprocessingResult.preprocessing?.background_removed ? 'Removed / isolated' : 'Not removed'}</strong></div>
                </div>
                {preprocessingResult.prompt_note && <p className="prompt-stage-note">{preprocessingResult.prompt_note}</p>}
                <p className="edge-stage-note">Canny is displayed for quality inspection only. DINOv2 receives the normalized RGB image, not the edge map.</p>
              </div>
            )}

            <div className="output-toolbar">
              <div className="output-file-info">
                <span className="file-icon"><Icon name="cube" size={17} /></span>
                <div>
                  <strong>{preprocessingResult ? 'DINOv2 conditioning complete' : 'No 3D mesh generated yet'}</strong>
                  <span>{preprocessingResult ? `Embedding ${preprocessingResult.embedding_shape?.join(' × ') || 'ready'} · CPU ONNX` : 'Mesh generation is the next backend stage'}</span>
                </div>
              </div>
              <div className="output-actions">
                {output && <button className="icon-button rerun-button" onClick={resetOutput} title="Clear current model" aria-label="Clear current model"><Icon name="rotate" size={16} /></button>}
                <button className="download-button" type="button" onClick={handleDownload} disabled={!output}>
                  <Icon name="download" size={16} /> GLB export pending
                </button>
              </div>
            </div>

            <div className="output-specs">
              <div><span className="spec-icon"><Icon name="image" size={15} /></span><span><strong>Input normalized</strong><small>Centered RGB image</small></span></div>
              <div><span className="spec-icon"><Icon name="scan" size={15} /></span><span><strong>Edges inspected</strong><small>Canny QC preview</small></span></div>
              <div><span className="spec-icon"><Icon name="cpu" size={15} /></span><span><strong>CPU inference</strong><small>DINOv2 embeddings</small></span></div>
            </div>
            {preprocessingResult && <div className="job-reference">REQUEST ID <code>{preprocessingResult.request_id}</code></div>}
            {output?.jobId && <div className="job-reference">JOB ID <code>{output.jobId}</code></div>}
          </section>
        </section>

        <section id="workflow" className="workflow-section">
          <div className="workflow-title">
            <span className="eyebrow"><span className="eyebrow-line" /> THE WORKFLOW</span>
            <h2>A small sketch. <span>A new dimension.</span></h2>
          </div>
          <div className="workflow-steps">
            <div className="workflow-step"><span className="workflow-number">01</span><div><strong>Sketch conditioning</strong><p>Draw or upload a source image. Optional text is retained for the later generation stage.</p></div><Icon name="pen" size={19} /></div>
            <div className="workflow-connector" />
            <div className="workflow-step"><span className="workflow-number">02</span><div><strong>DINOv2 conditioning</strong><p>The current backend produces image embeddings on CPU. Full shape generation is not wired yet.</p></div><Icon name="cpu" size={19} /></div>
            <div className="workflow-connector" />
            <div className="workflow-step"><span className="workflow-number">03</span><div><strong>Mesh & export · next</strong><p>DiT sampling, ShapeVAE decoding, mesh extraction and GLB export remain to be implemented.</p></div><Icon name="download" size={19} /></div>
          </div>
        </section>
      </main>

      <footer className="footer">
        <a className="footer-brand" href="#top">
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
        <a href="#workspace" className="back-top">Back to workspace ↑</a>
      </footer>
    </div>
  );
}