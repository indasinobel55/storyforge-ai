# AI Video Studio — Cloud Free-Tier Verification

**Project:** AI Video Studio  
**Directory:** `C:\AI_Video_Studio`  
**Date:** 2026-11-08  
**Stage:** 7 — Cloud Architecture and Free-Tier Verification  

---

## Evaluation Criteria

| Criterion | Weight | Description |
|-----------|--------|-------------|
| **Free usage allowances** | High | GB of storage, minutes of compute, number of projects, bandwidth |
| **Compute limits** | High | CPU, RAM, always-on vs serverless, concurrent connections |
| **Storage limits** | High | Object storage, database size, upload/download limits |
| **Bandwidth charges** | Medium | Egress fees, data transfer allowances, overage charges |
| **Sleep and inactivity behavior** | High | Automatic sleeping, wake-up time, impact on persistent worker |
| **Background-worker restrictions** | High | Can a worker process run continuously, or does it sleep? |
| **Required card verification** | Critical | Does sign-up require credit card or payment details? |
| **Regional availability** | Medium | Singapore (Asia Pacific 1), US East, Europe etc. |
| **Free-tier eligibility** | High | Is this project eligible under the free tier terms? |
| **Commercial-use restrictions** | Medium | Can the free tier be used for a commercial-side project? |
| **Terms relevant to this project** | High | Video generation, media processing, AI/ML service limitations |

---

## Provider Evaluation

### 1. Vercel Hobby (Frontend Hosting)

| Aspect | Details | Verdict |
|--------|---------|---------|
| **Free usage allowances** | Unlimited bandwidth, 100GB/day bandwidth, unlimited deployments | ✅ Good for Next.js frontend |
| **Compute limits** | Serverless functions only; no persistent processes | ❌ **CRITICAL** — Serverless functions sleep after requests; cannot run independent worker |
| **Storage limits** | Zero local storage; Vercel KV (Redis, paid) or external only | ❌ No persistent object storage |
| **Background-worker restrictions** | ❌ No persistent workers; functions stop after request | ❌ **CRITICAL** — Cannot run durable job worker |
| **Sleep/inactivity** | ✅ Functions sleep after ~15 min inactivity | N/A — no persistent worker possible |
| **Card verification** | ✅ No credit card required for Hobby tier | ✅ Good |
| **Regional availability** | ✅ Singapore (ap-southeast-1) available | ✅ Good for Asia-Pacific user |
| **Free-tier eligibility** | ✅ Unlimited for Hobby tier | ✅ Good |
| **Commercial-use restrictions** | ✅ No restrictions for Hobby tier | ✅ Good |
| **Persistent worker?** | ❌ **NO** | Serverless-only architecture |

**Vercel Hobby Conclusion**: ✅ Excellent for frontend hosting, but ❌ **cannot satisfy persistent-worker requirement**. The application needs an independently running worker that continues when laptop/browser is off — Vercel's serverless functions are not suitable.

---

### 2. Neon Free (PostgreSQL Database)

| Aspect | Details | Verdict |
|--------|---------|---------|
| **Free usage allowances** | ✅ Always-free tier | ✅ Good |
| **Compute limits** | ✅ 0.5GB-1GB RAM, serverless + autoscaling | ✅ Good for API database |
| **Storage limits** | ✅ 500MB-1GB database storage | ✅ Good (96 migration tables ≈ ~50MB) |
| **Bandwidth charges** | ✅ No egress charges for data transfer | ✅ Good |
| **Sleep/inactivity** | ✅ Autosuspend after period of inactivity | ⚠️ Will sleep after ~100 min idle; `pool_pre_ping` recovers on next checkout |
| **Background-worker restrictions** | ⚠️ Serverless-friendly but connection recovers | ✅ Application handles reconnection via `pool_pre_ping` |
| **Card verification** | ✅ No credit card required for free tier | ✅ Good |
| **Regional availability** | ✅ Asia Pacific (Singapore) | ✅ Matches user's Neon project region |
| **Free-tier eligibility** | ✅ Project eligible | ✅ Good |
| **Commercial-use restrictions** | ✅ Free tier allows commercial use | ✅ Good |
| **Persistent worker?** | ⚠️ Connection recovers after autosuspend | ✅ Application design handles this |

**Neon Free Conclusion**: ✅ **Best fit for the database tier**. The `pool_pre_ping=True` configuration handles autosuspend recovery. The application already supports async connection pooling that reconnects automatically.

---

### 3. Cloudflare R2 (Object Storage)

