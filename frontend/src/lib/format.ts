export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || !isFinite(bytes)) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

export function basename(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() || path;
}

export function dirname(path: string): string {
  const parts = path.split(/[\\/]/);
  parts.pop();
  return parts.join('/') || '/';
}

export function formatMs(ms: number | null | undefined): string {
  if (ms == null || !isFinite(ms)) return '—';
  if (ms < 1) return `${ms.toFixed(2)} ms`;
  if (ms < 100) return `${ms.toFixed(1)} ms`;
  return `${Math.round(ms)} ms`;
}

export function formatDate(v: string | number | null | undefined): string {
  if (v == null || v === '') return '—';
  const d = typeof v === 'number' ? new Date(v < 1e12 ? v * 1000 : v) : new Date(v);
  if (isNaN(d.getTime())) return String(v);
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export function hexToRgb(hex: string): [number, number, number] {
  let h = hex.replace('#', '').trim();
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  const n = parseInt(h.slice(0, 6), 16);
  if (isNaN(n)) return [128, 128, 128];
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function rgbToHex(r: number, g: number, b: number): string {
  return '#' + [r, g, b].map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('').toUpperCase();
}

/** Readable text colour (black/white) on top of `hex`. */
export function contrastText(hex: string): string {
  const [r, g, b] = hexToRgb(hex);
  return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? '#0f172a' : '#f8fafc';
}

/** Fallback cluster palette when the backend does not provide a colour. */
export const CLUSTER_FALLBACK = [
  '#818CF8', '#F472B6', '#34D399', '#FBBF24', '#60A5FA', '#F87171', '#A78BFA', '#2DD4BF',
  '#FB923C', '#A3E635', '#E879F9', '#38BDF8', '#FCA5A5', '#86EFAC', '#FDE68A', '#C4B5FD',
  '#5EEAD4', '#FDBA74', '#93C5FD', '#F9A8D4', '#BEF264', '#67E8F9', '#D8B4FE', '#FCD34D',
];

export function clusterColor(color: string | null | undefined, clusterId: number): string {
  if (color && /^#?[0-9a-fA-F]{3,8}$/.test(color)) return color.startsWith('#') ? color : `#${color}`;
  if (color && color.startsWith('rgb')) return color;
  return CLUSTER_FALLBACK[((clusterId % CLUSTER_FALLBACK.length) + CLUSTER_FALLBACK.length) % CLUSTER_FALLBACK.length];
}

export function isTypingTarget(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
}
