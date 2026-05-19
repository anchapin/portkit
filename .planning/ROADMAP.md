# portkit Roadmap

**Version**: 1.2
**Created**: 2026-03-13
**Last Updated**: 2026-03-29
**Status**: Active

---

## Roadmap Overview

This roadmap defines the phased delivery plan for portkit, organized into milestones and phases. Each phase contains detailed plans linked to requirements (REQ-IDs).

### Timeline Summary

```
2026
├── Q1 (Jan-Mar): Foundation & MVP
│   ├── Milestone v0.1: Core Infrastructure (Weeks 1-4)
│   └── Milestone v0.2: AI Conversion Pipeline (Weeks 5-8)
│
├── Q2 (Apr-Jun): MVP Launch
│   ├── Milestone v0.3: QA & Testing (Weeks 9-12)
│   └── Milestone v1.0: Public Beta (Weeks 13-16)
│
├── Q3 (Jul-Sep): Enhancement
│   ├── Milestone v1.5: Advanced Features (Months 5-6)
│   └── Milestone v2.0: Platform Expansion (Months 7-9) ✅ COMPLETE
│
└── Q4 (Oct-Dec): Automation & Scale
    ├── Milestone v2.5: Automation & Mode Conversion (Weeks 1-6) 📅 PLANNED
    └── Milestone v5.0: Coverage Optimization (Weeks 7-10) 📅 PLANNED
```

---

## Milestone v0.1: Core Infrastructure

**Duration**: Weeks 1-4 (Month 1)  
**Goal**: Foundational infrastructure for file handling, user management, and job processing  
**Success Criteria**: Users can upload files, create accounts, and track job status

### Phase 0.1: Project Setup & Infrastructure

**Phase Goal**: Establish development environment, CI/CD, and core infrastructure

**Deliverables**:
- [ ] Development environment setup (Docker Compose)
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Database schema with pgvector
- [ ] Redis job queue foundation
- [ ] Basic logging and monitoring

**Requirements Mapped**: REQ-1.11, REQ-1.12, REQ-1.15

**Plan**: `phases/01-foundation/01-01-PLAN.md`

---

### Phase 0.2: User Authentication & API

**Phase Goal**: Implement user accounts, authentication, and basic API endpoints

**Deliverables**:
- [ ] Email/password registration with verification
- [ ] Login/logout with JWT tokens
- [ ] Password reset flow
- [ ] Rate limiting middleware
- [ ] API key management

**Requirements Mapped**: REQ-1.13, REQ-1.14

**Plan**: `phases/01-foundation/01-02-PLAN.md`

---

### Phase 0.3: File Upload & Management

**Phase Goal**: Secure file upload, storage, and retrieval system

**Deliverables**:
- [ ] Drag-and-drop upload interface
- [ ] File validation (type, size, structure)
- [ ] Secure storage with auto-cleanup
- [ ] File download endpoints
- [ ] Storage quota enforcement

**Requirements Mapped**: REQ-1.1, REQ-1.12

**Plan**: `phases/01-foundation/01-03-PLAN.md`

---

## Milestone v0.2: AI Conversion Pipeline

**Duration**: Weeks 5-8 (Month 2)  
**Goal**: Core AI conversion functionality with basic translation capabilities  
**Success Criteria**: 60%+ syntactic correctness on simple mods

### Phase 0.4: Java Code Analysis

**Phase Goal**: Parse and analyze Java mod code with Tree-sitter

**Deliverables**:
- [ ] Tree-sitter Java parser integration
- [ ] AST extraction and traversal
- [ ] Data flow graph construction
- [ ] Mod component identification (items, blocks, entities)
- [ ] Mod loader detection (Forge, Fabric, NeoForge)

**Requirements Mapped**: REQ-1.2, REQ-1.3

**Plan**: `phases/02-ai-pipeline/02-01-PLAN.md`

---

### Phase 0.5: AI Model Integration

**Phase Goal**: Integrate CodeT5+ with RAG for code translation

**Deliverables**:
- [ ] CodeT5+ 16B model deployment (via Ollama or API)
- [ ] BGE-M3 embedding generation
- [ ] pgvector RAG database setup
- [ ] Semantic similarity search
- [ ] Hybrid search (semantic + keyword)
- [ ] Initial seed database (100+ conversions)

