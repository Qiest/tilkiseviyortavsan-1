import { Platform } from 'react-native';

// ─────────────────────────────────────────────────────────────────────────────
// RENDER URL: Burası senin backend'inin internetteki adresidir.
// ⚠️ Önemli: Linkin sonuna "/" koyma.
// ─────────────────────────────────────────────────────────────────────────────
const RENDER_URL = 'https://sapsaltavsan-backend.onrender.com'; 

export const API_BASE = RENDER_URL;

export const mediaUrl = (fileId: string) => `${API_BASE}/api/media/${fileId}`;