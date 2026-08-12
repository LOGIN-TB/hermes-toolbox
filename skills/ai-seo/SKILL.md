---
name: ai-seo
description: "Use when auditing or improving AI-search visibility."
version: 2.2.0-hermes.1
author: Corey Haines; Hermes-curated adaptation
license: MIT
metadata:
  hermes:
    tags: [ai-seo, aeo, geo, llmo, ai-overviews, citations]
    homepage: https://github.com/coreyhaines31/marketingskills/tree/main/skills/ai-seo
    upstream_commit: 7868cb9251fad80a73d26e488a5ad5f6c4a9f335
---

# AI SEO

Use this skill to improve how a brand or page is **retrieved, cited, mentioned, and recommended** in AI-generated answers. Treat traditional SEO, crawlability, useful content, and verifiable authority as the foundation; AI-specific structure is an additional layer, not a replacement.

This is a locally curated Hermes adaptation of Corey Haines' MIT-licensed `ai-seo` skill at the pinned upstream commit shown in frontmatter. It removes an upstream-only tools-registry link and corrects crawler guidance that conflated training crawlers, search crawlers, and user-triggered fetchers.

## Evidence policy

AI-search behavior changes quickly and many public studies are observational. Before presenting current percentages, crawler names, platform backends, ranking weights, or claimed visibility uplifts:

1. Check current first-party documentation or the cited primary study.
2. State the source and date.
3. Label correlation as correlation; do not present it as a ranking factor or causal guarantee.
4. Do not promise citation, ranking, traffic, or recommendation outcomes.
5. For Google AI features, default to Google's current guidance: normal Search eligibility and people-first SEO apply; no special AI markup or AI text file is required.

## Context first

If the project contains `.agents/product-marketing.md`, `.claude/product-marketing.md`, or `product-marketing-context.md`, read it before asking questions. Never search unrelated private directories, credentials, `.env`, auth files, or personal data.

Collect only missing task context:

- Domain and priority pages
- Brand, offer, audience, region, and language
- 10–20 commercially important prompts or queries
- Platforms to evaluate
- Known competitors and existing visibility
- Goal: retrieval, citation, mention, recommendation, or conversion
- Existing SEO, schema, author, source, and analytics signals

## The visibility ladder

Keep these outcomes separate:

1. **Retrieved** — the system reads the page while forming an answer.
2. **Cited** — the page appears as a source.
3. **Mentioned** — the brand appears in the answer text.
4. **Recommended** — the brand enters the buyer's shortlist.

A useful page can be cited while its publisher is not recommended. Recommendation depends heavily on web-wide corroboration: reviews, communities, analysts, earned media, videos, podcasts, and credible third-party discussion. For emerging brands, self-ranked “best tools” pages may teach the model about competitors without earning the publisher a recommendation.

## Audit workflow

### 1. Establish a reproducible baseline

For each priority prompt, record:

| Prompt | Platform/model | Date/region | Answer present | Brand retrieved/cited/mentioned/recommended | Sources | Framing |
|---|---|---|---|---|---|---|

Run enough repeated checks to expose volatility. Do not infer stable visibility from one answer or one account.

### 2. Check technical eligibility

- Page is publicly reachable with a successful status code.
- Canonical, robots directives, sitemap, and indexability are coherent.
- Essential content is available in rendered HTML and semantic structure.
- Main content is not hidden behind login, consent, or client-side failure.
- Titles, headings, authorship, publication/update dates, and internal links are clear.
- Structured data matches visible page content and current platform eligibility rules.
- Page works for visual, DOM, and accessibility-tree agents.

### 3. Check crawler policy precisely

Do not use a blanket “allow all AI bots” recommendation. Identify each operator's current tokens and purpose from first-party docs:

- **Search/index crawlers** may affect discoverability.
- **User-triggered fetchers** retrieve a page because a user requested it.
- **Training crawlers** govern model-training use and may not control search citation.

Important examples to verify live before editing `robots.txt`:

- OpenAI distinguishes `OAI-SearchBot`, `ChatGPT-User`, and `GPTBot`.
- Google says `Google-Extended` is separate from Google Search crawling and does not control inclusion or ranking in Google Search, including AI features.
- Anthropic and Perplexity publish separate bot documentation that can change.

Present privacy, licensing, server-load, discovery, and citation trade-offs. Never edit `robots.txt` without explicit approval and validation.

### 4. Evaluate content extractability

For each priority page:

