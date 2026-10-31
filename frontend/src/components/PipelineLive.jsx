import React from 'react';
import { fileUrl } from '../lib/api.js';

const STAGES = [
  ['control.png', 'Control map'],
  ['rendered.png', 'Render'],
  ['foreground.png', 'Cutout'],
  [null, 'Mesh'],
];

// Shows each pipeline stage's image as soon as the backend has finished it.
export default function PipelineLive({ jobId, step = 1 }) {
  return (
    <div className="pl-live">
      {STAGES.map(([file, label], i) => {
        const n = i + 1;
        const state = step > n ? 'done' : step === n ? 'active' : 'todo';
        return (
          <div key={label} className={`pl-chip ${state}`}>
            <div className="pl-thumb">
              {file && state === 'done' && jobId && (
                <img src={fileUrl(jobId, file)} alt="" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
              )}
              {state === 'active' && <span className="pl-pulse" />}
            </div>
            <small>{String(n).padStart(2, '0')}</small>
            <strong>{label}</strong>
          </div>
        );
      })}
    </div>
  );
}