**Requirements Mapped**: REQ-1.4, REQ-1.5

**Plan**: `phases/02-ai-pipeline/02-02-PLAN.md`

---

### Phase 0.6: Code Translation Engine

**Phase Goal**: Generate Bedrock JSON and JavaScript from Java

**Deliverables**:
- [ ] Java→Bedrock JSON generation (items, blocks, entities)
- [ ] Java→JavaScript Script API translation
- [ ] Recipe conversion (crafting, smelting)
- [ ] Manifest generation
- [ ] Basic pattern matching for common mod types

**Requirements Mapped**: REQ-1.4

**Plan**: `phases/02-ai-pipeline/02-03-PLAN.md`

---

## Milestone v0.3: QA & Testing

**Duration**: Weeks 9-12 (Month 3)  
**Goal**: Multi-agent QA system and automated testing  
**Success Criteria**: 80%+ functional correctness, 100% syntax validity

### Phase 0.7: Multi-Agent QA System

**Phase Goal**: Implement MetaGPT-style multi-agent quality assurance

**Deliverables**:
- [ ] Translator Agent with SOP
- [ ] Reviewer Agent with SOP
- [ ] Test Agent with SOP
- [ ] Semantic Checker Agent with SOP
- [ ] Agent communication protocol
- [ ] Quality score aggregation

**Requirements Mapped**: REQ-1.6

**Plan**: `phases/03-qa-testing/03-01-PLAN.md`

---

### Phase 0.8: Syntax Validation & Auto-Fix

**Phase Goal**: Ensure generated code is syntactically valid

**Deliverables**:
- [ ] Tree-sitter JavaScript parsing
- [ ] Bedrock JSON schema validation
- [ ] TypeScript compilation check
- [ ] Auto-fix for common syntax errors
- [ ] Error reporting with line numbers

**Requirements Mapped**: REQ-1.7

**Plan**: `phases/03-qa-testing/03-02-PLAN.md`

---

### Phase 0.9: Unit Test Generation

**Phase Goal**: Automated test generation and execution

**Deliverables**:
- [ ] Test case generation from Java docstrings
- [ ] Sandboxed test execution environment
- [ ] Output comparison (Java vs Bedrock)
- [ ] Pass/fail reporting
- [ ] Edge case test generation

**Requirements Mapped**: REQ-1.8

**Plan**: `phases/03-qa-testing/03-03-PLAN.md`

---

## Milestone v1.0: Public Beta

**Duration**: Weeks 13-16 (Month 4)  
**Goal**: Complete user-facing product ready for public beta launch  
**Success Criteria**: 100+ beta users, 4.0+ satisfaction rating

### Phase 1.0: Web Interface

**Phase Goal**: User-friendly web interface for conversion workflow

**Deliverables**:
- [ ] Upload page with drag-and-drop
- [ ] Conversion progress page (real-time WebSocket updates)
- [ ] Results page with conversion report
- [ ] Download management
- [ ] Responsive design (desktop, tablet, mobile)
- [ ] Error handling with user-friendly messages

**Requirements Mapped**: REQ-1.10

**Plan**: `phases/04-user-interface/04-01-PLAN.md`

---

### Phase 1.1: Conversion Report & Export

**Phase Goal**: Comprehensive reporting and .mcaddon packaging

**Deliverables**:
- [ ] Conversion success rate display
- [ ] Component inventory with file paths
- [ ] Incompatible features list with workarounds
- [ ] QA agent feedback summary
- [ ] Unit test results
- [ ] .mcaddon package generation
- [ ] PDF/Markdown report export

**Requirements Mapped**: REQ-1.9

**Plan**: `phases/04-user-interface/04-02-PLAN.md`

---

### Phase 1.2: Documentation & Onboarding

**Phase Goal**: User and developer documentation

**Deliverables**:
- [ ] Getting started guide
- [ ] Video tutorial (5 minutes)
- [ ] FAQ page
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Pricing page
- [ ] Interactive onboarding flow

**Requirements Mapped**: REQ-1.16, REQ-1.17

**Plan**: `phases/04-user-interface/04-03-PLAN.md`

