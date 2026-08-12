---
name: product-marketing
description: "Use when creating or updating product-marketing context."
version: 2.1.0-hermes.1
author: Corey Haines; Hermes-curated adaptation
license: MIT
metadata:
  hermes:
    tags: [product-marketing, positioning, icp, messaging, jtbd]
    homepage: https://github.com/coreyhaines31/marketingskills/tree/main/skills/product-marketing
    upstream_commit: 7868cb9251fad80a73d26e488a5ad5f6c4a9f335
---

# Product Marketing Context

Create and maintain a project-local product-marketing context that other marketing tasks can reuse. This is a locally curated Hermes adaptation of Corey Haines' MIT-licensed `product-marketing` skill at the pinned upstream commit.

## Safety and evidence rules

1. **Project-local scope only.** Work inside the user's explicitly identified project or repository. Do not scan the home directory, unrelated repositories, cloud drives, emails, credentials, `.env`, auth files, customer exports, analytics, CRM, support systems, or private conversations unless the user explicitly authorizes that source for this task.
2. **Read narrowly.** For auto-drafting, inspect likely marketing sources first: README, public landing/pricing/about pages, public docs, package metadata, and explicitly named files. Expand only when necessary.
3. **No automatic move or overwrite.** Never move legacy context, replace an existing document, or create `.agents/product-marketing.md` without showing the proposed result or targeted diff and receiving approval.
4. **Preserve provenance.** Distinguish verified facts, customer evidence, internal claims, inferred hypotheses, and unknowns.
5. **No invented proof.** Never fabricate customer quotes, metrics, logos, pricing, market size, competitors, objections, credentials, or research.
6. **Minimize sensitive data.** Store roles and patterns rather than personal data. Do not copy names, emails, phone numbers, confidential deal details, or private quotations unless required and approved.
7. **One project, one context.** Do not treat the document as global truth across unrelated products or brands.

## Canonical location

Default to `.agents/product-marketing.md` in the current project root. Before using it:

- Confirm the current project root.
- Check `.agents/product-marketing.md`.
- If absent, check project-local legacy locations such as `.claude/product-marketing.md`, `.agents/product-marketing-context.md`, `.claude/product-marketing-context.md`, and `product-marketing-context.md`.
- If multiple files exist, compare them and report conflicts. Do not merge or move them automatically.
- Respect applicable project policies before reading or writing.

## Workflow

### 1. Choose the task mode

Infer when obvious; otherwise offer:

- **Inspect** — summarize current context, gaps, version, and recent changes.
- **Auto-draft** — draft from explicitly permitted project/public sources.
- **Interview** — gather context conversationally, one section at a time.
- **Targeted update** — change only named sections.
- **Validate** — compare claims against supplied evidence and flag drift.

### 2. Build an evidence ledger

For every important statement, use one of:

- **Verified fact** — supported by public product material, contractually approved data, or user confirmation.
- **Customer evidence** — sourced interview/review/support language with date and permission status.
- **Internal claim** — asserted by the company but not independently proven.
- **Hypothesis** — inference requiring validation.
- **Unknown** — missing information.

Keep source paths or URLs in an evidence section. If the source is private, describe it generically and avoid copying sensitive details.

### 3. Gather only applicable sections

#### Product overview

- One-line factual description
- Product category and alternatives buyers compare
- Product type, delivery model, deployment, region
- Business model and current public pricing status
- Main capabilities and boundaries

#### Market and audience

- Market segment, industry, company size/stage, geography
- Ideal customer profile and disqualifiers
- Users, champions, decision makers, financial buyers, technical/security influencers
- Trigger events and buying situations
- Jobs to be done and priority use cases

#### Problem and switching dynamics

- Current situation and workaround
- Push away from status quo
- Pull toward the product
- Habits/inertia
- Switching anxiety and risk
- Cost of inaction, only when evidenced

#### Alternatives and competition

- Direct products
- Different approaches solving the same job
- Status quo, internal build, spreadsheets, manual work, or “do nothing”
- Selection criteria and trade-offs

Use neutral, evidence-based descriptions. Do not invent competitor weaknesses or write defamatory claims.

#### Positioning and messaging

- Target segment
- Frame of reference/category
- Primary value
- Differentiated capabilities
- Reasons to believe
- What the product is not
- Message hierarchy by audience and buying stage

#### Objections and anti-personas

- Objection
- Source/frequency
- Honest response
- Evidence or mitigation
- Unresolved risk
- Who should not buy and why

