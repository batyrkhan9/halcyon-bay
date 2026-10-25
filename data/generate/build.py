"""Builds the simulated hospital: people, visits, bills, applications, documents and the answer key."""

from __future__ import annotations

import random
from datetime import date, timedelta

import docs as D
import pools
import rules as R
from world import HISTORY_END, HISTORY_START, LIVE_START, WORLD_END, Rec, World, clamp

LETTERS = "ABCDEFGHJKLMNPRSTW"
FREQS = [("BI-WEEKLY", 50), ("WEEKLY", 20), ("SEMI-MONTHLY", 20), ("MONTHLY", 10)]
PAYERS = [("SELF PAY", 55), ("BLUE PACIFIC PPO", 12), ("GOLDEN STATE HEALTH HMO", 10), ("COASTAL CARE PLAN", 6),
          ("MEDICARE", 10), ("MEDI-CAL", 7)]
STYPES = [("ER", 45), ("OUTPATIENT", 20), ("CLINIC", 20), ("INPATIENT", 15)]
COUNTY = "SANTA LUCITA"


def pick(rng: random.Random, weighted):
    items, weights = zip(*weighted)
    return rng.choices(items, weights)[0]


def rday(rng: random.Random, a: date, b: date) -> date:
    return a + timedelta(days=rng.randint(0, max(0, (b - a).days)))


def title(s: str) -> str:
    return s.title() if s else s


