import React, { useEffect, useRef, useState } from 'react';
import Icon from './Icon.jsx';

const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp'];
const MAX_BYTES = 15 * 1024 * 1024;

export default function UploadPanel({ file, onFileChange }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState('');
  const [previewUrl, setPreviewUrl] = useState('');

  useEffect(() => {
    if (!file) {
      setPreviewUrl('');
      return undefined;
    }
    const nextUrl = URL.createObjectURL(file);
    setPreviewUrl(nextUrl);
    return () => URL.revokeObjectURL(nextUrl);
  }, [file]);

  const acceptFile = (candidate) => {
    if (!candidate) return;
    if (!ACCEPTED_TYPES.includes(candidate.type)) {
      setError('Use a PNG, JPG, or WEBP image.');
      return;
    }
    if (candidate.size > MAX_BYTES) {
      setError('This image is larger than 15 MB. Choose a smaller file.');
      return;
    }
    setError('');
    onFileChange(candidate);
  };

  const onInputChange = (event) => {
    acceptFile(event.target.files?.[0]);
    event.target.value = '';
  };

  const onDrop = (event) => {
    event.preventDefault();
    setDragging(false);
    acceptFile(event.dataTransfer.files?.[0]);
  };

  return (
    <div className="upload-module">
      {file ? (
        <div className="uploaded-file-card">
          <div className="uploaded-preview">
            <img src={previewUrl} alt="Uploaded sketch preview" />
          </div>
          <div className="uploaded-details">
            <span className="file-chip"><Icon name="image" size={13} /> SKETCH IMAGE</span>
            <strong title={file.name}>{file.name}</strong>
            <span>{(file.size / (1024 * 1024)).toFixed(2)} MB <span className="caption-separator">·</span> {file.type.split('/')[1].toUpperCase()}</span>
            <div className="uploaded-actions">
              <button className="text-button" onClick={() => inputRef.current?.click()}>Replace image</button>
              <button className="text-button danger-text" onClick={() => { onFileChange(null); setError(''); }}>Remove</button>
            </div>
          </div>
          <div className="file-success"><Icon name="check" size={16} /></div>
        </div>
      ) : (
        <button
          className={`dropzone ${dragging ? 'dragging' : ''}`}
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <span className="dropzone-icon"><Icon name="upload" size={23} /></span>
          <strong>Drop your sketch here</strong>
          <span>or <u>browse files</u> from your device</span>
          <small>PNG, JPG or WEBP <span>·</span> up to 15 MB</small>
        </button>
      )}
      <input ref={inputRef} className="visually-hidden" type="file" accept="image/png,image/jpeg,image/webp" onChange={onInputChange} />
      {error && <p className="input-error"><Icon name="alert" size={14} /> {error}</p>}
      <div className="upload-tip"><Icon name="sparkles" size={15} /><span>For best results, use a clear image with a visible object outline and minimal background clutter.</span></div>
    </div>
  );
}
