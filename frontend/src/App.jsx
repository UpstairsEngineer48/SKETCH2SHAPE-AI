import React, { useEffect, useRef, useState } from 'react';
import Icon from './components/Icon.jsx';
import SketchCanvas from './components/SketchCanvas.jsx';
import UploadPanel from './components/UploadPanel.jsx';
import ModelViewer from './components/ModelViewer.jsx';
import { checkApiHealth, generateModel } from './lib/api.js';

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
  const [uploadedFile, setUploadedFile] = useState(null);
  const [canvasHasContent, setCanvasHasContent] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [generationState, setGenerationState] = useState('idle');
  const [output, setOutput] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [apiState, setApiState] = useState('checking');
  const [apiDetail, setApiDetail] = useState('Checking the generation API');

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('theme', theme); } catch {}
  }, [theme]);

  useEffect(() => {
    let active = true;
    checkApiHealth()
      .then((health) => {
        if (!active) return;
        if (health?.model_loaded === false) {
          setApiState('warming');
          setApiDetail('API online · model weights are not loaded yet');
        } else {
          setApiState('online');
          setApiDetail('Generation API is reachable');
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
      setApiDetail('Submitting sketch to the generation API');
      const controller = new AbortController();
      const result = await generateModel({
        image: imageFile,
        prompt,
        inputType: inputMode,
        signal: controller.signal,
      });

      setOutput(result);
      setGenerationState('complete');
      setApiState('online');
      setApiDetail('Generation API is reachable');
    } catch (error) {
      console.error(error);
      setGenerationState('error');
      setErrorMessage(error.message || 'Something went wrong while generating the model.');
      setApiDetail('The generation request did not complete');
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
            <span>{apiState === 'checking' ? 'Checking API' : apiState === 'online' ? 'API connected' : apiState === 'warming' ? 'Model loading' : 'API offline'}</span>
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
            <p>Bring your rough ideas to life. Draw or upload a concept, add a little direction, and turn it into an inspectable 3D asset.</p>
          </div>
          <div className="intro-aside">
            <div className="aside-orbit"><span className="orbit-core" /><span className="orbit-ring ring-one" /><span className="orbit-ring ring-two" /><span className="orbit-spark spark-one" /><span className="orbit-spark spark-two" /></div>
            <div className="aside-copy"><strong>One view is enough to begin.</strong><span>AI-assisted geometry reconstruction<br />with export-ready output.</span></div>
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
              <UploadPanel file={uploadedFile} onFileChange={setUploadedFile} />
            )}

            <div className="prompt-divider"><span /> <small>OPTIONAL GUIDANCE</small> <span /></div>
            <div className="prompt-heading">
              <label htmlFor="object-prompt">Describe your object</label>
              <span>OPTIONAL</span>
            </div>
            <textarea
              id="object-prompt"
              className="prompt-input"
              maxLength={400}
              rows={3}
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="e.g. A compact desk lamp with a brushed aluminium finish, warm light and smooth rounded edges..."
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
                {generationState === 'generating' ? <><span className="button-spinner" /> Reconstructing model...</> : <><Icon name="sparkles" size={18} /> Generate 3D model <Icon name="chevron" size={17} /></>}
              </button>
              <div className="generate-caption"><Icon name="file" size={13} /> Your sketch stays the source of truth <span>·</span> Prompt is optional</div>
            </div>
          </section>

          <section className="panel output-panel" aria-labelledby="output-heading">
            <div className="panel-heading output-heading">
              <div>
                <div className="section-kicker"><span>02</span> RECONSTRUCTION</div>
                <h2 id="output-heading">3D workspace</h2>
                <p>Inspect your model from every angle.</p>
              </div>
              <div className={`output-status ${output ? 'output-ready' : ''}`}><span /> {output ? 'READY TO EXPORT' : 'AWAITING INPUT'}</div>
            </div>

            <ModelViewer modelUrl={output?.modelUrl} format={output?.format} isGenerating={generationState === 'generating'} />

            <div className="output-toolbar">
              <div className="output-file-info">
                <span className="file-icon"><Icon name="cube" size={17} /></span>
                <div>
                  <strong>{output?.filename || 'No model generated yet'}</strong>
                  <span>{output ? `3D asset · ${formatLabel(output.format)} format` : 'Your export will be listed here'}</span>
                </div>
              </div>
              <div className="output-actions">
                {output && <button className="icon-button rerun-button" onClick={resetOutput} title="Clear current model" aria-label="Clear current model"><Icon name="rotate" size={16} /></button>}
                <button className="download-button" type="button" onClick={handleDownload} disabled={!output}>
                  <Icon name="download" size={16} /> Export {output ? formatLabel(output.format) : '3D'}
                </button>
              </div>
            </div>

            <div className="output-specs">
              <div><span className="spec-icon"><Icon name="cube" size={15} /></span><span><strong>Real geometry</strong><small>Not a flat image</small></span></div>
              <div><span className="spec-icon"><Icon name="sparkles" size={15} /></span><span><strong>Surface detail</strong><small>Materials & textures</small></span></div>
              <div><span className="spec-icon"><Icon name="download" size={15} /></span><span><strong>Exportable</strong><small>GLB / OBJ supported</small></span></div>
            </div>
            {output?.jobId && <div className="job-reference">JOB ID <code>{output.jobId}</code></div>}
          </section>
        </section>

        <section id="workflow" className="workflow-section">
          <div className="workflow-title">
            <span className="eyebrow"><span className="eyebrow-line" /> THE WORKFLOW</span>
            <h2>A small sketch. <span>A new dimension.</span></h2>
          </div>
          <div className="workflow-steps">
            <div className="workflow-step"><span className="workflow-number">01</span><div><strong>Sketch conditioning</strong><p>Draw or upload a source image. Add optional details to guide the result.</p></div><Icon name="pen" size={19} /></div>
            <div className="workflow-connector" />
            <div className="workflow-step"><span className="workflow-number">02</span><div><strong>Image-to-3D</strong><p>The backend interprets the concept and reconstructs plausible geometry.</p></div><Icon name="cube" size={19} /></div>
            <div className="workflow-connector" />
            <div className="workflow-step"><span className="workflow-number">03</span><div><strong>Inspect & export</strong><p>Orbit around the output, then save a usable GLB or OBJ asset.</p></div><Icon name="download" size={19} /></div>
          </div>
        </section>
      </main>

      <footer className="footer">
        <a className="footer-brand" href="#top">
          <span className="brand-mark small-mark"><Icon name="cube" size={16} /></span>
          sketch<span>2</span>shape <i>AI</i>
        </a>
        <span>Team Tabhai</span>
        <span className="footer-separator" aria-hidden="true">·</span>
        <span>Built for creative prototyping</span>
        <span className="footer-separator" aria-hidden="true">·</span>
        <span>TechZephyr 4.0 <span className="footer-year">2026</span></span>
        <a href="#workspace" className="back-top">Back to workspace ↑</a>
      </footer>
    </div>
  );
}