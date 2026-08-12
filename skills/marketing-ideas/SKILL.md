---
name: marketing-ideas
description: "Use when generating evidence-aware marketing experiments."
version: 2.0.0-hermes.1
author: Corey Haines; Hermes-curated adaptation
license: MIT
metadata:
  hermes:
    tags: [marketing-ideas, ideation, growth, experiments, prioritization]
    homepage: https://github.com/coreyhaines31/marketingskills/tree/main/skills/marketing-ideas
    upstream_commit: 7868cb9251fad80a73d26e488a5ad5f6c4a9f335
    related_skills: [product-marketing, content-strategy, customer-research, b2b-ai-offer-strategy]
---

# Marketing ideas

Generate and prioritize context-specific marketing hypotheses, not a list of universally “proven” tactics. This is a locally curated Hermes adaptation of Corey Haines' MIT-licensed `marketing-ideas` skill at the pinned upstream commit.

Default to a shortlist and test brief in chat. Brainstorming authorizes analysis only. It does not authorize research into private systems, contact collection, outreach, posting, account actions, ad creation, budget spend, tracking, data sharing, purchasing, publishing, product changes, discounts, giveaways, partnerships, or contracts.

## Safety and evidence rules

1. **Project-local scope.** Use only explicitly supplied information and relevant files inside an identified project. Do not inspect unrelated folders, cloud drives, CRM, analytics, email, support, contact lists, browser profiles, credentials, `.env`, or private conversations without authorization for the named source and purpose.
2. **Ideas are hypotheses.** Do not label a tactic “proven,” “quick win,” “high intent,” “low cost,” or “best” without comparable evidence. Separate `Observed evidence`, `Internal claim`, `Third-party estimate`, `Hypothesis`, and `Unknown`.
3. **No automatic external research.** A request for ideas does not authorize competitor crawling, social listening, keyword research, customer-data mining, paid APIs, or private-community access. Propose a bounded research scope first when evidence is needed.
4. **No execution by implication.** Recommending a channel or experiment does not authorize implementation. Obtain explicit approval before contacting anyone, creating accounts, installing software, changing a product/site, submitting listings, launching ads, spending money, publishing, sending, scheduling, or entering an agreement.
5. **Claims and attribution.** Never invent audience demand, traffic, rankings, conversion, ROI, customer stories, reviews, awards, endorsements, scarcity, urgency, product results, competitor weaknesses, or market prevalence. Define metrics and attribution limits.
6. **Privacy and consent.** Do not recommend hidden tracking, fingerprinting, data-broker enrichment, cross-site identity stitching, unauthorized customer-data use, private-community mining, contact scraping, or audience sharing. Tracking, personalization, email, CRM, referral, webinar, and lead-capture ideas need dedicated privacy and consent design.
7. **No audience or pixel sharing by default.** Do not share remarketing pixels, hashed lists, lookalike seeds, CRM audiences, event data, or conversion data with partners/platforms without documented roles, notice/consent analysis, contracts, minimization, security, retention, and approval.
8. **Platform integrity.** Exclude engagement pods, fake reviews, review gating, coordinated inauthentic behavior, required social engagement that violates platform rules, deceptive account use, cloaking, purchased followers, undisclosed automation, and bypassing moderation or rate limits.
9. **Search integrity.** Avoid parasite/reputation abuse, doorway or thin programmatic pages, copied comparison pages, fabricated glossaries, mass low-value content, manipulative link schemes, or claims that a domain/platform will “rank faster.” Search ideas must provide distinct user value and follow current platform policies.
10. **Competitor fairness.** Comparisons and competitor-keyword campaigns require current evidence, neutral trade-offs, trademark/legal review where applicable, and no confusion about affiliation. Do not exploit confidential data, misrepresent weaknesses, impersonate, intercept accounts, or make defamatory claims.
11. **Outreach and communications.** Cold email, journalist pitches, podcast tours, influencer outreach, customer reactivation, newsletters, DMs, and partner swaps require legitimate targeting, consent/legal assessment, accurate identity, suppression handling, easy opt-out, and separate approval before sending. No mass unsolicited outreach.
12. **Partnerships and endorsements.** Affiliate, reseller, influencer, expert, referral, sponsorship, whitelisting, newsletter swap, certification, and integration programs need documented terms, disclosure, brand permissions, conflicts, data roles, fraud controls, tax/accounting review, and consent boundaries.
13. **Influencer whitelisting is sensitive.** Running ads from another person's account requires explicit written authorization, scoped access, approval rights, disclosure, account-security controls, end date, and verification. Never request passwords or take over accounts.
14. **Promotions and giveaways.** Contests, sweepstakes, referral rewards, grants, discounts, free trials, lifetime deals, early-access pricing, and giveaways require official rules, eligibility, geography, prize/odds disclosures, taxes, platform policy, privacy, consumer-law review, fulfillment, fraud controls, and budget approval. Do not require unlawful or prohibited engagement.
15. **No fabricated urgency.** Seasonal campaigns, launch windows, early access, limited inventory, price changes, and scarcity must be real, material, disclosed, and honored. Avoid fake countdowns, surprise renewal, hidden conditions, or pressure based on manufactured fear.
16. **Rights and provenance.** Verify permissions and licenses for customer language, quotes, screenshots, product data, original research, user stories, reviews, logos, images, music, documentaries, books, courses, playlists, templates, open-source releases, datasets, and third-party examples.
17. **Product and security ideas need engineering review.** Importers, scanners, extensions, APIs, OAuth, migrations, viral loops, powered-by badges, onboarding/offboarding, free tools, public demos, and open-source components require threat modeling, privacy, accessibility, abuse prevention, maintenance, terms, support, and truthful product behavior.
18. **Sensitive domains and groups.** Health, finance, legal, employment, housing, education, insurance, minors, politics, and vulnerable audiences require specialist review. Do not use protected or inferred sensitive traits for discriminatory targeting, exclusion, pricing, persuasion, or eligibility.
19. **Reputation and physical-world safety.** Controversy, humor, stunts, guerrilla activity, OOH, live events, challenges, documentaries, and reality-style customer content require brand, safety, property/permit, bystander consent, accessibility, crisis, insurance, and legal review. Do not provoke harm, trespass, deceive the public, or manufacture outrage.
20. **No automatic persistence.** Show recommendations, evidence ledger, scoring, or proposed experiment brief before writing files or changing external systems.