#### Customer language

- Exact wording only when sourced and permitted
- Otherwise label paraphrases explicitly
- Terms customers use, avoid, or misunderstand
- Glossary of product-specific language

#### Voice and claims

- Tone and style
- Approved claims
- Claims requiring qualification
- Prohibited/unsupported claims
- Regulatory or legal review needs

#### Proof

- Metrics with definition, population, period, methodology, and source
- Case studies and testimonials with permission status
- Certifications, integrations, customer counts, and awards with verification date
- Gaps where proof is still needed

#### Goals and measurement

- Business goal
- Target action and funnel stage
- Baseline, target, owner, timeframe, source
- Leading and lagging indicators

### 4. Validate the draft

Before saving:

- Show the complete draft or a focused diff.
- Highlight assumptions, unsupported claims, conflicts, and missing evidence.
- Ask for corrections to substantive facts.
- Ensure no sensitive information is being stored unintentionally.
- Confirm the target path.

### 5. Version and save

Use simple integer document versions: `v1`, `v2`, and so on.

- New document: `v1` with initial changelog entry.
- Substantive approved change: increment version, update date, prepend a concise changelog entry.
- Typo/format-only change: no version bump.
- Preserve previous changelog entries unchanged.
- For material repositioning, describe what changed and why.

Use today's date from the live system when writing; do not guess it.

## Document template

```markdown
# Product Marketing Context

**Product/project:**
**Document version:** v1
**Last updated:** YYYY-MM-DD
**Status:** Draft | Approved | Needs validation
**Owner:**

## Evidence and confidence

| Claim/area | Status | Source/date | Notes |
|---|---|---|---|
| | Verified fact / Customer evidence / Internal claim / Hypothesis / Unknown | | |

## Product overview

**One-line description:**
**Category/frame of reference:**
**Product type/deployment:**
**Business model/pricing status:**
**Core capabilities:**
-
**Boundaries / not a fit for:**
-

## Ideal customer profile

**Organizations:**
**Geography/language:**
**Trigger events:**
**Primary job:**
**Disqualifiers / anti-persona:**

## Buying group

| Role | User/champion/buyer/influencer | Cares about | Risk/objection | Value and proof |
|---|---|---|---|---|
| | | | | |

## Problems and switching dynamics

**Current situation:**
**Push:**
**Pull:**
**Habit/inertia:**
**Anxiety/risk:**
**Cost of inaction:**

## Alternatives and competition

| Alternative | When buyers choose it | Trade-offs | Evidence/source |
|---|---|---|---|
| | | | |

## Positioning

**For:**
**Who need:**
**The product is a:**
**That provides:**
**Unlike:**
**Because:**

## Message hierarchy

1. Primary value:
2. Supporting value:
3. Differentiated capability:
4. Proof:
5. CTA:

## Objections

| Objection | Frequency/source | Honest response | Proof/mitigation | Open risk |
|---|---|---|---|---|
| | | | | |

## Customer language

**Verified quotations:**
- “[quote]” — [source/date/permission]
**Paraphrased themes:**
-
**Words to use:**
**Words to avoid:**
**Glossary:**

## Brand voice and claims

**Tone:**
**Style:**
**Approved claims:**
**Claims requiring qualification:**
**Unsupported/prohibited claims:**

## Proof points

| Proof | Definition/scope | Source/date | Permission/status |
|---|---|---|---|
| | | | |

## Goals and measurement

| Goal | Baseline | Target/timeframe | Source | Owner |
|---|---|---|---|---|
| | | | | |

## Unknowns and validation plan

-

## Changelog

- v1 (YYYY-MM-DD) — Initial approved context.
```

## Quality checks

Before finalizing, verify:

- Product, category, audience, job, differentiator, proof, and CTA are internally consistent.
- Benefits are linked to capabilities and evidence.
- Personas reflect buying roles rather than invented demographics.
- Competitor statements are neutral and sourced.
- Customer language is truly verbatim or clearly marked as paraphrase.
- Metrics define numerator, denominator, population, period, and source where relevant.
- Unknowns remain visible instead of being filled with plausible fiction.
- Context is concise enough that downstream skills can use it reliably.

## Scope boundaries

- Use copywriting workflows to create final campaign or website copy.
- Use customer-research workflows to gather or synthesize interviews and reviews.
- Use competitive research before making detailed comparative claims.
- Use offer strategy for packaging and pricing decisions.
- This skill records product-marketing context; it does not make unapproved strategic decisions or publish assets.
