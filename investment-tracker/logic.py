"""Business rules: RAG status, realisation status, capacity checking."""
import calendar
from collections import defaultdict
from datetime import date, datetime

APP_NAME = "IT Investment Tracker"

ROLES = ["Developer", "Business Analyst", "Project Manager", "Architect", "Tester", "Change Manager"]
PHASE_NAMES = ["Initiation", "Design", "Build", "Test", "Deploy", "Close"]
DEFAULT_PHASE_DAYS = [14, 28, 56, 28, 14, 14]
PHASE_STATUSES = ["Not started", "In progress", "Complete"]

STAGES = [
    (1, "Business Case"),
    (2, "Portfolio Manager review"),
    (3, "Finance Sign-off"),
    (4, "Technical / Architecture Review"),
    (5, "Investment Board"),
]
STAGE_NAMES = dict(STAGES)

STATUSES = ["Draft", "In approval", "Approved", "Rejected", "Returned for rework"]
FIN_TYPES = ["Cost saving", "Cost avoidance", "New revenue"]
NONFIN_CATS = ["Service improvement", "Citizen or staff experience", "Compliance", "Risk reduction"]
STRATEGY_TAGS = [
    "Digital Government Strategy",
    "Departmental Statement of Strategy",
    "Public Service Data Strategy",
    "National Cyber Security Strategy",
    "Public Service Reform",
    "Climate Action Plan",
]
REALISATION_STATUSES = ["Not Started", "On Track", "Partially Realised", "Fully Realised", "Not Realised"]
RAG_ORDER = {"Red": 0, "Amber": 1, "Green": 2, None: 3}


# ---------------------------------------------------------------- dates
def pd(value):
    """Parse an ISO date (or datetime string) into a date; None if blank/invalid."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def add_months(d, n):
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def month_start(d):
    return d.replace(day=1)


# ---------------------------------------------------------------- RAG (Section 7)
def phase_slippage(p):
    """Days late: forecast end (actual end if complete) minus planned end. Early counts as 0."""
    planned_end = pd(p["planned_end"])
    if not planned_end:
        return 0
    if p["status"] == "Complete" and p.get("actual_end"):
        end = pd(p["actual_end"])
    else:
        end = pd(p.get("forecast_end")) or planned_end
    return max(0, (end - planned_end).days)


def rag_for_days(days):
    # Thresholds are fixed in code (not editable in the app).
    if days >= 21:
        return "Red"
    if days >= 7:
        return "Amber"
    return "Green"


def current_phase(phases):
    for p in phases:
        if p["status"] == "In progress":
            return p
    for p in phases:
        if p["status"] == "Not started":
            return p
    return phases[-1] if phases else None


def golive_phase(phases):
    if not phases:
        return None
    for p in phases:
        if p["name"].strip().lower() == "deploy":
            return p
    return phases[-2] if len(phases) >= 2 else phases[-1]


def golive_date(phases):
    p = golive_phase(phases)
    if not p:
        return None
    if p["status"] == "Complete" and p.get("actual_end"):
        return pd(p["actual_end"])
    return pd(p.get("forecast_end")) or pd(p["planned_end"])


def investment_rag(phases):
    out = {"current": None, "golive": None}
    cur = current_phase(phases)
    if cur:
        d = phase_slippage(cur)
        out["current"] = {"rag": rag_for_days(d), "days": d, "phase": cur["name"]}
    gl = golive_phase(phases)
    if gl:
        d = phase_slippage(gl)
        out["golive"] = {"rag": rag_for_days(d), "days": d, "phase": gl["name"]}
    return out


# ---------------------------------------------------------------- realisation (Section 8)
def metric_status(metric, measurements, go_live, today):
    """Return dict(status, progress, expected, latest) for a quantified metric.

    progress  = fraction of the baseline->target distance achieved (direction aware).
    expected  = fraction expected by the latest measurement date on a straight line
                from go-live (or first measurement) to the target date.
    """
    if not measurements:
        return {"status": "Not Started", "progress": None, "expected": None, "latest": None}
    latest = max(measurements, key=lambda m: (m["date"], m["id"]))
    b, t, v = metric["baseline"], metric["target"], latest["value"]
    if metric["direction"] == "lower":
        span = b - t
        progress = 1.0 if span == 0 else (b - v) / span
    else:
        span = t - b
        progress = 1.0 if span == 0 else (v - b) / span

    start = go_live or pd(min(m["date"] for m in measurements))
    target_date = pd(metric["target_date"])
    latest_date = pd(latest["date"])
    if not target_date or not start or target_date <= start:
        expected = 1.0
    else:
        expected = (latest_date - start).days / (target_date - start).days
        expected = max(0.0, min(1.0, expected))

    if progress >= 1.0:
        status = "Fully Realised"
    elif progress >= expected:
        status = "On Track"
    elif progress >= 0.25:
        status = "Partially Realised"
    elif target_date and target_date < today:
        status = "Not Realised"
    else:
        # Behind trajectory, under 25%, target date not yet reached: the spec does
        # not name this case; treated as Partially Realised (flagged in README).
        status = "Partially Realised"
    return {"status": status, "progress": progress, "expected": expected, "latest": latest}


# ---------------------------------------------------------------- capacity (Section 9)
def capacity(conn, today):
    """Monthly demand per role across all non-rejected investments (forecast dates)."""
    pool = {r["role"]: r["ftes"] for r in conn.execute("SELECT role, ftes FROM capacity_pool")}
    rows = conn.execute(
        """SELECT r.investment_id, i.name AS inv_name, r.role, r.ftes,
                  p.planned_start, p.planned_end, p.forecast_start, p.forecast_end
           FROM resources r
           JOIN phases p ON p.id = r.phase_id
           JOIN investments i ON i.id = r.investment_id
           WHERE i.status <> 'Rejected'"""
    ).fetchall()
    demand = defaultdict(float)
    contrib = defaultdict(lambda: defaultdict(float))
    names = {}
    for r in rows:
        s = pd(r["forecast_start"]) or pd(r["planned_start"])
        e = pd(r["forecast_end"]) or pd(r["planned_end"])
        if not s or not e or e < s:
            continue
        names[r["investment_id"]] = r["inv_name"]
        m = month_start(s)
        while m <= e:
            key = (r["role"], m)
            demand[key] += r["ftes"]
            contrib[key][r["investment_id"]] += r["ftes"]
            m = add_months(m, 1)

    cur = month_start(today)
    over, flagged = [], set()
    for key in sorted(demand, key=lambda k: (k[1], k[0])):
        role, m = key
        pl = pool.get(role, 0.0)
        if demand[key] > pl + 1e-9 and m >= cur:
            over.append({
                "role": role, "month": m, "demand": demand[key], "pool": pl,
                "shortfall": demand[key] - pl,
                "investments": [(i, names[i], f) for i, f in sorted(contrib[key].items())],
            })
            flagged.update(contrib[key].keys())
    months = [add_months(cur, i) for i in range(12)]
    return {"pool": pool, "demand": demand, "over": over, "flagged": flagged, "months": months}
