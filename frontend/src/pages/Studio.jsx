import React, { useEffect, useRef, useState } from 'react';
import Icon from '../components/Icon.jsx';
import SketchCanvas from '../components/SketchCanvas.jsx';
import UploadPanel from '../components/UploadPanel.jsx';
import ModelViewer from '../components/ModelViewer.jsx';
import { generateModel, getBackends } from '../lib/api.js';
import { log } from '../lib/logger.js';

const BACKEND_NAMES={hunyuan:'Hunyuan3D (local)',instantmesh_local:'InstantMesh (local)',instantmesh_api:'InstantMesh (API)'};

const PROMPT_SUGGESTIONS = ['Product design', 'Matte ceramic', 'Soft rounded edges', 'Studio lighting'];

function formatLabel(format) {
  return (format || 'GLB').toUpperCase();
}

export default function Studio({ api }) {
  const { setApiState, setApiDetail } = api;
  const sketchRef = useRef(null);
  const [inputMode, setInputMode] = useState('draw');
  const [uploadedFile, setUploadedFile] = useState(null);
  const [canvasHasContent, setCanvasHasContent] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [generationState, setGenerationState] = useState('idle');
  const [output, setOutput] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [progress,setProgress]=useState(null);
  const [backends,setBackends]=useState([{id:'auto',label:'Auto (with fallback)',available:true,note:''}]);
  const [backend,setBackend]=useState(()=>{
    try{return localStorage.getItem('backend')||'auto';}catch{return 'auto';}
  });

  useEffect(()=>{
    getBackends().then((list)=>{if(list.length)setBackends(list);}).catch(()=>{});
  },[]);

  useEffect(()=>{
    try{localStorage.setItem('backend',backend);}catch{}
  },[backend]);

  useEffect(() => {
    return () => {
      if (output?.isObjectUrl && output.modelUrl) URL.revokeObjectURL(output.modelUrl);
    };
  }, [output]);

  const canGenerate = inputMode === 'draw' ? canvasHasContent : Boolean(uploadedFile);

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
        log.warn('Generate clicked with no input',{inputMode});
        setErrorMessage(inputMode === 'draw' ? 'Draw a sketch on the canvas before generating.' : 'Upload a sketch image before generating.');
        return;
      }

      log.info('Generate clicked',{inputMode,backend,fileName:imageFile.name,fileBytes:imageFile.size});
      setGenerationState('generating');
      setProgress(null);
      setApiDetail('Submitting sketch to the generation API');
      const controller = new AbortController();
      const result = await generateModel({
        image: imageFile,
        prompt,
        inputType: inputMode,
        backend,
        signal: controller.signal,
        onProgress:(job)=>{setProgress(job);setApiDetail(job.label||'Working...');},
      });

      log.info('Model ready',{jobId:result.jobId,format:result.format,backend:result.backend});
      setOutput(result);
      setProgress(null);
      setGenerationState('complete');
      setApiState('online');
      setApiDetail('Generation API is reachable');
    } catch (error) {
      log.error('Generation failed',{message:error.message});
      setGenerationState('error');
      setProgress(null);
      setErrorMessage(error.message || 'Something went wrong while generating the model.');
      setApiDetail('The generation request did not complete');
    }
  };

  const handleDownload = async () => {
    if (!output?.modelUrl) return;
    try {
      const response = await fetch(output.modelUrl);
      if (!response.ok) throw new Error('Download request failed');
      log.info('Export clicked',{jobId:output.jobId,format:output.format});
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
      log.warn('Download via fetch failed, opening in a new tab',{message:error.message});
      window.open(output.modelUrl, '_blank', 'noopener,noreferrer');
    }
  };

  const resetOutput = () => {
    log.info('Output cleared',{jobId:output?.jobId});
    setOutput(null);
    setGenerationState('idle');
    setErrorMessage('');
  };

  return (
    <div className="studio-page">
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

            <div className="backend-picker">
              <label htmlFor="backend-select">3D engine</label>
              <select id="backend-select" value={backend} onChange={(event)=>setBackend(event.target.value)} disabled={generationState==='generating'}>
                {backends.map((item)=>(
                  <option key={item.id} value={item.id} disabled={!item.available}>{item.label}{item.available?'':` (${item.note||'unavailable'})`}</option>
                ))}
              </select>
              <small>{backend==='auto'?`Tries in order: ${backends.find((b)=>b.id==='auto')?.note||'default'}`:'Only this engine runs, no fallback'}</small>
            </div>

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
              
            </div>

            <ModelViewer modelUrl={output?.modelUrl} format={output?.format} isGenerating={generationState === 'generating'} statusText={progress?`${progress.label} · step ${progress.step}/${progress.total_steps} · ${progress.elapsed}s`:undefined} />

            <div className="output-toolbar">
              <div className="output-file-info">
                <span className="file-icon"><Icon name="cube" size={17} /></span>
                <div>
                  <strong>{output?.filename || 'No model generated yet'}</strong>
                  <span>{output ? `3D asset · ${formatLabel(output.format)} format${output.backend?` · ${BACKEND_NAMES[output.backend]||output.backend}`:''}` : 'Your export will be listed here'}</span>
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
      </main>

    </div>
  );
}