---

### Phase 1.3: Beta Launch & Monitoring

**Phase Goal**: Public beta launch with monitoring and feedback collection

**Deliverables**:
- [ ] Beta launch announcement
- [ ] User feedback collection system
- [ ] Analytics dashboard (conversion metrics)
- [ ] Error alerting (error rate >5%)
- [ ] Performance monitoring (latency, throughput)
- [ ] Support channel (Discord)

**Requirements Mapped**: REQ-1.15

**Plan**: `phases/04-user-interface/04-04-PLAN.md`

---

## Milestone v1.5: Advanced Features

**Duration**: Months 5-6 (Q3)  
**Goal**: Enhanced conversion capabilities and platform features  
**Success Criteria**: 200+ paying subscribers, 80%+ conversion accuracy

### Phase 1.5: Visual Conversion Editor

**Phase Goal**: Side-by-side editor for reviewing conversions

**Deliverables**:
- [ ] Split-pane code viewer
- [ ] Code section highlighting
- [ ] Interactive mapping adjustments
- [ ] Real-time Bedrock preview
- [ ] Manual editing with validation

**Requirements Mapped**: REQ-2.1

**Plan**: `phases/05-advanced/05-01-PLAN.md`

---

### Phase 1.6: Batch & Multi-Version Support

**Phase Goal**: Convert multiple mods and target multiple versions

**Deliverables**:
- [ ] Batch upload and processing
- [ ] Progress dashboard for batches
- [ ] Target version selection (1.19, 1.20, 1.21)
- [ ] Version-specific conversion rules
- [ ] Format version migration scripts

**Requirements Mapped**: REQ-2.2, REQ-2.3

**Plan**: `phases/05-advanced/05-02-PLAN.md`

---

### Phase 1.7: Community Pattern Library

**Phase Goal**: Community-contributed conversion patterns

**Deliverables**:
- [ ] Pattern submission system
- [ ] Rating and review system
- [ ] Pattern search and browse
- [ ] Featured patterns showcase
- [ ] Version tracking

**Requirements Mapped**: REQ-2.4

**Plan**: `phases/05-advanced/05-03-PLAN.md`

---

### Phase 1.8: Platform Integrations

**Phase Goal**: Direct publishing and team features

**Deliverables**:
- [ ] Modrinth OAuth integration
- [ ] CurseForge OAuth integration
- [ ] Auto-description generation
- [ ] Team creation and management
- [ ] Role-based permissions
- [ ] Shared projects

**Requirements Mapped**: REQ-2.9, REQ-2.10

**Plan**: `phases/05-advanced/05-04-PLAN.md`

---

## Milestone v2.0: Platform Expansion

**Duration**: Months 7-9 (Q4)  
**Goal**: Enterprise features and developer tools  
**Success Criteria**: 1,500+ paying users, $150K+ ARR

### Phase 2.0: Developer Tools

**Phase Goal**: CLI and IDE extensions for power users

**Deliverables**:
- [ ] npm/pip installable CLI
- [ ] Batch processing scripts
- [ ] CI/CD integration examples
- [ ] VS Code extension (alpha)
- [ ] Webhook integrations

**Requirements Mapped**: REQ-2.13, REQ-2.14, REQ-2.15

**Plan**: `phases/06-platform/06-01-PLAN.md`

---

### Phase 2.1: Enhanced Testing

**Phase Goal**: Advanced testing and debugging capabilities

**Deliverables**:
- [ ] In-game debugger (breakpoints, variable inspection)
- [ ] Multi-platform testing (Windows, Xbox, mobile)
- [ ] Security scanning
- [ ] Performance profiling
- [ ] Automated regression testing

**Requirements Mapped**: REQ-2.6, REQ-2.7, REQ-2.8

**Plan**: `phases/06-platform/06-02-PLAN.md`

---

### Phase 2.2: Analytics & Marketplace

**Phase Goal**: User analytics and template marketplace

**Deliverables**:
- [ ] Conversion history dashboard
- [ ] Success rate analytics
- [ ] Time saved estimates
- [ ] Template marketplace
- [ ] Creator revenue share system
- [ ] Export analytics (CSV, PDF)

