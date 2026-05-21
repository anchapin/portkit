# Portkit Business Assessment - Conversation Summary

**Date:** 2026-05-21
**Status:** Strategic Planning

---

## What We Discussed

### Product Overview
Portkit is an AI-powered Minecraft Java→Bedrock mod converter. The technical foundation is solid (2400+ tests, multi-agent pipeline, 68% coverage on textures/models/recipes/entities/sounds/lang files). The product exists but is not yet in a validated business state.

### Customer Focus
We identified **indie Java mod developers** as the primary target customer — not players who want mods on console. This makes sense because:
- They have money to spend (monetizing mods via CurseForge/Modrinth)
- They understand technical tradeoffs
- They have clear ROI: "I spent $X converting, now I sell to Bedrock players"

### The Defensibility Question
You noted that conversion pipeline and fine-tuned models would be the competitive advantage, but AI will likely one-shot these conversions eventually. This is a side project for you — goal is to make money while you can, not build a 10-year moat.

**Honest assessment:** The moat is 3-5 years max. Unfair advantages that last:
1. Domain-specific training data (real Java mod → Bedrock addon pairs)
2. Edge case handling (custom dimensions, multi-block machines)
3. Consistent output quality (valid .mcaddon files that load)
4. Validation reporting (clear "here's what worked and what didn't")

---

## Lean Canvas Summary

| Element | Decision |
|---------|----------|
| **Customer** | Indie Java mod developers with existing player base |
| **Problem** | Manual conversion takes weeks; no automated tools exist |
| **UVP** | "Only AI-powered tool that converts in minutes, not weeks, with clear reporting" |
| **Solution** | AI conversion pipeline + conversion report + smart defaults |
| **Revenue** | Pay-per-conversion ($19-49) — NOT subscription at launch |
| **Unfair Advantage** | Training data + edge case handling (medium durability) |
| **Channels** | CurseForge/Modrinth, Discord, Reddit, content marketing |
| **Key Metrics** | Conversion success rate, coverage %, time-to-delivery, CAC, LTV |

---

## Critical Gaps Identified

### 1. Pricing Disconnect (HIGH)
- `frontend/PricingPage.tsx` has Free/Pro/Studio/Enterprise ($9.99-$29.99/mo)
- `docs/pricing.md` has Free/Pay-as-you-go/Pro ($2.99-$29.99/conversion)

Two different models. Must unify before launch.

### 2. Launch Status Confusion
Landing page says "Coming Soon — Join the Waitlist" but pricing page exists with Stripe checkout and "14-day free trial." If you're taking pre-orders, call it Early Access. If not, remove the payment flow.

### 3. Weak Social Proof
- "30+ Mods Tested" is a very small sample
- No testimonials, customer names, or case studies
- No NPS or satisfaction scores

### 4. Missing Trust Indicators
No security certifications, no validation evidence, IP policy has disclaimers but no clear legal protection.

---

## Strategic Questions (Unresolved)

1. **What does "good enough" look like?** Is 80% coverage (textures + blocks + basic entities) enough for someone to pay $20/conversion?

2. **Who's your first paying customer likely to be?** Indie dev with 1 mod? Studio with 50 mods?

3. **Marketplace partner strategy** — Microsoft has relationships with big studios. Could Portkit become a recommended tool? Lower priority than getting indie devs first.

4. **Do you want to stay solo or bring in help?** Partner could shift the business model.

---

## Immediate Next Steps

### Priority 1: Validate with Real Users (THIS WEEK)

**Action:** Email all 3 waitlist contacts. Offer free conversion with conditions:
- They must actually install and test the output in Bedrock
- You need honest feedback, not politeness
- If conversion works, you get a testimonial

**Script:**
> "Hey [name], you signed up for early access to Portkit. Do you have a specific Java mod you'd like converted? We're looking for real feedback. If you have a mod handy, I'll do a conversion for free and I need you to actually test it in Bedrock and tell me specifically what worked and what didn't. Deal?"

**Why:** Free gets you feedback. Paid gets you truth. Free-with-conditions gets you both.

### Priority 2: Confirm End-to-End Works
Before offering conversions to anyone, verify the full loop works:
1. User uploads JAR
2. You get back valid .mcaddon
3. Output loads in Bedrock and shows something meaningful

If not ready, fix it first before burning contacts with bad experiences.

### Priority 3: Unify Pricing
Pick one model and stick to it:
- **Recommendation:** Pay-per-conversion ($19-49) over subscription
- Easier to start (no subscription commitment anxiety)
- Natural for one-off use case
- Aligns with ROI story for indie devs

---

## What to Do Next (Priority Order)

| # | Action | When |
|---|--------|------|
| 1 | Confirm conversion loop works end-to-end | Before anything else |
| 2 | Email 3 waitlist contacts with beta offer | This week |
| 3 | Get feedback from beta users | 1-2 weeks |
| 4 | Fix issues found in beta | 2-3 weeks |
| 5 | Get 3 paying customers (even at $10-20) | Before building anything else |
| 6 | Unify pricing page and docs | After first paying customers |

---

## What NOT to Build Yet

- Enterprise tier
- API access
- Multi-tenant architecture
- Advanced analytics
- White-label solution

All of these are premature until you have 10 real customers who are paying money.

---

## Key Metrics to Track

When you get paying customers, measure:

| Metric | Target |
|--------|--------|
| Conversion success rate | >90% produce valid output |
| Coverage % | >70% automated |
| Time-to-delivery | <4 hours for standard mods |
| CAC | <$50 |
| LTV | >$200 |
| LTV:CAC ratio | >3:1 |

---

## Files to Reference

- `docs/pricing.md` — needs unification with frontend pricing
- `docs/ENTERPRISE-ROADMAP.md` — good strategic thinking but premature
- `docs/PRD.md` — full product vision, second persona is better target
- `MILESTONE-v2.5-PLAN.md` — v2.5 automation milestones (never executed)
- `frontend/src/pages/PricingPage.tsx` — current pricing UI (has wrong model)
- `frontend/src/pages/LandingPage.tsx` — "Coming Soon" landing (needs update)

---

*Next session should focus on: validating the conversion loop actually works, and reporting back what beta users say.*