# IT Investment Tracker: Proof of Concept Specification

**Audience:** Claude (to generate a working proof of concept)
**Target users:** Large Irish Public Sector Organisations
**Version:** 0.2 (proof of concept)

---

## 1. Purpose

Build a web application that lets a large Irish public sector organisation track its IT investments from business case through approval, delivery and benefits realisation. The tracker records each investment's **Name, Owner, Approval, Cost, Value, Timeline, Capacity, Plan and Realisation**.

This is a proof of concept for demonstration. It should be easy to run locally, populated with realistic fictional data, and show the complete workflow end to end.

## 2. Scope

**In scope**
- Individual IT projects only, held in a flat list (no programmes, no hierarchy).
- Five-stage sequential approval workflow with a recorded decision at each stage.
- Cost tracking as budget vs actual vs forecast.
- Value captured as financial benefits, non-financial benefits and strategic alignment, with at least one quantified metric required.
- Timeline by phase, with automatically calculated RAG status.
- Delivery resource capacity in FTEs, by phase and role, checked against an organisation-wide pool.
- Delivery plan as structured fields.
- Value (benefits) realisation tracking and post-implementation reviews.
- Three dashboards in one shared view.
- Audit trail of changes.
- Role switcher instead of a login.
- Pre-loaded fictional sample data.

**Out of scope**
- Real authentication or user management.
- Programme or portfolio hierarchy.
- Document attachments or file uploads.
- Structured risk and issue logs (risks and dependencies are text within the plan).
- Per-role dashboard views (one shared view only).
- Administrator editing of RAG thresholds (they are fixed in the app).
- Integrations with finance, HR or other external systems.
- Dark theme, and layouts for tablet or mobile (desktop and light theme only).
- Hosted or cloud deployment (the proof of concept runs locally).
- Automated test suite (not required for the proof of concept).

## 3. Users and roles

There are four user groups. The proof of concept has no login: a **role switcher** at the top of every page lets the demo viewer act as any of the people below.

| Group | Main job in the tracker |
|---|---|
| Investment owners | Create and update their investments, submit for approval, rework when sent back, record plan, cost, timeline and resource data. |
| PMO / portfolio team | Review and maintain the portfolio, manage the capacity pool, oversee delivery health. Includes the Portfolio Manager approval stage. |
| Finance | Validate costs, record actuals and forecasts, give Finance Sign-off. |
| Senior leadership / Investment Board | View dashboards; the Investment Board gives final approval. |

**Approvers (named people the role switcher must include):** Head of Department, Portfolio Manager, Finance Director, CIO (or Enterprise Architect), Investment Board member.

**Permissions (assumption, see Section 15):**
- Owners can edit only their own investments, and only while the investment is in Draft or Returned for rework.
- Approvers can act only on the stage currently assigned to them.
- PMO can edit capacity pools and view everything.
- Finance can edit actual and forecast cost figures on any investment.
- Leadership is read-only apart from Investment Board decisions.

## 4. Technology

- **Language and framework:** Python with Flask.
- **Templates:** Jinja2 with server-rendered pages. Plain CSS, styled as described in Section 4.1. Charts may use Chart.js or similar loaded from a CDN.
- **Storage (assumption):** SQLite via SQLAlchemy or the built-in `sqlite3` module, with a seed script that creates the database and loads sample data.
- **Role switcher:** the selected user is held in the Flask session. No passwords.
- **Run instructions:** the project must start with `pip install -r requirements.txt` followed by `flask run` (or `python app.py`), and must include a short README.
- **Conventions:** currency in euro (€), amounts exclusive of VAT, dates shown as DD/MM/YYYY.

### 4.1 Front end look and feel

- **Overall style:** a government-service look for forms, tables and detail pages: plain, high-contrast, clearly labelled inputs, generous spacing, no decorative clutter. The dashboard home page uses dashboard-style summary cards and charts on top of that same plain foundation.
- **Branding:** a neutral placeholder application name and a restrained neutral palette (greys and one accent colour). No logo required. RAG colours (red, amber, green) must also be conveyed by text or icon, never by colour alone.
- **Theme:** light theme only. No dark mode.
- **Devices:** desktop only. Layouts target a typical desktop browser width; tablet and mobile layouts are not required.
- **Accessibility:** must meet **WCAG 2.1 AA** (the standard Irish public sector bodies follow through EN 301 549). This includes sufficient colour contrast, full keyboard navigation with visible focus, semantic HTML with proper headings and landmarks, labels associated with every form field, clear error messages, and text alternatives for charts (for example a data table or summary beneath each chart).

## 5. Data model

