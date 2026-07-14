// The API base URL is resolved at runtime from /config.json, which CDK writes
// to the S3 bucket at deploy time with the real Lambda Function URL. This
// decouples the static build from deploy-time values. Falls back to the local
// dev API (or NEXT_PUBLIC_API_URL) when config.json is unavailable.
const LOCAL_FALLBACK =
    (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_API_URL) ||
    'http://localhost:8000';

let _apiBasePromise: Promise<string> | null = null;

async function resolveApiBase(): Promise<string> {
    if (typeof window === 'undefined') return LOCAL_FALLBACK;
    try {
        const res = await fetch('/config.json', { cache: 'no-store' });
        if (res.ok) {
            const cfg = await res.json();
            // apiUrl may be an empty string, which means "same origin" — the
            // API is served under the same CloudFront domain (e.g. /jobs).
            if (cfg && typeof cfg.apiUrl === 'string') {
                return cfg.apiUrl.replace(/\/+$/, '');
            }
        }
    } catch {
        // config.json missing (e.g. local dev) — fall through to local fallback
    }
    return LOCAL_FALLBACK.replace(/\/+$/, '');
}

function getApiBase(): Promise<string> {
    if (!_apiBasePromise) _apiBasePromise = resolveApiBase();
    return _apiBasePromise;
}

export interface StyleSettings {
    duration: 'short' | 'medium' | 'long';
    tone: 'professional' | 'casual' | 'energetic';
    audience: string;
    voice: 'polly_default' | 'nova_sonic' | 'byo';
    voice_profile_id?: string;
    visual_style: 'cinematic' | 'cartoon' | 'anime' | 'claymation' | 'watercolor';
}

export interface JobCreate {
    mode: 'BLOG' | 'TALK' | 'TEXT';
    blog_url?: string;
    audio_s3_key?: string;
    source_text?: string;
    style: StyleSettings;
    auto_upload_youtube: boolean;
}

export interface JobOutputs {
    script_url?: string;
    audio_url?: string;
    video_url?: string;
    captions_url?: string;
    metadata_url?: string;
    thumbnail_url?: string;
    package_url?: string;
}

export interface Job {
    job_id: string;
    user_id: string;
    mode: 'BLOG' | 'TALK' | 'TEXT';
    status: string;
    style: StyleSettings;
    blog_url?: string;
    audio_s3_key?: string;
    auto_upload_youtube: boolean;
    outputs?: JobOutputs;
    error?: string;
    created_at: string;
    updated_at: string;
}

export interface PresignResponse {
    upload_url: string;
    s3_key: string;
}

// ── Jobs ──
export async function createJob(data: JobCreate): Promise<Job> {
    const API_BASE = await getApiBase();
    const res = await fetch(`${API_BASE}/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(`Failed to create job: ${res.statusText}`);
    return res.json();
}

export async function getJob(jobId: string): Promise<Job> {
    const API_BASE = await getApiBase();
    const res = await fetch(`${API_BASE}/jobs/${jobId}`);
    if (!res.ok) throw new Error(`Failed to get job: ${res.statusText}`);
    return res.json();
}

export async function listJobs(): Promise<Job[]> {
    const API_BASE = await getApiBase();
    const res = await fetch(`${API_BASE}/jobs`);
    if (!res.ok) throw new Error(`Failed to list jobs: ${res.statusText}`);
    return res.json();
}

// ── Uploads ──
export async function getPresignedUrl(filename: string, contentType: string): Promise<PresignResponse> {
    const API_BASE = await getApiBase();
    const res = await fetch(`${API_BASE}/uploads/presign`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename, content_type: contentType }),
    });
    if (!res.ok) throw new Error(`Failed to get presigned URL: ${res.statusText}`);
    return res.json();
}

export async function uploadToS3(file: File): Promise<string> {
    const { upload_url, s3_key } = await getPresignedUrl(file.name, file.type);
    const res = await fetch(upload_url, {
        method: 'PUT',
        headers: { 'Content-Type': file.type },
        body: file,
    });
    if (!res.ok) throw new Error('Failed to upload file to S3');
    return s3_key;
}

// ── Health ──
export async function healthCheck(): Promise<{ status: string }> {
    const API_BASE = await getApiBase();
    const res = await fetch(`${API_BASE}/health`);
    return res.json();
}

// ── Job Actions ──
export async function cancelJob(jobId: string): Promise<{ status: string }> {
    const API_BASE = await getApiBase();
    const res = await fetch(`${API_BASE}/jobs/${jobId}/cancel`, { method: 'POST' });
    if (!res.ok) throw new Error(`Failed to cancel job: ${res.statusText}`);
    return res.json();
}

export async function pauseJob(jobId: string): Promise<{ status: string }> {
    const API_BASE = await getApiBase();
    const res = await fetch(`${API_BASE}/jobs/${jobId}/pause`, { method: 'POST' });
    if (!res.ok) throw new Error(`Failed to pause job: ${res.statusText}`);
    return res.json();
}