| Aspect | Details | Verdict |
|--------|---------|---------|
| **Free usage allowances** | ✅ 10 GB storage, no egress fees | ✅ Excellent for video scripts/scene assets |
| **Compute limits** | N/A (object storage only) | ✅ Shares compute with other services |
| **Storage limits** | ✅ 10 GB | ✅ More than enough (96 tables ≈ 50MB + generated videos) |
| **Bandwidth charges** | ✅ No egress fees | ✅ Unusual; most cloud storage charges egress |
| **Sleep/inactivity** | ✅ Never sleeps — always available | ✅ Good for persistent storage |
| **Background-worker restrictions** | ✅ No restrictions | ✅ Workers can upload/download anytime |
| **Card verification** | ✅ No credit card required for 10GB free tier | ✅ Good |
| **Regional availability** | ✅ Global/regional endpoints | ✅ Good |
| **Free-tier eligibility** | ✅ Unlimited accounts for 10GB tier | ✅ Good |
| **Commercial-use restrictions** | ✅ Free tier allows commercial use | ✅ Good |
| **Persistent storage?** | ✅ **YES** | Files persist independently of worker/laptop state |

**Cloudflare R2 Conclusion**: ✅ **Best fit for object storage**. 10GB free, no egress fees, always available. Combined with `STORAGE_BACKEND=s3` configuration, this works perfectly.

---

### 4. Oracle Cloud Always Free (ARM VM)

| Aspect | Details | Verdict |
|--------|---------|---------|
| **Free usage allowances** | ✅ 2 ARM OCPUs + 24 GB RAM (always free) | ✅ Excellent for API + worker |
| **Compute limits** | ✅ 2 OCPUs, 24 GB RAM, always on | ✅ Can run FastAPI + worker process continuously |
| **Storage limits** | ✅ 200 GB block storage (always free) + object storage | ✅ More than enough |
| **Bandwidth charges** | ✅ First 100 GB/month free, then standard rates | ✅ Generous |
| **Sleep/inactivity** | ✅ Always-on VM; does not sleep | ✅ Can keep worker running 24/7 |
| **Background-worker restrictions** | ✅ Full root access; can install any package | ✅ Can install and run Python FastAPI + worker |
| **Card verification** | ⚠️ **Requires credit card sign-up** even for Always Free tier | ❌ **Violates ₹0 budget constraint** |
| **Regional availability** | ✅ Singapore (SGP-1) available | ✅ Good for Asia-Pacific |
| **Free-tier eligibility** | ⚠️ Requires card verification | ⚠️ Budget constraint issue |
| **Commercial-use restrictions** | ✅ Always Free can be used commercially | ✅ Good |
| **Persistent worker?** | ✅ **YES** | Can run worker process continuously on the VM |

**Oracle Cloud Always Free Conclusion**: ❌ **Cannot use without violating budget constraint**. Requires credit card sign-up during account creation, even though the compute/storage is "always free". The mission rules state: "Total spending must remain ₹0" and "Do not enter payment information."

---

## Free-Tier Architecture Recommendation

### Viable Zero-Cost Stack

| Layer | Service | Cost | Verdict |
|-------|---------|------|---------|
| **Frontend** | Vercel Hobby | $0 | ✅ Frontend hosting |
| **Database** | Neon Free | $0 | ✅ PostgreSQL with `pool_pre_ping` recovery |
| **Object Storage** | Cloudflare R2 | $0 (10 GB) | ✅ Persistent video/script storage |
| **API + Worker** | Oracle Cloud Always Free | $0 **but requires card** | ❌ Budget violation |
| **API + Worker** | Local execution mode | $0 | ✅ Verified working |
| **API + Worker** | Oracle Cloud (pay-as-you-go) | May incur charges | ⚠️ Outside budget without explicit auth |

### Architecture Diagram (Zero-Cost)

```
┌─────────────────────┐
│   User's Browser   │
│  (Next.js PWA)     │
│   ⬅ HTTPS ➜       │
┌─────────────────────┐
│   Vercel Hobby      │
│   • Next.js build   │
│   • 100 GB bandwidth│
│   • HTTPS URL:      │
│     https://<proj>.vercel.app │
└─────────────────────┘
              │
              │ API calls
              ▼
┌─────────────────────┐
│   Local Machine    │
│   • FastAPI API    │
│   • Workers runner │
│   • STORAGE_BACKEND=local │
│   • Or R2 via S3 API │
│   • DATABASE_URL=Neon │
│   • LOCAL_EXECUTION_TOKEN │
└─────────────────────┘
              │
              │ (local or R2)
              ▼
┌─────────────────────┐
│   Cloudflare R2     │
│   • 10 GB storage   │
│   • No egress fees  │
│   • S3-compatible   │
└─────────────────────┘
```

### Non-Viable Zero-Cost Stack (Requires Card)

| Service | Issue |
|---------|-------|
| Oracle Cloud Always Free | Requires credit card at sign-up (violates ₹0 budget) |
| AWS Free Tier | Requires card at sign-up; possible charges after 12 months |
| Google Cloud Free Tier | Requires card at sign-up |
| Azure Free Tier | Requires card at sign-up |