### 5.1 Investment (core record)
- Name (required, unique)
- Owner (a user)
- Short description
- Overall approval status: Draft, In approval, Approved, Rejected, Returned for rework
- Created and last updated dates

### 5.2 Approval
One record per stage per investment, in this fixed order:

1. **Business Case**, approved by the Head of Department
2. **Portfolio Manager review**, approved by the Portfolio Manager (early gate)
3. **Finance Sign-off**, approved by the Finance Director
4. **Technical / Architecture Review**, approved by the CIO or Enterprise Architect
5. **Investment Board**, final approval

Each stage record holds: stage name, named approver, status (Pending, Approved, Rejected, Returned for rework, Not yet reached), decision date, comments, and conditions attached to the approval.

### 5.3 Cost
Per investment, per financial year (assumption, see Section 15), with three figures: **Budget**, **Actual** and **Forecast**. Totals are calculated. Variance (forecast minus budget) is shown as a figure and a percentage.

### 5.4 Value
- **Financial benefits:** entries with a type (cost saving, cost avoidance, new revenue), description and amount.
- **Non-financial benefits:** entries with a category (service improvement, citizen or staff experience, compliance, risk reduction) and description.
- **Strategic alignment:** a free-text statement plus one or more tags linking the investment to organisational or national priorities (for example a digital strategy or departmental statement of strategy).
- **Quantified metrics (benefits):** each has a name, unit, baseline, target, target date and **benefit owner**. **At least one quantified metric is required** before an investment can be submitted for approval.

### 5.5 Timeline
An investment has an ordered list of **phases**. Default phase set (assumption): Initiation, Design, Build, Test, Deploy, Close. Each phase has:
- Planned start and planned end
- Forecast start and forecast end
- Actual start and actual end (when known)
- Status: Not started, In progress, Complete

### 5.6 Capacity (delivery resource)
Resource demand rows hold: investment, phase, **role**, and **FTEs** required. Roles are a fixed list (for example Developer, Business Analyst, Project Manager, Architect, Tester, Change Manager). Internal staff, contractors and vendors are **not** tracked separately.

The **capacity pool** is a single organisation-wide table: role and FTEs available. Managed by the PMO.

### 5.7 Plan
Structured fields (separate inputs, no file attachments):
- Approach
- Scope (in and out)
- Deliverables
- Assumptions
- Dependencies (text)
- Risks (text)

### 5.8 Realisation
- **Measurements:** for each quantified metric, periodic records of date and actual value (for example quarterly).
- **Realisation status per benefit**, calculated automatically (see Section 8).
- **Post-implementation reviews:** scheduled at set intervals after go-live (assumption: 6 and 12 months), each holding review date, reviewer, findings and lessons learned.

### 5.9 Audit log
One row per change: timestamp, user, investment, field or area changed, old value, new value.

## 6. Approval workflow

- Stages run **strictly in sequence**. Only the current stage's approver can act.
- At each stage the approver can:
  - **Approve:** moves the investment to the next stage; records approver, date, comments and any conditions.
  - **Reject:** requires comments; the investment status becomes Rejected.
  - **Return for rework:** requires comments; the investment goes back to the owner, who edits and resubmits.
- On resubmission after rework, the workflow restarts at the stage that returned it (assumption, see Section 15). Earlier approvals are kept visible in the history.
- When the Investment Board approves, the investment status becomes Approved.
- An investment cannot be submitted unless it has at least one quantified metric, at least one phase, and cost figures.
- The investment page shows the full approval history: stage, approver, decision, date, comments, conditions.

## 7. Timeline RAG (automatic)

**Slippage** for a phase or for go-live is: forecast end date (or actual end date if complete) minus planned end date, in days. Early or on-time counts as zero.

| RAG | Rule |
|---|---|
| Green | On plan, or less than 1 week late (under 7 days) |
| Amber | 1 week or more and less than 3 weeks late (7 to 20 days) |
| Red | 3 weeks or more late (21 days or more) |

Thresholds are **fixed in the code**, not editable in the app.

Two RAG statuses are shown for every investment:
1. **Current phase RAG:** based on the phase currently In progress (or the next phase if none is in progress).
2. **Final go-live RAG:** based on the end date of the final deploy phase against its plan.

## 8. Value realisation status (automatic)

Each quantified metric gets a status calculated from the latest measurement against target:

| Status | Rule (assumption, see Section 15) |
|---|---|
| Not Started | No measurement recorded yet |
| On Track | Latest measurement is at or ahead of the expected trajectory toward the target |
| Partially Realised | Latest measurement is between 25% and 99% of the target but behind trajectory |
| Fully Realised | Latest measurement meets or exceeds the target |
| Not Realised | Target date has passed and the latest measurement is under 25% of target |

