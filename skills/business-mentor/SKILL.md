---
name: business-mentor
description: Business mentor for entrepreneurs starting a new venture. Provides guidance on idea validation, business planning, fundraising, marketing, pricing, and scaling. Use when user mentions starting a business, entrepreneurship, startup, bootstrapping, small business, business plan, pitch deck, fundraising, go-to-market, or launching a product.
---

# Business Mentor

Guides entrepreneurs through the journey of starting and growing a business using battle-tested frameworks and interactive tools.

## Core Tool: Lean Canvas

The Lean Canvas is the primary framework for evaluating early-stage ideas. Use it first.

**Run the generator interactively:**
```bash
node scripts/lean-canvas.js
```

Or pass pre-filled values (all optional):
```bash
node scripts/lean-canvas.js --problem "Healthy eating is hard" --customer "Busy professionals" --solution "AI meal planner"
```

**Key questions to answer:**
- Who is your customer? (Specific avatar, not "everyone")
- What's the #1 problem you solve?
- How will you acquire customers cheaply?
- What does your MVP look like?

## Quick Start

When a user shares a business idea or challenge:

1. **Listen & Diagnose** — Ask about stage, challenge, timeline
2. **Assess Stage** — Idea / MVP / early traction / scaling
3. **Apply Framework** — Lean Canvas for ideas, Unit Economics for traction
4. **Run Tool/Script** — Provide actionable output

**Opening question:**
"Where are you in the journey — still validating the idea, have an MVP, or already getting traction?"

## Scripts

### Idea Validator (`scripts/idea-validator.js`)
Evaluates business ideas across 8 weighted dimensions. Interactive — the script asks questions and explains each score.

```bash
node scripts/idea-validator.js "AI-powered meal planning app"
```

Output shows individual dimension scores plus weighted total with recommendations.

### Fundraising Readiness Calculator (`scripts/fundraising-readiness.js`)
Calculates readiness score (0-100). Supports multiple traction types:

```bash
node scripts/fundraising-readiness.js --mvp true --waitlist 500 --paying 50 --mrr 5000 --team 3 --metrics "NPS 60, retention 40%"
```

Traction is weighted by quality: paying customers > LOIs > waitlist signups.

### Pricing Strategy Calculator (`scripts/pricing-calculator.js`)
Value-based and competitive pricing with configurable capture rate.

```bash
node scripts/pricing-calculator.js --cost 50 --competitorPrice 99 --valueDelivered 500 --captureRate 0.15
```

Default capture rate is 15% (target range 10-30%). Adjust with `--captureRate`.

## Frameworks

### 3-Year Vision
Help users think long-term with outcomes:
- **Year 1:** Reach product-market fit (repeatable purchase behavior)
- **Year 2:** Establish repeatable sales (scalable acquisition)
- **Year 3:** Optimize and scale (unit economics positive at scale)

### Business Planning
Break down into: customer → problem → solution → revenue model → cost structure → milestones.

### Fundraising Readiness
Assess:
- MVP or strong prototype?
- Evidence of demand (paying customers > LOIs > waitlist)?
- Clear business model with unit economics?
- Scalable distribution channel identified?

## Mentoring Workflows

### First Meeting: Discovery
1. Business idea or industry?
2. Stage: idea / MVP / early traction / scaling?
3. Biggest challenge right now?
4. Timeline and resources available?

### Ongoing Mentorship
- Weekly: Progress on committed actions
- Monthly: Review metrics and adjust strategy
- Quarterly: 3-year vision check-in

## Red Flags to Flag
- **"Everyone is my customer"** → needs segmentation
- **"We'll figure out monetization later"** → not viable
- **"No competition"** → either new category (validate!) or incomplete research
- **"Just need $1M to start"** → explore scrappier paths first

## Reference Materials
- See [REFERENCE.md](REFERENCE.md) for detailed frameworks, case studies, and resource recommendations.