## Context brief

Infer low-risk details when clear; otherwise ask only what changes the shortlist:

- product/service, geography, language, market, and business model;
- target organizations, buying group, user job, trigger, and exclusions;
- current stage, objective, decision horizon, and actual baseline;
- approved product claims and proof;
- current channels, owned audience, distribution advantages, and constraints;
- prior experiments, results, methodology, and learnings;
- team capacity, skills, budget ceiling, review time, and maintenance capacity;
- sales cycle, average value, margin, implementation/support burden;
- regulatory, privacy, security, accessibility, brand, and legal constraints;
- risk appetite and actions that are explicitly off-limits.

Use an approved project-local `.agents/product-marketing.md` under the `product-marketing` safeguards when available. Do not auto-read private systems.

## Ideation workflow

### 1. Define the problem

Convert “grow,” “get leads,” or “build authority” into a measurable decision:

- target audience and behavior;
- funnel or customer stage;
- baseline and source;
- desired outcome and period;
- practical constraint;
- leading metric, lagging metric, and guardrails;
- what decision follows the experiment.

Fast acquisition is not synonymous with paid ads or outbound. Channel speed depends on audience access, offer readiness, sales cycle, proof, creative, instrumentation, budget, and operational capacity.

### 2. Build an evidence ledger

| ID | Signal/claim | Class | Source/date | Relevance | Confidence | Unknowns |
|---|---|---|---|---|---|---|
| E-01 | | Observed / Internal / Estimate / Hypothesis / Unknown | | | High/Medium/Low | |

A tactic used by a competitor is evidence of activity, not performance or suitability. Public ad duration, engagement, backlinks, rankings, and visibility do not establish profit, incrementality, legal compliance, or strategic fit.

### 3. Generate across mechanisms

Create a diverse candidate pool, such as:

- product utility and customer success;
- educational and decision-support content;
- search/discovery with unique value;
- founder/expert distribution;
- customer advocacy with permission;
- partnerships with clear mutual value;
- community participation without extraction;
- events and demonstrations;
- referrals and product loops with user control;
- paid demand capture or creation;
- PR based on genuinely newsworthy evidence;
- lifecycle communication to appropriately permissioned recipients;
- localization only where operational readiness exists.

Do not present the upstream catalog's numbering or categories as evidence of quality.

### 4. Screen before scoring

Reject or escalate ideas that depend on:

- unlawful or unclear data use;
- platform manipulation or deceptive UX;
- unverified claims or false endorsement;
- unauthorized IP, likeness, account, or customer use;
- mass unsolicited contact;
- unavailable product capabilities;
- hidden recurring costs or material operational load;
- discrimination or exploitation of vulnerability;
- physical, reputational, legal, or security risk beyond the stated appetite.

### 5. Score transparently

Agree criteria and weights rather than using a universal formula. Candidate criteria:

- strength of audience evidence;
- fit to objective and buying stage;
- offer/product readiness;
- access to distribution;
- expected learning value;
- proof and creative readiness;
- time to observable signal;
- implementation and maintenance effort;
- cash exposure and downside cap;
- privacy, legal, platform, security, accessibility, and reputation risk;
- measurement feasibility;
- reversibility;
- confidence.

Show assumptions and sensitivity. Missing data lowers confidence; do not fill it with plausible numbers.

### 6. Recommend a portfolio

Default to three to five ideas only when that helps decision-making. Include a balance where appropriate:

- one low-cost learning test;
- one reusable/compounding asset;
- one distribution or relationship experiment;
- optionally one higher-risk/higher-investment test clearly labeled.

A long list is acceptable when explicitly requested, but group it and mark low-confidence or prerequisite-heavy ideas rather than presenting everything as equally suitable.

