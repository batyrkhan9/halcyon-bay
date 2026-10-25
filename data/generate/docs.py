"""Document text, written to look like mailroom OCR output. Everything is fictional."""

from __future__ import annotations

import random
from datetime import date, timedelta

PERIODS = {"WEEKLY": 52, "BI-WEEKLY": 26, "SEMI-MONTHLY": 24, "MONTHLY": 12}
PERIOD_DAYS = {"WEEKLY": 7, "BI-WEEKLY": 14, "SEMI-MONTHLY": 15, "MONTHLY": 30}
HOURS = {"WEEKLY": 40.0, "BI-WEEKLY": 80.0, "SEMI-MONTHLY": 86.67, "MONTHLY": 173.33}


def usd(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    c = abs(cents)
    return f"{sign}{c // 100:,}.{c % 100:02d}"


def mdy(d: date) -> str:
    return d.strftime("%m/%d/%Y")


def _ocr_word(rng: random.Random, word: str) -> str:
    """Swap the odd O/0 or l/1 in a label, never in a number."""
    if any(ch.isdigit() for ch in word) or rng.random() > 0.08:
        return word
    swaps = [("O", "0"), ("o", "0"), ("l", "1"), ("I", "1"), ("S", "5")]
    a, b = rng.choice(swaps)
    i = word.find(a)
    return word if i < 0 else word[:i] + b + word[i + 1:]


def ocr(rng: random.Random, text: str) -> str:
    """Make text look scanned: stray spacing, swapped letters in labels, a smudge line."""
    out = []
    for line in text.split("\n"):
        words = line.split(" ")
        words = [_ocr_word(rng, w) for w in words]
        line = " ".join(words)
        if line.strip() and rng.random() < 0.15:
            line = " " * rng.randint(1, 4) + line
        if rng.random() < 0.05:
            line = line.replace("  ", "   ", 1)
        out.append(line.rstrip())
    if rng.random() < 0.3:
        out.insert(rng.randint(1, max(1, len(out) - 1)), rng.choice(["~ ~ .  ,", "| |   .", "_ _ _ _", "  . : ."]))
    return "\n".join(out) + "\n"


def footer(rng: random.Random, received: date) -> str:
    return rng.choice([
        f"\n-- scanned {mdy(received)} HBCH mailroom  pg 1/1 --",
        f"\n[HBCH PATIENT FINANCIAL SERVICES  RECEIVED {mdy(received)}]",
        f"\nFAX RECEIVED {mdy(received)} 10:{rng.randint(10, 59)}   P.01",
        f"\nRECEIVED {received.strftime('%b %d %Y').upper()}  - mailroom",
    ])


def deductions(gross_cents: int, fed_pct: int) -> tuple[int, int, int, int, int]:
    """Federal, Social Security, Medicare, SDI and net pay for one stub. Same gross, same net."""
    fed = gross_cents * fed_pct // 100
    ss = (gross_cents * 62 + 50) // 1000
    med = (gross_cents * 145 + 500) // 10000
    sdi = (gross_cents * 11 + 50) // 1000
    return fed, ss, med, sdi, gross_cents - fed - ss - med - sdi


def stub_net(gross_cents: int, fed_pct: int) -> int:
    return deductions(gross_cents, fed_pct)[4]


def pay_stub(rng, *, employer, title, name, emp_id, frequency, gross_cents, pay_date: date,
             received: date, ytd_periods: int, hourly: bool, hours: float | None = None, rate_cents: int | None = None,
             extra_text: str = "", fed_pct: int | None = None, ytd_cents: int | None = None) -> str:
    days = PERIOD_DAYS[frequency]
    start = pay_date - timedelta(days=days + 4)
    end = pay_date - timedelta(days=5)
    hours = hours if hours is not None else HOURS[frequency]
    rate = (rate_cents / 100) if rate_cents is not None else gross_cents / 100 / hours
    fed, ss, med, sdi, net = deductions(gross_cents, fed_pct if fed_pct is not None else rng.randint(4, 11))
    ytd = ytd_cents if ytd_cents is not None else gross_cents * ytd_periods
    lines = [
        f"{employer}",
        f"{rng.randint(100, 9999)} {rng.choice(['INDUSTRIAL', 'HARBOR', 'COMMERCE', 'MARKET'])} WAY   CA",
        "                         EARNINGS STATEMENT",
        f"Employee: {name.upper()}        Emp ID: {emp_id}",
        f"Position: {title}",
        f"Pay Period: {mdy(start)} - {mdy(end)}     Pay Date: {mdy(pay_date)}",
        f"Pay Frequency: {frequency.title()}",
        "-" * 62,
        "EARNINGS            RATE      HOURS     THIS PERIOD        YTD",
    ]
    if hourly:
        lines.append(f"Regular            {rate:6.2f}    {hours:6.2f}    {usd(gross_cents):>11}   {usd(ytd):>11}")
    else:
        lines.append(f"Salary                                  {usd(gross_cents):>11}   {usd(ytd):>11}")
    lines += [
        f"GROSS PAY                               {usd(gross_cents):>11}   {usd(ytd):>11}",
        "DEDUCTIONS",
        f"  Federal Income Tax                    {usd(fed):>9}",
        f"  Social Security                       {usd(ss):>9}",
        f"  Medicare                              {usd(med):>9}",
        f"  CA SDI                                {usd(sdi):>9}",
        f"NET PAY                                 {usd(net):>9}",
        "-" * 62,
    ]
    if extra_text:
        lines.append(extra_text)
    text = ocr(rng, "\n".join(lines))
    return text + footer(rng, received) + "\n"


def bank_statement(rng, *, bank, name, period_end: date, deposits: list[tuple[date, str, int]],
                   savings_cents: int | None, received: date, period_start: date | None = None) -> str:
    start = period_start or period_end.replace(day=1)
    assert all(start <= d[0] <= period_end for d in deposits), "deposits must fall inside the statement period"
    assert period_end < received, "a statement can't cover days after it was received"
    begin = rng.randint(20_000, 300_000)
    dep_total = sum(d[2] for d in deposits)
    wd = dep_total * rng.randint(85, 105) // 100
    lines = [
        f"{bank}",
        f"Statement Period {mdy(start)} - {mdy(period_end)}",
        f"Member: {name.upper()}       Account ending {rng.randint(1000, 9999)}",
        "",
        "CHECKING SUMMARY",
        f"  Beginning balance        {usd(begin):>12}",
        f"  Deposits                 {usd(dep_total):>12}",
        f"  Withdrawals              {usd(-wd):>12}",
        f"  Ending balance           {usd(begin + dep_total - wd):>12}",
        "",
        "DEPOSITS AND CREDITS",
    ]
    for d, desc, amt in deposits:
        lines.append(f"  {d.strftime('%m/%d')}  {desc:<38} {usd(amt):>10}")
    if savings_cents is not None:
        lines += [
            "",
            f"SAVINGS SUMMARY  (Share Savings ending {rng.randint(1000, 9999)})",
            f"  Ending balance           {usd(savings_cents):>12}",
            f"  Dividends paid           {usd(savings_cents * 4 // 10000):>12}",
        ]
    lines += ["", "Thank you for banking with us.  Page 1 of 2"]
    return ocr(rng, "\n".join(lines)) + footer(rng, received) + "\n"


def tax_return(rng, *, name, tax_year: int, filing_status: str, dependents: int, wages_cents: int,
               other_cents: int, received: date) -> str:
    total = wages_cents + other_cents
    lines = [
        f"Form 1040   U.S. Individual Income Tax Return   {tax_year}",
        "(copy - summary page)",
        f"Filing Status: {filing_status}",
        f"Your first name and middle initial / Last name:  {name.upper()}",
        f"Your social security number: XXX-XX-{rng.randint(1000, 9999)}",
        f"Dependents: {dependents}",
        "Income",
        f" 1a  Total amount from Form(s) W-2, box 1 ...........  {usd(wages_cents):>11}",
        f" 8   Additional income from Schedule 1, line 10 ......  {usd(other_cents):>11}",
        f" 9   Total income ....................................  {usd(total):>11}",
        f" 10  Adjustments to income ...........................  {usd(0):>11}",
        f" 11  Adjusted gross income ...........................  {usd(total):>11}",
        f" 12  Standard deduction ..............................  {usd(14_600_00 if filing_status == 'Single' else 21_900_00):>11}",
        "",
        "Sign Here   Under penalties of perjury, I declare that I have examined this return...",
        f"Your signature: /s/ {name}        Date: 04/{rng.randint(1, 15):02d}/{tax_year + 1}",
    ]
    return ocr(rng, "\n".join(lines)) + footer(rng, received) + "\n"


def employer_letter(rng, *, employer, title, name, hr_name, since: date, letter_date: date,
                    annual_cents: int | None, hourly_cents: int | None, weekly_hours: int | None,
                    received: date) -> str:
    if annual_cents is not None:
        pay = f"current annual salary is ${usd(annual_cents)}"
    else:
        pay = f"rate of pay is ${usd(hourly_cents)} per hour, for a regular schedule of {weekly_hours} hours per week"
    lines = [
        f"{employer}",
        f"{rng.randint(100, 9999)} {rng.choice(['HARBOR', 'MAIN', 'FRONT', 'MISSION'])} ST",
        "",
        f"{letter_date.strftime('%B %d, %Y')}",
        "",
        "To Whom It May Concern:",
        "",
        f"This letter confirms that {name} has been employed with {employer.title()} since",
        f"{since.strftime('%B %Y')} in the position of {title}. Their {pay}.",
        "Employment is ongoing. Please contact our office with any questions.",
        "",
        "Sincerely,",
        f"{hr_name}",
        "Human Resources",
    ]
    return ocr(rng, "\n".join(lines)) + footer(rng, received) + "\n"


def benefit_letter(rng, *, kind, name, household: int | None, amount_cents: int | None, letter_date: date,
                   county: str, received: date) -> str:
    if kind == "CALFRESH":
        lines = [
            f"COUNTY OF {county} - DEPARTMENT OF SOCIAL SERVICES",
            "NOTICE OF ACTION",
            "CalFresh Approval",
            f"Date: {mdy(letter_date)}",
            f"Case name: {name.upper()}",
            "",
            f"Your application for CalFresh dated {mdy(letter_date - timedelta(days=rng.randint(12, 30)))} is APPROVED.",
            f"Number of people in your CalFresh household: {household}",
            f"Your monthly CalFresh benefit: ${usd(amount_cents)}",
            f"Benefits are issued to your EBT card beginning {mdy(letter_date.replace(day=1))}.",
            "Certification period: 12 months. You must report changes as required.",
            "",
            "Questions? Call your eligibility worker.",
        ]
    elif kind == "MEDI_CAL":
        lines = [
            f"COUNTY OF {county} - DEPARTMENT OF SOCIAL SERVICES",
            "NOTICE OF ACTION",
            "Medi-Cal Approval",
            f"Date: {mdy(letter_date)}",
            f"Beneficiary: {name.upper()}",
            "",
            f"You are approved for full scope Medi-Cal with no share of cost beginning {mdy(letter_date.replace(day=1))}.",
            "Keep this notice. Your Benefits Identification Card (BIC) will be mailed separately.",
        ]
    elif kind == "EDD":
        lines = [
            "EMPLOYMENT DEVELOPMENT DEPARTMENT - STATE OF CALIFORNIA",
            "NOTICE OF UNEMPLOYMENT INSURANCE AWARD",
            f"Date mailed: {mdy(letter_date)}",
            f"Claimant: {name.upper()}",
            "",
            f"Weekly benefit amount: ${usd(amount_cents)}",
            f"Maximum benefit amount: ${usd(amount_cents * 26)}",
            "Claim effective date: " + mdy(letter_date - timedelta(days=rng.randint(10, 40))),
        ]
    else:  # SSA
        lines = [
            "SOCIAL SECURITY ADMINISTRATION",
            "Retirement, Survivors and Disability Insurance",
            f"Date: {mdy(letter_date)}",
            f"{name.upper()}",
            "",
            "This letter is proof of the benefits you receive.",
            f"Beginning December {letter_date.year - 1}, the full monthly Social Security benefit is ${usd(amount_cents)}.",
            "We deduct $0.00 for medical insurance premiums each month.",
        ]
    return ocr(rng, "\n".join(lines)) + footer(rng, received) + "\n"


def self_attestation(rng, *, name, household: int, monthly_cents: int, source: str, signed: date,
                     received: date) -> str:
    if monthly_cents == 0:
        stmt = f"I have no income at this time. {source}"
    else:
        stmt = f"My household's total income is about ${usd(monthly_cents)} per month from {source}."
    lines = [
        "HALCYON BAY COMMUNITY HOSPITAL",
        "Financial Assistance Program - Self-Attestation of Income",
        "",
        f"I, {name}, live in a household of {household} people.",
        stmt,
        "I do not have pay stubs or other income documents to send.",
        "I declare under penalty of perjury that the information above is true.",
        "",
        f"Signature: {name}            Date: {mdy(signed)}",
    ]
    return ocr(rng, "\n".join(lines)) + footer(rng, received) + "\n"


def shelter_letter(rng, *, shelter, name, since: date, letter_date: date, received: date) -> str:
    lines = [
        f"{shelter}",
        "",
        f"{letter_date.strftime('%B %d, %Y')}",
        "",
        "To whom it may concern,",
        f"{name} has been staying at our shelter since {since.strftime('%B %Y')} and has no fixed address.",
        "Mail for this person can be sent care of our front desk.",
        "",
        "Case manager, intake office",
    ]
    return ocr(rng, "\n".join(lines)) + footer(rng, received) + "\n"
