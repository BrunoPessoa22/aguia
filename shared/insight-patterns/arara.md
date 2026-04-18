# ARARA — Insight Patterns to capture

Call wiki-remember.sh when you observe any of these:

1. **Rejection pattern (3+ applications same company/role-type with same reason)**
   Title: `ARARA rejection cluster — [company or role-type]`
   Content: company/role, n applications, extracted reason (if any), whether Bruno's profile missing a specific requirement, recommended retry strategy or deprioritization.

2. **Form automation failure (company-specific)**
   Title: `ARARA form blocker — [company] [field]`
   Content: company career site URL, specific field that blocks automation, manual-only vs scrape-able workaround, whether Playwright hit a captcha/SSO.

3. **Unexpected early-stage response (recruiter reach-out, auto-interview invite)**
   Title: `ARARA positive signal — [company] [stage]`
   Content: company, role, stage, timeline from submit → response, what Bruno did that might have triggered (resume bullet, LinkedIn activity, referral).

4. **Compensation data point (published salary, negotiated offer, recruiter disclosure)**
   Title: `Comp data — [company tier] [role] [location]`
   Content: company tier (FAANG/scale-up/seed/etc), role title, location, base/equity/bonus if disclosed, data source.

5. **Target company shift (layoffs, pivot, M&A affecting fit)**
   Title: `Target company shift — [company] [event]`
   Content: company, event, source URL, revised Bruno-fit assessment (still apply / deprioritize / skip entirely).

DO NOT write for every application sent or standard rejection boilerplate.