## Experiment brief

For each shortlisted idea provide:

1. **Idea and mechanism** — what behavior is expected and why.
2. **Fit** — audience, stage, objective, and relevant evidence.
3. **Hypothesis** — falsifiable statement, not a promised outcome.
4. **Minimum test** — smallest ethical implementation that can answer the question.
5. **Inputs** — owner, skills, time range, budget cap, dependencies, and tools.
6. **Evidence/claims needed** — facts, permissions, creative, product readiness.
7. **Risks and review gates** — privacy, legal, rights, platform, security, accessibility, reputation.
8. **Measurement** — numerator, denominator, cohort, source, period, quality and harm guardrails.
9. **Decision rule** — continue, revise, stop, or investigate.
10. **Approval boundary** — exact external action not yet authorized.

Use ranges only when grounded. Expected outcome should describe an observable signal, not a guaranteed business result.

## Channel safeguards

### Content, search, social, and community

Use `content-strategy`, `seo-audit`, `ai-seo`, `social`, and community workflows. Preserve unique value, source provenance, moderation norms, accessibility, disclosure, and customer privacy. Do not scrape private groups, post automatically, or copy competitors.

### Paid media and retargeting

Verify current platform policies, targeting restrictions, consent/data requirements, creative claims, landing-page truth, budget, billing, attribution, brand safety, exclusions, frequency, and stop-loss before launch. Do not optimize using sensitive traits or upload customer audiences without approval.

### Email and lifecycle

Use only appropriate recipients and purposes. Separate operational messages from marketing. Honor unsubscribe, suppression, deletion, and consent withdrawal. Do not treat churned, expired-trial, or inactive users as automatically contactable.

### Referrals, affiliates, and promotions

Design user benefit, incentives, abuse controls, disclosure, attribution, terms, tax/accounting treatment, eligibility, caps, and support. Do not create coerced invitations, spam loops, pyramid-like structures, or undisclosed endorsements.

### Research, reports, and personalized wraps

Use authorized, minimized, sufficiently aggregated data. Document sample, methodology, exclusions, uncertainty, re-identification risk, consent/purpose, retention, rights, and review. Personalized summaries require secure access and must not expose private behavior or manipulate sharing.

### Product-led and developer ideas

Treat these as software/product projects, not simple marketing switches. Require specs, consent and permissions, security review, test environments, rollback, support, monitoring, deprecation, and real QA before release.

### Events, PR, and unconventional activity

Obtain speaker/participant consent, recording permissions, venue/platform rights, insurance/permit review, accessibility, disclosures, crisis plan, moderation, and truthful media relations. Never fabricate newsworthiness or customer participation.

## Measurement principles

- Define metric semantics before setting targets.
- Include quality, cost, privacy complaints, unsubscribes, support burden, accessibility failures, fraud, brand safety, and negative feedback as guardrails.
- Distinguish correlation from incrementality and contribution from attribution.
- Do not declare success from impressions, clicks, followers, signups, rankings, or mentions alone.
- Use a comparable baseline, holdout, geo split, time series, or another defensible design when feasible.
- Account for novelty effects, seasonality, channel overlap, sales lag, and selection bias.
- Stop or reassess when data quality, legal basis, delivery capacity, or user harm is unacceptable.

## Output format

### Shortlist

| Rank | Idea | Mechanism | Evidence | Minimum test | Time/cost range | Main risk | Metric/guardrails | Confidence |
|---:|---|---|---|---|---|---|---|---|

Then provide an experiment brief for the top candidate and list the approvals needed before execution.

### Large idea set

When the user explicitly requests many ideas, group by mechanism and show for each:

- one-line concept;
- fit and prerequisite;
- evidence class/confidence;
- indicative effort and cash exposure;
- key risk/review;
- next validation step.

Do not add fake precision merely to fill the table.

## Review checklist

- [ ] Objective, audience, baseline, constraint, and decision are explicit.
- [ ] Evidence, estimates, hypotheses, and unknowns are separate.
- [ ] Ideas were screened before scoring.
- [ ] No idea depends on hidden tracking, spam, manipulation, false proof, or unauthorized assets or data.
- [ ] Costs include implementation, media, tools, labor, support, maintenance, compliance, and downside.
- [ ] Claims, permissions, platform rules, legal/privacy, security, accessibility, and reputation are visible.
- [ ] Metrics include quality and harm guardrails, not just volume.
- [ ] Expected outcomes are signals, not promises.
- [ ] Every experiment has owner, cap, stop rule, and approval boundary.
- [ ] No external action, spend, contact, post, purchase, product change, or publication occurred without approval.

## Boundaries

- `product-marketing` supplies approved positioning, audience, proof, and exclusions.
- `customer-research` validates needs without uncontrolled profiling.
- `content-strategy` designs sustainable content portfolios.
- `b2b-ai-offer-strategy` packages complex AI services into evidence-backed offers.
- Dedicated channel, software-development, research, creative, privacy, legal, and operational workflows govern execution.
- This skill generates and prioritizes hypotheses; it does not silently implement them.