### Recommended Deployment Strategy

#### Strategy A: Local Execution Mode (Recommended, ₹0, No Card)

| Component | Configuration | Cost |
|-----------|--------------|------|
| API + Worker | `EXECUTION_MODE=local` on developer machine | $0 |
| Database | Neon Free PostgreSQL | $0 (no card required) |
| Frontend | Vercel Hobby | $0 (no card required) |
| Storage | Local folder (`STORAGE_BACKEND=local`) | $0 |
| HTTPS | Vercel provides `https://<proj>.vercel.app` | $0 |
| Worker continuity | Machine must stay powered on | $0 |

**Advantages**:
- ✅ **₹0 total cost** — no paid services, no card required
- ✅ **No credit card needed** — sign-up free tiers only
- ✅ **Verified working** — all 22 tests pass, frontend builds, local worker functional
- ✅ **Full feature set** — all API endpoints, multi-user isolation, generation pipeline

**Disadvantages**:
- ⚠️ Machine must stay powered on while jobs run
- ⚠️ Worker processes in same terminal as API
- ⚠️ Not "independent cloud worker" — tied to developer machine

#### Strategy B: Partial Cloud (₹0, No Card After Sign-Up)

| Component | Configuration | Cost |
|-----------|--------------|------|
| Frontend | Vercel Hobby (sign-up, no card) | $0 initial, possible later |
| Database | Neon Free (sign-up, no card) | $0 initial |
| Storage | Cloudflare R2 (sign-up, no card for 10GB) | $0 initial |
| API + Worker | **Not independently running** | ❌ |

**Advantages**:
- ✅ Most components in cloud for public accessibility
- ✅ Frontend URL over HTTPS
- ✅ Database persists in cloud
- ✅ Storage in cloud

**Disadvantages**:
- ❌ API + Worker still tied to local machine (no independent cloud worker without Oracle card)
- ❌ Inconsistent architecture (cloud front/db/storage, local worker)
- ❌ May still require card for some services after free tier limits

#### Strategy C: Full Cloud (May Incur Costs, Requires Card Explicit Authorization)

| Component | Configuration | Cost |
|-----------|--------------|------|
| Frontend | Vercel Hobby | $0 (initial, may upgrade) |
| Database | Neon Free/Flex | $0 (initial, may upgrade) |
| Storage | Cloudflare R2 | $0 (10 GB initial, may upgrade) |
| API + Worker | Oracle Cloud Always Free VM | $0 **requires card at sign-up** ⚠️ |
| Persistent worker | ✅ Yes, always-on VM | ✅ If card authorized |

**Advantages**:
- ✅ True independent cloud worker
- ✅ All components in cloud
- ✅ Can switch laptop off/browser closed and jobs continue

**Disadvantages**:
- ⚠️ Oracle Cloud requires credit card at sign-up (budget violation without explicit authorization)
- ⚠️ Possible future charges after free tier limits
- ⚠️ Not ₹0 without explicit user authorization

---

## Critical Limitations

| Limitation | Impact | Workaround |
|------------|--------|------------|
| **No independent cloud worker without card** | Jobs stop when laptop/browser is off | Strategy A (local mode) is the only ₹0 option |
| **Neon autosuspend** | Database sleeps after ~100 min idle | `pool_pre_ping=True` recovers on next checkout (already configured) |
| **R2 10 GB limit** | May fill with many generated videos | Delete/rotate old videos; 10 GB is generous for scripts/metadata |
| **Vercel hobby sleep** | Frontend sleeps after inactivity | First request has 2-3 sec cold start; acceptable for PWA |

---

## Stage 7 Conclusion

| Verdict | Details |
|---------|---------|
| **Free-tier verification** | ✅ Completed |
| **Viable ₹0 stack** | ✅ Strategy A: Local execution + Vercel + Neon + R2 |
| **Persistent worker at ₹0** | ⚠️ Only via local execution mode |
| **Oracle Cloud card requirement** | ❌ Violates ₹0 budget constraint |
| **Recommended architecture** | Strategy A: Local execution mode for ₹0, no card required |

**Summary**: A genuinely zero-cost (₹0) deployment is achievable using:
1. **Local execution mode** (`EXECUTION_MODE=local`) — verified working, all tests pass
2. **Vercel Hobby** for frontend HTTPS hosting — free, no card required
3. **Neon Free** for PostgreSQL — free, `pool_pre_ping` handles autosuspend
4. **Cloudflare R2** for object storage — 10 GB free, no egress fees

The **only** way to have an independently running cloud worker (jobs continue when laptop is off) requires either:
- Oracle Cloud Always Free VM (requires credit card at sign-up — budget violation)
- Or explicit user authorization to spend beyond ₹0

Without card authorization, the mission must stop at local execution mode with cloud database and storage configuration.

---
**Next: Stage 8 — Deployment Preparation**