**Requirements Mapped**: REQ-2.11, REQ-2.12

**Plan**: `phases/06-platform/06-03-PLAN.md`

---

### Phase 2.3: Incremental Conversion

**Phase Goal**: Module-by-module conversion with hybrid testing

**Deliverables**:
- [ ] Mod module identification
- [ ] Incremental conversion workflow
- [ ] Hybrid Java/Bedrock testing
- [ ] Per-module progress tracking
- [ ] Module rollback capability

**Requirements Mapped**: REQ-2.5

**Plan**: `phases/06-platform/06-04-PLAN.md`

---

## Future Milestones (v3.0+)

### Milestone v3.0: Bidirectional & Multi-Loader (Months 10-12)

**Phases**:
- Bidirectional conversion (Bedrock→Java)
- Multi-loader conversion (Forge↔Fabric↔NeoForge)
- AI model fine-tuning on successful conversions

**Requirements**: REQ-3.1, REQ-3.2, REQ-3.3

---

### Milestone v4.0: Enterprise & Education (Year 2)

**Phases**:
- Enterprise on-premise deployment
- Educational platform for schools
- API marketplace for third-party integrations

**Requirements**: REQ-3.4, REQ-3.5

---

## Requirements Coverage Matrix

| Requirement | Phase | Milestone | Status |
|-------------|-------|-----------|--------|
| REQ-1.1 | 0.3 | v0.1 | ⏳ Pending |
| REQ-1.2 | 0.4 | v0.2 | ⏳ Pending |
| REQ-1.3 | 0.4 | v0.2 | ⏳ Pending |
| REQ-1.4 | 0.5, 0.6 | v0.2 | ⏳ Pending |
| REQ-1.5 | 0.5 | v0.2 | ⏳ Pending |
| REQ-1.6 | 0.7 | v0.3 | ⏳ Pending |
| REQ-1.7 | 0.8 | v0.3 | ⏳ Pending |
| REQ-1.8 | 0.9 | v0.3 | ⏳ Pending |
| REQ-1.9 | 1.1 | v1.0 | ⏳ Pending |
| REQ-1.10 | 1.0 | v1.0 | ⏳ Pending |
| REQ-1.11 | 0.1 | v0.1 | ⏳ Pending |
| REQ-1.12 | 0.1, 0.3 | v0.1 | ⏳ Pending |
| REQ-1.13 | 0.2 | v0.1 | ⏳ Pending |
| REQ-1.14 | 0.2 | v0.1 | ⏳ Pending |
| REQ-1.15 | 0.1, 1.3 | v0.1, v1.0 | ⏳ Pending |
| REQ-1.16 | 1.2 | v1.0 | ⏳ Pending |
| REQ-1.17 | 1.2 | v1.0 | ⏳ Pending |
| REQ-2.1 | 1.5 | v1.5 | 📅 Future |
| REQ-2.2 | 1.6 | v1.5 | 📅 Future |
| REQ-2.3 | 1.6 | v1.5 | 📅 Future |
| REQ-2.4 | 1.7 | v1.5 | 📅 Future |
| REQ-2.5 | 2.3 | v2.0 | 📅 Future |
| REQ-2.6 | 2.1 | v2.0 | 📅 Future |
| REQ-2.7 | 2.1 | v2.0 | 📅 Future |
| REQ-2.8 | 2.1 | v2.0 | 📅 Future |
| REQ-2.9 | 1.8 | v1.5 | 📅 Future |
| REQ-2.10 | 1.8 | v1.5 | 📅 Future |
| REQ-2.11 | 2.2 | v2.0 | 📅 Future |
| REQ-2.12 | 2.2 | v2.0 | 📅 Future |
| REQ-2.13 | 2.0 | v2.0 | 📅 Future |
| REQ-2.14 | 2.0 | v2.0 | 📅 Future |
| REQ-2.15 | 2.0 | v2.0 | 📅 Future |
| COV-01 | 21.1 | v5.0 | 📅 Future |
| COV-02 | 21.2 | v5.0 | 📅 Future |
| COV-03 | 21.3 | v5.0 | 📅 Future |
| COV-04 | 21.4 | v5.0 | 📅 Future |
| COV-05 | 21.5 | v5.0 | 📅 Future |

