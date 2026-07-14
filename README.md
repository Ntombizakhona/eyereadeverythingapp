# eyereadeverything

**Turn any blog post, text, or voice idea into a YouTube-ready video package — powered by Amazon Nova AI.**

eyereadeverything is a production-grade, AWS-native microservices application that takes a blog URL, raw text, or audio recording and generates a complete YouTube package: script, narration, video, AI-generated thumbnail, captions, and metadata.

---

## Modes

| Mode | Input | How It Works |
|------|-------|-------------|
| **Blog → Video** | Blog URL | Nova Pro extracts and analyzes content from the URL |
| **Text → Video** | Pasted text | Direct text input — no URL fetching needed |
| **Talk → Video** | Audio recording | Amazon Transcribe converts speech to text |

All three modes feed into the same AI pipeline: plan → script → metadata → captions → thumbnail → narration → render → package.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Frontend (Next.js on ECS Fargate)                                  │
│  ┌──────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌─────────┐ │
│  │ Home │ │ Blog→Video │ │ Text→Video │ │ Talk→Video │ │Dashboard│ │
│  └──────┘ └────────────┘ └────────────┘ └────────────┘ └─────────┘ │
└────────────────────────────┬────────────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│  API (FastAPI on ECS Fargate)                                        │
└────────────────────────────┬─────────────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│  AWS Step Functions Pipeline                                         │
│                                                                      │
│  Validate → Ingest → Context → Generate → TTS → Render → Package    │
│                                    │                                 │
│                          ┌─────────┴──────────┐                      │
│                          │  Nova Pro (5 stages)│                      │
│                          │  + Nova Canvas thumb│                      │
│                          └────────────────────┘                      │
│                                                    ↓                 │
│                                            [Optional] Nova Act       │
│                                            YouTube Upload            │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Amazon Nova AI Integration

| Model | Purpose |
|-------|---------|
| **Nova Pro** | Content extraction, video planning, script writing, metadata, captions, render plans |
| **Nova Canvas** | AI-generated YouTube thumbnails (1280×720) |
| **Nova Act** | Browser automation for blog scraping and YouTube uploads |
| **Polly (Neural)** | Text-to-speech narration with SSML style-matching |

---

## Quick Start

### Prerequisites

- Node.js 18+, Python 3.11+, AWS CLI, Docker

### Run Locally

```bash
# Install
cd apps/web && npm install && cd ../..
pip install -r apps/api/requirements.txt

# Configure
cp .env.example .env

# Start
cd apps/api && uvicorn main:app --reload    # API at :8000
cd apps/web && npm run dev                   # Web at :3000
```

### Deploy to AWS

```bash
cd infra && npm install
npx cdk bootstrap
npx cdk deploy
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for full deployment guide.

### Run Tests

```bash
pip install -r tests/requirements-test.txt
python -m pytest tests/ -v
```

---

## Project Structure

```
eyereadeverything/
├── apps/
│   ├── web/                      # Next.js frontend (ECS Fargate)
│   │   └── src/app/
│   │       ├── page.tsx              # Home — hero + 3 mode cards
│   │       ├── blog/page.tsx         # Blog → Video form
│   │       ├── text/page.tsx         # Text → Video textarea
│   │       ├── talk/page.tsx         # Talk → Video recorder
│   │       ├── job/[id]/page.tsx     # Job status timeline
│   │       └── dashboard/page.tsx    # Job history + quick actions
│   └── api/                      # FastAPI backend (ECS Fargate)
│       ├── main.py
│       ├── config.py
│       ├── models.py                 # BLOG, TEXT, TALK modes
│       └── routes/
├── services/
│   ├── validate/                 # Input validation Lambda
│   ├── ingest/                   # Blog extraction (Nova Pro) / Transcribe / Text passthrough
│   ├── context/                  # Embeddings + OpenSearch Lambda
│   ├── generate/                 # Nova Pro 5-stage pipeline + Nova Canvas thumbnails
│   │   └── prompts/                  # 6 structured prompt templates
│   ├── tts/                      # Polly narration Lambda
│   ├── package/                  # ZIP + pre-signed URLs Lambda
│   ├── render-worker/            # FFmpeg video render (ECS Fargate)
│   └── nova-act-worker/          # Nova Act browser automation (ECS Fargate)
│       ├── upload.py                 # YouTube upload via Nova Act
│       └── scrape.py                 # Blog scraping via Nova Act
├── infra/                        # AWS CDK (TypeScript)
│   └── lib/eyereadeverything-stack.ts         # Full stack: VPC, ECS, Lambda, S3, DynamoDB, Step Functions
├── tests/                        # pytest test suite
├── scripts/deploy.sh             # Deployment automation
├── DEPLOYMENT.md                 # Deployment guide
└── .env.example
```

---

## Pipeline Stages

1. **Validate:** Check inputs, map duration settings
2. **Ingest** Extract blog content (Nova Pro), transcribe audio, or pass through text
3. **Context:** Retrieve channel style exemplars via embeddings (OpenSearch)
4. **Generate:** 6-stage Nova Pro pipeline:
   - Video Plan → Script → Metadata → Captions → Render Plan → AI Thumbnail (Nova Canvas)
5. **TTS:** Polly neural narration with SSML prosody controls
6. **Render:** FFmpeg video assembly (ECS Fargate)
7. **Package:** ZIP bundle + pre-signed download URLs
8. **Upload:** Nova Act YouTube automation (optional)

---

## AWS Services

| Service | Purpose |
|---------|---------|
| **ECS Fargate** | API, web frontend, render worker, Nova Act worker |
| **Lambda** | Pipeline stages (validate → package) |
| **Step Functions** | Workflow orchestration |
| **S3** | Upload storage, render outputs |
| **DynamoDB** | Job records, voice profiles |
| **Bedrock** | Nova Pro (generation), Nova Canvas (thumbnails) |
| **Polly** | Neural TTS narration |
| **Transcribe** | Audio-to-text for Talk mode |
| **ECR** | Container image registry |
| **ALB** | Load balancing for API and web |

---

## License

MIT
