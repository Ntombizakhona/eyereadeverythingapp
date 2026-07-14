"use client";

import { useState, useEffect, useCallback, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { getJob, cancelJob, pauseJob, type Job } from "@/lib/api";

const PIPELINE_STEPS = [
    { status: "QUEUED", label: "Queued", desc: "Job is in the queue" },
    { status: "VALIDATING", label: "Validating", desc: "Checking input parameters" },
    { status: "INGESTING", label: "Ingesting", desc: "Extracting content from source" },
    { status: "RETRIEVING_CONTEXT", label: "Context", desc: "Fetching channel style exemplars" },
    { status: "PLANNING", label: "Planning", desc: "Creating video plan with scene beats" },
    { status: "SCRIPTING", label: "Scripting", desc: "Writing narration script" },
    { status: "GENERATING_METADATA", label: "Metadata", desc: "Generating YouTube SEO metadata" },
    { status: "GENERATING_CAPTIONS", label: "Captions", desc: "Creating SRT subtitle file" },
    { status: "NARRATING", label: "Narrating", desc: "Synthesizing voice narration" },
    { status: "RENDERING", label: "Rendering", desc: "Building video with FFmpeg" },
    { status: "PACKAGING", label: "Packaging", desc: "Assembling download package" },
    { status: "UPLOADING", label: "Uploading", desc: "Uploading to YouTube via Nova Act" },
    { status: "DONE", label: "Complete", desc: "Your video is ready!" },
];

const FRIENDLY_ERRORS: Record<string, string> = {
    "403 Forbidden": "The source website blocked our request. Try using Text → Video mode instead and paste the content directly.",
    "Cancelled by user": "You cancelled this job.",
    "Paused by user": "This job was paused.",
};

function getFriendlyError(error: string): string {
    for (const [key, friendly] of Object.entries(FRIENDLY_ERRORS)) {
        if (error.includes(key)) return friendly;
    }
    if (error.includes("timeout") || error.includes("Timeout")) {
        return "The operation took too long and timed out. This can happen with very large content. Try again with shorter text.";
    }
    if (error.includes("Connection") || error.includes("connect")) {
        return "Couldn't connect to an external service. This is usually temporary — try again in a minute.";
    }
    if (error.includes("Transcription failed")) {
        return "We couldn't transcribe the audio. Make sure the file is a valid audio format (MP3, WAV, etc.) and isn't empty.";
    }
    if (error.includes("ValidationError") || error.includes("requires")) {
        return "Something was missing from the input. Please go back and make sure all required fields are filled in.";
    }
    return `Something went wrong during processing. Details: ${error}`;
}

function getStepState(stepStatus: string, currentStatus: string, isFailed: boolean) {
    if (isFailed && stepStatus === currentStatus) return "error";
    const currentIdx = PIPELINE_STEPS.findIndex((s) => s.status === currentStatus);
    const stepIdx = PIPELINE_STEPS.findIndex((s) => s.status === stepStatus);
    if (stepIdx < currentIdx) return "done";
    if (stepIdx === currentIdx) return isFailed ? "error" : "active";
    return "pending";
}

function getModeIcon(mode: string) {
    if (mode === "BLOG") return "📝";
    if (mode === "TEXT") return "✍️";
    return "🎙️";
}

function JobView() {
    const searchParams = useSearchParams();
    const router = useRouter();
    const jobId = searchParams.get("id") ?? "";
    const [job, setJob] = useState<Job | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [actionLoading, setActionLoading] = useState<string | null>(null);

    const fetchJob = useCallback(async () => {
        if (!jobId) {
            setError("No job id provided.");
            return;
        }
        try {
            const data = await getJob(jobId);
            setJob(data);
        } catch {
            setError("Failed to load job. Make sure the API is running.");
        }
    }, [jobId]);

    const isTerminal = job?.status === "DONE" || job?.status === "FAILED" || job?.status === "CANCELLED" || job?.status === "PAUSED";

    useEffect(() => {
        fetchJob();
        if (isTerminal) return;
        const interval = setInterval(fetchJob, 3000);
        return () => clearInterval(interval);
    }, [fetchJob, isTerminal]);

    const handleCancel = async () => {
        if (!job || actionLoading) return;
        setActionLoading("cancel");
        try {
            await cancelJob(jobId);
            await fetchJob();
        } catch {
            await fetchJob();
        } finally {
            setActionLoading(null);
        }
    };

    const handlePause = async () => {
        if (!job || actionLoading) return;
        setActionLoading("pause");
        try {
            await pauseJob(jobId);
            await fetchJob();
        } catch {
            await fetchJob();
        } finally {
            setActionLoading(null);
        }
    };

    if (error) {
        return (
            <div className="container">
                <div className="page-header"><h1>Job Status</h1></div>
                <div className="glass-card" style={{ textAlign: "center", padding: 48 }}>
                    <p style={{ color: "#ef4444" }}>{error}</p>
                </div>
            </div>
        );
    }

    if (!job) {
        return (
            <div className="container">
                <div className="page-header"><h1>Loading...</h1></div>
            </div>
        );
    }

    const isFailed = job.status === "FAILED" || job.status === "CANCELLED";
    const isDone = job.status === "DONE";
    const isPaused = job.status === "PAUSED";
    const isRunning = !isTerminal;

    return (
        <div className="container">
            <div className="page-header">
                <h1>
                    {isDone ? "✅ " : isFailed ? "❌ " : isPaused ? "⏸️ " : "⏳ "}
                    Job <span className="gradient-text">Status</span>
                </h1>
                <p>
                    {getModeIcon(job.mode)} {job.mode} mode •{" "}
                    <span style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>{job.job_id}</span>
                </p>
            </div>

            <div className="glass-card" style={{ maxWidth: 720, margin: "0 auto" }}>
                {/* Action Buttons */}
                {isRunning && (
                    <div style={{ display: "flex", gap: 12, marginBottom: 24 }}>
                        <button
                            className="btn btn-secondary"
                            onClick={handlePause}
                            disabled={!!actionLoading}
                            style={{ flex: 1 }}
                        >
                            {actionLoading === "pause" ? "Pausing..." : "⏸️ Pause"}
                        </button>
                        <button
                            className="btn"
                            onClick={handleCancel}
                            disabled={!!actionLoading}
                            style={{
                                flex: 1,
                                background: "rgba(239, 68, 68, 0.15)",
                                color: "#ef4444",
                                border: "1px solid rgba(239, 68, 68, 0.3)",
                                cursor: actionLoading ? "not-allowed" : "pointer",
                            }}
                        >
                            {actionLoading === "cancel" ? "Cancelling..." : "✕ Cancel"}
                        </button>
                    </div>
                )}

                {/* Paused Banner */}
                {isPaused && (
                    <div style={{
                        marginBottom: 24,
                        padding: 16,
                        borderRadius: "var(--radius-md)",
                        background: "rgba(234, 179, 8, 0.1)",
                        border: "1px solid rgba(234, 179, 8, 0.3)",
                        color: "#eab308",
                        fontSize: "0.9rem",
                        display: "flex",
                        alignItems: "center",
                        gap: 12,
                    }}>
                        <span style={{ fontSize: "1.3rem" }}>⏸️</span>
                        <div>
                            <div style={{ fontWeight: 600 }}>Job Paused</div>
                            <div style={{ fontSize: "0.8rem", opacity: 0.8 }}>
                                This job has been paused. You can start a new one from the dashboard.
                            </div>
                        </div>
                    </div>
                )}

                {/* Pipeline Timeline */}
                <div className="timeline">
                    {PIPELINE_STEPS.map((step, idx) => {
                        const state = getStepState(step.status, job.status, isFailed);
                        const isLast = idx === PIPELINE_STEPS.length - 1;
                        return (
                            <div key={step.status} className={`timeline-step ${state}`}>
                                <div className="timeline-indicator">
                                    {state === "done" ? "✓" : state === "error" ? "✗" : state === "active" ? "●" : idx + 1}
                                </div>
                                {!isLast && <div className="timeline-connector" />}
                                <div className="timeline-content">
                                    <div className="timeline-title">{step.label}</div>
                                    <div className="timeline-desc">{step.desc}</div>
                                </div>
                            </div>
                        );
                    })}
                </div>

                {/* Friendly Error Message */}
                {(isFailed || isPaused) && job.error && (
                    <div style={{
                        marginTop: 24,
                        padding: 20,
                        borderRadius: "var(--radius-md)",
                        background: isFailed ? "rgba(239, 68, 68, 0.08)" : "rgba(234, 179, 8, 0.08)",
                        border: `1px solid ${isFailed ? "rgba(239, 68, 68, 0.25)" : "rgba(234, 179, 8, 0.25)"}`,
                        fontSize: "0.9rem",
                    }}>
                        <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                            <span style={{ fontSize: "1.3rem", flexShrink: 0 }}>
                                {job.status === "CANCELLED" ? "🚫" : "⚠️"}
                            </span>
                            <div>
                                <div style={{ fontWeight: 600, color: isFailed ? "#ef4444" : "#eab308", marginBottom: 4 }}>
                                    {job.status === "CANCELLED" ? "Job Cancelled" : "Something went wrong"}
                                </div>
                                <div style={{ color: "var(--text-secondary)", lineHeight: 1.5 }}>
                                    {getFriendlyError(job.error)}
                                </div>
                            </div>
                        </div>
                        <div style={{ marginTop: 16, display: "flex", gap: 12 }}>
                            <button
                                className="btn btn-primary"
                                onClick={() => router.push("/dashboard")}
                                style={{ fontSize: "0.85rem" }}
                            >
                                ← Back to Dashboard
                            </button>
                            <button
                                className="btn btn-secondary"
                                onClick={() => {
                                    if (job.mode === "BLOG") router.push("/blog");
                                    else if (job.mode === "TEXT") router.push("/text");
                                    else router.push("/talk");
                                }}
                                style={{ fontSize: "0.85rem" }}
                            >
                                Try Again
                            </button>
                        </div>
                    </div>
                )}

                {/* Downloads */}
                {isDone && job.outputs && (
                    <div className="download-section">
                        <h3 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: 4 }}>
                            🎉 Your package is ready!
                        </h3>
                        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginBottom: 16 }}>
                            Download individual files or grab the complete ZIP.
                        </p>
                        {job.outputs.video_url && (
                            <video
                                controls
                                src={job.outputs.video_url}
                                poster={job.outputs.thumbnail_url || undefined}
                                style={{
                                    width: "100%",
                                    borderRadius: "var(--radius-md)",
                                    border: "1px solid var(--border-glass)",
                                    background: "#000",
                                    marginBottom: 16,
                                    display: "block",
                                }}
                            >
                                Your browser does not support the video tag.
                            </video>
                        )}
                        <div className="download-grid">
                            {job.outputs.package_url && (
                                <a href={job.outputs.package_url} className="download-item" target="_blank" rel="noopener noreferrer">
                                    📦 Complete ZIP
                                </a>
                            )}
                            {job.outputs.video_url && (
                                <a href={job.outputs.video_url} className="download-item" target="_blank" rel="noopener noreferrer">
                                    🎬 Video (MP4)
                                </a>
                            )}
                            {job.outputs.captions_url && (
                                <a href={job.outputs.captions_url} className="download-item" target="_blank" rel="noopener noreferrer">
                                    📝 Captions (SRT)
                                </a>
                            )}
                            {job.outputs.metadata_url && (
                                <a href={job.outputs.metadata_url} className="download-item" target="_blank" rel="noopener noreferrer">
                                    📊 Metadata (JSON)
                                </a>
                            )}
                            {job.outputs.script_url && (
                                <a href={job.outputs.script_url} className="download-item" target="_blank" rel="noopener noreferrer">
                                    📄 Script (MD)
                                </a>
                            )}
                            {job.outputs.thumbnail_url && (
                                <a href={job.outputs.thumbnail_url} className="download-item" target="_blank" rel="noopener noreferrer">
                                    🖼️ Thumbnail
                                </a>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

export default function JobPage() {
    return (
        <Suspense
            fallback={
                <div className="container">
                    <div className="page-header"><h1>Loading...</h1></div>
                </div>
            }
        >
            <JobView />
        </Suspense>
    );
}