For metrics where lower is better (for example processing time), the comparison is inverted. Each metric records a direction: "higher is better" or "lower is better".

## 9. Capacity checking

- Demand is calculated per role per calendar month by summing the FTEs of all phases (across **all investments combined**) that overlap that month, using forecast dates.
- Demand is compared with the organisation-wide pool for that role.
- Where demand exceeds the pool, the app **flags over-allocation**: a warning on the capacity page showing role, month, demand, pool and shortfall, and a warning badge on any investment contributing to it.

## 10. Dashboards

One shared view (a dashboard page with three sections or tabs) visible to all roles.

1. **Portfolio overview:** total budget, actual and forecast; variance; count of investments by approval status; list of investments with owner, current approval stage, cost variance, current-phase RAG and go-live RAG.
2. **Benefits view:** target vs realised benefits across the portfolio (financial totals and metric-level progress); count of benefits by realisation status; upcoming post-implementation reviews.
3. **Approval pipeline:** a visual of the five stages with the investments currently sitting at each, and the number of days each has been waiting at its current gate.

## 11. Pages and navigation

- **Header:** app name, role switcher (dropdown of named people with role labels), current user shown.
- **Dashboard** (home).
- **Investments list:** sortable, filterable by status, owner and RAG; button to create a new investment.
- **Investment detail:** tabs for Overview, Approval, Cost, Value, Timeline, Capacity, Plan, Realisation, and History (audit log).
- **Capacity pool:** PMO-editable table of roles and FTEs, plus the over-allocation report.
- **Audit log:** a filterable list of all changes.

## 12. Audit trail

Every create and update of an investment, cost, value, phase, resource, plan, measurement or approval decision writes an audit row. Audit rows are read-only and visible on each investment's History tab and on the global Audit log page.

## 13. Sample data

Seed **8 to 10 fictional investments** (no real organisations, people or products) with a realistic Irish public sector flavour, for example a case management system, a citizen portal, a network refresh, a data platform, an HR system replacement, a cyber security uplift and a records digitisation project. The set must include:
- Investments at every approval stage, plus at least one Rejected and one Returned for rework.
- A mix of Green, Amber and Red for both current-phase and go-live RAG.
- At least one live (post go-live) investment with several quarterly measurements, showing different realisation statuses.
- At least one over-allocated role in a future month.
- Cost variances both over and under budget.
- Audit log entries and approval history comments with conditions on some approvals.

## 14. Acceptance criteria and definition of done

The proof of concept is **done** when it runs locally, is working and demonstrable, and **every step of the demo script below passes**. An automated test suite is not required. Documentation is a README (see items 11 and 12).

1. Switching roles changes the current user and what actions are available.
2. As an owner, create an investment, add at least one quantified metric, phases, cost and resource demand, and submit it.
3. Submission is blocked if there is no quantified metric.
4. Approve the investment through all five stages as each named approver, in order; an out-of-order approver cannot act.
5. Reject one investment and return another for rework, each with a comment; the owner can see the comments and resubmit.
6. Changing a phase's forecast end date changes the RAG status according to Section 7.
7. Adding demand that exceeds the pool for a role in a month triggers an over-allocation flag.
8. Adding a measurement changes the benefit's realisation status according to Section 8.
9. All three dashboard sections show correct figures from the data.
10. Every change appears in the audit log with user, time, old and new values.
11. The app starts locally with the documented commands and loads the sample data.
12. A README is included with setup instructions, a list of the sample roles and people, and a short walkthrough of the demo script.
13. The front end meets the look and feel and WCAG 2.1 AA requirements in Section 4.1 (contrast, keyboard navigation, labels, headings, and RAG not conveyed by colour alone).

## 15. Assumptions to confirm

These were not specified and were filled with sensible defaults. Change any that do not suit.

1. Amounts are in euro, exclusive of VAT.
2. Cost is recorded per financial year.
3. Default phases are Initiation, Design, Build, Test, Deploy and Close.
4. Storage is SQLite.
5. Permissions are as listed in Section 3.
6. Reject ends the workflow; Return for rework sends the investment back to the owner and, on resubmission, restarts at the stage that returned it.
7. Post-implementation reviews are scheduled at 6 and 12 months after go-live.
8. Realisation status rules in Section 8 (including the 25% cut-off and the inversion for lower-is-better metrics).
9. Capacity demand is calculated monthly using forecast dates.
10. The fixed role list for resources and the strategic alignment tags are illustrative and can be extended.
11. Branding is a neutral placeholder name and palette (no specific organisation colours or logo).
