"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { listJobs, type Job } from "@/lib/api";

const statusColors: Record<string, string> = {
    DONE: "var(--accent-emerald)",
    FAILED: "#ef4444",
    CANCELLED: "#ef4444",
    PAUSED: "#eab308",
    QUEUED: "var(--text-muted)",
};

function getStatusColor(status: string): string {
    return statusColors[status] || "var(--accent-blue)";
}

function formatDate(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
}

export default function DashboardPage() {
    const [jobs, setJobs] = useState<Job[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        listJobs()
            .then(setJobs)
            .catch(() => { })
            .finally(() => setLoading(false));
    }, []);

    return (
        <div className="container">
            <div className="page-header">
                <h1>
                    📊 <span className="gradient-text">Dashboard</span>
                </h1>
                <p>Your video generation jobs</p>
            </div>

            {/* Quick Actions */}
            <div style={{ display: "flex", gap: 12, marginBottom: 32 }}>
                <Link href="/blog" className="btn btn-primary">📝 New Blog Video</Link>
                <Link href="/text" className="btn btn-primary">✍️ New Text Video</Link>
                <Link href="/talk" className="btn btn-secondary">🎙️ New Talk Video</Link>
            </div>

            {/* Jobs List */}
            {loading ? (
                <div className="glass-card" style={{ textAlign: "center", padding: 48 }}>
                    <p style={{ color: "var(--text-muted)" }}>Loading jobs...</p>
                </div>
            ) : jobs.length === 0 ? (
                <div className="glass-card" style={{ textAlign: "center", padding: 64 }}>
                    <div style={{ fontSize: "3rem", marginBottom: 16 }}>🎬</div>
                    <h3 style={{ marginBottom: 8 }}>No jobs yet</h3>
                    <p style={{ color: "var(--text-muted)", marginBottom: 24 }}>
                        Start by creating a new Blog → Video or Talk → Video job.
                    </p>
                    <Link href="/blog" className="btn btn-primary">Get Started</Link>
                </div>
            ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    {jobs.map((job) => (
                        <Link
                            key={job.job_id}
                            href={`/job/?id=${job.job_id}`}
                            className="glass-card"
                            style={{
                                padding: "20px 24px",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "space-between",
                                textDecoration: "none",
                            }}
                        >
                            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                                <span style={{ fontSize: "1.5rem" }}>
                                    {job.mode === "BLOG" ? "📝" : job.mode === "TEXT" ? "✍️" : "🎙️"}
                                </span>
                                <div>
                                    <div style={{ fontWeight: 600, fontSize: "0.95rem" }}>
                                        {job.blog_url
                                            ? (() => { try { return new URL(job.blog_url).hostname; } catch { return job.blog_url; } })()
                                            : job.mode === "TEXT" ? "Text Input" : "Voice Recording"}
                                    </div>
                                    <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                                        {formatDate(job.created_at)}
                                    </div>
                                </div>
                            </div>

                            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                                <span
                                    style={{
                                        fontSize: "0.75rem",
                                        fontWeight: 600,
                                        padding: "4px 12px",
                                        borderRadius: "var(--radius-full)",
                                        background: `color-mix(in srgb, ${getStatusColor(job.status)} 15%, transparent)`,
                                        color: getStatusColor(job.status),
                                        border: `1px solid color-mix(in srgb, ${getStatusColor(job.status)} 30%, transparent)`,
                                        textTransform: "uppercase",
                                        letterSpacing: "0.05em",
                                    }}
                                >
                                    {job.status}
                                </span>
                                <span style={{ color: "var(--text-muted)" }}>→</span>
                            </div>
                        </Link>
                    ))}
                </div>
            )}
        </div>
    );
}
