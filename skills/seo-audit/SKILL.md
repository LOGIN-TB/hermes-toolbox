---
name: seo-audit
description: "Use when auditing or diagnosing organic-search issues."
version: 2.0.0-hermes.1
author: Corey Haines; Hermes-curated adaptation
license: MIT
metadata:
  hermes:
    tags: [seo, technical-seo, on-page, indexing, migrations]
    homepage: https://github.com/coreyhaines31/marketingskills/tree/main/skills/seo-audit
    upstream_commit: 7868cb9251fad80a73d26e488a5ad5f6c4a9f335
---

# SEO Audit

Use this skill to diagnose crawl, indexing, rendering, performance, content, internal-linking, international, local, and migration problems with reproducible evidence. This is a locally curated Hermes adaptation of Corey Haines' MIT-licensed `seo-audit` skill at the pinned upstream commit.

## Audit principles

1. **Inspect the live source first.** If the user gives a URL, inspect that site rather than relying on memory or old conversation summaries.
2. **Separate observation from inference.** Label what was measured, what was reported by a platform, and what is a hypothesis.
3. **Do not promise rankings or traffic.** SEO outcomes depend on competition, demand, quality, indexing, and changing systems.
4. **Validate current rules.** Search-engine documentation and rich-result eligibility change; verify first-party guidance before high-impact recommendations.
5. **Do not convert heuristics into requirements.** Character counts, H1 counts, click depth, keyword placement, and word count are diagnostic clues, not universal ranking rules.
6. **Respect access boundaries.** Never search credentials, `.env`, auth files, private customer data, analytics, or Search Console without explicit access and task relevance.
7. **No changes without approval.** Auditing is read-only unless the user explicitly asks for implementation.

## Context first

If the project contains `.agents/product-marketing.md`, `.claude/product-marketing.md`, or `product-marketing-context.md`, read only that relevant context before asking questions.

Gather what is missing:

- Site, country, language, business model, and conversion goal
- Audit scope: full site, template, page group, or incident
- Priority queries and landing pages
- Known competitors
- Baseline dates and metrics
- Recent deploys, migrations, redesigns, domain changes, CMS or rendering changes
- Available first-party data: Search Console, analytics, server logs, crawl export

When traffic or rankings dropped, compare the decline date against releases, migrations, tracking changes, seasonality, demand, manual actions, security incidents, and documented search updates. Do not assume an algorithm update caused it.

## Evidence hierarchy

Prefer, in order:

1. Search Console URL Inspection, Performance, Page Indexing, Manual Actions, Security Issues, and Core Web Vitals
2. Server/CDN logs and reproducible HTTP/rendered-page checks
3. Analytics with validated tracking
4. Version-control and deployment history
5. Crawl exports and page-template samples
6. Current first-party search-engine documentation
7. Third-party SEO tools as supporting evidence

`site:` queries are rough discovery checks, not an index count. Browser or static fetch results alone do not prove what Google indexed.

## Audit sequence

### 1. Establish scope and baseline

- Confirm hostname variants, protocols, locale variants, subdomains, and canonical environment.
- Define before/after periods and annotate launches or migrations.
- Segment by query, country, device, page type, directory, and search appearance.
- Verify analytics and Search Console data integrity before diagnosing traffic.
- Choose representative URLs for each important template and state.

### 2. Crawlability and indexability

Inspect:

- HTTP status, redirects, redirect chains/loops, soft-404 behavior
- `robots.txt` syntax and effective rules for relevant crawlers
- Meta robots and `X-Robots-Tag`
- Canonical hints and conflicting signals
- XML sitemaps: reachable, valid, current, canonical/indexable URLs only
- Internal discoverability, orphan pages, pagination, faceted navigation
- Parameter handling, session IDs, infinite-scroll fallback
- Search Console indexing reasons and URL Inspection samples

A canonical element is a hint, not a command. Self-referencing canonicals are often useful for consistency, but do not report their absence as an error without a duplication or canonicalization risk.

### 3. Rendering and content parity

Compare initial HTML, rendered DOM, accessibility tree, and important resources:

- Main content and links available without client-side failure
- Consistency across mobile and desktop
- Hydration/render errors
- Lazy-loaded content and pagination accessible to crawlers/users
- Consent walls, login gates, geolocation or language redirects
- JavaScript-generated canonicals, robots tags, internal links, and structured data

Schema detection rule: `curl` can detect server-rendered JSON-LD but not reliably client-injected data. Use a rendered browser DOM and, where applicable, Google's current Rich Results Test or Schema.org Validator. Presence does not prove validity or rich-result eligibility.

### 4. Site architecture and internal linking

- Important pages have contextually relevant internal links.
- Navigation, breadcrumbs, hubs, and pagination expose key pages.
- Anchor text describes destination naturally.
- Orphans, broken links, excessive duplicate links, and dead ends are identified.
- Click depth is used as a prioritization signal, not a universal three-click rule.
- URL structure is stable, descriptive, and consistent; keyword inclusion is not forced.

### 5. Technical quality and performance

Use both field and lab data:

- **Field:** CrUX/Search Console where available
- **Lab:** PageSpeed Insights/Lighthouse/DevTools/WebPageTest for diagnosis

Current Core Web Vitals good thresholds at the 75th percentile:

- LCP ≤ 2.5 s
- INP ≤ 200 ms
- CLS ≤ 0.1

