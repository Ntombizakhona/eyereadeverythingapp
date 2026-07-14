"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createJob, type StyleSettings } from "@/lib/api";

export default function BlogPage() {
    const router = useRouter();
    const [blogUrl, setBlogUrl] = useState("");
    const [loading, setLoading] = useState(false);
    const [style, setStyle] = useState<StyleSettings>({
        duration: "medium",
        tone: "professional",
        audience: "general",
        voice: "polly_default",
        visual_style: "cinematic",
    });
    const [autoUpload, setAutoUpload] = useState(false);

    const handleGenerate = async () => {
        if (!blogUrl.trim()) return;
        setLoading(true);
        try {
            const job = await createJob({
                mode: "BLOG",
                blog_url: blogUrl,
                style,
                auto_upload_youtube: autoUpload,
            });
            router.push(`/job/?id=${job.job_id}`);
        } catch (err) {
            console.error(err);
            alert("Failed to create job. Check that the API is running.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="container">
            <div className="page-header">
                <h1>
                    📝 Blog <span className="gradient-text">→ Video</span>
                </h1>
                <p>Paste a blog URL and we&apos;ll turn it into a YouTube-ready video package.</p>
            </div>

            <div className="glass-card" style={{ maxWidth: 720, margin: "0 auto" }}>
                {/* Blog URL */}
                <div className="form-group">
                    <label className="form-label">Blog URL</label>
                    <input
                        type="url"
                        className="form-input"
                        placeholder="https://example.com/my-blog-post"
                        value={blogUrl}
                        onChange={(e) => setBlogUrl(e.target.value)}
                    />
                </div>

                {/* Style Controls */}
                <div className="controls-grid">
                    <div className="form-group">
                        <label className="form-label">Duration</label>
                        <select
                            className="form-select"
                            value={style.duration}
                            onChange={(e) => setStyle({ ...style, duration: e.target.value as StyleSettings["duration"] })}
                        >
                            <option value="short">Short (~1 min)</option>
                            <option value="medium">Medium (~3 min)</option>
                            <option value="long">Long (~5 min)</option>
                        </select>
                    </div>

                    <div className="form-group">
                        <label className="form-label">Tone</label>
                        <select
                            className="form-select"
                            value={style.tone}
                            onChange={(e) => setStyle({ ...style, tone: e.target.value as StyleSettings["tone"] })}
                        >
                            <option value="professional">Professional</option>
                            <option value="casual">Casual</option>
                            <option value="energetic">Energetic</option>
                        </select>
                    </div>

                    <div className="form-group">
                        <label className="form-label">Voice</label>
                        <select
                            className="form-select"
                            value={style.voice}
                            onChange={(e) => setStyle({ ...style, voice: e.target.value as StyleSettings["voice"] })}
                        >
                            <option value="polly_default">Amazon Polly (Default)</option>
                            <option value="nova_sonic">Nova Sonic</option>
                            <option value="byo">BYO Voice</option>
                        </select>
                    </div>

                    <div className="form-group">
                        <label className="form-label">Visual Style</label>
                        <select
                            className="form-select"
                            value={style.visual_style}
                            onChange={(e) => setStyle({ ...style, visual_style: e.target.value as StyleSettings["visual_style"] })}
                        >
                            <option value="cinematic">🎬 Cinematic (Realistic)</option>
                            <option value="cartoon">🎨 Cartoon (2D Animated)</option>
                            <option value="anime">🌸 Anime</option>
                            <option value="claymation">🧱 Claymation</option>
                            <option value="watercolor">🖌️ Watercolor</option>
                        </select>
                    </div>
                </div>

                <div className="form-group">
                    <label className="form-label">Target Audience</label>
                    <input
                        type="text"
                        className="form-input"
                        placeholder="e.g. tech professionals, beginners, students..."
                        value={style.audience}
                        onChange={(e) => setStyle({ ...style, audience: e.target.value })}
                    />
                </div>

                {/* YouTube Upload Toggle */}
                <div className="form-group" style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <input
                        type="checkbox"
                        id="auto-upload"
                        checked={autoUpload}
                        onChange={(e) => setAutoUpload(e.target.checked)}
                        style={{ width: 18, height: 18, cursor: "pointer" }}
                    />
                    <label htmlFor="auto-upload" style={{ cursor: "pointer", fontSize: "0.9rem" }}>
                        📤 Auto-upload to YouTube via Nova Act (set to Private)
                    </label>
                </div>

                {/* Generate Button */}
                <button
                    className="btn btn-primary btn-lg"
                    onClick={handleGenerate}
                    disabled={loading || !blogUrl.trim()}
                    style={{ width: "100%", marginTop: 8 }}
                >
                    {loading ? "Creating job..." : "🚀 Generate Video"}
                </button>
            </div>
        </div>
    );
}
