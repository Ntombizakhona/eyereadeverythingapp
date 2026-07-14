import Link from "next/link";

export default function Home() {
  return (
    <div className="container">
      {/* Hero Section */}
      <section className="hero">
        <div className="hero-badge">
          <span className="hero-badge-dot" />
          Powered by Amazon Nova AI
        </div>
        <h1 className="hero-title">
          Turn Any Idea Into a<br />
          <span className="gradient-text">YouTube-Ready Video</span>
        </h1>
        <p className="hero-subtitle">
          Paste a blog URL or speak your idea. We generate the script, narration,
          visuals, captions, and metadata — ready to upload.
        </p>
      </section>

      {/* Mode Cards */}
      <div className="mode-cards">
        <Link href="/blog" className="glass-card mode-card blog">
          <div className="mode-card-icon">📝</div>
          <h2 className="mode-card-title">Blog → Video</h2>
          <p className="mode-card-desc">
            Paste a blog URL or choose from your connected feed.
            We&apos;ll extract the content, generate a script, narrate it,
            and render a complete YouTube package.
          </p>
        </Link>

        <Link href="/text" className="glass-card mode-card blog">
          <div className="mode-card-icon">✍️</div>
          <h2 className="mode-card-title">Text → Video</h2>
          <p className="mode-card-desc">
            Write or paste any text — an article, essay, idea, or notes.
            We&apos;ll generate a script, narrate it, and render
            a complete YouTube-ready video.
          </p>
        </Link>

        <Link href="/talk" className="glass-card mode-card talk">
          <div className="mode-card-icon">🎙️</div>
          <h2 className="mode-card-title">Talk → Video</h2>
          <p className="mode-card-desc">
            Record your idea or upload an audio clip.
            Our AI will transcribe, plan, script, and render
            your thoughts into a polished video.
          </p>
        </Link>
      </div>

      {/* Features Row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "16px", marginTop: "64px", marginBottom: "64px" }}>
        {[
          { icon: "🧠", title: "Nova 2 Lite", desc: "AI script & metadata generation" },
          { icon: "🎥", title: "Nova Reel", desc: "AI-generated video footage" },
          { icon: "🔊", title: "Polly Narration", desc: "Neural voice synthesis" },
          { icon: "🎬", title: "FFmpeg Compositing", desc: "Overlays, captions & assembly" },
          { icon: "📤", title: "Nova Act", desc: "Auto-upload to YouTube" },
        ].map((f) => (
          <div key={f.title} className="glass-card" style={{ textAlign: "center", padding: "24px" }}>
            <div style={{ fontSize: "2rem", marginBottom: "12px" }}>{f.icon}</div>
            <h3 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "4px" }}>{f.title}</h3>
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{f.desc}</p>
          </div>
        ))}
      </div>

      {/* Visual Styles Showcase */}
      <section style={{ marginBottom: "80px" }}>
        <div style={{ textAlign: "center", marginBottom: "28px" }}>
          <h2 style={{ fontFamily: "'Outfit', sans-serif", fontSize: "1.6rem", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "6px" }}>
            Pick your visual style
          </h2>
          <p style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>
            Every video can be rendered in the look you want — powered by Amazon Nova Reel.
          </p>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "12px" }}>
          {[
            { icon: "🎬", title: "Cinematic", desc: "Realistic live-action footage" },
            { icon: "🎨", title: "Cartoon", desc: "2D flat-design animation" },
            { icon: "🌸", title: "Anime", desc: "Cel-shaded Japanese style" },
            { icon: "🧱", title: "Claymation", desc: "Stop-motion clay look" },
            { icon: "🖌️", title: "Watercolor", desc: "Hand-painted illustration" },
          ].map((s) => (
            <div key={s.title} className="glass-card" style={{ textAlign: "center", padding: "20px" }}>
              <div style={{ fontSize: "1.8rem", marginBottom: "10px" }}>{s.icon}</div>
              <h3 style={{ fontSize: "0.9rem", fontWeight: 600, marginBottom: "4px" }}>{s.title}</h3>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", lineHeight: 1.4 }}>{s.desc}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