class Builder:
    def __init__(self, id_rng: random.Random | None = None):
        self.w = World(id_rng or random.Random("13/ids"))
        self.used_ssn: set[str] = set()
        self.used_phone: set[str] = set()
        self.used_addr: set[str] = set()
        self.personas = pools.load_personas()
        for p in self.personas.values():
            self.used_ssn.add(p["ssn"])
            self.used_phone.add(p["phone"])
        bad = pools.PERSONA_SURNAMES | pools.STAFF_SURNAMES
        self.last_names = [n for n in pools.LAST_NAMES if n.upper() not in bad]
        self.person_info: dict[int, dict] = {}       # person.seq -> answer key facts
        self.allow_overtime = True                   # ordinary stubs sometimes say "includes overtime"
        self.last_stub: dict | None = None

    # ------------------------------------------------------------------ people

    def new_ssn(self, rng) -> str:
        while True:
            area = rng.randint(100, 899)
            if area == 666:
                continue
            s = f"{area:03d}00{rng.randint(1, 9999):04d}"
            if s not in self.used_ssn:
                self.used_ssn.add(s)
                return s

    def new_phone(self, rng) -> str:
        while True:
            p = f"555{rng.randint(200, 999)}{rng.randint(0, 9999):04d}"
            if p not in self.used_phone:
                self.used_phone.add(p)
                return p

    def new_address(self, rng, town=None) -> dict:
        while True:
            city, zip_code, _ = town or pick(rng, [((t[0], t[1], 0), t[2]) for t in pools.TOWNS])
            street = rng.choice(pools.STREET_NAMES)
            abbr, full = rng.choice(pools.STREET_SUFFIX)
            num = rng.randint(100, 9899)
            unit = f"{rng.randint(1, 4)}{rng.choice('ABCD')}" if rng.random() < 0.25 else (
                str(rng.randint(1, 40)) if rng.random() < 0.08 else "")
            line1 = f"{num} {street} {abbr}" + (f" APT {unit}" if unit else "")
            if line1 + city in self.used_addr:
                continue
            self.used_addr.add(line1 + city)
            style = rng.random()
            fa = f"{num} {title(street)} {full if style < 0.5 else title(abbr)}"
            if unit:
                fa += rng.choice([f" Apt {unit}", f" #{unit}", f" Unit {unit}"])
            return {"line1": line1, "fa_line1": fa, "city": city, "state": "CA", "zip": zip_code}

    def new_person(self, rng, *, age=(19, 84), household=None, homeless=False, sex=None, mismatch="auto",
                   last=None, first=None) -> object:
        sex = sex or rng.choice("FM")
        first = first or rng.choice(pools.FEMALE_FIRST if sex == "F" else pools.MALE_FIRST)
        middle = rng.choice(LETTERS) if rng.random() < 0.7 else ""
        if last is None:
            last = rng.choice(self.last_names)
            if rng.random() < 0.05:
                last = f"{last}-{rng.choice(self.last_names)}"
        a = rng.randint(*age)
        dob = date(2026 - a, 1, 1) + timedelta(days=rng.randint(0, 364))
        hh = household or pick(rng, [(1, 24), (2, 22), (3, 20), (4, 18), (5, 10), (6, 6)])
        if homeless:
            hh = household or 1
        if mismatch == "auto":
            mismatch = None
            if rng.random() < 0.12:
                mismatch = pick(rng, [("nickname", 3), ("married", 2), ("typo_first", 1), ("dm_swap", 2),
                                      ("old_address", 2), ("no_middle", 1)])
                if mismatch == "nickname" and title(first) not in pools.NICKNAMES:
                    mismatch = "no_middle"
                if mismatch == "married" and sex != "F":
                    mismatch = "dm_swap"
        addr = self.new_address(rng)
        employer, job = rng.choice(pools.EMPLOYERS)
        p = self.w.person(first=first.upper(), middle=middle, last=last.upper(), sex=sex, dob=dob,
                          ssn=self.new_ssn(rng), phone=self.new_phone(rng), addr=addr, household=hh,
                          employer=employer, job=job, mismatch=mismatch, homeless=homeless)
        p.old_addr = self.new_address(rng) if mismatch == "old_address" else None
        p.married_last = rng.choice(self.last_names).upper() if mismatch == "married" else None
        p.applicants = []
        p.patients = []
        return p

    def persona_person(self, pid: str, *, household=1, sex="F", employer=None, job=None) -> object:
        ident = self.personas[pid]
        addr = {"line1": ident["street1"], "fa_line1": title(ident["street1"]), "city": ident["city"],
                "state": ident["state"], "zip": ident["zip"]}
        p = self.w.person(first=ident["first_name"], middle="", last=ident["last_name"], sex=sex,
                          dob=date.fromisoformat(ident["dob"]), ssn=ident["ssn"], phone=ident["phone"], addr=addr,
                          household=household, employer=employer or "BAYLINE LOGISTICS INC",
                          job=job or "Warehouse associate", mismatch=None, homeless=False, persona=pid)
        p.old_addr = None
        p.married_last = None
        p.applicants = []
        p.patients = []
        return p

    # --------------------------------------------------------------- renderings

    @staticmethod
    def fmt_phone_billing(p: str) -> str:
        return f"({p[:3]}) {p[3:6]}-{p[6:]}"

    @staticmethod
    def fmt_phone_fa(p: str) -> str:
        return f"{p[:3]}-{p[3:6]}-{p[6:]}"

    @staticmethod
    def one_line(addr: dict) -> str:
        if addr["line1"] == "HOMELESS":
            return f"HOMELESS, {addr['city']} {addr['state']} {addr['zip']}"
        return f"{addr['line1']}, {addr['city']} {addr['state']} {addr['zip']}"

    def typo_ssn(self, rng, ssn: str) -> str:
        if ssn.startswith("666"):
            return ssn
        pos = rng.choice([1, 2, 5, 6, 7, 8])
        d = str((int(ssn[pos]) + rng.randint(1, 9)) % 10)
        out = ssn[:pos] + d + ssn[pos + 1:]
        return out if not out.startswith("666") and not out.startswith("000") else ssn

    def register(self, rng, person, registered_on: date, *, ssn_mode="auto", first=None, last=None,
                 middle=None, addr=None) -> Rec:
        """A billing patient record (MRN) for this person."""
        first = first or person.first
        if person.mismatch == "typo_first" and first == person.first and len(first) > 3:
            i = rng.randint(1, len(first) - 2)
            first = first[:i] + first[i + 1] + first[i] + first[i + 2:]
        middle = person.middle if middle is None else middle
        if person.mismatch == "no_middle":
            middle = ""
        addr = addr or (person.old_addr if person.old_addr else person.addr)
        if person.homeless:
            addr = person.addr
        if ssn_mode == "auto":
            ssn_mode = "blank" if (rng.random() < 0.10 and not person.persona) else "exact"
        ssn = {"blank": "", "exact": person.ssn, "typo": self.typo_ssn(rng, person.ssn)}[ssn_mode]
        pat = self.w.patient(person, registered_on, last_name=(last or person.last), first_name=first,
                             middle_initial=middle, dob=person.dob, ssn=ssn, address_line1=addr["line1"],
                             city=addr["city"], state=addr["state"], zip=addr["zip"],
                             phone=self.fmt_phone_billing(person.phone), addr=addr)
        person.patients.append(pat)
        return pat

    # ------------------------------------------------------------------ visits

    def charges(self, rng, stype: str) -> int:
        lo, hi = {"ER": (1500, 12000), "OUTPATIENT": (300, 6000), "CLINIC": (300, 3500),
                  "INPATIENT": (15000, 95000)}[stype]
        return rng.randint(lo * 100, hi * 100)

    def visit(self, rng, patient: Rec, service: date, *, stype=None, payer=None, total_cents=None,
              fsd_gap=None) -> Rec:
        stype = stype or pick(rng, STYPES)
        payer = payer or pick(rng, PAYERS)
        los = rng.randint(2, 9) if stype == "INPATIENT" else 0
        discharge = service + timedelta(days=los)
        recorded = discharge + timedelta(days=rng.randint(1, 3))
        fsd = discharge + timedelta(days=fsd_gap if fsd_gap is not None else rng.randint(5, 15))
        if fsd <= recorded:
            fsd = recorded + timedelta(days=1)
        total = total_cents or self.charges(rng, stype)
        if payer == "SELF PAY":
            ins_paid, ins_adj = 0, 0
        elif payer == "MEDICARE":
            ins_adj = total * rng.randint(40, 58) // 100
            allowed = total - ins_adj
            ins_paid = allowed * rng.randint(72, 80) // 100
        elif payer == "MEDI-CAL":
            ins_adj = total * rng.randint(55, 70) // 100
            allowed = total - ins_adj
            ins_paid = allowed * rng.randint(70, 88) // 100
        else:
            ins_adj = total * rng.randint(25, 45) // 100
            allowed = total - ins_adj
            ins_paid = allowed * rng.randint(62, 85) // 100
        pr = total - ins_paid - ins_adj
        acc = self.w.account(patient, recorded, service_date=service, discharge_date=discharge, service_type=stype,
                             payer=payer, total_charges=total, insurance_paid=ins_paid, insurance_adjustment=ins_adj,
                             patient_responsibility=pr, first_statement_date=None, status="OPEN")
        acc.fsd = fsd
        acc.snap(recorded)
        acc.snap(fsd, first_statement_date=fsd)
        self.w.txn(acc, discharge, "CHARGE", total, f"{stype.lower()} charges", recorded=recorded)
        if ins_paid:
            self.w.txn(acc, recorded, "INSURANCE_PAYMENT", -ins_paid, f"{payer} remit", recorded=recorded)
        if ins_adj:
            self.w.txn(acc, recorded, "INSURANCE_ADJUSTMENT", -ins_adj, "contractual adjustment", recorded=recorded)
        return acc

    def status(self, acc: Rec, day: date, status: str) -> None:
        acc.snap(day, status=status)

    def pay(self, acc: Rec, day: date, cents: int, note="patient payment", kind="PATIENT_PAYMENT") -> None:
        if cents > 0 and day <= WORLD_END:
            self.w.txn(acc, day, kind, -cents, note)

    # ------------------------------------------------------------ applications

    def applicant_for(self, person, day: date, new=False) -> Rec:
        if person.applicants and not new:
            return person.applicants[0]
        a = self.w.applicant(person, day)
        person.applicants.append(a)
        return a

    def application(self, rng, person, patient: Rec | None, accounts: list[Rec], received: date, *,
                    household: int, income_stated: int | None, form: str | None = None,
                    assets: int | None = None, medi_cal="N", homeless="N", mrn_given="auto",
                    accounts_given="auto", applicant=None, first=None, last=None, ssn="auto") -> Rec:
        applicant = applicant or self.applicant_for(person, received)
        form = form or ("2020" if received <= R.OLD_POLICY_END else "2025")
        first = first or person.first
        last = last or person.last
        if person.mismatch == "nickname":
            first = pools.NICKNAMES.get(title(person.first), title(person.first)).upper()
        if person.mismatch == "married" and person.married_last:
            last = f"{person.last}-{person.married_last}" if rng.random() < 0.5 else person.married_last
        if ssn == "auto":
            r = rng.random()
            ssn = "" if r < 0.12 else (self.typo_ssn(rng, person.ssn) if r < 0.14 else person.ssn)
            if ssn and rng.random() < 0.3:
                ssn = f"{ssn[:3]}-{ssn[3:5]}-{ssn[5:]}"
        addr = person.addr
        line1 = addr["fa_line1"] if addr["line1"] != "HOMELESS" else "Homeless"
        if mrn_given == "auto":
            mrn_given = patient if (patient is not None and rng.random() < 0.85) else ""
        if accounts_given == "auto":
            accounts_given = list(accounts)
        app = self.w.app(applicant, received, mrn_given=mrn_given, accounts_given=accounts_given,
                         first_name=title(first), last_name=title(last), dob=person.dob, ssn=ssn,
                         phone=self.fmt_phone_fa(person.phone) if rng.random() < 0.95 else "",
                         address_line1=line1, city=title(addr["city"]), state=addr["state"], zip=addr["zip"],
                         household_size=household, income_stated="" if income_stated is None else income_stated,
                         income_verified="", income_proof="", monetary_assets="" if assets is None else assets,
                         medi_cal=medi_cal, homeless=homeless, form_version=form, status="RECEIVED", decision="",
                         decision_date=None, decided_by="", reason="")
        app.person = person
        app.accounts = list(accounts)
        app.snap(received)
        return app

    def decide(self, app: Rec, day: date, status: str, decision: str, by: str, reason: str,
               verified: int | None = None, proof: str = "") -> None:
        app.snap(day, status=status, decision=decision, decision_date=day if decision else None, decided_by=by,
                 reason=reason, income_verified="" if verified is None else verified, income_proof=proof)

    # --------------------------------------------------------------- documents

    def income_docs(self, rng, app: Rec | None, person, proof: str, annual_cents: int, received: date,
                    files=True, bank=False, savings_cents=None, name=None, extra_stub_text="") -> int:
        """Make the documents for this proof type. Returns the yearly income they show, in cents."""
        name = name or f"{title(person.first)} {title(person.last)}"
        docs_made = []
        if proof == "PAY_STUBS":
            freq = pick(rng, FREQS)
            periods = D.PERIODS[freq]
            hourly = rng.random() < 0.65
            hours, rate = None, None
            if hourly:
                hours = D.HOURS[freq]
                rate = round(annual_cents / (periods * hours))
                if rate < 1650:                      # part-time at a real wage, not full-time at $5/hour
                    rate = rng.randint(1650, 1900)
                    hours = max(8.0, round(annual_cents / (periods * rate) * 4) / 4)
                gross = round(rate * hours)
            else:
                gross = round(annual_cents / periods)
            truth = gross * periods
            n = pick(rng, [(2, 60), (3, 25), (1, 15)])
            last_pay = received - timedelta(days=rng.randint(3, 18))
            emp_id = f"{rng.randint(10000, 99999)}"
            fed_pct = rng.randint(4, 11)                 # one withholding rate per job, so net pay repeats
            net = D.stub_net(gross, fed_pct)
            step = D.PERIOD_DAYS[freq]
            ot_text = ""
            if self.allow_overtime and rng.random() < 0.06:
                ot_text = f"  includes overtime {rng.choice(['1.50', '2.00', '2.50', '3.00', '4.00'])} hrs"
            for k in range(n):
                pd = last_pay - timedelta(days=step * k)
                ytd = max(1, (pd - date(pd.year, 1, 1)).days // step + 1)
                extra = "\n".join(x for x in (ot_text, extra_stub_text if k == 0 else "") if x)
                text = D.pay_stub(rng, employer=person.employer, title=person.job, name=name, emp_id=emp_id,
                                  frequency=freq, gross_cents=gross, pay_date=pd, received=received,
                                  ytd_periods=ytd, hourly=hourly, hours=hours, rate_cents=rate,
                                  extra_text=extra, fed_pct=fed_pct)
                docs_made.append(("PAY_STUB", text))
            self.last_stub = {"net": net, "gross": gross, "step": step, "last_pay": last_pay,
                              "employer": person.employer}
            if bank or savings_cents is not None:
                # the last full calendar month before the documents arrived; payroll lands on the stub pay dates
                end = received.replace(day=1) - timedelta(days=1)
                start = end.replace(day=1)
                while True:
                    deps = []
                    d = last_pay
                    while d >= start:
                        if d <= end:
                            deps.append((d, f"PAYROLL DIR DEP {person.employer[:18]}", net))
                        d -= timedelta(days=step)
                    if deps:
                        break
                    start = (start - timedelta(days=1)).replace(day=1)
                text = D.bank_statement(rng, bank=rng.choice(pools.BANKS), name=name, period_start=start,
                                        period_end=end, deposits=sorted(deps), savings_cents=savings_cents,
                                        received=received)
                docs_made.append(("BANK_STATEMENT", text))
        elif proof == "TAX_RETURN":
            truth = round(annual_cents / 100) * 100
            hh = self.person_household(person)
            status = "Single" if hh == 1 else rng.choice(["Married filing jointly", "Head of household"])
            text = D.tax_return(rng, name=name, tax_year=received.year - (1 if received.month >= 5 else 2),
                                filing_status=status,
                                dependents=max(0, hh - (2 if status.startswith("Married") else 1)),
                                wages_cents=truth, other_cents=0, received=received)
            docs_made.append(("TAX_RETURN", text))
        elif proof == "EMPLOYER_LETTER":
            if rng.random() < 0.6:
                truth = round(annual_cents / 100) * 100
                text = D.employer_letter(rng, employer=person.employer, title=person.job, name=name,
                                         hr_name=f"{rng.choice(pools.FEMALE_FIRST)} {rng.choice(self.last_names)}",
                                         since=received - timedelta(days=rng.randint(200, 3000)),
                                         letter_date=received - timedelta(days=rng.randint(2, 20)),
                                         annual_cents=truth, hourly_cents=None, weekly_hours=None, received=received)
            else:
                hrs = rng.choice([20, 24, 30, 32, 36, 40])
                hourly = round(annual_cents / (hrs * 52))
                if hourly < 1650:
                    hourly = rng.randint(1650, 1850)
                    hrs = max(6, round(annual_cents / (hourly * 52)))
                    hourly = round(annual_cents / (hrs * 52))
                truth = hourly * hrs * 52
                text = D.employer_letter(rng, employer=person.employer, title=person.job, name=name,
                                         hr_name=f"{rng.choice(pools.MALE_FIRST)} {rng.choice(self.last_names)}",
                                         since=received - timedelta(days=rng.randint(200, 3000)),
                                         letter_date=received - timedelta(days=rng.randint(2, 20)),
                                         annual_cents=None, hourly_cents=hourly, weekly_hours=hrs, received=received)
            docs_made.append(("EMPLOYER_LETTER", text))
        elif proof == "BENEFIT_LETTER":
            if annual_cents < 22_000_00 and rng.random() < 0.35:
                weekly = round(annual_cents / 52)
                truth = weekly * 52
                text = D.benefit_letter(rng, kind="EDD", name=name, household=None, amount_cents=weekly,
                                        letter_date=received - timedelta(days=rng.randint(5, 40)), county=COUNTY,
                                        received=received)
            else:
                monthly = round(annual_cents / 12)
                truth = monthly * 12
                text = D.benefit_letter(rng, kind="SSA", name=name, household=None, amount_cents=monthly,
                                        letter_date=received - timedelta(days=rng.randint(5, 90)), county=COUNTY,
                                        received=received)
            docs_made.append(("BENEFIT_LETTER", text))
        elif proof == "SELF_ATTESTATION":
            monthly = round(annual_cents / 12 / 1000) * 1000
            truth = monthly * 12
            text = D.self_attestation(rng, name=name, household=self.person_household(person), monthly_cents=monthly,
                                      source=rng.choice(["odd jobs and help from family", "cash work cleaning houses",
                                                         "day labor", "selling at the flea market",
                                                         "family members who help with rent"]),
                                      signed=received - timedelta(days=rng.randint(0, 6)), received=received)
            docs_made.append(("SELF_ATTESTATION", text))
        else:
            raise ValueError(proof)
        if files:
            for doc_type, text in docs_made:
                self.w.doc(app, received, doc_type, name if rng.random() < 0.7 else name.upper(), text)
        return truth

    def person_household(self, person) -> int:
        return getattr(person, "true_household", None) or person.household

    # ------------------------------------------------------------ money moves

    def apply_fa(self, acc: Rec, day: date, outcome: str, rng, refund_to_paid=True) -> None:
        """Post the charity or discount adjustment for a decided application."""
        pr = acc.f["patient_responsibility"]
        if outcome == "FREE":
            self.w.txn(acc, day, "CHARITY_ADJUSTMENT", -pr, "FAP charity care 100%")
        elif outcome == "DISCOUNT":
            self.w.txn(acc, day, "DISCOUNT_ADJUSTMENT", -(pr - R.discounted_cents(pr)), "FAP discount, pt pays 30%")
        bal = self.w.balance(acc, day)
        if bal < 0 and refund_to_paid:
            self.w.txn(acc, day + timedelta(days=rng.randint(5, 20)), "REFUND", -bal, "refund of patient payments")
        self.status(acc, day, "ADJUSTED")

    def run_plan(self, rng, patient: Rec, accounts: list[Rec], created: date, *, miss_at=None, stop=None,
                 note_author=None) -> Rec:
        """A payment plan with its monthly payments. `stop` = (day, by, reason) stops it."""
        bal = sum(self.w.balance(a, created) for a in accounts)
        monthly = R.plan_monthly_dollars(bal)
        months = R.plan_months(bal, monthly)
        start = created + timedelta(days=rng.randint(14, 28))
        plan = self.w.plan(patient, accounts, created, start_date=start, monthly_amount=monthly * 100, months=months,
                           status="ACTIVE", missed_payments=0, last_payment_on=None, stopped_on=None, stopped_by="",
                           stop_reason="")
        plan.snap(created)
        remaining = bal
        k = 0
        missed = 0
        due = start
        while remaining > 0:
            if stop and due >= stop[0]:
                break
            if due > WORLD_END:
                break
            if miss_at is not None and k in miss_at:
                missed += 1
                miss_day = due + timedelta(days=10)
                if stop and miss_day >= stop[0]:
                    miss_day = stop[0]
                plan.snap(miss_day, missed_payments=missed)
            else:
                amt = min(remaining, monthly * 100)
                paid_day = due + timedelta(days=rng.randint(0, 6))
                if paid_day > WORLD_END:
                    break
                left = amt
                for a in accounts:
                    b = self.w.balance(a, paid_day)
                    part = min(b, left)
                    if part > 0:
                        self.pay(a, paid_day, part, "payment plan installment")
                        left -= part
                remaining -= amt
                plan.snap(paid_day, last_payment_on=paid_day)
                if remaining <= 0:
                    plan.snap(paid_day, status="COMPLETED")
                    for a in accounts:
                        self.status(a, paid_day, "PAID")
            k += 1
            due = R.add_months(start, k)
        if stop and stop[0] <= WORLD_END:
            plan.snap(stop[0], status="STOPPED", stopped_on=stop[0], stopped_by=stop[1], stop_reason=stop[2])
        plan.monthly = monthly
        return plan

    def place(self, rng, acc: Rec, day: date, *, notice=True, notice_gap=None, style=None) -> Rec:
        """Place an account with Golden Coast Recovery, with an optional final notice first."""
        if notice:
            nd = day - timedelta(days=notice_gap or rng.randint(31, 45))
            acc.final_notices.append(nd)
        bal = self.w.balance(acc, day)
        person = acc.f["patient"].f["person"]
        pat = acc.f["patient"]
        dob = person.dob
        dob_s = dob.strftime("%m/%d/%Y")
        if person.mismatch == "dm_swap" and dob.day <= 12 and dob.day != dob.month:
            dob_s = f"{dob.day:02d}/{dob.month:02d}/{dob.year}"
        addr = pat.f["addr"]
        name = f"{pat.f['last_name']}, {pat.f['first_name']}" + (f" {pat.f['middle_initial']}" if pat.f["middle_initial"] and rng.random() < 0.5 else "")
        pl = self.w.placement(acc, day, client_style=style or pick(rng, [("plain", 60), ("noprefix", 25), ("dashes", 15)]),
                              debtor_name=name, debtor_dob=dob_s,
                              debtor_address=f"{addr['line1']} {addr['city']} {addr['state']} {addr['zip']}",
                              debtor_phone=person.phone, placed_balance=bal, current_balance=bal, status="ACTIVE",
                              last_activity="new placement - initial letter queued")
        pl.snap(day)
        acc.statement_stop = day
        self.status(acc, day, "IN_COLLECTIONS")
        acc.placement = pl
        return pl

    def agency_collect(self, rng, pl: Rec, day: date, cents: int, full=False) -> None:
        acc = pl.f["account"]
        if day > WORLD_END:
            return
        self.pay(acc, day, cents, "collected by Golden Coast Recovery", kind="AGENCY_PAYMENT")
        cur = pl.f["current_balance"] - cents
        if full or cur <= 0:
            pl.snap(day, current_balance=0, status="PAID", last_activity="paid in full - closing")
            self.status(acc, day, "PAID")
        else:
            pl.snap(day, current_balance=cur, last_activity=rng.choice(
                ["payment received by phone", "partial pmt rec'd", "debtor paid online", "check received"]))

    # -------------------------------------------------------------- statements

    def finalize_statements(self, rng) -> None:
        for acc in self.w.accounts:
            fsd = acc.fsd
            if fsd > WORLD_END:
                continue
            pat = acc.f["patient"]
            mailed = acc.mail_to or self.one_line(pat.f["addr"])
            ret = acc.returned_mail
            stop = acc.statement_stop
            self.w.statement(acc, fsd, "FIRST", self.w.balance(acc, fsd), mailed, ret)
            if not acc.no_monthly:
                for k in (1, 2, 3):
                    day = fsd + timedelta(days=30 * k + rng.randint(-2, 2))
                    if day > WORLD_END or (stop and day >= stop):
                        break
                    bal = self.w.balance(acc, day)
                    if bal <= 0:
                        break
                    self.w.statement(acc, day, "MONTHLY", bal, mailed, ret)
            for nd in acc.final_notices:
                if nd <= WORLD_END:
                    self.w.statement(acc, nd, "FINAL_NOTICE", self.w.balance(acc, nd), mailed, ret)

    # ------------------------------------------------------------- answer key

    def answer(self, acc: Rec, person, *, outcome: str, pct=None, adjustment=0, owes=0, refund=0, monthly=None,
               handling="AUTO", ask_role="", approver="", required=(), forbidden=(), planted=(), reason="") -> dict:
        row = {"account": acc, "person": person, "outcome": outcome, "fpl_pct": pct, "adjustment": adjustment,
               "patient_owes": owes, "refund": refund, "monthly_payment": monthly, "handling": handling,
               "ask_role": ask_role, "approver_role": approver, "required": list(required),
               "forbidden": list(forbidden), "planted": list(planted), "reason": reason}
        self.w.answers.append(row)
        return row

    def screen_answer(self, acc: Rec, person, outcome: str, pct, on: date, *, proof_label="", handling="AUTO",
                      ask_role="", extra_required=(), extra_forbidden=(), planted=(), reason=None,
                      merged_balance=None, approver_override=None, owes_override=None, drop_required=(),
                      forbidden_only=None) -> dict:
        """The right answer for an account whose outcome is known, as of day `on`."""
        pr = acc.f["patient_responsibility"]
        paid = self.w.paid_by_patient(acc, on)
        adj = R.adjustment_cents(outcome, pr) if outcome in ("FREE", "DISCOUNT") else 0
        # patient_owes is the share under the right decision, before payments already made (core patient_pays_cents)
        share = R.patient_share_cents(outcome, pr) if outcome in ("FREE", "DISCOUNT") else pr
        owes = share
        refund = max(0, paid - share)
        monthly = None
        req, forb = [], []
        if outcome == "FREE":
            req, forb = ["FREE_CARE"], ["DENY", "DISCOUNT", "PAYMENT_PLAN", "COLLECTIONS_REFERRAL"]
            approver = R.approver_for_adjustment(adj)
        elif outcome == "DISCOUNT":
            req, forb = ["DISCOUNT"], ["DENY", "FREE_CARE", "COLLECTIONS_REFERRAL"]
            approver = R.approver_for_adjustment(adj)
        elif outcome == "PAYMENT_PLAN":
            req, forb = ["PAYMENT_PLAN"], ["FREE_CARE", "DISCOUNT", "COLLECTIONS_REFERRAL"]
            approver = "COUNSELOR"
            monthly = R.plan_monthly_dollars(merged_balance if merged_balance is not None else owes - paid)
        elif outcome == "NEEDS_INFO":
            req, forb = ["REQUEST_INFO"], ["DENY", "FREE_CARE", "DISCOUNT", "COLLECTIONS_REFERRAL"]
            approver = ""
        else:
            approver = ""
        for x in extra_required:
            if x not in req:
                req.append(x)
        for x in extra_forbidden:
            if x not in forb:
                forb.append(x)
        req = [x for x in req if x not in drop_required]
        if forbidden_only is not None:
            forb = list(forbidden_only)
        forb = [x for x in forb if x not in req]
        if approver_override is not None:
            approver = approver_override
        if owes_override is not None:
            owes = owes_override
            refund = max(0, paid - owes)
        if reason is None:
            reason = self.reason_line(outcome, pct, person, proof_label, on)
        return self.answer(acc, person, outcome=outcome, pct=pct, adjustment=adj, owes=owes, refund=refund,
                           monthly=monthly, handling=handling, ask_role=ask_role, approver=approver, required=req,
                           forbidden=forb, planted=planted, reason=reason)

    def reason_line(self, outcome, pct, person, proof_label, on: date) -> str:
        hh = self.person_household(person)
        if pct is None:
            return f"{outcome}"
        where = f"{pct:.1f}% of the {on.year} poverty level for a household of {hh}"
        src = f" ({proof_label})" if proof_label else ""
        if outcome == "FREE":
            return f"Income {where}{src}: free care."
        if outcome == "DISCOUNT":
            return f"Income {where}{src}: discount, patient pays 30%."
        if outcome == "PAYMENT_PLAN":
            return f"Income {where}{src}: over 400%, payment plan only."
        return f"Income {where}{src}."


PROOF_LABEL = {"PAY_STUBS": "pay stubs", "TAX_RETURN": "tax return", "EMPLOYER_LETTER": "employer letter",
               "BENEFIT_LETTER": "benefit letter", "SELF_ATTESTATION": "self-attestation"}


def income_for_pct(pct: float, household: int, year: int) -> int:
    """Yearly income in cents that lands at `pct` of the poverty level."""
    return round(pct * R.poverty_line(year, household))
