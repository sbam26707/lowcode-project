# IT Investment Tracker (proof of concept)

A Flask + SQLite web app for tracking IT investments in a large Irish public sector organisation, from business case through five-stage approval, delivery and benefits realisation. All data is fictional.

## Setup

```
pip install -r requirements.txt
flask run          # or: python app.py
```

Open http://127.0.0.1:5000. The database (`tracker.db`) is created and loaded with sample data on first start. To reset it at any time run `python seed.py`. Sample dates are relative to today, so statuses and RAG always look current. Charts load Chart.js from a CDN (each has a data table beneath it, so the app still works offline).

Conventions: euro, exclusive of VAT, calendar financial years, dates as DD/MM/YYYY. Desktop and light theme only; built to WCAG 2.1 AA.

## Sample roles and people (role switcher, top right)

| Person | Role | Can act on |
|---|---|---|
| Aoife Brennan, Ciarán Doyle, Niamh Gallagher | Investment owners | Create and edit own investments in Draft / Returned; submit |
| Seán Murphy | Head of Department | Approval stage 1 (Business Case) |
| Orla Kavanagh | Portfolio Manager (PMO) | Stage 2; edits capacity pool |
| Declan Walsh | PMO analyst | Edits capacity pool; records measurements and forecasts |
| Mairéad Costello | Finance Director | Stage 3 (Finance Sign-off); edits actuals/forecasts |
| Tadhg Nolan | Finance officer | Edits actuals/forecasts |
| Eoin Fitzgerald | CIO | Stage 4 (Technical / Architecture Review) |
| Róisín Hegarty | Investment Board member | Stage 5 (final approval) |
| Pádraig Lynch | Senior leadership | Read-only |

## Demo script (matches acceptance criteria)

1. **Switch roles** with the dropdown; the signed-in user and available buttons change.
2. As **Aoife Brennan**: Investments > Create new investment. Add a quantified metric (Value tab), default phases (Timeline tab), a cost row (Cost tab) and resource demand (Capacity tab). Then Overview > Submit for approval.
3. Before step 2 is complete, try Submit: it is refused with a message that a quantified metric is needed.
4. Approve in order: Seán Murphy, Orla Kavanagh, Mairéad Costello, Eoin Fitzgerald, Róisín Hegarty (Approval tab). Try Róisín first: she cannot act out of order.
5. Reject one and return another: the sample data already has *Legacy Payroll Interface Upgrade* (Rejected) and *Inspection Mobile App* (Returned). Return needs comments; the owner sees them on Overview and resubmits, restarting at the stage that returned it.
6. Timeline tab: change a phase's forecast end date. Under 7 days late is Green, 7 to 20 Amber, 21 or more Red.
7. Capacity tab: add demand above the pool (for example 50 Architect FTEs). A warning appears, plus a badge on the investment and on the Capacity pool page.
8. Open *Case Management System Replacement* > Realisation (as owner or PMO) and add a measurement; the metric's status recalculates.
9. Dashboard: Portfolio overview, Benefits view and Approval pipeline show figures from the data.
10. Audit log (and each investment's History tab) lists every change with user, time, old and new values.

## Assumptions and notes

- Permissions follow Section 3 of the spec. Finance edits actual and forecast; owners edit budget and forecast while Draft or Returned. After approval, the owner or PMO can update forecast dates and record measurements and reviews.
- Rejected investments are excluded from capacity demand and dashboard cost totals.
- Realisation: progress is the share of the baseline-to-target distance achieved. "On trajectory" is a straight line from go-live to the target date. One case the spec leaves open (behind trajectory, under 25%, target date not yet passed) is shown as Partially Realised.
- Go-live is the Deploy phase. Post-implementation reviews (6 and 12 months) are created when the Investment Board approves.
- No automated tests, real authentication or hosted deployment (out of scope).
