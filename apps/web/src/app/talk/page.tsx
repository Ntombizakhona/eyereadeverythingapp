"use client";

import { useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { createJob, uploadToS3, type StyleSettings } from "@/lib/api";

export default function TalkPage() {
    const router = useRouter();
    const [recording, setRecording] = useState(false);
    const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
    const [audioUrl, setAudioUrl] = useState<string | null>(null);
    const [uploadedFile, setUploadedFile] = useState<File | null>(null);
    const [timer, setTimer] = useState(0);
    const [loading, setLoading] = useState(false);
    const [autoUpload, setAutoUpload] = useState(false);
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const chunksRef = useRef<Blob[]>([]);

    const [style, setStyle] = useState<StyleSettings>({
        duration: "medium",
        tone: "casual",
        audience: "general",
        voice: "polly_default",
        visual_style: "cinematic",
    });

    const formatTime = (s: number) => {
        const m = Math.floor(s / 60);
        const sec = s % 60;
        return `${m.toString().padStart(2, "0")}:${sec.toString().padStart(2, "0")}`;
    };

    const startRecording = useCallback(async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mr = new MediaRecorder(stream, { mimeType: "audio/webm" });
            chunksRef.current = [];

            mr.ondataavailable = (e) => {
                if (e.data.size > 0) chunksRef.current.push(e.data);
            };

            mr.onstop = () => {
                const blob = new Blob(chunksRef.current, { type: "audio/webm" });
                setAudioBlob(blob);
                setAudioUrl(URL.createObjectURL(blob));
                stream.getTracks().forEach((t) => t.stop());
            };

            mediaRecorderRef.current = mr;
            mr.start(1000);
            setRecording(true);
            setTimer(0);
            timerRef.current = setInterval(() => setTimer((t) => t + 1), 1000);
        } catch (err) {
            alert("Could not access microphone. Please allow microphone access.");
        }
    }, []);

    const stopRecording = useCallback(() => {
        if (mediaRecorderRef.current) {
            mediaRecorderRef.current.stop();
            setRecording(false);
            if (timerRef.current) clearInterval(timerRef.current);
        }
    }, []);

    const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            setUploadedFile(file);
            setAudioBlob(file);
            setAudioUrl(URL.createObjectURL(file));
        }
    };

    const handleGenerate = async () => {
        if (!audioBlob) return;
        setLoading(true);
        try {
            const file = uploadedFile || new File([audioBlob], "recording.webm", { type: "audio/webm" });
            const s3Key = await uploadToS3(file);

            const job = await createJob({
                mode: "TALK",
                audio_s3_key: s3Key,
                style,
                auto_upload_youtube: autoUpload,
            });
            router.push(`/job/?id=${job.job_id}`);
        } catch (err) {
            console.error(err);
            alert("Failed to create job.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="container">
            <div className="page-header">
                <h1>
                    🎙️ Talk <span className="gradient-text">→ Video</span>
                </h1>
                <p>Record your idea or upload an audio clip. We&apos;ll handle the rest.</p>
            </div>

            <div className="glass-card" style={{ maxWidth: 720, margin: "0 auto" }}>
                {/* Recorder */}
                <div className={`recorder ${recording ? "recording" : ""}`}>
                    <button
                        className={`record-btn ${recording ? "recording" : ""}`}
                        onClick={recording ? stopRecording : startRecording}
                        title={recording ? "Stop recording" : "Start recording"}
                    />
                    <span className="record-timer">{formatTime(timer)}</span>
                    <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                        {recording ? "Recording... click to stop" : "Click to start recording"}
                    </p>
                </div>

                {/* Or upload */}
                <div style={{ textAlign: "center", margin: "24px 0", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                    — or upload an audio file —
                </div>

                <div className="form-group">
                    <input
                        type="file"
                        accept="audio/*"
                        onChange={handleFileUpload}
                        className="form-input"
                        style={{ cursor: "pointer" }}
                    />
                </div>

                {/* Audio preview */}
                {audioUrl && (
                    <div style={{ margin: "16px 0" }}>
                        <audio controls src={audioUrl} style={{ width: "100%" }} />
                    </div>
                )}

                {/* Style Controls */}
                <div className="controls-grid" style={{ marginTop: 24 }}>
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
                        placeholder="e.g. tech professionals, beginners..."
                        value={style.audience}
                        onChange={(e) => setStyle({ ...style, audience: e.target.value })}
                    />
                </div>

                {/* YouTube Upload Toggle */}
                <div className="form-group" style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <input
                        type="checkbox"
                        id="auto-upload-talk"
                        checked={autoUpload}
                        onChange={(e) => setAutoUpload(e.target.checked)}
                        style={{ width: 18, height: 18, cursor: "pointer" }}
                    />
                    <label htmlFor="auto-upload-talk" style={{ cursor: "pointer", fontSize: "0.9rem" }}>
                        📤 Auto-upload to YouTube via Nova Act (set to Private)
                    </label>
                </div>

                <button
                    className="btn btn-primary btn-lg"
                    onClick={handleGenerate}
                    disabled={loading || !audioBlob}
                    style={{ width: "100%", marginTop: 8 }}
                >
                    {loading ? "Uploading & creating job..." : "🚀 Generate Video"}
                </button>
            </div>
        </div>
    );
}