- Lead sections with a direct, accurate answer where natural.
- Use descriptive H2/H3 headings matching real questions.
- Keep each paragraph focused on one idea.
- Use tables for genuine comparisons and numbered lists for processes.
- Make key claims self-contained without turning the page into fragmented “AI bait.”
- Include precise definitions, limitations, dates, units, and examples.
- Ensure accessibility labels, landmarks, heading hierarchy, and alt text are correct.

Google-specific caution: write for people and organize normally. Do not create separate doorway-like AI content or mass-produce thin variants.

### 5. Evaluate authority and evidence

- Prefer original research, first-party documentation, and named primary sources.
- Add dates and methodological context to statistics.
- Show first-hand experience and concrete implementation detail.
- Use real author names and relevant credentials where appropriate.
- Separate facts, estimates, opinions, and vendor claims.
- Remove unsupported superlatives and stale figures.
- Cite original research rather than a marketing summary of it.

Never fabricate statistics, quotes, customers, reviews, awards, credentials, or citations.

### 6. Evaluate off-site consensus

For recommendation goals, inspect:

- Relevant review platforms
- Practitioner communities and forums
- Analyst and industry coverage
- Earned media
- YouTube, podcasts, and transcript visibility
- Accurate entity profiles and organization data

Recommend authentic participation only. Do not propose fake reviews, undisclosed placements, Wikipedia manipulation, forum spam, or fabricated citations.

### 7. Assess machine-readable additions conservatively

Possible additions include `llms.txt`, public markdown documentation, transparent pricing/specification files, feeds, or other agent-readable resources. Treat them as accessibility/discovery experiments, not confirmed ranking factors.

- Keep them consistent with visible canonical content.
- Add them only when maintainable.
- Do not expose confidential pricing, internal data, personal data, or gated IP.
- Do not claim Google requires them for AI Overviews.
- Validate links, freshness, and indexing behavior after deployment.

Treat OKF or similar emerging protocols as experimental until first-party adoption is confirmed.

## Useful content patterns

### Definition

```markdown
## What is [term]?

[Direct definition.] [Key scope or distinction.] [Why it matters.]
```

### Process

```markdown
## How to [goal]

1. **[Step]** — [specific action]
2. **[Step]** — [specific action]
3. **[Step]** — [specific action]
```

### Balanced comparison

```markdown
| Criterion | Option A | Option B |
|---|---|---|
| Best fit | ... | ... |
| Limits | ... | ... |
| Evidence/date | ... | ... |
```

Use verifiable criteria, current dates, primary sources, and explicit selection methodology. Do not rank the publisher first by default.

### Evidence block

```markdown
[Claim]. [Primary source] reports [specific result, date, and scope]. [Limitation or context]. [Practical implication].
```

### FAQ

Use genuine buyer questions. Answer directly, but add FAQ structured data only when current search-engine rules permit it and the Q&A is visibly present.

## Prioritization

Score each fix by:

- Expected business value
- Evidence strength
- Implementation effort
- Risk of misleading users or violating policy
- Ability to measure the result

Default priority:

1. Crawl/index/render failures
2. Incorrect or unsupported claims
3. Missing core product/category information
4. Weak page structure and accessibility
5. Missing primary evidence and authorship
6. Off-site consensus gaps
7. Experimental machine-readable files

## Measurement

Use a measurement triad:

1. **Prompt tracking** — repeated platform checks with prompt, date, model, region, citations, and framing.
2. **Self-reported attribution** — “How did you hear about us?”
3. **Sales/conversation evidence** — call notes or recordings where lawful and consented.

Also monitor branded search, qualified visits, conversions, bot logs, and cited landing pages. AI influence often arrives through branded search or direct traffic rather than a visible referral.

## Deliverable format

Return:

1. **Scope and methodology**
2. **Evidence snapshot** with source dates
3. **Findings by visibility rung**
4. **Findings by Structure / Authority / Presence**
5. **Platform-specific caveats**
6. **Prioritized fixes** with owner, effort, impact hypothesis, and validation
7. **30/60/90-day plan**
8. **Measurement table**
9. **Uncertainties and claims requiring revalidation**

## Scope boundaries

- Use a traditional SEO-audit workflow for broad ranking or traffic-loss investigations.
- Validate schema against current official documentation and rich-result eligibility.
- Do not modify websites, crawler policy, analytics, or third-party profiles without explicit approval.
- Do not rely on unverified numeric claims from this or any upstream skill.
