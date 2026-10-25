"""The ordinary work of the billing office: legal decisions, paid bills, placements, live applications."""

from __future__ import annotations

import random
from datetime import date, timedelta

import pools
import rules as R
from build import PROOF_LABEL, Builder, income_for_pct, pick, rday, title
from world import HISTORY_END, LIVE_START, WORLD_END, clamp

D25 = date(2025, 1, 1)
NEW_POLICY = date(2025, 7, 1)
LAST_HISTORY_DECISION = date(2026, 6, 26)

COUNTS = {
    "H_FREE": 400, "H_DISCOUNT": 250, "H_DENIED": 120, "H_MEDICAL": 40, "H_HOMELESS": 25, "H_CLOSED": 60,
    "H_NOAPP": 520, "L_FREE": 95, "L_MEDICAL": 9, "L_HOMELESS": 6, "L_DISCOUNT": 60, "L_PLAN": 50,
    "L_NOWORK": 95,
}


def counselor(rng, day: date) -> str:
    if day < NEW_POLICY:
        return pick(rng, [("S-005", 30), ("S-006", 30), ("S-001", 30), ("S-004", 10)])
    return pick(rng, [("S-001", 35), ("S-004", 35), ("S-005", 15), ("S-006", 15)])


def note_staff(rng) -> str:
    return rng.choice(pools.ACCESS_STAFF + pools.BILLING_STAFF[:3])


REASONS = {
    "FREE": ["approved 100% charity - income under 200% FPL", "Approved full charity per FAP. verified w/ {proof}",
             "100% adj approved", "free care approved, {pct}% FPL", "APPROVED - FULL CHARITY", "ok'd 100% charity care",
             "approved charity 100pct, hh {hh}"],
    "DISCOUNT": ["approved discount - pt pays 30%", "partial charity 70% adj, income 200-400% FPL",
                 "Discount approved per FAP sliding scale", "approved disc. pt resp 30 pct",
                 "DISCOUNT APPROVED {pct}% FPL", "70% discount ok'd"],
    "DENIED": ["denied - over income (>400% FPL), payment plan offered", "Over income limit. Offered 12 mo plan",
               "income above 400% fpl - denied, offered pmt plan", "DENIED OVER INCOME", "over 400% - not eligible, plan offered",
               "denied: income {pct}% FPL. 12 month plan offered"],
    "MEDICAL": ["approved - active Medi-Cal, no income docs needed", "Medi-Cal active - presumptive 100% charity",
                "approved full charity (Medi-Cal)", "MEDI-CAL ELIGIBLE - 100% ADJ"],
    "HOMELESS": ["homeless - approved full charity w/o income docs", "pt homeless per shelter letter, approved 100%",
                 "approved 100% - no fixed address", "APPROVED - HOMELESS"],
    "CLOSED": ["closed - no docs received after 2 requests", "incomplete app, closed after 60 days",
               "closed - pt never sent income proof", "CLOSED INCOMPLETE", "no response to info request - closed"],
    "NEEDS_INFO": ["need pay stubs", "missing income proof - letter sent", "pending docs", "need proof of income, mailed request",
                   "waiting on income documents"],
}


def reason_text(rng, kind, pct=None, proof="", hh=None) -> str:
    t = rng.choice(REASONS[kind])
    return t.format(pct=f"{pct:.0f}" if pct is not None else "", proof=PROOF_LABEL.get(proof, "docs"), hh=hh)


def gap_days(rng) -> int:
    r = rng.random()
    if r < 0.40:
        return rng.randint(5, 30)
    if r < 0.75:
        return rng.randint(30, 90)
    return rng.randint(90, 200)


# ---------------------------------------------------------------------- history