---

## Milestone v5.0: Coverage Optimization (NEW)

**Duration**: 4 weeks (Q4 2026)
**Goal**: Increase overall test coverage to 80%+
**Success Criteria**: Coverage >= 80% for both backend and ai-engine

### Phase 21: Coverage Optimization

**Phase Goal**: Systematic coverage increase across high-impact modules

**Plans**:
- [x] 21-01-PLAN.md — AI Engine Core Agents (Wave 1)
- [x] 21-02-PLAN.md — Backend Advanced Services (Wave 1)
- [x] 21-03-PLAN.md — AI Engine Logic & RL (Wave 2)
- [x] 21-04-PLAN.md — Backend API & Data Persistence (Wave 2)
- [x] 21-05-PLAN.md — System-wide Utilities & Main Entrypoints (Wave 3)

---

## Critical Path (Updated)

```
Phase 0.1 (Infrastructure)
    ↓
Phase 0.2 (Auth & API)
    ↓
Phase 0.3 (File Upload)
    ↓
Phase 0.4 (Java Analysis)
    ↓
Phase 0.5 (AI Model + RAG)
    ↓
Phase 0.6 (Translation Engine)
    ↓
Phase 0.7 (Multi-Agent QA)
    ↓
Phase 0.8 (Syntax Validation)
    ↓
Phase 0.9 (Unit Testing)
    ↓
Phase 1.0 (Web UI)
    ↓
Phase 1.1 (Reports & Export)
    ↓
Phase 1.3 (Beta Launch)
    ↓
Phase 21.0 (Coverage Optimization)
```


---

## Research Scout Update — 2026-04-18

*Auto-generated by PortKit Research Scout from weekly arxiv + Semantic Scholar sweep.*

### New Issues Created from Research Findings

