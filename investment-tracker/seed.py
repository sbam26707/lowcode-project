"""Create the database and load fictional sample data.

Run `python seed.py` to reset the database at any time.
Dates are relative to today so the sample data always looks current.
"""
import os
from datetime import date, datetime, timedelta

import db as dbm
from logic import PHASE_NAMES, ROLES, STAGE_NAMES

TODAY = date.today()


def d(offset):
    return TODAY + timedelta(days=offset)


def ts(offset, hour=10):
    return datetime.combine(d(offset), datetime.min.time()).replace(hour=hour).strftime("%Y-%m-%d %H:%M:%S")


USERS = [
    # name, title, group, approver_stage
    ("Aoife Brennan", "Investment Owner", "owner", None),
    ("Ciarán Doyle", "Investment Owner", "owner", None),
    ("Niamh Gallagher", "Investment Owner", "owner", None),
    ("Seán Murphy", "Head of Department", "leadership", 1),
    ("Orla Kavanagh", "Portfolio Manager (PMO)", "pmo", 2),
    ("Declan Walsh", "PMO Analyst", "pmo", None),
    ("Mairéad Costello", "Finance Director", "finance", 3),
    ("Tadhg Nolan", "Finance Officer", "finance", None),
    ("Eoin Fitzgerald", "CIO", "leadership", 4),
    ("Róisín Hegarty", "Investment Board member", "leadership", 5),
    ("Pádraig Lynch", "Senior Leadership (read-only)", "leadership", None),
]

POOL = {"Developer": 26, "Business Analyst": 12, "Project Manager": 12,
        "Architect": 7, "Tester": 10, "Change Manager": 5}


