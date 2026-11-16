// On-device face tracking. Video frames never leave the browser; we keep only
// "face found" and "looking at the camera" per sample. No emotion labels, ever.
import { FaceLandmarker, FilesetResolver } from '/static/vendor/mediapipe/vision_bundle.mjs';

// Calibration knobs: how far from your own baseline still counts as looking at the camera.
export const HEAD_MAX_DEG = 20;   // head turn away from the calibrated direction
export const EYE_MAX_DEV = 0.35;  // largest change in any eye-direction blendshape (0..1)
const EYE_KEYS = ['eyeLookInLeft', 'eyeLookOutLeft', 'eyeLookUpLeft', 'eyeLookDownLeft',
  'eyeLookInRight', 'eyeLookOutRight', 'eyeLookUpRight', 'eyeLookDownRight'];

const unit = v => { const n = Math.hypot(...v) || 1; return v.map(x => x / n); };

export async function createTracker() {
  const files = await FilesetResolver.forVisionTasks('/static/vendor/mediapipe/wasm');
  const options = delegate => ({
    baseOptions: { modelAssetPath: '/static/vendor/mediapipe/face_landmarker.task', delegate },
    runningMode: 'VIDEO', numFaces: 1,
    outputFaceBlendshapes: true, outputFacialTransformationMatrixes: true,
  });
  let landmarker;
  try { landmarker = await FaceLandmarker.createFromOptions(files, options('GPU')); }
  catch { landmarker = await FaceLandmarker.createFromOptions(files, options('CPU')); }

  let last = 0;
  // One frame -> undefined (video not ready), null (no face) or { forward, eyes }.
  return function read(video) {
    if (video.readyState < 2) return undefined;
    const ts = Math.max(performance.now(), last + 1);  // timestamps must strictly increase
    last = ts;
    const result = landmarker.detectForVideo(video, ts);
    const m = result.facialTransformationMatrixes?.[0]?.data;
    if (!m) return null;
    const eyes = {};
    for (const c of result.faceBlendshapes?.[0]?.categories || []) {
      if (EYE_KEYS.includes(c.categoryName)) eyes[c.categoryName] = c.score;
    }
    // Third column of the column-major 4x4 transform: the face's forward axis in camera space.
    return { forward: unit([m[8], m[9], m[10]]), eyes };
  };
}

// Average of the frames captured while the student looked at the lens.
export function baseline(frames) {
  const faces = frames.filter(Boolean);
  if (faces.length < 5) return null;
  const forward = unit([0, 1, 2].map(i => faces.reduce((s, f) => s + f.forward[i], 0)));
  const eyes = Object.fromEntries(EYE_KEYS.map(k => [k, faces.reduce((s, f) => s + (f.eyes[k] || 0), 0) / faces.length]));
  return { forward, eyes };
}

export function isFacing(frame, base) {
  if (!frame || !base) return false;
  const cos = frame.forward.reduce((s, x, i) => s + x * base.forward[i], 0);
  const degrees = Math.acos(Math.min(1, Math.max(-1, cos))) * 180 / Math.PI;
  const eyeShift = Math.max(...EYE_KEYS.map(k => Math.abs((frame.eyes[k] || 0) - (base.eyes[k] || 0))));
  return degrees <= HEAD_MAX_DEG && eyeShift <= EYE_MAX_DEV;
}