Also inspect TTFB, caching, CDN behavior, image dimensions/formats, font loading, JavaScript main-thread work, CSS delivery, third-party scripts, mobile viewport, tap targets, horizontal overflow, HTTPS, certificate, mixed content, and security headers where relevant.

Core Web Vitals are one set of page-experience signals, not a substitute for relevance and quality. A generic “page loads in five seconds” observation is not itself a CWV measurement.

### 6. On-page and search appearance

For representative pages, evaluate:

- Search intent and page purpose
- Descriptive, distinct title and main heading
- Useful snippet candidate/meta description
- Heading hierarchy and semantic structure
- Canonical URL, robots directives, language, dates, authorship
- Main content clarity, originality, evidence, and completeness
- Image alt text based on function/context, not keyword stuffing
- Internal links and related page relationships
- Search-result appearance and actual rewritten titles/snippets when observable

Do not enforce:

- Exactly one H1 as a ranking requirement
- Fixed title or meta-description character limits
- A keyword in the first 100 words
- A minimum word count
- Exact-match keywords in every title, heading, URL, or alt attribute

Use pixel/display risk and actual search results where possible; search engines may rewrite titles and snippets.

### 7. Content quality and trust

Assess whether content:

- Satisfies the query and audience need
- Demonstrates first-hand experience or appropriate expertise
- Uses primary sources, dates, and transparent methodology
- Distinguishes fact, estimate, opinion, and vendor claim
- Has clear authorship and accountable organization information
- Is maintained when freshness matters
- Avoids doorway pages, scaled low-value variants, copied descriptions, and misleading claims
- Adds information or utility beyond currently available alternatives

Do not treat bounce rate, time on page, pages per session, or return visits as confirmed direct ranking factors. Use them as UX/business diagnostics only, with context.

Do not use superficial “AI writing tells” such as em dashes or word lists as evidence of low quality or policy violations. Evaluate factuality, originality, usefulness, sourcing, and scaled-abuse patterns instead.

### 8. Authority and external signals

Where relevant, inspect:

- Earned links and referring-domain quality
- Link loss or migration-related link equity loss
- Brand/entity consistency
- Reviews and reputable third-party coverage
- Spammy, paid, hacked, or manipulative link patterns

Do not recommend buying links, private blog networks, fabricated reviews, automated outreach spam, or manipulative anchor text.

### 9. International SEO

When multiple languages or regions exist, verify current first-party documentation before implementation. Check:

- Unique locale URLs; avoid IP-only or `Accept-Language`-only discovery
- `hreflang` codes, self and reciprocal annotations, and reachable indexable targets
- Canonicals aligned with intended locale URLs
- Consistency across HTML, headers, or XML sitemap methods
- `x-default` only when a real fallback/selector URL exists and it serves the intended purpose
- Fully localized main content, metadata, currency, address, and support details where relevant
- Redirects do not prevent crawlers or users from reaching locale variants

Do not state that every page must use `x-default` or that any single missing tag invalidates an entire site. Report the exact affected URL pairs/clusters and evidence.

### 10. Site-type checks

**SaaS/B2B**
- Product/category clarity, use cases, evidence, comparisons, integration/docs discoverability

**E-commerce**
- Facets, parameters, pagination, variants, category quality, product availability, duplicate descriptions, merchant data

**Editorial/blog**
- Cannibalization, content decay, topic coverage, author accountability, internal linking, update workflow

**Local business**
- Accurate NAP, Google Business Profile, location/service-area pages, reviews, local relevance, duplicate doorway-location pages

**Migration**
- Old-to-new URL mapping, status codes, canonicals, robots, sitemaps, internal links, content/metadata parity, analytics tags, backlinks, host variants, Search Console properties

## Incident workflow for traffic loss

1. Confirm the drop is real and tracking is intact.
2. Identify exact start date and affected segments.
3. Check deploy/migration/change history first.
4. Check manual actions, security issues, indexation and crawl errors.
5. Compare lost queries/pages, not only aggregate traffic.
6. Inspect redirects, canonicals, robots, templates, rendering and internal links.
7. Evaluate demand/seasonality and SERP changes.
8. Form ranked hypotheses with evidence and tests.
9. Implement one controlled fix set at a time.
10. Monitor defined leading and lagging indicators without promising a recovery date.

## Findings standard

Every finding must include:

- **Issue**
- **Affected URLs/templates**
- **Evidence and method**
- **Confidence:** confirmed / likely / hypothesis
- **Impact:** critical / high / medium / low
- **Recommended fix**
- **Validation after fix**
- **Owner and effort**, when useful

Do not call something “critical” unless it blocks crawling/indexing, creates severe duplication/canonicalization failure, breaks rendering, causes large-scale errors, or presents comparable business risk.

## Deliverable

1. Executive summary
2. Scope, date, tools, and access limitations
3. Baseline and segmentation
4. Critical blockers
5. Technical findings
6. Rendering and structured-data findings
7. On-page/content findings
8. Architecture/internal-link findings
9. International/local findings where relevant
10. Prioritized action plan
11. Verification plan and monitoring cadence
12. Open questions and unsupported hypotheses

## Scope boundaries

- Use `ai-seo` for AI-answer visibility, citations, and recommendation analysis.
- Use a schema-specific workflow for structured-data implementation.
- A page-speed audit should distinguish field from lab data.
- Search Console and analytics access must be explicitly authorized.
- Never modify production, submit removals, change canonical/robots rules, disavow links, or publish content without explicit approval.