def run(path=None):
    path = path or dbm.DB_PATH
    if os.path.exists(path):
        os.remove(path)
    conn = dbm.connect(path)
    dbm.init_schema(conn)
    uid = {}
    for name, title, grp, stage in USERS:
        cur = conn.execute("INSERT INTO users (name,title,grp,approver_stage) VALUES (?,?,?,?)",
                           (name, title, grp, stage))
        uid[name] = cur.lastrowid
    for role, f in POOL.items():
        conn.execute("INSERT INTO capacity_pool (role, ftes) VALUES (?,?)", (role, f))

    def audit(inv, user, offset, area, field, old, new, hour=10):
        conn.execute(
            "INSERT INTO audit (ts,user_id,user_name,investment_id,area,field,old_value,new_value) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (ts(offset, hour), uid[user], user, inv, area, field, str(old), str(new)))

    # ------------------------------------------------------------ helpers
    def make_inv(name, owner, desc, created, status, stage, entered, strategic, tags, plan):
        cur = conn.execute(
            """INSERT INTO investments (name, owner_id, description, status, current_stage, stage_entered,
               created_at, updated_at, strategic_statement, strategic_tags,
               approach, scope, deliverables, assumptions, dependencies, risks)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (name, uid[owner], desc, status, stage, d(entered).isoformat() if entered is not None else None,
             d(created).isoformat(), d(min(0, created + 5)).isoformat(), strategic, "|".join(tags),
             *plan))
        iid = cur.lastrowid
        dbm.create_approval_rows(conn, iid)
        audit(iid, owner, created, "Investment", "created", "", name, 9)
        return iid

    def approvals(iid, owner, steps):
        """steps: list of (decision, days_ago(negative offset), comments, conditions).
        decision in Approved / Rejected / Returned for rework / Pending."""
        for stage, (decision, off, comments, conditions) in enumerate(steps, start=1):
            approver = conn.execute("SELECT u.id, u.name FROM users u WHERE approver_stage=?", (stage,)).fetchone()
            if decision == "Pending":
                conn.execute("UPDATE approvals SET status='Pending' WHERE investment_id=? AND stage=?", (iid, stage))
                continue
            conn.execute(
                "UPDATE approvals SET status=?, decision_date=?, comments=?, conditions=? "
                "WHERE investment_id=? AND stage=?",
                (decision, d(off).isoformat(), comments, conditions, iid, stage))
            conn.execute(
                "INSERT INTO approval_history (investment_id,stage,stage_name,approver_id,approver_name,decision,"
                "decision_date,comments,conditions) VALUES (?,?,?,?,?,?,?,?,?)",
                (iid, stage, STAGE_NAMES[stage], approver["id"], approver["name"], decision,
                 d(off).isoformat(), comments, conditions))
            audit(iid, approver["name"], off, f"Approval: {STAGE_NAMES[stage]}", "decision", "Pending", decision, 14)

    def phases(iid, start, durs, slips, done, in_prog):
        cur_start, ids = start, []
        for i, (name, dur) in enumerate(zip(PHASE_NAMES, durs)):
            ps, pe = d(cur_start), d(cur_start + dur)
            fs = ps + timedelta(days=slips[i - 1] if i else 0)
            fe = pe + timedelta(days=slips[i])
            if i < done:
                status, a_s, a_e = "Complete", fs.isoformat(), fe.isoformat()
            elif i == in_prog:
                status, a_s, a_e = "In progress", fs.isoformat(), None
            else:
                status, a_s, a_e = "Not started", None, None
            cur = conn.execute(
                "INSERT INTO phases (investment_id,position,name,planned_start,planned_end,forecast_start,"
                "forecast_end,actual_start,actual_end,status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (iid, i + 1, name, ps.isoformat(), pe.isoformat(), fs.isoformat(), fe.isoformat(), a_s, a_e, status))
            ids.append(cur.lastrowid)
            cur_start += dur
        return ids

    def resources(iid, ids, dev, ba, tester, arch, pm=1.0, cm=1.0):
        profile = [
            [("Project Manager", pm), ("Business Analyst", ba * 0.5)],
            [("Project Manager", pm), ("Business Analyst", ba), ("Architect", arch)],
            [("Project Manager", pm), ("Developer", dev), ("Tester", tester * 0.5), ("Architect", arch * 0.5)],
            [("Project Manager", pm), ("Tester", tester), ("Business Analyst", ba * 0.5), ("Developer", dev * 0.5)],
            [("Project Manager", pm), ("Change Manager", cm), ("Developer", max(1.0, dev * 0.25))],
            [("Project Manager", pm * 0.5), ("Business Analyst", ba * 0.5)],
        ]
        for pid, rows in zip(ids, profile):
            for role, f in rows:
                assert role in ROLES
                conn.execute("INSERT INTO resources (investment_id,phase_id,role,ftes) VALUES (?,?,?,?)",
                             (iid, pid, role, f))

    def costs(iid, rows):
        for fy, b, a, f in rows:
            conn.execute("INSERT INTO costs (investment_id,fy,budget,actual,forecast) VALUES (?,?,?,?,?)",
                         (iid, fy, b, a, f))

    def benefits(iid, fin, nonfin):
        for t, desc, amt, real in fin:
            conn.execute("INSERT INTO fin_benefits (investment_id,type,description,amount,realised_amount) "
                         "VALUES (?,?,?,?,?)", (iid, t, desc, amt, real))
        for c, desc in nonfin:
            conn.execute("INSERT INTO nonfin_benefits (investment_id,category,description) VALUES (?,?,?)",
                         (iid, c, desc))

    def metric(iid, name, unit, direction, base, target, tdate, owner, meas=()):
        cur = conn.execute(
            "INSERT INTO metrics (investment_id,name,unit,direction,baseline,target,target_date,owner_id) "
            "VALUES (?,?,?,?,?,?,?,?)", (iid, name, unit, direction, base, target, d(tdate).isoformat(), uid[owner]))
        mid = cur.lastrowid
        for off, val in meas:
            conn.execute("INSERT INTO measurements (metric_id,date,value) VALUES (?,?,?)",
                         (mid, d(off).isoformat(), val))
            audit(iid, "Declan Walsh", off, f"Measurement: {name}", "value", "", val, 15)
        return mid

    # ============================================================ 1. live investment
    i1 = make_inv(
        "Case Management System Replacement", "Aoife Brennan",
        "Replaces the unsupported legacy case system used by regional offices with a single cloud-hosted platform.",
        -560, "Approved", None, None,
        "Supports the Department's commitment to modern, joined-up case handling and the national digital strategy.",
        ["Digital Government Strategy", "Departmental Statement of Strategy"],
        ("Phased regional rollout on a configured commercial platform with a single data migration wave.",
         "In: case intake, workflow, reporting, document handling. Out: HR and payroll functions.",
         "Configured platform, migrated case data, trained staff, decommissioned legacy system.",
         "Vendor remains supported for ten years; regional offices released for training.",
         "Identity platform upgrade; records retention policy sign-off.",
         "Data quality in legacy files; staff adoption in smaller offices."))
    approvals(i1, "Aoife Brennan", [
        ("Approved", -540, "Strong case: replaces an unsupported platform.", "Data migration plan to be agreed before Build."),
        ("Approved", -535, "Aligned with portfolio priorities.", ""),
        ("Approved", -525, "Costs validated against framework prices.", "10% contingency held centrally by Finance."),
        ("Approved", -515, "Architecture complies with government cloud policy.", ""),
        ("Approved", -505, "Approved by the Board.", "Post-implementation reviews at 6 and 12 months."),
    ])
    ph = phases(i1, -492, [30, 60, 120, 45, 15, 30], [0, 0, 3, 5, 5, 5], 6, None)
    resources(i1, ph, 8, 3, 3, 1)
    costs(i1, [(2025, 600000, 585000, 585000), (2026, 500000, 430000, 495000)])
    audit(i1, "Tadhg Nolan", -20, "Cost: FY2026", "actual", 380000, 430000, 11)
    audit(i1, "Mairéad Costello", -60, "Cost: FY2026", "forecast", 520000, 495000, 11)
    benefits(i1,
             [("Cost saving", "Retire legacy hosting and support contracts", 540000, 180000),
              ("Cost avoidance", "Avoided cost of extended legacy support", 250000, 250000)],
             [("Service improvement", "Faster, more consistent decisions on cases"),
              ("Citizen or staff experience", "Single view of a case for staff and applicants")])
    metric(i1, "Average case processing time", "days", "lower", 42, 21, 150, "Aoife Brennan",
           [(-120, 38), (-30, 30)])
    metric(i1, "Cases closed within service standard", "%", "higher", 61, 90, 150, "Aoife Brennan",
           [(-120, 65), (-30, 70)])
    metric(i1, "Paper case files created per month", "files", "lower", 1200, 200, -20, "Aoife Brennan",
           [(-120, 900), (-30, 1050)])
    metric(i1, "Staff completing system training", "%", "higher", 0, 95, -60, "Aoife Brennan",
           [(-150, 60), (-60, 97)])
    metric(i1, "Applicant satisfaction score", "score /10", "higher", 6.1, 8.0, 300, "Aoife Brennan")
    conn.execute("INSERT INTO reviews (investment_id,months_after,review_date,reviewer_id,findings,lessons) "
                 "VALUES (?,?,?,?,?,?)",
                 (i1, 6, d(-28).isoformat(), uid["Orla Kavanagh"],
                  "Platform stable; processing times improving. Paper file creation remains high in two regions.",
                  "Engage regional managers earlier on process change; allow more time for paper-to-digital habits."))
    conn.execute("INSERT INTO reviews (investment_id,months_after) VALUES (?,12)", (i1,))
    audit(i1, "Aoife Brennan", -35, "Phase: Deploy", "actual_end", "", d(-217).isoformat(), 16)

    # ============================================================ 2. network refresh (delivery, Red/Red)
    i2 = make_inv(
        "National Network Refresh", "Niamh Gallagher",
        "Replaces end-of-life switches and wireless equipment across 40 offices with a managed, secure network.",
        -170, "Approved", None, None,
        "Provides resilient connectivity needed for digital service delivery and hybrid working.",
        ["Digital Government Strategy", "Climate Action Plan"],
        ("Site-by-site replacement in waves with a pilot in two offices.",
         "In: switches, wireless, WAN links for 40 offices. Out: telephony.",
         "New network at 40 sites, updated documentation, decommissioned equipment.",
         "Sites available for out-of-hours work; supplier stock secured.",
         "Supplier lead times; building access in leased offices.",
         "Global hardware shortages; site access delays."))
    approvals(i2, "Niamh Gallagher", [
        ("Approved", -160, "Clear operational need.", ""),
        ("Approved", -155, "Good fit with the infrastructure roadmap.", ""),
        ("Approved", -150, "Funding confirmed.", "Quarterly cost reporting to Finance."),
        ("Approved", -145, "Aligned with network architecture standards.", ""),
        ("Approved", -140, "Approved.", "Pilot results to be reported before main rollout."),
    ])
    ph = phases(i2, -120, [20, 40, 100, 60, 30, 20], [0, 5, 25, 30, 30, 30], 2, 2)
    resources(i2, ph, 2, 1, 2, 1)
    costs(i2, [(2026, 900000, 350000, 980000), (2027, 700000, 0, 760000)])
    benefits(i2, [("Cost avoidance", "Avoided emergency equipment replacement", 400000, 0)],
             [("Risk reduction", "Fewer outages from end-of-life equipment")])
    metric(i2, "Network availability", "%", "higher", 98.4, 99.9, 220, "Niamh Gallagher")
    conn.execute("INSERT INTO reviews (investment_id,months_after) VALUES (?,6)", (i2,))
    conn.execute("INSERT INTO reviews (investment_id,months_after) VALUES (?,12)", (i2,))
    audit(i2, "Niamh Gallagher", -25, "Phase: Build", "forecast_end", d(40).isoformat(), d(65).isoformat(), 16)
    audit(i2, "Tadhg Nolan", -10, "Cost: FY2026", "forecast", 920000, 980000, 11)

    # ============================================================ 3. cyber security uplift (Amber/Green)
    i3 = make_inv(
        "Cyber Security Uplift", "Niamh Gallagher",
        "Strengthens monitoring, endpoint protection and incident response across the Department.",
        -210, "Approved", None, None,
        "Delivers the Department's obligations under the national cyber security strategy.",
        ["National Cyber Security Strategy", "Departmental Statement of Strategy"],
        ("Risk-based rollout: monitoring first, then endpoint and identity controls.",
         "In: SOC tooling, endpoint protection, privileged access. Out: operational technology.",
         "24/7 monitoring service, hardened endpoints, tested incident response plan.",
         "Managed security service available under existing framework.",
         "Network refresh completion at larger sites.",
         "Scarcity of security specialists; user disruption during endpoint changes."))
    approvals(i3, "Niamh Gallagher", [
        ("Approved", -200, "Priority risk reduction.", ""),
        ("Approved", -196, "Approved at early gate.", ""),
        ("Approved", -192, "Costs reasonable.", ""),
        ("Approved", -188, "Meets security architecture principles.", "Independent penetration test before go-live."),
        ("Approved", -183, "Approved.", ""),
    ])
    ph = phases(i3, -150, [15, 30, 90, 60, 20, 15], [0, 0, 0, 9, 5, 5], 3, 3)
    resources(i3, ph, 3, 1, 2, 1)
    costs(i3, [(2026, 450000, 180000, 400000), (2027, 300000, 0, 300000)])
    audit(i3, "Mairéad Costello", -15, "Cost: FY2026", "forecast", 440000, 400000, 11)
    benefits(i3, [("Cost avoidance", "Reduced exposure to incident recovery costs", 500000, 0)],
             [("Risk reduction", "Lower likelihood and impact of a significant cyber incident"),
              ("Compliance", "Alignment with national minimum security standards")])
    metric(i3, "Mean time to detect incidents", "hours", "lower", 72, 4, 200, "Niamh Gallagher")
    conn.execute("INSERT INTO reviews (investment_id,months_after) VALUES (?,6)", (i3, ))
    conn.execute("INSERT INTO reviews (investment_id,months_after) VALUES (?,12)", (i3, ))

    # ============================================================ 4. data platform (stage 5)
    i4 = make_inv(
        "Enterprise Data Platform", "Aoife Brennan",
        "A shared, governed data platform to support analytics and reporting across the Department.",
        -30, "In approval", 5, -12,
        "Enables evidence-based policy and meets the public service data strategy.",
        ["Public Service Data Strategy", "Digital Government Strategy"],
        ("Incremental delivery: core platform, then domain data products.",
         "In: platform, ingestion, governance tooling. Out: new analytics tools for end users.",
         "Production data platform, five data products, data governance framework.",
         "Data owners agree sharing arrangements.",
         "Case management data feeds; data protection impact assessment.",
         "Data quality; skills availability."))
    approvals(i4, "Aoife Brennan", [
        ("Approved", -25, "Good strategic fit.", ""),
        ("Approved", -20, "Scope clear; sequence with other build work.", ""),
        ("Approved", -16, "Cost profile accepted.", "Benefits owner to be named per data product."),
        ("Approved", -12, "Architecture sound.", "Cloud region and data residency to be confirmed."),
        ("Pending", 0, "", ""),
    ])
    ph = phases(i4, 60, [30, 60, 150, 60, 30, 30], [0, 0, 10, 14, 14, 14], 0, None)
    resources(i4, ph, 5, 2, 2, 2)
    costs(i4, [(2027, 1200000, 0, 1350000), (2028, 1400000, 0, 1400000)])
    benefits(i4, [("Cost saving", "Retire duplicated reporting tools", 600000, 0)],
             [("Service improvement", "Faster, more reliable management information")])
    metric(i4, "Time to produce monthly performance report", "days", "lower", 15, 3, 700, "Aoife Brennan")

    # ============================================================ 5. citizen portal (stage 4)
    i5 = make_inv(
        "Citizen Services Portal", "Ciarán Doyle",
        "A single online portal for citizens to apply for and track Department services.",
        -20, "In approval", 4, -5,
        "Moves high-volume services online in line with digital-first principles.",
        ["Digital Government Strategy", "Public Service Reform"],
        ("Agile delivery of the highest-volume services first.",
         "In: identity, applications, tracking, notifications. Out: payments.",
         "Live portal with six services, accessibility audit, service desk playbook.",
         "National identity service available for integration.",
         "Case management platform APIs.",
         "Accessibility compliance; citizen adoption."))
    approvals(i5, "Ciarán Doyle", [
        ("Approved", -14, "Compelling citizen benefit.", ""),
        ("Approved", -9, "Approved; manage overlap with data platform.", ""),
        ("Approved", -5, "Costs validated.", "Accessibility audit funded within budget."),
        ("Pending", 0, "", ""),
    ])
    ph = phases(i5, 45, [20, 45, 120, 45, 20, 20], [0, 0, 0, 0, 0, 0], 0, None)
    resources(i5, ph, 8, 2, 2, 1)
    costs(i5, [(2027, 800000, 0, 800000), (2028, 500000, 0, 500000)])
    benefits(i5, [("Cost saving", "Reduced postal and counter handling", 450000, 0)],
             [("Citizen or staff experience", "24/7 online access with status tracking")])
    metric(i5, "Applications submitted online", "%", "higher", 22, 75, 600, "Ciarán Doyle")

    # ============================================================ 6. finance reporting (stage 3)
    i6 = make_inv(
        "Finance Reporting Modernisation", "Ciarán Doyle",
        "Replaces spreadsheet-based financial reporting with an automated reporting solution.",
        -22, "In approval", 3, -9,
        "Improves financial management and transparency of Departmental spend.",
        ["Departmental Statement of Strategy", "Public Service Reform"],
        ("Configure a commercial reporting tool on top of existing ledgers.",
         "In: management and statutory reporting. Out: ledger replacement.",
         "Automated monthly reports, reconciliation process, trained finance staff.",
         "Ledger data is clean enough to automate.",
         "Data platform for long-term data sharing.",
         "Reconciliation differences found late."))
    approvals(i6, "Ciarán Doyle", [
        ("Approved", -15, "Sensible efficiency measure.", ""),
        ("Approved", -9, "Aligned with priorities.", ""),
        ("Pending", 0, "", ""),
    ])
    ph = phases(i6, 30, [15, 30, 75, 30, 15, 15], [0, 0, 22, 22, 22, 22], 0, None)
    resources(i6, ph, 6, 1, 1, 1)
    costs(i6, [(2027, 350000, 0, 410000)])
    benefits(i6, [("Cost saving", "Reduced manual reporting effort", 180000, 0)],
             [("Compliance", "Timely and consistent statutory reporting")])
    metric(i6, "Monthly close duration", "days", "lower", 12, 5, 500, "Mairéad Costello")

    # ============================================================ 7. records digitisation (stage 2)
    i7 = make_inv(
        "Records Digitisation Project", "Aoife Brennan",
        "Digitises archived paper records and moves them into a managed electronic records system.",
        -25, "In approval", 2, -18,
        "Supports records management obligations and reduces storage costs.",
        ["Digital Government Strategy", "Departmental Statement of Strategy"],
        ("Batch scanning by record series with quality checks and metadata capture.",
         "In: 2.4 million archived files. Out: records already in electronic systems.",
         "Digitised records, searchable index, destruction of approved paper records.",
         "Records schedule approved by National Archives guidance.",
         "Electronic records system licence.",
         "Scanning quality; handling of sensitive records."))
    approvals(i7, "Aoife Brennan", [
        ("Approved", -18, "Reduces storage costs and risk.", ""),
        ("Pending", 0, "", ""),
    ])
    ph = phases(i7, 75, [20, 30, 180, 45, 30, 20], [0, 0, 0, 0, 0, 0], 0, None)
    resources(i7, ph, 4, 2, 2, 1)
    costs(i7, [(2027, 600000, 0, 570000), (2028, 400000, 0, 400000)])
    benefits(i7, [("Cost saving", "Reduced off-site storage fees", 220000, 0)],
             [("Compliance", "Improved retention and retrieval compliance")])
    metric(i7, "Paper records in off-site storage", "boxes", "lower", 48000, 8000, 800, "Aoife Brennan")

    # ============================================================ 8. HR system (stage 1)
    i8 = make_inv(
        "HR System Replacement", "Niamh Gallagher",
        "Replaces the ageing HR and rostering system with a modern shared-service solution.",
        -4, "In approval", 1, -3,
        "Aligns with public service reform and shared HR service goals.",
        ["Public Service Reform"],
        ("Adopt the standard shared-service platform with minimal configuration.",
         "In: core HR, leave, rostering. Out: payroll.",
         "Live HR platform, migrated employee data, retired legacy system.",
         "Shared service platform capacity available.",
         "Payroll interface timelines.",
         "Data migration quality; change fatigue."))
    approvals(i8, "Niamh Gallagher", [("Pending", 0, "", "")])
    ph = phases(i8, 90, [30, 60, 150, 60, 45, 30], [0, 0, 0, 0, 0, 0], 0, None)
    resources(i8, ph, 3, 2, 2, 1)
    costs(i8, [(2027, 1000000, 0, 1000000), (2028, 1200000, 0, 1200000), (2029, 600000, 0, 600000)])
    benefits(i8, [("Cost saving", "Reduced HR administration effort", 300000, 0)],
             [("Citizen or staff experience", "Self-service for staff leave and records")])
    metric(i8, "HR requests resolved by self-service", "%", "higher", 10, 70, 1000, "Niamh Gallagher")

    # ============================================================ 9. payroll interface (rejected)
    i9 = make_inv(
        "Legacy Payroll Interface Upgrade", "Ciarán Doyle",
        "Upgrades the custom interface between HR and payroll systems.",
        -50, "Rejected", 3, None,
        "Maintains payroll accuracy.",
        ["Departmental Statement of Strategy"],
        ("Upgrade existing custom interface code.",
         "In: HR to payroll interface only.",
         "Upgraded interface.",
         "Legacy platform remains in service.",
         "None identified.",
         "Interface may be replaced by shared services."))
    approvals(i9, "Ciarán Doyle", [
        ("Approved", -40, "Operational need acknowledged.", ""),
        ("Approved", -35, "Fits the infrastructure roadmap.", ""),
        ("Rejected", -28, "Investment would be superseded by shared payroll services within 18 months. "
                           "Not value for money.", ""),
    ])
    ph = phases(i9, 40, [10, 20, 60, 30, 10, 10], [0] * 6, 0, None)
    resources(i9, ph, 3, 1, 1, 0.5)
    costs(i9, [(2027, 220000, 0, 220000)])
    benefits(i9, [("Cost avoidance", "Avoided payroll errors", 60000, 0)], [])
    metric(i9, "Payroll interface failures per month", "failures", "lower", 6, 1, 500, "Ciarán Doyle")

    # ============================================================ 10. inspection app (returned)
    i10 = make_inv(
        "Inspection Mobile App", "Aoife Brennan",
        "A mobile app for field inspectors to capture inspection results offline and sync to the case system.",
        -34, "Returned for rework", 2, None,
        "Improves the efficiency and quality of field inspections.",
        ["Digital Government Strategy"],
        ("Build a lightweight offline-first app.",
         "In: capture, photos, sync. Out: scheduling.",
         "Mobile app, device management, inspector training.",
         "Field devices already issued.",
         "Case management APIs.",
         "Connectivity in rural areas."))
    approvals(i10, "Aoife Brennan", [
        ("Approved", -30, "Practical improvement.", ""),
        ("Returned for rework", -20,
         "Benefits are not quantified well enough and the delivery plan does not address overlap with the case "
         "management platform. Please revise the metrics and dependencies, then resubmit.", ""),
    ])
    ph = phases(i10, 50, [15, 30, 80, 30, 15, 10], [0] * 6, 0, None)
    resources(i10, ph, 4, 1, 1, 1)
    costs(i10, [(2027, 280000, 0, 300000)])
    benefits(i10, [("Cost saving", "Reduced inspector admin time", 120000, 0)],
             [("Service improvement", "Same-day inspection reports")])
    metric(i10, "Inspection report turnaround", "days", "lower", 9, 2, 450, "Aoife Brennan")
    audit(i10, "Orla Kavanagh", -19, "Investment", "status", "In approval", "Returned for rework", 14)

    # a few extra edit entries for flavour
    audit(i4, "Aoife Brennan", -28, "Cost: FY2027", "budget", 1100000, 1200000, 16)
    audit(i6, "Ciarán Doyle", -21, "Plan", "approach", "", "Configure a commercial reporting tool", 11)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    run()
    print(f"Database created at {dbm.DB_PATH} with sample data.")
