import React, { forwardRef, useImperativeHandle, useRef, useState } from 'react';
import Icon from './Icon.jsx';

const COLORS = ['#202638', '#7668D8', '#E18458', '#238B7C'];
const WIDTH = 1400;
const HEIGHT = 900;

const SketchCanvas = forwardRef(function SketchCanvas({ onContentChange }, ref) {
  const canvasRef = useRef(null);
  const drawingRef = useRef(false);
  const lastPointRef = useRef(null);
  const historyRef = useRef([]);
  const historyIndexRef = useRef(0);
  const [tool, setTool] = useState('brush');
  const [color, setColor] = useState(COLORS[0]);
  const [brushSize, setBrushSize] = useState(6);
  const [historyState, setHistoryState] = useState({ index: 0, length: 1 });
  const [hasMarks, setHasMarks] = useState(false);

  const context = () => canvasRef.current?.getContext('2d', { willReadFrequently: true });

  const pushHistory = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const snapshot = canvas.toDataURL('image/png');
    const next = historyRef.current.slice(0, historyIndexRef.current + 1);
    next.push(snapshot);
    historyRef.current = next;
    historyIndexRef.current = next.length - 1;
    setHistoryState({ index: historyIndexRef.current, length: next.length });
    const hasContent = checkHasMarks();
    setHasMarks(hasContent);
    onContentChange?.(hasContent);
  };

  const checkHasMarks = () => {
    const canvas = canvasRef.current;
    const ctx = context();
    if (!canvas || !ctx) return false;
    const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    // Sampling keeps the blank-canvas check fast on high-resolution displays.
    for (let i = 0; i < pixels.length; i += 4 * 2) {
      if (pixels[i] < 240 || pixels[i + 1] < 240 || pixels[i + 2] < 240) return true;
    }
    return false;
  };

  const restoreSnapshot = (index) => {
    const canvas = canvasRef.current;
    const ctx = context();
    const snapshot = historyRef.current[index];
    if (!canvas || !ctx || !snapshot) return;
    const image = new Image();
    image.onload = () => {
      ctx.clearRect(0, 0, WIDTH, HEIGHT);
      ctx.drawImage(image, 0, 0, WIDTH, HEIGHT);
      historyIndexRef.current = index;
      setHistoryState({ index, length: historyRef.current.length });
      const hasContent = checkHasMarks();
      setHasMarks(hasContent);
      onContentChange?.(hasContent);
    };
    image.src = snapshot;
  };

  const clearCanvas = () => {
    const canvas = canvasRef.current;
    const ctx = context();
    if (!canvas || !ctx) return;
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, WIDTH, HEIGHT);
    pushHistory();
    setTool('brush');
  };

  const pointFromEvent = (event) => {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) / rect.width) * canvas.width,
      y: ((event.clientY - rect.top) / rect.height) * canvas.height,
    };
  };

  const handlePointerDown = (event) => {
    const canvas = canvasRef.current;
    const ctx = context();
    if (!canvas || !ctx) return;
    event.preventDefault();
    canvas.setPointerCapture(event.pointerId);
    drawingRef.current = true;
    const point = pointFromEvent(event);
    lastPointRef.current = point;
    ctx.globalCompositeOperation = 'source-over';
    ctx.strokeStyle = tool === 'eraser' ? '#ffffff' : color;
    ctx.fillStyle = tool === 'eraser' ? '#ffffff' : color;
    ctx.lineWidth = tool === 'eraser' ? Math.max(brushSize * 3, 24) : brushSize * 2;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.arc(point.x, point.y, ctx.lineWidth / 2, 0, Math.PI * 2);
    ctx.fill();
  };

  const handlePointerMove = (event) => {
    if (!drawingRef.current) return;
    const ctx = context();
    if (!ctx) return;
    event.preventDefault();
    const point = pointFromEvent(event);
    const previous = lastPointRef.current;
    ctx.beginPath();
    ctx.moveTo(previous.x, previous.y);
    ctx.lineTo(point.x, point.y);
    ctx.stroke();
    lastPointRef.current = point;
  };

  const handlePointerUp = (event) => {
    if (!drawingRef.current) return;
    drawingRef.current = false;
    lastPointRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    pushHistory();
  };

  const undo = () => {
    if (historyIndexRef.current <= 0) return;
    restoreSnapshot(historyIndexRef.current - 1);
  };

  const redo = () => {
    if (historyIndexRef.current >= historyRef.current.length - 1) return;
    restoreSnapshot(historyIndexRef.current + 1);
  };

  useImperativeHandle(ref, () => ({
    hasContent: () => checkHasMarks(),
    toFile: () => new Promise((resolve, reject) => {
      const canvas = canvasRef.current;
      if (!canvas || !checkHasMarks()) {
        resolve(null);
        return;
      }
      canvas.toBlob((blob) => {
        if (!blob) {
          reject(new Error('Could not export the drawing canvas.'));
          return;
        }
        resolve(new File([blob], 'sketch-canvas.png', { type: 'image/png' }));
      }, 'image/png');
    }),
    clear: clearCanvas,
  }));

  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.width = WIDTH;
    canvas.height = HEIGHT;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, WIDTH, HEIGHT);
    historyRef.current = [canvas.toDataURL('image/png')];
    historyIndexRef.current = 0;
    onContentChange?.(false);
  }, []);

  return (
    <div className="drawing-module">
      <div className="drawing-toolbar">
        <div className="tool-switch" role="group" aria-label="Drawing tools">
          <button className={`tool-button ${tool === 'brush' ? 'active' : ''}`} onClick={() => setTool('brush')} title="Brush">
            <Icon name="pen" size={16} /> <span>Brush</span>
          </button>
          <button className={`tool-button ${tool === 'eraser' ? 'active' : ''}`} onClick={() => setTool('eraser')} title="Eraser">
            <span className="eraser-glyph">◩</span> <span>Eraser</span>
          </button>
        </div>
        <div className="drawing-controls">
          <div className="color-swatches" role="group" aria-label="Brush color">
            {COLORS.map((swatch) => (
              <button
                key={swatch}
                className={`color-swatch ${color === swatch ? 'selected' : ''}`}
                style={{ '--swatch': swatch }}
                onClick={() => { setColor(swatch); setTool('brush'); }}
                aria-label={`Use ${swatch} brush color`}
              />
            ))}
          </div>
          <label className="brush-size-control">
            <span>Size</span>
            <input aria-label="Brush size" type="range" min="1" max="18" value={brushSize} onChange={(event) => setBrushSize(Number(event.target.value))} />
          </label>
          <span className="brush-size-value">{brushSize}px</span>
          <span className="toolbar-divider" />
          <button className="icon-button" onClick={undo} disabled={historyState.index === 0} title="Undo" aria-label="Undo">
            <Icon name="undo" size={16} />
          </button>
          <button className="icon-button" onClick={redo} disabled={historyState.index >= historyState.length - 1} title="Redo" aria-label="Redo">
            <Icon name="redo" size={16} />
          </button>
          <button className="icon-button clear-button" onClick={clearCanvas} title="Clear canvas" aria-label="Clear canvas">
            <Icon name="trash" size={16} />
          </button>
        </div>
      </div>
      <div className="canvas-wrap">
        <canvas
          ref={canvasRef}
          className="sketch-canvas"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          aria-label="Sketch drawing area"
        />
        {!hasMarks && (
          <div className="canvas-hint" aria-hidden="true">
            <span className="canvas-hint-mark"><Icon name="pen" size={22} /></span>
            <span>Start with a simple outline</span>
            <small>Draw directly on this canvas</small>
          </div>
        )}
      </div>
      <div className="canvas-caption">
        <span><span className="live-dot" /> Canvas ready</span>
        <span>1400 × 900 px <span className="caption-separator">·</span> PNG output</span>
      </div>
    </div>
  );
});

export default SketchCanvas;
