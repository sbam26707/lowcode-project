"""IT Investment Tracker - proof of concept (Flask + SQLite)."""
import math
import os
import re
from collections import Counter
from datetime import date, datetime

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from markupsafe import Markup, escape

import db as dbm
import logic
from logic import STAGE_NAMES, STAGES, pd

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "poc-demo-only-not-a-real-secret")
app.teardown_appcontext(dbm.close_db)

if not os.path.exists(dbm.DB_PATH):
    import seed
    seed.run()

TABS = [("overview", "Overview"), ("approval", "Approval"), ("cost", "Cost"), ("value", "Value"),
        ("timeline", "Timeline"), ("capacity", "Capacity"), ("plan", "Plan"),
        ("realisation", "Realisation"), ("history", "History")]
TAB_KEYS = [k for k, _ in TABS]


# ------------------------------------------------------------------ helpers
def today():
    return date.today()


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def rows(sql, args=()):
    return dbm.get_db().execute(sql, args).fetchall()


def row(sql, args=()):
    return dbm.get_db().execute(sql, args).fetchone()


def run(sql, args=()):
    return dbm.get_db().execute(sql, args)


def sv(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def audit(iid, area, field, old, new):
    if sv(old) == sv(new):
        return
    run("INSERT INTO audit (ts,user_id,user_name,investment_id,area,field,old_value,new_value) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (now_str(), g.user["id"], g.user["name"], iid, area, field, sv(old), sv(new)))


def touch(iid):
    run("UPDATE investments SET updated_at=? WHERE id=?", (today().isoformat(), iid))


def form_str(name):
    return (request.form.get(name) or "").strip()


MAX_NAME_LEN = 120
MAX_DESC_LEN = 2000


def check_len(errors, value, label, limit):
    if len(value) > limit:
        errors.append(f"{label} must be {limit} characters or fewer.")
        return False
    return True

def form_num(name, errors, label, required=True, minimum=None):
    raw = form_str(name)
    if raw == "":
        if required:
            errors.append(f"Enter {label}.")
        return None
    try:
        v = float(raw.replace(",", ""))
    except ValueError:
        errors.append(f"{label[0].upper() + label[1:]} must be a number.")
        return None
    if not math.isfinite(v):
        errors.append(f"{label[0].upper() + label[1:]} must be a number.")
        return None
    if minimum is not None and v < minimum:
        errors.append(f"{label[0].upper() + label[1:]} must be {sv(minimum)} or more.")
        return None
    return v


def form_date(name, errors, label, required=True):
    raw = form_str(name)
    if raw == "":
        if required:
            errors.append(f"Enter {label}.")
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
    except ValueError:
        errors.append(f"{label[0].upper() + label[1:]} must be a real date.")
        return None


def back(iid, tab, **kw):
    return redirect(url_for("investment_tab", iid=iid, tab=tab, **kw))


def fail(errors, iid, tab, **kw):
    for e in errors:
        flash(e, "error")
    return back(iid, tab, **kw)


def deny(iid, tab):
    flash("You do not have permission to do that as the current user.", "error")
    return back(iid, tab)


def get_inv(iid):
    inv = row("SELECT i.*, u.name AS owner_name FROM investments i JOIN users u ON u.id=i.owner_id "
              "WHERE i.id=?", (iid,))
    if not inv:
        abort(404)
    return inv


def perms(inv):
    u = g.user
    own = u["id"] == inv["owner_id"]
    p = {
        "can_edit": own and inv["status"] in ("Draft", "Returned for rework"),
        "can_track": (own and inv["status"] == "Approved") or u["grp"] == "pmo",
        "can_finance": u["grp"] == "finance",
        "can_decide": inv["status"] == "In approval" and u["approver_stage"] == inv["current_stage"],
    }
    p["can_realise_fin"] = p["can_track"] or p["can_finance"]
    return p


def get_capacity():
    if "cap" not in g:
        g.cap = logic.capacity(dbm.get_db(), today())
    return g.cap


def phases_of(iid):
    return [dict(p) for p in rows("SELECT * FROM phases WHERE investment_id=? ORDER BY position, id", (iid,))]


def metrics_for(iid):
    gl = logic.golive_date(phases_of(iid))
    out = []
    for m in rows("SELECT m.*, u.name AS owner_name FROM metrics m LEFT JOIN users u ON u.id=m.owner_id "
                  "WHERE m.investment_id=? ORDER BY m.id", (iid,)):
        ms = [dict(x) for x in rows("SELECT * FROM measurements WHERE metric_id=? ORDER BY date, id", (m["id"],))]
        st = logic.metric_status(dict(m), ms, gl, today())
        out.append({"m": m, "ms": ms, **st})
    return out


def stage_label(inv):
    st = inv["status"]
    name = STAGE_NAMES.get(inv["current_stage"], "")
    if st == "In approval":
        return f"{inv['current_stage']}. {name}"
    if st == "Returned for rework":
        return f"Returned at {name}"
    if st == "Rejected":
        return f"Rejected at {name}"
    if st == "Approved":
        return "Complete"
    return "Not submitted"


def summarise(inv):
    iid = inv["id"]
    s = dict(inv)
    ph = phases_of(iid)
    c = row("SELECT COALESCE(SUM(budget),0) b, COALESCE(SUM(actual),0) a, COALESCE(SUM(forecast),0) f, "
            "COUNT(*) n FROM costs WHERE investment_id=?", (iid,))
    rag = logic.investment_rag(ph)
    s.update(budget=c["b"], actual=c["a"], forecast=c["f"], cost_rows=c["n"],
             variance=c["f"] - c["b"],
             variance_pct=((c["f"] - c["b"]) / c["b"] * 100) if c["b"] else None,
             rag=rag, rag_current=rag["current"]["rag"] if rag["current"] else None,
             rag_golive=rag["golive"]["rag"] if rag["golive"] else None,
             stage_label=stage_label(inv), phases=ph,
             waiting=((today() - pd(inv["stage_entered"])).days
                      if inv["status"] == "In approval" and pd(inv["stage_entered"]) else None),
             over_allocated=iid in get_capacity()["flagged"])
    return s


def all_summaries():
    return [summarise(i) for i in rows(
        "SELECT i.*, u.name AS owner_name FROM investments i JOIN users u ON u.id=i.owner_id ORDER BY i.name")]


# ------------------------------------------------------------------ template support
@app.before_request
def load_user():
    if request.endpoint == "static":
        return
    uid = session.get("user_id")
    user = row("SELECT * FROM users WHERE id=?", (uid,)) if uid else None
    if not user:
        user = row("SELECT * FROM users ORDER BY id LIMIT 1")
        session["user_id"] = user["id"]
    g.user = user


@app.after_request
def commit(resp):
    if "db" in g:
        g.db.commit()
    return resp


RAG_ICON = {"Green": "●", "Amber": "▲", "Red": "■"}


def rag_badge(r, days=None):
    if not r:
        return Markup('<span class="muted">n/a</span>')
    extra = f" ({days}d late)" if days else ""
    return Markup(f'<span class="badge rag-{escape(r).lower()}"><span aria-hidden="true">{RAG_ICON[r]}</span> '
                  f'{escape(r)}{escape(extra)}</span>')


def status_badge(s):
    cls = re.sub(r"[^a-z]+", "-", s.lower()).strip("-")
    return Markup(f'<span class="badge st-{cls}">{escape(s)}</span>')


def variance_text(var, budget):
    if not budget and not var:
        return "—"
    sign = "+" if var > 0 else ("-" if var < 0 else "")
    pct = f" ({var / budget * 100:+.1f}%)" if budget else ""
    word = "over budget" if var > 0 else ("under budget" if var < 0 else "on budget")
    return f"{sign}€{abs(var):,.0f}{pct}, {word}"


@app.context_processor
def inject():
    return dict(app_name=logic.APP_NAME, current_user=getattr(g, "user", None),
                all_users=rows("SELECT * FROM users ORDER BY id") if hasattr(g, "user") else [],
                today=today(), rag_badge=rag_badge, status_badge=status_badge,
                variance_text=variance_text, STAGES=STAGES, ROLES=logic.ROLES,
                realisation_statuses=logic.REALISATION_STATUSES)


@app.template_filter("dmy")
def f_dmy(v):
    d = pd(v)
    return d.strftime("%d/%m/%Y") if d else "—"


@app.template_filter("dmyhm")
def f_dmyhm(v):
    try:
        return datetime.strptime(v, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return v or ""


@app.template_filter("month")
def f_month(v):
    return v.strftime("%m/%Y")


@app.template_filter("eur")
def f_eur(v):
    if v is None:
        return "—"
    v = float(v)
    s = f"€{abs(v):,.0f}"
    return "-" + s if round(v) < 0 else s


@app.template_filter("num")
def f_num(v):
    if v is None:
        return "—"
    v = float(v)
    return f"{v:,.0f}" if v.is_integer() else f"{v:,.2f}".rstrip("0").rstrip(".")


@app.template_filter("pct")
def f_pct(v):
    return "—" if v is None else f"{v * 100:.0f}%"


@app.template_filter("auditval")
def f_auditval(v):
    if v and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return f_dmy(v)
    return v


# ------------------------------------------------------------------ role switcher
@app.post("/switch-user")
def switch_user():
    uid = request.form.get("user_id", type=int)
    if uid and row("SELECT 1 FROM users WHERE id=?", (uid,)):
        session["user_id"] = uid
    nxt = request.form.get("next") or ""
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = url_for("dashboard")
    return redirect(nxt)


# ------------------------------------------------------------------ dashboard
@app.route("/")
def dashboard():
    sums = all_summaries()
    live = [s for s in sums if s["status"] != "Rejected"]
    tot = {"budget": sum(s["budget"] for s in live), "actual": sum(s["actual"] for s in live),
           "forecast": sum(s["forecast"] for s in live)}
    tot["variance"] = tot["forecast"] - tot["budget"]
    status_counts = [(st, sum(1 for s in sums if s["status"] == st)) for st in logic.STATUSES]
    cost_chart = {"labels": [s["name"] for s in live if s["cost_rows"]],
                  "budget": [s["budget"] for s in live if s["cost_rows"]],
                  "actual": [s["actual"] for s in live if s["cost_rows"]],
                  "forecast": [s["forecast"] for s in live if s["cost_rows"]]}

    approved = [s for s in sums if s["status"] == "Approved"]
    fin_rows = []
    for s in approved:
        f = row("SELECT COALESCE(SUM(amount),0) t, COALESCE(SUM(realised_amount),0) r "
                "FROM fin_benefits WHERE investment_id=?", (s["id"],))
        fin_rows.append({"name": s["name"], "target": f["t"], "realised": f["r"]})
    fin_total = {"target": sum(r["target"] for r in fin_rows), "realised": sum(r["realised"] for r in fin_rows)}
    metric_rows, counter = [], Counter()
    for s in approved:
        for m in metrics_for(s["id"]):
            metric_rows.append({"inv": s["name"], "inv_id": s["id"], **m})
            counter[m["status"]] += 1
    status_by_real = [(st, counter.get(st, 0)) for st in logic.REALISATION_STATUSES]
    pirs = []
    for s in approved:
        gl = logic.golive_date(s["phases"])
        for r in rows("SELECT * FROM reviews WHERE investment_id=? AND review_date IS NULL ORDER BY months_after",
                      (s["id"],)):
            if gl:
                pirs.append({"inv": s["name"], "inv_id": s["id"], "months": r["months_after"],
                             "due": logic.add_months(gl, r["months_after"])})
    pirs.sort(key=lambda p: p["due"])
    benefit_chart = {"labels": [r["name"] for r in fin_rows], "target": [r["target"] for r in fin_rows],
                     "realised": [r["realised"] for r in fin_rows]}

    pipeline = []
    for stage, name in STAGES:
        approver = row("SELECT name, title FROM users WHERE approver_stage=?", (stage,))
        items = sorted([s for s in sums if s["status"] == "In approval" and s["current_stage"] == stage],
                       key=lambda s: -(s["waiting"] or 0))
        pipeline.append({"stage": stage, "name": name, "approver": approver, "items": items})

    return render_template("dashboard.html", sums=sums, tot=tot, status_counts=status_counts,
                           cost_chart=cost_chart, fin_rows=fin_rows, fin_total=fin_total,
                           metric_rows=metric_rows, status_by_real=status_by_real, pirs=pirs,
                           benefit_chart=benefit_chart, pipeline=pipeline)


# ------------------------------------------------------------------ investments list
@app.route("/investments")
def investments():
    sums = all_summaries()
    f_status = request.args.get("status", "")
    f_owner = request.args.get("owner", "")
    f_cur = request.args.get("rag_current", "")
    f_gl = request.args.get("rag_golive", "")
    if f_status:
        sums = [s for s in sums if s["status"] == f_status]
    if f_owner:
        sums = [s for s in sums if str(s["owner_id"]) == f_owner]
    if f_cur:
        sums = [s for s in sums if s["rag_current"] == f_cur]
    if f_gl:
        sums = [s for s in sums if s["rag_golive"] == f_gl]

    keys = {
        "name": lambda s: s["name"].lower(),
        "owner": lambda s: s["owner_name"],
        "status": lambda s: logic.STATUSES.index(s["status"]),
        "stage": lambda s: (s["current_stage"] or 0) if s["status"] == "In approval" else 99,
        "variance": lambda s: s["variance_pct"] if s["variance_pct"] is not None else 0,
        "rag_current": lambda s: logic.RAG_ORDER[s["rag_current"]],
        "rag_golive": lambda s: logic.RAG_ORDER[s["rag_golive"]],
    }
    sort = request.args.get("sort", "name")
    if sort not in keys:
        sort = "name"
    direction = request.args.get("dir", "asc")
    sums.sort(key=keys[sort], reverse=(direction == "desc"))
    base = {k: v for k, v in request.args.items() if k in ("status", "owner", "rag_current", "rag_golive") and v}
    sort_urls = {k: url_for("investments", **base, sort=k,
                            dir=("desc" if sort == k and direction == "asc" else "asc")) for k in keys}
    owners = rows("SELECT id, name FROM users WHERE grp='owner' ORDER BY name")
    return render_template("investments.html", sums=sums, sort=sort, direction=direction, sort_urls=sort_urls,
                           f_status=f_status, f_owner=f_owner, f_cur=f_cur, f_gl=f_gl, owners=owners,
                           statuses=logic.STATUSES)


@app.route("/investments/new", methods=["GET", "POST"])
def investment_new():
    if g.user["grp"] != "owner":
        flash("Only investment owners can create investments. Switch to an owner role.", "error")
        return redirect(url_for("investments"))
    if request.method == "POST":
        name, desc = form_str("name"), form_str("description")
        errors = []
        if not name:
            errors.append("Enter a name for the investment.")
        elif row("SELECT 1 FROM investments WHERE lower(name)=lower(?)", (name,)):
            errors.append("An investment with that name already exists. Names must be unique.")
        check_len(errors, name, "The investment name", MAX_NAME_LEN)
        check_len(errors, desc, "The description", MAX_DESC_LEN)    
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("investment_new.html", name=name, description=desc)
        c = run("INSERT INTO investments (name, owner_id, description, status, created_at, updated_at) "
                "VALUES (?,?,?,'Draft',?,?)", (name, g.user["id"], desc, today().isoformat(), today().isoformat()))
        iid = c.lastrowid
        dbm.create_approval_rows(dbm.get_db(), iid)
        audit(iid, "Investment", "created", "", name)
        flash("Investment created as a draft. Add value, cost, timeline and resource details, then submit it.",
              "success")
        return back(iid, "overview")
    return render_template("investment_new.html", name="", description="")


# ------------------------------------------------------------------ investment tabs
@app.route("/investments/<int:iid>/")
def investment_home(iid):
    return back(iid, "overview")


@app.route("/investments/<int:iid>/<tab>")
def investment_tab(iid, tab):
    if tab not in TAB_KEYS:
        abort(404)
    inv = get_inv(iid)
    ctx = {"inv": inv, "tab": tab, "tabs": TABS, "p": perms(inv),
           "over_allocated": iid in get_capacity()["flagged"]}
    ctx.update(globals()[f"load_{tab}"](inv, ctx))
    return render_template(f"inv_{tab}.html", **ctx)


def load_overview(inv, ctx):
    s = summarise(inv)
    iid = inv["id"]
    checks = {
        "metrics": row("SELECT COUNT(*) n FROM metrics WHERE investment_id=?", (iid,))["n"],
        "phases": len(s["phases"]),
        "costs": s["cost_rows"],
    }
    returned = None
    if inv["status"] == "Returned for rework":
        returned = row("SELECT * FROM approval_history WHERE investment_id=? AND decision='Returned for rework' "
                       "ORDER BY id DESC LIMIT 1", (iid,))
    current_approver = None
    if inv["status"] == "In approval":
        current_approver = row("SELECT u.name, u.title FROM approvals a JOIN users u ON u.id=a.approver_id "
                               "WHERE a.investment_id=? AND a.stage=?", (iid, inv["current_stage"]))
    return {"s": s, "checks": checks, "returned": returned, "current_approver": current_approver,
            "ready": all(checks.values())}


def load_approval(inv, ctx):
    iid = inv["id"]
    return {"approvals": rows("SELECT a.*, u.name AS approver_name, u.title AS approver_title FROM approvals a "
                              "LEFT JOIN users u ON u.id=a.approver_id WHERE a.investment_id=? ORDER BY a.stage",
                              (iid,)),
            "history": rows("SELECT * FROM approval_history WHERE investment_id=? ORDER BY id", (iid,))}


def load_cost(inv, ctx):
    iid = inv["id"]
    costs = rows("SELECT * FROM costs WHERE investment_id=? ORDER BY fy", (iid,))
    t = {"budget": sum(c["budget"] for c in costs), "actual": sum(c["actual"] for c in costs),
         "forecast": sum(c["forecast"] for c in costs)}
    t["variance"] = t["forecast"] - t["budget"]
    fy = request.args.get("fy", type=int)
    edit = row("SELECT * FROM costs WHERE investment_id=? AND fy=?", (iid, fy)) if fy else None
    p = ctx["p"]
    return {"costs": costs, "tot": t, "edit": edit, "default_fy": fy or today().year,
            "can_budget": p["can_edit"], "can_forecast": p["can_edit"] or p["can_finance"],
            "can_actual": p["can_finance"]}


def load_value(inv, ctx):
    iid = inv["id"]
    return {"fin": rows("SELECT * FROM fin_benefits WHERE investment_id=? ORDER BY id", (iid,)),
            "nonfin": rows("SELECT * FROM nonfin_benefits WHERE investment_id=? ORDER BY id", (iid,)),
            "metrics": metrics_for(iid),
            "tags": [t for t in inv["strategic_tags"].split("|") if t],
            "all_tags": logic.STRATEGY_TAGS, "fin_types": logic.FIN_TYPES, "nonfin_cats": logic.NONFIN_CATS,
            "users": rows("SELECT id, name, title FROM users ORDER BY name")}


def load_timeline(inv, ctx):
    ph = phases_of(inv["id"])
    for p in ph:
        d = logic.phase_slippage(p)
        p["days_late"], p["rag"] = d, logic.rag_for_days(d)
    return {"phases": ph, "rag": logic.investment_rag(ph), "phase_statuses": logic.PHASE_STATUSES,
            "can_planned": ctx["p"]["can_edit"],
            "can_forecast": ctx["p"]["can_edit"] or ctx["p"]["can_track"],
            "phase_names": logic.PHASE_NAMES}


def load_capacity(inv, ctx):
    iid = inv["id"]
    res = rows("SELECT r.*, p.name AS phase_name, p.forecast_start, p.forecast_end FROM resources r "
               "JOIN phases p ON p.id=r.phase_id WHERE r.investment_id=? ORDER BY p.position, r.role", (iid,))
    mine = [o for o in get_capacity()["over"] if any(i == iid for i, _, _ in o["investments"])]
    return {"res": res, "phases": phases_of(iid), "mine": mine, "roles": logic.ROLES}


def load_plan(inv, ctx):
    return {"fields": [("approach", "Approach"), ("scope", "Scope (in and out)"),
                       ("deliverables", "Deliverables"), ("assumptions", "Assumptions"),
                       ("dependencies", "Dependencies"), ("risks", "Risks")]}


def load_realisation(inv, ctx):
    iid = inv["id"]
    ph = phases_of(iid)
    gl = logic.golive_date(ph)
    revs = []
    for r in rows("SELECT r.*, u.name AS reviewer_name FROM reviews r LEFT JOIN users u ON u.id=r.reviewer_id "
                  "WHERE r.investment_id=? ORDER BY r.months_after", (iid,)):
        d = dict(r)
        d["due"] = logic.add_months(gl, r["months_after"]) if gl else None
        revs.append(d)
    return {"metrics": metrics_for(iid), "fin": rows("SELECT * FROM fin_benefits WHERE investment_id=? ORDER BY id", (iid,)),
            "reviews": revs, "golive": gl, "users": rows("SELECT id, name FROM users ORDER BY name")}


def load_history(inv, ctx):
    return {"entries": rows("SELECT * FROM audit WHERE investment_id=? ORDER BY id DESC", (inv["id"],))}


# ------------------------------------------------------------------ overview / plan / value edits
@app.post("/investments/<int:iid>/overview")
def save_overview(iid):
    inv = get_inv(iid)
    if not perms(inv)["can_edit"]:
        return deny(iid, "overview")
    name, desc = form_str("name"), form_str("description")
    errors = []
    if not name:
        errors.append("Enter a name for the investment.")
    elif row("SELECT 1 FROM investments WHERE lower(name)=lower(?) AND id<>?", (name, iid)):
        errors.append("An investment with that name already exists. Names must be unique.")
    check_len(errors, name, "The investment name", MAX_NAME_LEN)    
    check_len(errors, desc, "The description", MAX_DESC_LEN)        
    if errors:
        return fail(errors, iid, "overview")
    audit(iid, "Investment", "name", inv["name"], name)
    audit(iid, "Investment", "description", inv["description"], desc)
    run("UPDATE investments SET name=?, description=? WHERE id=?", (name, desc, iid))
    touch(iid)
    flash("Overview saved.", "success")
    return back(iid, "overview")


@app.post("/investments/<int:iid>/plan")
def save_plan(iid):
    inv = get_inv(iid)
    if not perms(inv)["can_edit"]:
        return deny(iid, "plan")
    for f in ("approach", "scope", "deliverables", "assumptions", "dependencies", "risks"):
        new = form_str(f)
        audit(iid, "Plan", f, inv[f], new)
        run(f"UPDATE investments SET {f}=? WHERE id=?", (new, iid))
    touch(iid)
    flash("Plan saved.", "success")
    return back(iid, "plan")


@app.post("/investments/<int:iid>/value/strategic")
def save_strategic(iid):
    inv = get_inv(iid)
    if not perms(inv)["can_edit"]:
        return deny(iid, "value")
    tags = [t for t in request.form.getlist("tags") if t in logic.STRATEGY_TAGS]
    other = form_str("other_tag").replace("|", " ")
    if other:
        tags.append(other)
    statement = form_str("statement")
    new_tags = "|".join(tags)
    audit(iid, "Value: strategic alignment", "statement", inv["strategic_statement"], statement)
    audit(iid, "Value: strategic alignment", "tags", inv["strategic_tags"].replace("|", ", "), ", ".join(tags))
    run("UPDATE investments SET strategic_statement=?, strategic_tags=? WHERE id=?", (statement, new_tags, iid))
    touch(iid)
    flash("Strategic alignment saved.", "success")
    return back(iid, "value")


@app.post("/investments/<int:iid>/value/financial")
def add_financial(iid):
    inv = get_inv(iid)
    if not perms(inv)["can_edit"]:
        return deny(iid, "value")
    errors = []
    t, desc = form_str("type"), form_str("description")
    if t not in logic.FIN_TYPES:
        errors.append("Choose a type of financial benefit.")
    if not desc:
        errors.append("Enter a description of the financial benefit.")
    amount = form_num("amount", errors, "the benefit amount in euro", minimum=0.01)
    if errors:
        return fail(errors, iid, "value")
    run("INSERT INTO fin_benefits (investment_id,type,description,amount) VALUES (?,?,?,?)", (iid, t, desc, amount))
    audit(iid, "Value: financial benefit", "added", "", f"{t}: {desc} (€{sv(amount)})")
    touch(iid)
    flash("Financial benefit added.", "success")
    return back(iid, "value")


@app.post("/investments/<int:iid>/value/financial/<int:bid>/delete")
def delete_financial(iid, bid):
    inv = get_inv(iid)
    if not perms(inv)["can_edit"]:
        return deny(iid, "value")
    b = row("SELECT * FROM fin_benefits WHERE id=? AND investment_id=?", (bid, iid))
    if b:
        run("DELETE FROM fin_benefits WHERE id=?", (bid,))
        audit(iid, "Value: financial benefit", "removed", f"{b['type']}: {b['description']} (€{sv(b['amount'])})", "")
        touch(iid)
        flash("Financial benefit removed.", "success")
    return back(iid, "value")


@app.post("/investments/<int:iid>/value/nonfinancial")
def add_nonfinancial(iid):
    inv = get_inv(iid)
    if not perms(inv)["can_edit"]:
        return deny(iid, "value")
    errors = []
    c, desc = form_str("category"), form_str("description")
    if c not in logic.NONFIN_CATS:
        errors.append("Choose a category of non-financial benefit.")
    if not desc:
        errors.append("Enter a description of the non-financial benefit.")
    if errors:
        return fail(errors, iid, "value")
    run("INSERT INTO nonfin_benefits (investment_id,category,description) VALUES (?,?,?)", (iid, c, desc))
    audit(iid, "Value: non-financial benefit", "added", "", f"{c}: {desc}")
    touch(iid)
    flash("Non-financial benefit added.", "success")
    return back(iid, "value")


@app.post("/investments/<int:iid>/value/nonfinancial/<int:bid>/delete")
def delete_nonfinancial(iid, bid):
    inv = get_inv(iid)
    if not perms(inv)["can_edit"]:
        return deny(iid, "value")
    b = row("SELECT * FROM nonfin_benefits WHERE id=? AND investment_id=?", (bid, iid))
    if b:
        run("DELETE FROM nonfin_benefits WHERE id=?", (bid,))
        audit(iid, "Value: non-financial benefit", "removed", f"{b['category']}: {b['description']}", "")
        touch(iid)
        flash("Non-financial benefit removed.", "success")
    return back(iid, "value")


@app.post("/investments/<int:iid>/value/metric")
def add_metric(iid):
    inv = get_inv(iid)
    if not perms(inv)["can_edit"]:
        return deny(iid, "value")
    errors = []
    name, unit, direction = form_str("name"), form_str("unit"), form_str("direction")
    if not name:
        errors.append("Enter a name for the metric.")
    if not unit:
        errors.append("Enter a unit for the metric, for example days or %.")
    if direction not in ("higher", "lower"):
        errors.append("Choose whether higher or lower is better.")
    baseline = form_num("baseline", errors, "the baseline value")
    target = form_num("target", errors, "the target value")
    tdate = form_date("target_date", errors, "the target date")
    owner = request.form.get("owner_id", type=int)
    if not owner or not row("SELECT 1 FROM users WHERE id=?", (owner,)):
        errors.append("Choose a benefit owner.")
    if not errors and direction == "higher" and target <= baseline:
        errors.append("For a metric where higher is better, the target must be above the baseline.")
    if not errors and direction == "lower" and target >= baseline:
        errors.append("For a metric where lower is better, the target must be below the baseline.")
    if errors:
        return fail(errors, iid, "value")
    run("INSERT INTO metrics (investment_id,name,unit,direction,baseline,target,target_date,owner_id) "
        "VALUES (?,?,?,?,?,?,?,?)", (iid, name, unit, direction, baseline, target, tdate, owner))
    audit(iid, "Value: quantified metric", "added", "",
          f"{name} ({unit}): baseline {sv(baseline)}, target {sv(target)} by {f_dmy(tdate)}")
    touch(iid)
    flash("Quantified metric added.", "success")
    return back(iid, "value")


@app.post("/investments/<int:iid>/value/metric/<int:mid>/delete")
def delete_metric(iid, mid):
    inv = get_inv(iid)
    if not perms(inv)["can_edit"]:
        return deny(iid, "value")
    m = row("SELECT * FROM metrics WHERE id=? AND investment_id=?", (mid, iid))
    if m:
        run("DELETE FROM measurements WHERE metric_id=?", (mid,))
        run("DELETE FROM metrics WHERE id=?", (mid,))
        audit(iid, "Value: quantified metric", "removed", m["name"], "")
        touch(iid)
        flash("Quantified metric removed.", "success")
    return back(iid, "value")


# ------------------------------------------------------------------ cost
@app.post("/investments/<int:iid>/cost")
def save_cost(iid):
    inv = get_inv(iid)
    p = perms(inv)
    can_budget, can_forecast, can_actual = p["can_edit"], p["can_edit"] or p["can_finance"], p["can_finance"]
    if not (can_budget or can_forecast or can_actual):
        return deny(iid, "cost")
    errors = []
    fy = request.form.get("fy", type=int)
    if not fy or fy < 2000 or fy > 2100:
        errors.append("Enter a financial year, for example 2027.")
    vals = {}
    for key, allowed, label in (("budget", can_budget, "the budget"), ("actual", can_actual, "the actual cost"),
                                ("forecast", can_forecast, "the forecast cost")):
        vals[key] = form_num(key, errors, f"{label} in euro", required=False, minimum=0) if allowed else None
    if errors:
        return fail(errors, iid, "cost")
    existing = row("SELECT * FROM costs WHERE investment_id=? AND fy=?", (iid, fy))
    if existing:
        new = {k: (vals[k] if vals[k] is not None else existing[k]) for k in vals}
        for k in new:
            audit(iid, f"Cost: FY{fy}", k, existing[k], new[k])
        run("UPDATE costs SET budget=?, actual=?, forecast=? WHERE id=?",
            (new["budget"], new["actual"], new["forecast"], existing["id"]))
    else:
        new = {k: (vals[k] if vals[k] is not None else 0.0) for k in vals}
        run("INSERT INTO costs (investment_id,fy,budget,actual,forecast) VALUES (?,?,?,?,?)",
            (iid, fy, new["budget"], new["actual"], new["forecast"]))
        for k in new:
            audit(iid, f"Cost: FY{fy}", k, "", new[k])
    touch(iid)
    flash(f"Cost figures for FY{fy} saved.", "success")
    return back(iid, "cost")


# ------------------------------------------------------------------ timeline
def _phase_checks(ps, pe, fs, fe, as_, ae, status, errors):
    for a, b, label in ((ps, pe, "planned"), (fs, fe, "forecast"), (as_, ae, "actual")):
        if a and b and b < a:
            errors.append(f"The {label} end date cannot be before the {label} start date.")
    if status == "Complete" and not ae:
        errors.append("Enter an actual end date for a phase marked Complete.")


@app.post("/investments/<int:iid>/timeline/add")
def add_phase(iid):
    inv = get_inv(iid)
    if not perms(inv)["can_edit"]:
        return deny(iid, "timeline")
    errors = []
    name = form_str("name")
    if not name:
        errors.append("Enter a phase name.")
    ps = form_date("planned_start", errors, "the planned start date")
    pe = form_date("planned_end", errors, "the planned end date")
    _phase_checks(ps, pe, None, None, None, None, "", errors)
    if errors:
        return fail(errors, iid, "timeline")
    pos = row("SELECT COALESCE(MAX(position),0)+1 n FROM phases WHERE investment_id=?", (iid,))["n"]
    run("INSERT INTO phases (investment_id,position,name,planned_start,planned_end,forecast_start,forecast_end,status) "
        "VALUES (?,?,?,?,?,?,?,'Not started')", (iid, pos, name, ps, pe, ps, pe))
    audit(iid, f"Phase: {name}", "added", "", f"{f_dmy(ps)} to {f_dmy(pe)}")
    touch(iid)
    flash("Phase added.", "success")
    return back(iid, "timeline")


@app.post("/investments/<int:iid>/timeline/defaults")
def add_default_phases(iid):
    inv = get_inv(iid)
    if not perms(inv)["can_edit"]:
        return deny(iid, "timeline")
    errors = []
    start = form_date("start_date", errors, "the project start date")
    if row("SELECT 1 FROM phases WHERE investment_id=?", (iid,)):
        errors.append("Default phases can only be added when the investment has no phases yet.")
    if errors:
        return fail(errors, iid, "timeline")
    cur = pd(start)
    for i, (name, days) in enumerate(zip(logic.PHASE_NAMES, logic.DEFAULT_PHASE_DAYS), start=1):
        s, e = cur.isoformat(), (cur + (date.resolution * days)).isoformat()
        run("INSERT INTO phases (investment_id,position,name,planned_start,planned_end,forecast_start,forecast_end,"
            "status) VALUES (?,?,?,?,?,?,?,'Not started')", (iid, i, name, s, e, s, e))
        audit(iid, f"Phase: {name}", "added", "", f"{f_dmy(s)} to {f_dmy(e)}")
        cur = cur + date.resolution * days
    touch(iid)
    flash("Default phases added. Adjust the dates as needed.", "success")
    return back(iid, "timeline")


@app.post("/investments/<int:iid>/timeline/<int:pid>/save")
def save_phase(iid, pid):
    inv = get_inv(iid)
    p = perms(inv)
    ph = row("SELECT * FROM phases WHERE id=? AND investment_id=?", (pid, iid))
    if not ph:
        abort(404)
    can_planned = p["can_edit"]
    can_fore = p["can_edit"] or p["can_track"]
    if not can_fore:
        return deny(iid, "timeline")
    errors = []
    v = {k: ph[k] for k in ("planned_start", "planned_end", "forecast_start", "forecast_end",
                            "actual_start", "actual_end", "status")}
    label = {"planned_start": "the planned start date", "planned_end": "the planned end date",
             "forecast_start": "the forecast start date", "forecast_end": "the forecast end date"}
    if can_planned:
        for k in ("planned_start", "planned_end"):
            v[k] = form_date(k, errors, label[k])
    for k in ("forecast_start", "forecast_end"):
        v[k] = form_date(k, errors, label[k])
    for k in ("actual_start", "actual_end"):
        v[k] = form_date(k, errors, k.replace("_", " ") + " date", required=False)
    status = form_str("status")
    if status not in logic.PHASE_STATUSES:
        errors.append("Choose a status for the phase.")
    v["status"] = status
    if not errors:
        _phase_checks(v["planned_start"], v["planned_end"], v["forecast_start"], v["forecast_end"],
                      v["actual_start"], v["actual_end"], status, errors)
    if errors:
        return fail([f"{ph['name']}: {e}" for e in errors], iid, "timeline")
    for k, new in v.items():
        audit(iid, f"Phase: {ph['name']}", k, ph[k], new)
    run("UPDATE phases SET planned_start=?, planned_end=?, forecast_start=?, forecast_end=?, actual_start=?, "
        "actual_end=?, status=? WHERE id=?",
        (v["planned_start"], v["planned_end"], v["forecast_start"], v["forecast_end"], v["actual_start"],
         v["actual_end"], v["status"], pid))
    touch(iid)
    updated = phases_of(iid)
    r = logic.investment_rag(updated)
    flash(f"{ph['name']} saved. Current phase RAG: {r['current']['rag']}; go-live RAG: {r['golive']['rag']}.",
          "success")
    return back(iid, "timeline")


@app.post("/investments/<int:iid>/timeline/<int:pid>/delete")
def delete_phase(iid, pid):
    inv = get_inv(iid)
    if not perms(inv)["can_edit"]:
        return deny(iid, "timeline")
    ph = row("SELECT * FROM phases WHERE id=? AND investment_id=?", (pid, iid))
    if ph:
        run("DELETE FROM resources WHERE phase_id=?", (pid,))
        run("DELETE FROM phases WHERE id=?", (pid,))
        audit(iid, f"Phase: {ph['name']}", "removed", f"{f_dmy(ph['planned_start'])} to {f_dmy(ph['planned_end'])}", "")
        touch(iid)
        flash("Phase and its resource demand removed.", "success")
    return back(iid, "timeline")


# ------------------------------------------------------------------ capacity
@app.post("/investments/<int:iid>/capacity/add")
def add_resource(iid):
    inv = get_inv(iid)
    if not perms(inv)["can_edit"]:
        return deny(iid, "capacity")
    errors = []
    pid = request.form.get("phase_id", type=int)
    ph = row("SELECT * FROM phases WHERE id=? AND investment_id=?", (pid, iid)) if pid else None
    if not ph:
        errors.append("Choose a phase.")
    role = form_str("role")
    if role not in logic.ROLES:
        errors.append("Choose a role.")
    ftes = form_num("ftes", errors, "the FTEs required", minimum=0.01)
    if errors:
        return fail(errors, iid, "capacity")
    run("INSERT INTO resources (investment_id,phase_id,role,ftes) VALUES (?,?,?,?)", (iid, pid, role, ftes))
    audit(iid, f"Resource: {ph['name']}", role, "", f"{sv(ftes)} FTE")
    touch(iid)
    g.pop("cap", None)
    mine = [o for o in get_capacity()["over"] if o["role"] == role and any(i == iid for i, _, _ in o["investments"])]
    if mine:
        months = ", ".join(o["month"].strftime("%m/%Y") for o in mine)
        flash(f"Warning: this demand causes over-allocation of {role} in {months}. See the capacity report below.",
              "warning")
    else:
        flash("Resource demand added.", "success")
    return back(iid, "capacity")


@app.post("/investments/<int:iid>/capacity/<int:rid>/delete")
def delete_resource(iid, rid):
    inv = get_inv(iid)
    if not perms(inv)["can_edit"]:
        return deny(iid, "capacity")
    r = row("SELECT r.*, p.name AS phase_name FROM resources r JOIN phases p ON p.id=r.phase_id "
            "WHERE r.id=? AND r.investment_id=?", (rid, iid))
    if r:
        run("DELETE FROM resources WHERE id=?", (rid,))
        audit(iid, f"Resource: {r['phase_name']}", r["role"], f"{sv(r['ftes'])} FTE", "")
        touch(iid)
        flash("Resource demand removed.", "success")
    return back(iid, "capacity")


@app.route("/capacity", methods=["GET", "POST"])
def capacity_pool():
    if request.method == "POST":
        if g.user["grp"] != "pmo":
            flash("Only the PMO / portfolio team can edit the capacity pool.", "error")
            return redirect(url_for("capacity_pool"))
        errors, new = [], {}
        for role in logic.ROLES:
            new[role] = form_num(f"pool_{role}", errors, f"the FTEs available for {role}", minimum=0)
        if errors:
            for e in errors:
                flash(e, "error")
            return redirect(url_for("capacity_pool"))
        old = {r["role"]: r["ftes"] for r in rows("SELECT * FROM capacity_pool")}
        for role, v in new.items():
            audit(None, "Capacity pool", role, old.get(role, ""), v)
            run("INSERT INTO capacity_pool (role, ftes) VALUES (?,?) ON CONFLICT(role) DO UPDATE SET ftes=excluded.ftes",
                (role, v))
        flash("Capacity pool saved.", "success")
        return redirect(url_for("capacity_pool"))
    cap = get_capacity()
    return render_template("capacity.html", cap=cap, pool=cap["pool"], can_edit=g.user["grp"] == "pmo",
                           roles=logic.ROLES)


# ------------------------------------------------------------------ realisation
@app.post("/investments/<int:iid>/realisation/measurement")
def add_measurement(iid):
    inv = get_inv(iid)
    if not perms(inv)["can_track"]:
        return deny(iid, "realisation")
    errors = []
    mid = request.form.get("metric_id", type=int)
    m = row("SELECT * FROM metrics WHERE id=? AND investment_id=?", (mid, iid)) if mid else None
    if not m:
        errors.append("Choose a metric.")
    dt = form_date("date", errors, "the measurement date")
    val = form_num("value", errors, "the measured value")
    if errors:
        return fail(errors, iid, "realisation")
    run("INSERT INTO measurements (metric_id,date,value) VALUES (?,?,?)", (mid, dt, val))
    audit(iid, f"Measurement: {m['name']}", "value", "", f"{sv(val)} on {f_dmy(dt)}")
    touch(iid)
    status = next(x for x in metrics_for(iid) if x["m"]["id"] == mid)["status"]
    flash(f"Measurement recorded. {m['name']} is now: {status}.", "success")
    return back(iid, "realisation")


@app.post("/investments/<int:iid>/realisation/financial/<int:bid>")
def save_realised(iid, bid):
    inv = get_inv(iid)
    if not perms(inv)["can_realise_fin"]:
        return deny(iid, "realisation")
    b = row("SELECT * FROM fin_benefits WHERE id=? AND investment_id=?", (bid, iid))
    if not b:
        abort(404)
    errors = []
    val = form_num("realised", errors, "the realised amount in euro", minimum=0)
    if errors:
        return fail(errors, iid, "realisation")
    audit(iid, f"Realisation: {b['description']}", "realised amount", b["realised_amount"], val)
    run("UPDATE fin_benefits SET realised_amount=? WHERE id=?", (val, bid))
    touch(iid)
    flash("Realised amount saved.", "success")
    return back(iid, "realisation")


@app.post("/investments/<int:iid>/realisation/review/<int:rid>")
def save_review(iid, rid):
    inv = get_inv(iid)
    if not perms(inv)["can_track"]:
        return deny(iid, "realisation")
    r = row("SELECT * FROM reviews WHERE id=? AND investment_id=?", (rid, iid))
    if not r:
        abort(404)
    errors = []
    rd = form_date("review_date", errors, "the review date")
    reviewer = request.form.get("reviewer_id", type=int)
    if not reviewer or not row("SELECT 1 FROM users WHERE id=?", (reviewer,)):
        errors.append("Choose a reviewer.")
    findings, lessons = form_str("findings"), form_str("lessons")
    if errors:
        return fail(errors, iid, "realisation")
    area = f"Post-implementation review ({r['months_after']} months)"
    audit(iid, area, "review date", r["review_date"], rd)
    audit(iid, area, "reviewer", r["reviewer_id"], reviewer)
    audit(iid, area, "findings", r["findings"], findings)
    audit(iid, area, "lessons learned", r["lessons"], lessons)
    run("UPDATE reviews SET review_date=?, reviewer_id=?, findings=?, lessons=? WHERE id=?",
        (rd, reviewer, findings, lessons, rid))
    touch(iid)
    flash("Post-implementation review saved.", "success")
    return back(iid, "realisation")


# ------------------------------------------------------------------ approval workflow
@app.post("/investments/<int:iid>/submit")
def submit(iid):
    inv = get_inv(iid)
    if not perms(inv)["can_edit"]:
        return deny(iid, "overview")
    errors = []
    if not row("SELECT 1 FROM metrics WHERE investment_id=?", (iid,)):
        errors.append("Add at least one quantified metric on the Value tab before submitting.")
    if not row("SELECT 1 FROM phases WHERE investment_id=?", (iid,)):
        errors.append("Add at least one phase on the Timeline tab before submitting.")
    if not row("SELECT 1 FROM costs WHERE investment_id=?", (iid,)):
        errors.append("Enter cost figures on the Cost tab before submitting.")
    if errors:
        flash("This investment cannot be submitted yet.", "error")
        return fail(errors, iid, "overview")
    stage = inv["current_stage"] if inv["status"] == "Returned for rework" and inv["current_stage"] else 1
    run("UPDATE approvals SET status='Pending', decision_date=NULL, comments='', conditions='' "
        "WHERE investment_id=? AND stage=?", (iid, stage))
    run("UPDATE investments SET status='In approval', current_stage=?, stage_entered=? WHERE id=?",
        (stage, today().isoformat(), iid))
    audit(iid, "Investment", "status", inv["status"], "In approval")
    touch(iid)
    flash(f"Submitted. The investment is now waiting at stage {stage}: {STAGE_NAMES[stage]}.", "success")
    return back(iid, "approval")


@app.post("/investments/<int:iid>/decide")
def decide(iid):
    inv = get_inv(iid)
    if not perms(inv)["can_decide"]:
        flash("Only the named approver for the current stage can record a decision, and only while the "
              "investment is in approval.", "error")
        return back(iid, "approval")
    decision = form_str("decision")
    comments, conditions = form_str("comments"), form_str("conditions")
    outcome = {"approve": "Approved", "reject": "Rejected", "return": "Returned for rework"}.get(decision)
    if not outcome:
        return fail(["Choose a decision: approve, reject or return for rework."], iid, "approval")
    if outcome != "Approved" and not comments:
        return fail([f"Enter comments explaining why you are choosing to "
                     f"{'reject' if outcome == 'Rejected' else 'return this for rework'}."], iid, "approval")
    stage = inv["current_stage"]
    name = STAGE_NAMES[stage]
    u = g.user
    run("UPDATE approvals SET status=?, approver_id=?, decision_date=?, comments=?, conditions=? "
        "WHERE investment_id=? AND stage=?", (outcome, u["id"], today().isoformat(), comments, conditions, iid, stage))
    run("INSERT INTO approval_history (investment_id,stage,stage_name,approver_id,approver_name,decision,"
        "decision_date,comments,conditions) VALUES (?,?,?,?,?,?,?,?,?)",
        (iid, stage, name, u["id"], u["name"], outcome, today().isoformat(), comments, conditions))
    audit(iid, f"Approval: {name}", "decision", "Pending", outcome)
    if outcome == "Approved":
        if stage < 5:
            run("UPDATE approvals SET status='Pending' WHERE investment_id=? AND stage=?", (iid, stage + 1))
            run("UPDATE investments SET current_stage=?, stage_entered=? WHERE id=?",
                (stage + 1, today().isoformat(), iid))
            flash(f"Approved. The investment moves to stage {stage + 1}: {STAGE_NAMES[stage + 1]}.", "success")
        else:
            run("UPDATE investments SET status='Approved', current_stage=NULL, stage_entered=NULL WHERE id=?", (iid,))
            audit(iid, "Investment", "status", "In approval", "Approved")
            for months in (6, 12):
                if not row("SELECT 1 FROM reviews WHERE investment_id=? AND months_after=?", (iid, months)):
                    run("INSERT INTO reviews (investment_id, months_after) VALUES (?,?)", (iid, months))
            flash("Final approval recorded. The investment is now Approved.", "success")
    elif outcome == "Rejected":
        run("UPDATE investments SET status='Rejected' WHERE id=?", (iid,))
        audit(iid, "Investment", "status", "In approval", "Rejected")
        flash("Investment rejected.", "success")
    else:
        run("UPDATE investments SET status='Returned for rework' WHERE id=?", (iid,))
        audit(iid, "Investment", "status", "In approval", "Returned for rework")
        flash("Investment returned to the owner for rework.", "success")
    touch(iid)
    return back(iid, "approval")


# ------------------------------------------------------------------ audit log
@app.route("/audit")
def audit_log():
    f_inv = request.args.get("investment", "")
    f_user = request.args.get("user", "")
    f_q = request.args.get("q", "").strip()
    sql = ("SELECT a.*, i.name AS inv_name FROM audit a LEFT JOIN investments i ON i.id=a.investment_id WHERE 1=1")
    args = []
    if f_inv == "none":
        sql += " AND a.investment_id IS NULL"
    elif f_inv:
        sql += " AND a.investment_id=?"
        args.append(f_inv)
    if f_user:
        sql += " AND a.user_id=?"
        args.append(f_user)
    if f_q:
        sql += " AND (a.area LIKE ? OR a.field LIKE ? OR a.old_value LIKE ? OR a.new_value LIKE ?)"
        args += [f"%{f_q}%"] * 4
    sql += " ORDER BY a.ts DESC, a.id DESC LIMIT 500"
    return render_template("audit.html", entries=rows(sql, args), f_inv=f_inv, f_user=f_user, f_q=f_q,
                           invs=rows("SELECT id, name FROM investments ORDER BY name"),
                           users=rows("SELECT id, name FROM users ORDER BY name"))


if __name__ == "__main__":
    app.run(debug=True)