def history_fa_case(b: Builder, rng: random.Random, kind: str, files: bool) -> dict:
    """One person who applied in history and got a legal decision (or closed incomplete)."""
    homeless = kind == "HOMELESS"
    age = (66, 88) if (kind == "DENIED" and rng.random() < 0.1) else (19, 80)
    person = b.new_person(rng, homeless=homeless, age=age)
    if homeless:
        if rng.random() < 0.5:
            person.addr = {"line1": "HOMELESS", "fa_line1": "Homeless", "city": "HALCYON BAY", "state": "CA",
                           "zip": "95081"}
        else:
            line, city, z = rng.choice(pools.SHELTERS)
            person.addr = {"line1": line, "fa_line1": title(line), "city": city, "state": "CA", "zip": z}
    service = rday(rng, date(2024, 11, 1), date(2026, 3, 25))
    reg = service if rng.random() < 0.6 else rday(rng, date(2012, 1, 1), service - timedelta(days=60))
    patient = b.register(rng, person, reg)
    payer = "SELF PAY" if homeless else None
    if kind == "MEDICAL":
        payer = rng.choice(["SELF PAY", "MEDI-CAL"])
    elif payer is None:
        payer = pick(rng, [("SELF PAY", 60), ("BLUE PACIFIC PPO", 12), ("GOLDEN STATE HEALTH HMO", 10),
                           ("COASTAL CARE PLAN", 6), ("MEDICARE", 12)])
    acc = b.visit(rng, patient, service, payer=payer)
    accounts = [acc]
    max_gap = (LAST_HISTORY_DECISION - acc.fsd).days - 45
    gap = max(5, min(gap_days(rng), max_gap))
    received = acc.fsd + timedelta(days=gap)
    if rng.random() < 0.13 and (received - service).days > 50:
        s2 = rday(rng, service + timedelta(days=20), received - timedelta(days=30))
        a2 = b.visit(rng, patient, s2, payer=payer, stype=rng.choice(["ER", "CLINIC", "OUTPATIENT"]))
        if a2.fsd < received:
            accounts.append(a2)
    if rng.random() < 0.10:
        pday = rday(rng, acc.fsd + timedelta(days=3), received - timedelta(days=1))
        if pday > acc.fsd:
            b.pay(acc, pday, min(rng.randint(25, 200) * 100, acc.f["patient_responsibility"] // 2))
    needs_info = kind == "CLOSED" or (kind in ("FREE", "DISCOUNT", "DENIED") and rng.random() < 0.3)
    if needs_info:
        ni_day = received + timedelta(days=rng.randint(2, 7))
        docs_day = ni_day + timedelta(days=rng.randint(5, 25))
        decision = docs_day + timedelta(days=rng.randint(1, 7))
    else:
        ni_day = None
        docs_day = received + timedelta(days=rng.choice([0, 0, 0, 1, 2, 3]))
        decision = docs_day + timedelta(days=rng.randint(2, 18))
    if kind in ("MEDICAL", "HOMELESS"):
        docs_day = received
        decision = received + timedelta(days=rng.randint(1, 10))
    if kind == "CLOSED":
        decision = ni_day + timedelta(days=rng.randint(45, 75))
    if decision < date(2025, 1, 6):
        decision = date(2025, 1, 6) + timedelta(days=rng.randint(0, 20))
        docs_day = min(docs_day, decision)
    decision = min(decision, LAST_HISTORY_DECISION)
    year = decision.year
    hh = person.household
    info = {"person": person, "patient": patient, "accounts": accounts, "kind": kind}

    form = "2020" if received < NEW_POLICY or rng.random() < 0.04 else "2025"
    assets = None
    if form == "2020" and rng.random() < 0.8:
        assets = rng.choice([0, 0, 150, 400, 900, 1500, 2200, 3500, 5000, 7200]) + rng.randint(0, 99)
    medi = "Y" if kind == "MEDICAL" else "N"
    hl = "Y" if homeless else "N"

    if kind in ("FREE", "DISCOUNT", "DENIED"):
        lo, hi = {"FREE": (22, 190), "DISCOUNT": (210, 390), "DENIED": (412, 820)}[kind]
        pct_t = rng.uniform(lo, hi)
        target = income_for_pct(pct_t, hh, year)
        if decision < NEW_POLICY:
            proof = pick(rng, [("PAY_STUBS", 88), ("TAX_RETURN", 4), ("EMPLOYER_LETTER", 4), ("BENEFIT_LETTER", 4)])
        else:
            proof = pick(rng, [("PAY_STUBS", 66), ("TAX_RETURN", 10), ("EMPLOYER_LETTER", 9), ("BENEFIT_LETTER", 8),
                               ("SELF_ATTESTATION", 7)])
        if proof in ("SELF_ATTESTATION", "BENEFIT_LETTER") and kind != "FREE":
            proof = "PAY_STUBS"
        app = b.application(rng, person, patient, accounts, received, household=hh, income_stated=None,
                            form=form, assets=assets, medi_cal=medi, homeless=hl)
        truth = b.income_docs(rng, app, person, proof, target, docs_day, files=files, bank=rng.random() < 0.3)
        pct = truth / R.poverty_line(year, hh)
        outcome = R.band(pct)
        stated = round(truth / 100 * rng.uniform(0.96, 1.02) / 100) * 100
        app.snap(received, income_stated=stated if rng.random() < 0.93 else "")
        if needs_info:
            b.decide(app, ni_day, "NEEDS_INFO", "", "", reason_text(rng, "NEEDS_INFO"))
            if rng.random() < 0.6:
                b.w.note(ni_day, counselor(rng, ni_day), rng.choice([
                    "Mailed request for proof of income. 30 days to respond.",
                    "LVM for pt re: missing pay stubs.", "Called pt, will bring stubs next week.",
                    "Sent missing info letter.",
                ]), app=app)
        by = counselor(rng, decision)
        dec = {"FREE": "FREE", "DISCOUNT": "DISCOUNT", "PAYMENT_PLAN": "DENIED"}[outcome]
        kind_txt = {"FREE": "FREE", "DISCOUNT": "DISCOUNT", "PAYMENT_PLAN": "DENIED"}[outcome]
        b.decide(app, decision, "APPROVED" if dec != "DENIED" else "DENIED", dec, by,
                 reason_text(rng, kind_txt, pct, proof, hh), verified=round(truth / 100),
                 proof=proof)
        info.update(app=app, outcome=outcome, pct=pct, decision=decision, by=by, proof=proof, truth=truth)
        if rng.random() < 0.45:
            b.w.note(decision, by, decision_note(rng, outcome, pct, proof), app=app)
        post_decision(b, rng, info)
    elif kind in ("MEDICAL", "HOMELESS"):
        app = b.application(rng, person, patient, accounts, received, household=hh, income_stated=None, form=form,
                            assets=None, medi_cal=medi, homeless=hl)
        if files or rng.random() < 0.5:
            if kind == "MEDICAL":
                from docs import benefit_letter
                b.w.doc(app, docs_day, "BENEFIT_LETTER", f"{title(person.first)} {title(person.last)}",
                        benefit_letter(rng, kind="MEDI_CAL", name=f"{title(person.first)} {title(person.last)}",
                                       household=None, amount_cents=None,
                                       letter_date=received - timedelta(days=rng.randint(5, 120)), county="SANTA LUCITA",
                                       received=docs_day))
            elif person.addr["line1"] != "HOMELESS":
                from docs import shelter_letter
                b.w.doc(app, docs_day, "OTHER", f"{title(person.first)} {title(person.last)}",
                        shelter_letter(rng, shelter=person.addr["line1"], name=f"{title(person.first)} {title(person.last)}",
                                       since=received - timedelta(days=rng.randint(30, 400)),
                                       letter_date=received - timedelta(days=rng.randint(1, 10)), received=docs_day))
        by = counselor(rng, decision)
        b.decide(app, decision, "APPROVED", "FREE", by, reason_text(rng, kind), proof="NONE")
        info.update(app=app, outcome="FREE", pct=None, decision=decision, by=by, proof="NONE", truth=None)
        if rng.random() < 0.5:
            b.w.note(decision, by, "Medi-Cal confirmed active in eligibility portal, approved 100%." if kind == "MEDICAL"
                     else "Pt staying at shelter / no address. Approved full charity, no income docs needed.", app=app)
        post_decision(b, rng, info)
    else:  # CLOSED incomplete
        app = b.application(rng, person, patient, accounts, received, household=hh,
                            income_stated=rng.choice([None, round(rng.uniform(12, 60)) * 1000]), form=form,
                            assets=assets, medi_cal="N", homeless="N")
        b.decide(app, ni_day, "NEEDS_INFO", "", "", reason_text(rng, "NEEDS_INFO"))
        by = counselor(rng, decision)
        b.decide(app, decision, "CLOSED", "", by, reason_text(rng, "CLOSED"))
        if rng.random() < 0.5:
            b.w.note(ni_day + timedelta(days=rng.randint(10, 30)), by,
                     rng.choice(["2nd request for income docs mailed.", "LVM x2, no call back.",
                                 "Pt said will send stubs, nothing received."]), app=app)
        info.update(app=app, outcome="CLOSED", pct=None, decision=decision, by=by, proof="", truth=None)
        unpaid_flow(b, rng, accounts, allow_place=True, screened=True)
    return info


def decision_note(rng, outcome, pct, proof) -> str:
    p = f"{pct:.0f}" if pct is not None else "?"
    if outcome == "FREE":
        return rng.choice([f"Verified income from {PROOF_LABEL[proof]}, {p}% FPL. Approved 100%, letter mailed.",
                           f"Approval letter sent. {p}% of FPL.", "Approved free care, adj posted."])
    if outcome == "DISCOUNT":
        return rng.choice([f"{p}% FPL - discount approved, pt owes 30%. Letter mailed.",
                           "Discount approved. Pt to pay balance or set up plan."])
    return rng.choice([f"Income {p}% FPL, over limit. Denial letter mailed with payment plan offer.",
                       "Over 400%. Explained 12 month interest free plan option to pt."])


def post_decision(b: Builder, rng, info: dict) -> None:
    """What happens to the bill after a legal decision."""
    outcome = info["outcome"]
    day = info["decision"] + timedelta(days=rng.randint(0, 3))
    accounts = info["accounts"]
    patient = info["patient"]
    if outcome == "FREE":
        for a in accounts:
            b.apply_fa(a, day, "FREE", rng)
        return
    if outcome == "DISCOUNT":
        for a in accounts:
            b.apply_fa(a, day, "DISCOUNT", rng)
        r = rng.random()
        owed = sum(b.w.balance(a, day) for a in accounts)
        if owed <= 0:
            return
        if r < 0.62:
            pay_day = day + timedelta(days=rng.randint(10, 45))
            for a in accounts:
                bal = b.w.balance(a, pay_day)
                if bal > 0 and pay_day <= WORLD_END:
                    b.pay(a, pay_day, bal)
                    b.status(a, pay_day, "PAID")
        elif r < 0.85:
            plan = b.run_plan(rng, patient, accounts, day + timedelta(days=rng.randint(3, 15)))
            info["plan"] = plan
        else:
            unpaid_flow(b, rng, accounts, allow_place=True, screened=True, after=day)
        return
    # DENIED over income: a payment plan is offered
    r = rng.random()
    if r < 0.55:
        miss = None
        if rng.random() < 0.1:
            miss = {rng.randint(2, 6)}
        plan = b.run_plan(rng, patient, accounts, day + timedelta(days=rng.randint(3, 15)), miss_at=miss)
        info["plan"] = plan
    elif r < 0.80:
        pay_day = day + timedelta(days=rng.randint(7, 40))
        for a in accounts:
            bal = b.w.balance(a, pay_day)
            if bal > 0 and pay_day <= WORLD_END:
                b.pay(a, pay_day, bal)
                b.status(a, pay_day, "PAID")
    else:
        unpaid_flow(b, rng, accounts, allow_place=True, screened=True, after=day)


def unpaid_flow(b: Builder, rng, accounts, *, allow_place: bool, screened: bool, after: date | None = None) -> None:
    """An unpaid balance: placed with the agency once it is old enough, else paid."""
    for a in accounts:
        earliest = a.fsd + timedelta(days=rng.randint(125, 175))
        if after:
            earliest = max(earliest, after + timedelta(days=rng.randint(30, 60)))
        if allow_place and earliest <= HISTORY_END - timedelta(days=5):
            pl = b.place(rng, a, earliest, notice=rng.random() < 0.7)
            agency_life(b, rng, pl)
        else:
            pay_day = (after or a.fsd) + timedelta(days=rng.randint(10, 40))
            bal = b.w.balance(a, pay_day)
            if bal > 0:
                b.pay(a, min(pay_day, HISTORY_END), bal)
                b.status(a, min(pay_day, HISTORY_END), "PAID")


def agency_life(b: Builder, rng, pl) -> None:
    """What Golden Coast Recovery reports back on a placement during history."""
    placed = pl.f["placed_date"]
    r = rng.random()
    pl.snap(placed + timedelta(days=rng.randint(3, 10)), last_activity="letter 1 mailed to debtor")
    if r < 0.18:
        d1 = placed + timedelta(days=rng.randint(30, 120))
        if d1 <= HISTORY_END:
            amt = pl.f["current_balance"] * rng.randint(15, 45) // 100
            b.agency_collect(rng, pl, d1, amt)
    elif r < 0.25:
        d1 = placed + timedelta(days=rng.randint(30, 150))
        if d1 <= HISTORY_END:
            b.agency_collect(rng, pl, d1, pl.f["current_balance"], full=True)
    elif r < 0.33:
        d1 = placed + timedelta(days=rng.randint(200, 320))
        if d1 <= HISTORY_END:
            pl.snap(d1, status="CLOSED", last_activity="closed - unable to locate debtor, returned to client")
    else:
        d1 = placed + timedelta(days=rng.randint(40, 90))
        if d1 <= HISTORY_END:
            pl.snap(d1, last_activity=rng.choice(["skip trace in progress", "no contact - letter 2 sent",
                                                  "debtor disputes balance, sent itemization",
                                                  "called debtor, no pickup, LVM"]))


def history_noapp(b: Builder, rng, pool_paid: list) -> None:
    """Visits with no application: most are paid, unpaid self-pay balances go to the agency."""
    person, patient = None, None
    if pool_paid and rng.random() < 0.12:
        person, patient = rng.choice(pool_paid)
        lo = max(date(2024, 11, 1), patient.f["registered_on"] + timedelta(days=10))
        if lo > date(2026, 5, 31):
            person, patient = None, None
    if person is None:
        person = b.new_person(rng)
        lo = date(2024, 11, 1)
    service = rday(rng, lo, date(2026, 5, 31))
    if patient is None:
        reg = service if rng.random() < 0.6 else rday(rng, date(2010, 1, 1), service - timedelta(days=30))
        patient = b.register(rng, person, reg)
    payer = pick(rng, [("SELF PAY", 42), ("BLUE PACIFIC PPO", 18), ("GOLDEN STATE HEALTH HMO", 15),
                       ("COASTAL CARE PLAN", 8), ("MEDICARE", 12), ("MEDI-CAL", 5)])
    stype = pick(rng, [("ER", 45), ("CLINIC", 28), ("OUTPATIENT", 22), ("INPATIENT", 5)])
    acc = b.visit(rng, patient, service, payer=payer, stype=stype)
    old_enough = acc.fsd <= date(2026, 2, 15)
    if payer == "SELF PAY" and old_enough and (stype == "INPATIENT" or rng.random() < 0.55):
        if rng.random() < 0.25:
            b.pay(acc, acc.fsd + timedelta(days=rng.randint(10, 60)),
                  min(rng.randint(20, 150) * 100, acc.f["patient_responsibility"] // 2))
        unpaid_flow(b, rng, [acc], allow_place=True, screened=False)
    elif payer != "SELF PAY" and old_enough and rng.random() < 0.12:
        unpaid_flow(b, rng, [acc], allow_place=True, screened=False)
    else:
        pay_day = acc.fsd + timedelta(days=rng.randint(4, 40))
        if pay_day > HISTORY_END:
            pay_day = acc.fsd + timedelta(days=rng.randint(1, 3))
        if rng.random() < 0.2 and pay_day + timedelta(days=30) <= min(HISTORY_END, acc.fsd + timedelta(days=80)):
            half = b.w.balance(acc, pay_day) // 2
            b.pay(acc, pay_day, half)
            pay_day += timedelta(days=30)
        b.pay(acc, pay_day, b.w.balance(acc, pay_day))
        b.status(acc, pay_day, "PAID")
        pool_paid.append((person, patient))


# ------------------------------------------------------------------------- live


def live_timeline(b: Builder, rng, patient, *, recent_share=0.35, stype=None, payer=None):
    """A visit whose bill lands so that an application can arrive during the live window."""
    if rng.random() < recent_share:
        service = rday(rng, date(2026, 3, 1), date(2026, 6, 12))
    else:
        service = rday(rng, date(2026, 6, 25), date(2026, 8, 31))
    stype = stype or pick(rng, [("ER", 47), ("OUTPATIENT", 20), ("CLINIC", 18), ("INPATIENT", 15)])
    if stype == "INPATIENT" and service > date(2026, 8, 20):
        service = service - timedelta(days=15)
    acc = b.visit(rng, patient, service, stype=stype, payer=payer)
    earliest = max(acc.fsd + timedelta(days=5), LIVE_START)
    latest = min(acc.fsd + timedelta(days=200), WORLD_END - timedelta(days=2))
    received = earliest + timedelta(days=rng.randint(0, max(0, min(40, (latest - earliest).days))))
    return acc, received


def live_clear_case(b: Builder, rng, kind: str, pool_paid: list) -> dict:
    """A live application with clear documents: FREE, DISCOUNT or PAYMENT_PLAN, or Medi-Cal / homeless."""
    homeless = kind == "HOMELESS"
    returning = pool_paid and rng.random() < 0.12 and kind not in ("HOMELESS",)
    if returning:
        person, patient = pool_paid.pop(rng.randrange(len(pool_paid)))
    else:
        person = b.new_person(rng, homeless=homeless)
        patient = None
        if homeless:
            if rng.random() < 0.5:
                person.addr = {"line1": "HOMELESS", "fa_line1": "Homeless", "city": "HALCYON BAY", "state": "CA",
                               "zip": "95081"}
            else:
                line, city, z = rng.choice(pools.SHELTERS)
                person.addr = {"line1": line, "fa_line1": title(line), "city": city, "state": "CA", "zip": z}
    payer = "SELF PAY" if kind in ("HOMELESS",) else None
    if kind == "MEDICAL":
        payer = rng.choice(["SELF PAY", "MEDI-CAL"])
    if patient is None:
        tmp_service = date(2026, 3, 1)
        patient = b.register(rng, person, tmp_service)  # registered_on fixed below
    acc, received = live_timeline(b, rng, patient, payer=payer, recent_share=0.0 if returning else 0.35)
    if not returning:
        reg = acc.f["service_date"] if rng.random() < 0.7 else rday(rng, date(2012, 1, 1), date(2024, 12, 1))
        patient.f["registered_on"] = reg
        patient.versions = [(clamp(reg), dict(patient.f))]
        patient.first_day = reg
    accounts = [acc]
    if rng.random() < 0.12 and acc.fsd < received - timedelta(days=4):
        pday = rday(rng, acc.fsd + timedelta(days=2), received - timedelta(days=1))
        b.pay(acc, pday, min(rng.randint(40, 300) * 100, acc.f["patient_responsibility"] // 2))
    hh = person.household
    docs_day = received if rng.random() < 0.7 else min(received + timedelta(days=rng.randint(1, 7)),
                                                        WORLD_END - timedelta(days=1))
    year = 2026
    medi = "Y" if kind == "MEDICAL" else "N"
    hl = "Y" if homeless else "N"
    form = "2025" if rng.random() < 0.95 else "2020"
    assets = (rng.randint(0, 60) * 100) if form == "2020" and rng.random() < 0.7 else None
    if kind in ("FREE", "DISCOUNT", "PLAN"):
        lo, hi = {"FREE": (20, 188), "DISCOUNT": (212, 388), "PLAN": (412, 780)}[kind]
        target = income_for_pct(rng.uniform(lo, hi), hh, year)
        app = b.application(rng, person, patient, accounts, received, household=hh, income_stated=None, form=form,
                            assets=assets, medi_cal=medi, homeless=hl)
        truth = b.income_docs(rng, app, person, "PAY_STUBS", target, docs_day, files=True,
                              bank=rng.random() < 0.35)
        if rng.random() < 0.12:
            b.income_docs(rng, app, person, "TAX_RETURN", truth, docs_day, files=True)
        pct = truth / R.poverty_line(year, hh)
        outcome = R.band(pct)
        stated = round(truth / 100 * rng.uniform(0.97, 1.01) / 100) * 100
        if R.band(stated * 100 / R.poverty_line(year, hh)) != outcome:
            stated = round(truth / 10000) * 100
        app.snap(received, income_stated=stated if rng.random() < 0.94 else "")
        if rng.random() < 0.35:
            b.w.note(received, note_staff(rng), rng.choice([
                "Pt dropped off FA application with pay stubs at PFS window.",
                "FA app received by mail, stubs attached.", "Pt asked about financial assistance, gave app. Returned same day.",
                "Spoke w/ pt re balance, pt submitting FA app.", "App + income docs scanned to FA queue.",
            ]), app=app)
        label = "pay stubs"
        row = b.screen_answer(acc, person, outcome, pct, received, proof_label=label)
        return {"person": person, "app": app, "accounts": accounts, "outcome": outcome, "pct": pct, "row": row,
                "patient": patient}
    # Medi-Cal or homeless: free care without income documents
    app = b.application(rng, person, patient, accounts, received, household=hh, income_stated=None, form=form,
                        assets=None, medi_cal=medi, homeless=hl)
    name = f"{title(person.first)} {title(person.last)}"
    if kind == "MEDICAL" and rng.random() < 0.8:
        from docs import benefit_letter
        b.w.doc(app, docs_day, "BENEFIT_LETTER", name,
                benefit_letter(rng, kind="MEDI_CAL", name=name, household=None, amount_cents=None,
                               letter_date=received - timedelta(days=rng.randint(5, 90)), county="SANTA LUCITA",
                               received=docs_day))
    if kind == "HOMELESS" and person.addr["line1"] != "HOMELESS":
        from docs import shelter_letter
        b.w.doc(app, docs_day, "OTHER", name,
                shelter_letter(rng, shelter=person.addr["line1"], name=name,
                               since=received - timedelta(days=rng.randint(30, 300)),
                               letter_date=received - timedelta(days=rng.randint(1, 10)), received=docs_day))
    if rng.random() < 0.5:
        b.w.note(received, note_staff(rng), "Pt states has Medi-Cal, card copied." if kind == "MEDICAL"
                 else "Pt experiencing homelessness, staying at shelter. Gave FA app.", app=app)
    why = "Medi-Cal" if kind == "MEDICAL" else "homeless"
    row = b.screen_answer(acc, person, "FREE", None, received,
                          reason="Patient is on Medi-Cal: free care without income documents." if kind == "MEDICAL"
                          else "Patient is homeless: free care without income documents.")
    return {"person": person, "app": app, "accounts": accounts, "outcome": "FREE", "pct": None, "why": why,
            "row": row, "patient": patient}


def live_nowork(b: Builder, rng, pool_paid: list) -> None:
    """A live visit the patient pays in full. Nothing for the core to do."""
    if pool_paid and rng.random() < 0.2:
        person, patient = pool_paid.pop(rng.randrange(len(pool_paid)))
    else:
        person = b.new_person(rng)
        patient = None
    service = rday(rng, date(2026, 6, 26), date(2026, 9, 2))
    if patient is None:
        patient = b.register(rng, person, service if rng.random() < 0.7 else rday(rng, date(2011, 1, 1),
                                                                                  date(2024, 6, 1)))
    payer = pick(rng, [("SELF PAY", 30), ("BLUE PACIFIC PPO", 25), ("GOLDEN STATE HEALTH HMO", 20),
                       ("COASTAL CARE PLAN", 10), ("MEDICARE", 15)])
    stype = pick(rng, [("ER", 30), ("CLINIC", 40), ("OUTPATIENT", 30)])
    acc = b.visit(rng, patient, service, payer=payer, stype=stype,
                  total_cents=rng.randint(300_00, 1_800_00) if payer == "SELF PAY" else None)
    pay_day = min(acc.fsd + timedelta(days=rng.randint(3, 25)), WORLD_END)
    b.pay(acc, pay_day, b.w.balance(acc, pay_day))
    b.status(acc, pay_day, "PAID")


def build_base(b: Builder) -> dict:
    """The ordinary office. Returns pools the planted cases can draw on."""
    rng = random.Random(13)
    hist_rng = random.Random(13 * 101)
    live_rng = random.Random(13 * 103)
    pool_paid: list = []
    hist_cases: list[dict] = []
    order = (["FREE"] * COUNTS["H_FREE"] + ["DISCOUNT"] * COUNTS["H_DISCOUNT"] + ["DENIED"] * COUNTS["H_DENIED"]
             + ["MEDICAL"] * COUNTS["H_MEDICAL"] + ["HOMELESS"] * COUNTS["H_HOMELESS"]
             + ["CLOSED"] * COUNTS["H_CLOSED"])
    rng.shuffle(order)
    for kind in order:
        hist_cases.append(history_fa_case(b, hist_rng, kind, files=hist_rng.random() < 0.45))
    for _ in range(COUNTS["H_NOAPP"]):
        history_noapp(b, hist_rng, pool_paid)
    live_cases: list[dict] = []
    order = (["FREE"] * COUNTS["L_FREE"] + ["MEDICAL"] * COUNTS["L_MEDICAL"] + ["HOMELESS"] * COUNTS["L_HOMELESS"]
             + ["DISCOUNT"] * COUNTS["L_DISCOUNT"] + ["PLAN"] * COUNTS["L_PLAN"])
    rng.shuffle(order)
    for kind in order:
        live_cases.append(live_clear_case(b, live_rng, kind, pool_paid))
    for _ in range(COUNTS["L_NOWORK"]):
        live_nowork(b, live_rng, pool_paid)
    return {"hist": hist_cases, "live": live_cases, "pool_paid": pool_paid}


def patterns(b: Builder, pools_: dict) -> None:
    """What a careful reader of the history should learn, with evidence counts."""
    w = b.w
    final = []
    for a in w.apps:
        if a.f["received_on"] > HISTORY_END:
            continue
        last = None
        for day, state in a.versions:
            if day <= HISTORY_END:
                last = state
        if last:
            final.append((a, last))
    tag = lambda a: getattr(a, "tag", "")
    free = sum(1 for a, s in final if s["decision"] == "FREE" and s["income_proof"] not in ("NONE", "")
               and s["medi_cal"] != "Y" and s["homeless"] != "Y")
    disc = sum(1 for a, s in final if s["decision"] == "DISCOUNT")
    denied_income = sum(1 for a, s in final if s["decision"] == "DENIED" and tag(a) == "")
    medi = sum(1 for a, s in final if s["decision"] == "FREE" and s["medi_cal"] == "Y")
    homeless = sum(1 for a, s in final if s["decision"] == "FREE" and s["homeless"] == "Y")
    late = sum(1 for a, s in final if tag(a) in ("ILLEGAL_LATE", "DECOY_LATE"))
    savings = sum(1 for a, s in final if tag(a) in ("ILLEGAL_SAVINGS", "DECOY_SAVINGS"))
    nostubs = sum(1 for a, s in final if tag(a) == "ILLEGAL_NO_STUBS")
    calfresh = sum(1 for a, s in final if tag(a).startswith("CALFRESH"))
    coverage = sum(1 for acc in w.accounts if getattr(acc, "covered_by", None) is not None
                   and acc.f["service_date"] <= HISTORY_END)
    plans = [p for p in w.plans if p.first_day <= HISTORY_END]
    plan_ok = sum(1 for p in plans if p.versions and p.versions[0][1]["months"] <= 12)
    w.patterns = [
        {"pattern": "Free care when household income is at or under 200% of the poverty level", "evidence_count": free,
         "legal": "Y", "note": "Matches both policy versions. Verified income, decision-year poverty table."},
        {"pattern": "Discount above 200% up to 400%: patient pays 30% of the patient balance", "evidence_count": disc,
         "legal": "Y", "note": "Adjustment is 70% of patient_responsibility, rounded to the cent."},
        {"pattern": "Denied as over income above 400%, interest-free payment plan offered",
         "evidence_count": denied_income, "legal": "Y", "note": "Outcome is a payment plan, not a write-off."},
        {"pattern": "Medi-Cal enrollees get free care without income documents", "evidence_count": medi,
         "legal": "Y", "note": "income_proof NONE, medi_cal Y."},
        {"pattern": "Homeless patients get free care without income documents", "evidence_count": homeless,
         "legal": "Y", "note": "income_proof NONE, homeless Y, HOMELESS or shelter address."},
        {"pattern": "Applications denied as late (over 240 days after the first bill)", "evidence_count": late,
         "legal": "N", "note": "AB 2297: no application deadline from 2025-01-01, even while the old policy was in effect."},
        {"pattern": "Applications denied for savings over $10,000", "evidence_count": savings,
         "legal": "N", "note": "AB 2297: savings and other monetary assets can't be counted from 2025-01-01."},
        {"pattern": "Applications denied for no pay stubs when other proof was on file", "evidence_count": nostubs,
         "legal": "N", "note": "AB 2297: other proof of income must be accepted from 2025-01-01."},
        {"pattern": "An approval covers every visit in the 12 months from the decision date", "evidence_count": coverage,
         "legal": "Y", "note": "Later visits inside the 12 months were written off under the earlier approval."},
        {"pattern": "Payment plans: 12 equal monthly payments rounded up to the dollar, at least $25, no interest",
         "evidence_count": plan_ok, "legal": "Y", "note": "Fewer months only when $25 a month pays it off sooner."},
        {"pattern": "CalFresh enrollees handled inconsistently (some approved free without income documents, others left in needs info or closed)",
         "evidence_count": calfresh, "legal": "Y",
         "note": "No written rule in either policy version. A counselor's correction can turn it into one."},
    ]