| Issue | Paper | Priority |
|-------|-------|----------|
| [#1091 — Conformal reliability scoring](https://github.com/anchapin/portkit/issues/1091) | [Diagnosing LLM Judge Reliability](https://arxiv.org/abs/2604.15302v1) | High |
| [#1089 — Training-free multi-candidate selection (DPC)](https://github.com/anchapin/portkit/issues/1089) | [Dual-Paradigm Consistency](https://arxiv.org/abs/2604.15163v1) | Medium |
| [#1090 — Semantic chunking for large mods](https://github.com/anchapin/portkit/issues/1090) | [LLM Length Generalization](https://arxiv.org/abs/2604.15306v1) | Medium |

### Roadmap Implications

**Phase 0.6 (Code Translation Engine)**
- Add multi-candidate generation (N=3) + DPC-style consistency selection → improves Pass@1 without execution oracle
- Symbolic representation of Java math/physics logic for Bedrock optimization (motivated by [Prism](https://arxiv.org/abs/2604.15272v1))

**Phase 0.7 (Multi-Agent QA System)**
- Add conformal reliability scoring to QA pipeline → each converted block gets a confidence score
- Per-segment "needs manual review" flags surface in conversion report → core to B2B "60-80% accelerator" value prop

**Phase 0.4 (Java Code Analysis)**
- Semantic chunking using Tree-sitter AST boundaries → handles mods > 50k LOC without context overflow
- Topological sort of chunks by dependency → correct ordering preserves inter-class references

**Issue #997 (Fine-tune Code LLM)**
- Add second-stage RL using a generator-discriminator framework (motivated by [RAD-2](https://arxiv.org/abs/2604.15308v1))
- Discriminator trained on QA test suite pass/fail labels → richer training signal than supervised-only

*Full weekly digest: [.planning/research/digest-2026-04-18.md](.planning/research/digest-2026-04-18.md)*


---

## Research Scout Update — 2026-04-20

*Auto-generated by PortKit Research Scout — weekly arxiv + Semantic Scholar sweep.*

### New Issues Created from Research Findings

| Issue | Paper | Priority |
|-------|-------|----------|
| [#1138 — Adversarial Logic Auditor agent for Multi-Agent QA](https://github.com/anchapin/portkit/issues/1138) | [ASMR-Bench: Auditing for Sabotage in ML Research](https://arxiv.org/abs/2604.16286v1) | High |

### Roadmap Implications

**Phase 0.7 (Multi-Agent QA System)**
- Add an "Adversarial Logic Auditor" sub-agent that specifically hunts for subtle logic discrepancies — conversions that pass syntax/schema checks but break gameplay behavior (e.g., off-by-one on damage formulas, entity spawning conditions that silently never fire). Motivated by the ASMR-Bench sabotage audit framework.

**Phase 0.6 (Code Translation Engine)**
- Add a "Pattern Insight Pre-Processor" step before code generation: use a high-level reasoning pass to identify the core technique a Java class is implementing (state machine, loot table, damage curve, event bus subscription) before attempting translation. This reduces hallucinated Bedrock equivalents for non-linear mod mechanics. Motivated by *Learning to Reason with Insight for Informal Theorem Proving*.

**Phase 0.5 (AI Model Integration) — Research Horizon**
- Explore a Bedrock↔Java Knowledge Graph mapping API symbols, obfuscation mappings (Mojang/Yarn), and behavioral semantics. A KG could provide explainable conversion rationale to mod creators. Motivated by *Using LLMs and Knowledge Graphs to Improve ML Interpretability*.

*Full digest: [.planning/research/digest-2026-04-20.md](.planning/research/digest-2026-04-20.md)*


---

## Research Scout Update — 2026-04-27

*Auto-generated by PortKit Research Scout — weekly arxiv + Semantic Scholar sweep.*

### New Issues Created from Research Findings

| Issue | Paper | Priority |
|-------|-------|----------|
| [#1188 — Token budget prediction & cost monitoring](https://github.com/anchapin/ModPorter-AI/issues/1188) | [How Do AI Agents Spend Your Money?](https://arxiv.org/abs/2604.22750v1) | Medium |
| [#1189 — UAE for Bedrock API documentation RAG](https://github.com/anchapin/ModPorter-AI/issues/1189) | [Aligning Dense Retrievers with LLM Utility](https://arxiv.org/abs/2604.22722v1) | Medium |

### Roadmap Implications

**Phase 0.5 (AI Model Integration) / B2B Business Model**
- Add pre-conversion token estimation endpoint (`/estimate`) — show "This mod will cost ~$2.30 to convert" before the job starts. Per-phase cost breakdown in the final report justifies B2B pricing. (Issue #1188)
- Key insight from paper: most tokens are spent in *context re-reads*, not generation. Implement a sliding window context strategy for large mod conversions to cap repeat-read overhead.

**Phase 0.6 (Code Translation Engine)**
- Replace cosine-similarity RAG with UAE embeddings for Bedrock API doc retrieval. UAE finds docs that actually *help the LLM generate correct Bedrock code*, not just docs that look similar to the Java query. Primary payoff: fewer hallucinated Bedrock component names. (Issue #1189)
- UAE requires logged conversion history with correct/incorrect labels — Phase 0.4 logging must be in place first.

**Research Horizon (no issue yet)**
- *Agentic World Modeling* (70%) — structured environment modeling for Java↔Bedrock dynamics. Revisit when Phase 0.7 multi-agent system matures.
- *Vibe Coding UX* (65%) — natural language guidance for the 20-40% manual review step mod creators still do. Worth exploring for the human-in-the-loop phase.

*Full digest: [.planning/research/digest-2026-04-27.md](.planning/research/digest-2026-04-27.md)*

---

## Research Scout Update — 2026-05-04

*Auto-generated by PortKit Research Scout — weekly arxiv + Semantic Scholar sweep.*

### New Issues Created from Research Findings

| Issue | Paper | Priority |
|-------|-------|----------|
| [#1269 — Minecraft-specific reward models for Bedrock API idiomaticity](https://github.com/anchapin/ModPorter-AI/issues/1269) | [Themis: Training Robust Multilingual Code Reward Models](https://arxiv.org/abs/2605.00754v1) | Medium |
| [#1268 — Minecraft contract & repair loop for Bedrock schema validation](https://github.com/anchapin/ModPorter-AI/issues/1268) | [GeoContra: Geography-Grounded Repair](https://arxiv.org/abs/2605.00782v1) | High |
| [#1270 — RunAgent constraint-guided multi-agent execution framework](https://github.com/anchapin/ModPorter-AI/issues/1270) | [RunAgent: Interpreting Natural-Language Plans](https://arxiv.org/abs/2605.00798v1) | Medium |
| [#1267 — Procedural execution diagnostic suite for multi-step conversion fidelity](https://github.com/anchapin/ModPorter-AI/issues/1267) | [When LLMs Stop Following Steps](https://arxiv.org/abs/2605.00817v1) | High |

### Roadmap Implications

**Phase 0.5b (AI Model Integration) — Minecraft-Specific Reward Models**
- Train an RM on Bedrock ecosystem code to score "idiomaticity" vs. "translator output." Enable RL fine-tuning on weighted criteria: 60% correctness + 30% idiomaticity + 10% conciseness. Expected outcome: mod creators report fewer manual edits needed. (Issue #1269)

**Phase 0.3 / 0.6 (QA & Testing / Code Translation) — Minecraft Contract & Repair Loop**
- Implement static validation layer that detects schema violations (coordinate semantics, component nesting, JSON schema, API contract violations) and triggers LLM repair cycles. Reduces cascading failures and silent mod breakage. (Issue #1268)

**Phase 0.6 / 0.7 (Translation Engine / Multi-Agent QA) — RunAgent Constraint-Guided Execution**
- Codify the Java-to-Bedrock conversion protocol as a DAG with step rubrics. Wrap agents in constraint-guided execution to prevent step reordering, skipping, or deviation under time pressure. Provides auditable traces of every conversion. (Issue #1270)

**Phase 0.7 (Multi-Agent QA System) — Procedural Execution Diagnostic Suite**
- Build a 20-30 task benchmark to measure whether agents faithfully execute multi-step procedures (sequential, conditional, loop handling, error recovery). Baseline fidelity scores → target improvements after implementing RunAgent and other procedural fixes. (Issue #1267)

**Research Horizon (no issue yet)**
- *Computational Domain-Specific Evaluation* (70%) — the AutoMat paper (Can Coding Agents Reproduce Findings in Materials Science) offers a methodology for evaluating how agents handle Minecraft-specific code and procedures.

*Full digest: [.planning/research/digest-2026-05-04.md](.planning/research/digest-2026-05-04.md)*

---

## Research Scout Update — 2026-05-11

*Auto-generated by PortKit Research Scout — weekly arxiv + Semantic Scholar sweep.*

### New Issues Created from Research Findings

| Issue | Paper | Priority | Relevance |
|-------|-------|----------|-----------|
| [#1369 — VecCISC reasoning trace clustering for multi-agent code review](https://github.com/anchapin/ModPorter-AI/issues/1369) | [VecCISC: Improving Confidence-Informed Self-Consistency](https://arxiv.org/abs/2605.08070v1) | High | 95% |
| [#1368 — Agentic reasoning pattern discovery for test-time scaling](https://github.com/anchapin/ModPorter-AI/issues/1368) | [LLMs Improving LLMs: Agentic Discovery](https://arxiv.org/abs/2605.08083v1) | Medium | 85% |
| [#1367 — Rubric-grounded evaluation framework for conversion quality](https://github.com/anchapin/ModPorter-AI/issues/1367) | [Rubric-Grounded RL: Structured Judge Rewards](https://arxiv.org/abs/2605.08061v1) | High | 90% |

### Roadmap Implications

**Phase 0.3 (QA & Testing) — Reasoning Trace Clustering & Candidate Selection**
- Multi-agent code review: Instead of simple majority voting, cluster reasoning traces from different agents. Candidates with coherent, converging reasoning paths are more trustworthy. Use confidence-informed selection to pick the highest-weighted candidate. Critical for complex conversions (Java event handlers → Bedrock events, NBT → JSON). (Issue #1369)

**Phase 0.5b / 0.6 (AI Integration / Translation Engine) — Agentic Reasoning Pattern Discovery**
- Replace hand-crafted reasoning patterns with automated discovery via environment feedback. Instead of telling agents a fixed sequence (Extract → Map → Translate), let the framework discover the optimal pattern for each conversion type. Expect higher pass rates on complex conversions without manual prompt engineering. (Issue #1368)

**Phase 0.3 (QA & Testing) — Structured Rubric-Grounded Evaluation**
- Decompose conversion quality into verifiable rubrics: does it preserve intended behavior? Are Bedrock constraints respected? Is the code idiomatic? Each rubric gets a partial-credit score. RL uses structured reward signals (not just binary pass/fail) to fine-tune the conversion pipeline. (Issue #1367)

**Horizon Notes (not issues yet)**
- *Vibe Inference Validation* (75%) — "Vibe coding" paper identifies a class of failures where AI-generated code looks right but violates unstated domain assumptions. Could lead to a dedicated validation phase targeting these blind spots.
- *Conformal Prediction for Path Reasoning* (70%) — Using conformal prediction to provide statistical guarantees over Java-to-Bedrock reasoning paths, improving reliability and interpretability of complex logic mappings.

*Full digest: [.planning/research/digest-2026-05-11.md](.planning/research/digest-2026-05-11.md)*

---

## Research Scout Update — 2026-05-18

*Auto-generated by PortKit Research Scout — weekly arxiv + Semantic Scholar sweep.*
*(Note: automated script hit rate limits this run; papers sourced via manual web search fallback.)*

### New Issues Created from Research Findings

| Issue | Paper | Priority | Relevance |
|-------|-------|----------|-----------|
| [#1577 — Audit PortKit eval pipeline for false failure categories](https://github.com/anchapin/portkit/issues/1577) | [Beyond Translation Accuracy: Addressing False Failures in LLM Code Translation](https://arxiv.org/abs/2605.02195) | High | 85% |
| [#1578 — Pivot-IR transpilation + Aggressive-Partial-Functional RL reward for MMSD fine-tuning](https://github.com/anchapin/portkit/issues/1578) | [CodePivot: Bootstrapping Multilingual Transpilation via RL without Parallel Corpora](https://arxiv.org/abs/2604.18027) | Medium | 85% |
| [#1579 — Iterative agent-driven prompt spec audit across LangGraph pipeline lanes](https://github.com/anchapin/portkit/issues/1579) | [Iterative Audit Convergence in LLM-Managed Multi-Agent Systems](https://arxiv.org/abs/2605.12280) | Medium | 80% |

### Roadmap Implications

**Phase 0.3 (QA & Testing) — Eval Pipeline Integrity**
- A significant share of current "failures" may be pipeline-induced (Bedrock API shim misconfiguration, missing resource links, unenforced runtime constraints) rather than LLM errors. Auditing and fixing the eval harness could improve apparent pass rate without any model changes — and is critical for producing clean MMSD fine-tuning reward labels. (Issue #1577)

**Phase 0.5b (MMSD Fine-Tuning) — Pivot-IR RL Transpilation**
- CodePivot's pivot-IR approach eliminates the parallel corpus bottleneck: train Java→PivotIR and PivotIR→Bedrock separately using abundant unpaired data. The Aggressive-Partial-Functional (APF) reward gives stable partial credit for near-correct conversions — directly complements the Minecraft-specific reward model (#1269). Together, APF + domain reward covers both training stability and idiomaticity. (Issue #1578)

**Phase 0.6 (AI Integration) — Cross-Lane Prompt Spec Audit**
- PortKit's LangGraph pipeline has data contracts flowing across multiple agent lanes. Iterative Claude-driven auditing (checklist-based, sequential rounds until convergence) surfaces prompt-spec consistency defects invisible to single-file review. Targets the class of failures that only appear on complex Java mods, not simple ones. Complements rubric-grounded eval (#1367) by auditing upstream (prompt specs) rather than downstream (output quality). (Issue #1579)

**Horizon Notes (not issues yet)**
- *Tree-Fold Code Evaluation* (75%) — correctness + code quality + developer survey (production-readiness perception). Once Phase 0.3 QA is stable, this adds a third eval dimension that automated correctness benchmarks can't surface.
- *IRIS-14B: LLM IR-to-IR Translation* (65%) — neuro-symbolic interoperability layer concept has structural relevance to PortKit's AST translation, but too low-level for immediate application.

*Full digest: [.planning/research/digest-2026-05-18.md](.planning/research/digest-2026-05-18.md)*