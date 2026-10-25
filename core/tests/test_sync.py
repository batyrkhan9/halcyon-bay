import csv
from datetime import date

import pytest

from core.agent import Agent
from core.reader import Reader, case_file
from core.scripted import ScriptedClaude, reading
from core.store import Store
from core.sync import Sync, account_number

HEADERS = {
    "billing/patients.csv": "recorded_on,mrn,last_name,first_name,middle_initial,dob,ssn,address_line1,city,state,zip,phone,registered_on",
    "billing/accounts.csv": "recorded_on,account_no,mrn,service_date,discharge_date,service_type,payer,total_charges,"
                            "insurance_paid,insurance_adjustment,patient_responsibility,first_statement_date,status",
    "billing/transactions.csv": "recorded_on,txn_id,account_no,posted_on,txn_type,amount,note",
    "billing/statements.csv": "recorded_on,statement_id,account_no,sent_on,kind,amount_due,mailed_to,returned_mail",
    "billing/payment_plans.csv": "recorded_on,plan_id,mrn,account_nos,start_date,monthly_amount,months,status,"
                                 "missed_payments,last_payment_on,stopped_on,stopped_by,stop_reason",
    "fa/applications.csv": "recorded_on,application_id,applicant_id,mrn_given,accounts_given,first_name,last_name,dob,ssn,"
                           "phone,address_line1,city,state,zip,household_size,income_stated,income_verified,income_proof,"
                           "monetary_assets,medi_cal,homeless,received_on,form_version,status,decision,decision_date,"
                           "decided_by,reason",
    "fa/notes.csv": "recorded_on,note_id,application_id,account_no,author,written_on,text",
    "agency/placements.csv": "recorded_on,agency_ref,client_account,debtor_name,debtor_dob,debtor_address,debtor_phone,"
                             "placed_date,placed_balance,current_balance,status,last_activity",
    "agency/requests.csv": "recorded_on,request_id,agency_ref,client_account,requested_action,requested_date,agency_note",
    "documents/index.csv": "recorded_on,doc_id,application_id,name_on_document,doc_type,received_on,file",
    "staff/staff.csv": "recorded_on,staff_id,first_name,last_name,role,approval_limit,email,dob,address_line1,city,"
                       "state,zip,phone,active",
}

STUB = "ACME CO\nEARNINGS STATEMENT\nEmployee: ANA REYES\nPay Frequency: Bi-Weekly\nGROSS PAY  1,269.23\n"


def world(tmp_path, rows: dict):
    root = tmp_path / "world"
    for file, header in HEADERS.items():
        path = root / file
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header.split(","), restval="")
            writer.writeheader()
            writer.writerows(rows.get(file, []))
    (root / "documents" / "files").mkdir(parents=True, exist_ok=True)
    (root / "documents" / "files" / "DOC-100001.txt").write_text(STUB)
    return root


def account(recorded_on, account_no, mrn, owed, status="OPEN", first_bill="2026-05-01"):
    return dict(recorded_on=recorded_on, account_no=account_no, mrn=mrn, service_date="2026-04-20",
                discharge_date="2026-04-20", service_type="ER", payer="SELF PAY", total_charges=owed,
                insurance_paid="0.00", insurance_adjustment="0.00", patient_responsibility=owed,
                first_statement_date=first_bill, status=status)


BASE = {
    "billing/patients.csv": [
        dict(recorded_on="2025-03-01", mrn="M1000001", last_name="REYES", first_name="ANA", dob="1990-01-02",
             address_line1="1 OLD RD", city="HALCYON BAY", state="CA", zip="95081"),
        dict(recorded_on="2026-02-01", mrn="M1000001", last_name="REYES", first_name="ANA", dob="1990-01-02",
             address_line1="2 NEW RD", city="HALCYON BAY", state="CA", zip="95081"),
        dict(recorded_on="2025-01-01", mrn="M1000009", last_name="KIM", first_name="LEE", dob="1980-05-05",
             address_line1="HOMELESS", city="HALCYON BAY", state="CA"),
    ],
    "billing/accounts.csv": [
        account("2026-05-01", "HB26000001", "M1000001", "3300.00"),
        account("2026-05-01", "HB26000002", "M1000001", "450.00"),
        account("2026-05-01", "HB26000003", "M1000001", "0.00", status="PAID"),
        account("2026-05-01", "HB26000009", "M1000009", "1200.00"),
    ],
    "billing/statements.csv": [
        dict(recorded_on="2026-06-01", statement_id="ST0000001", account_no="HB26000009", sent_on="2026-06-01",
             kind="FINAL_NOTICE", amount_due="1200.00"),
    ],
    "staff/staff.csv": [
        dict(recorded_on="2025-01-01", staff_id="S-001", first_name="Dana", last_name="Morales",
             role="FINANCIAL_COUNSELOR", approval_limit="5000.00", dob="1986-04-22", active="Y"),
        dict(recorded_on="2025-01-01", staff_id="S-002", first_name="Luis", last_name="Ferreira",
             role="REVENUE_CYCLE_DIRECTOR", dob="1971-09-13", active="Y"),
        dict(recorded_on="2025-01-01", staff_id="S-009", first_name="Lee", last_name="Kim",
             role="BILLING_SPECIALIST", dob="1980-05-05", active="Y"),
    ],
    "fa/applications.csv": [
        dict(recorded_on="2026-07-01", application_id="FA-26-00001", applicant_id="APL-1", mrn_given="M1000001",
             accounts_given="HB-2600-0001", first_name="Ana", last_name="Reyes", dob="1990-01-02",
             household_size="3", income_stated="30000", medi_cal="N", homeless="N", received_on="2026-07-01",
             form_version="2025", status="RECEIVED"),
    ],
    "documents/index.csv": [
        dict(recorded_on="2026-07-01", doc_id="DOC-100001", application_id="FA-26-00001", name_on_document="Ana Reyes",
             doc_type="PAY_STUB", received_on="2026-07-01", file="files/DOC-100001.txt"),
    ],
    "fa/notes.csv": [
        dict(recorded_on="2026-07-01", note_id="N0000001", application_id="FA-26-00001", author="S-001",
             written_on="2026-07-01", text="Pt dropped off app with stubs."),
    ],
}


@pytest.fixture
def synced(tmp_path):
    store = Store()
    sync = Sync(store, sources=[world(tmp_path, BASE)])
    sync.onboard()
    return store, sync


def test_onboarding_loads_history_only_and_latest_wins(synced):
    store, _ = synced
    assert store.today() == date(2026, 6, 30)
    assert store.record("patient", "M1000001")["address_line1"] == "2 NEW RD"
    assert store.record("application", "FA-26-00001") is None          # recorded 2026-07-01: the future
    assert store.account("HB26000001")["billed_cents"] == 3_300_00
    assert store.all("SELECT * FROM work_items") == []


def test_staff_roles_and_staff_who_are_patients(synced):
    store, _ = synced
    assert store.actor("S-001").role == "counselor"
    assert store.actor("S-002").role == "director"
    assert store.actor("S-009").role == "billing_specialist"
    assert store.actor("S-009").patient_ids == frozenset({"M1000009"})


def test_a_live_application_opens_work_for_the_accounts_it_reaches(synced):
    store, sync = synced
    summary = sync.day(date(2026, 7, 1))
    items = {store.work_item(i)["account_id"] for i in summary["opened"]}
    assert items == {"HB26000001", "HB26000002"}                         # listed, and open under the MRN given
    assert "HB26000003" not in store.accounts_for("FA-26-00001")         # paid: nothing to do


def test_the_case_file_has_the_form_the_stub_the_note_and_the_billing_record(synced):
    store, sync = synced
    sync.day(date(2026, 7, 1))
    kinds = {d.kind for d in case_file(store, "HB26000001").documents}
    assert kinds == {"APPLICATION", "PAY_STUB", "NOTE", "BILLING"}
    form = next(d for d in case_file(store, "HB26000001").documents if d.kind == "APPLICATION")
    assert "Household size: 3" in form.text and "ssn" not in form.text.lower()


def test_days_cannot_be_loaded_twice_or_out_of_order(synced):
    _, sync = synced
    sync.day(date(2026, 7, 1))
    with pytest.raises(ValueError):
        sync.day(date(2026, 7, 1))


def test_new_documents_put_a_waiting_item_back_to_work(tmp_path):
    rows = dict(BASE)
    rows["documents/index.csv"] = BASE["documents/index.csv"] + [
        dict(recorded_on="2026-07-02", doc_id="DOC-100002", application_id="FA-26-00001", name_on_document="Ana Reyes",
             doc_type="EMPLOYER_LETTER", received_on="2026-07-02", file="files/DOC-100002.txt")]
    root = world(tmp_path, rows)
    (root / "documents" / "files" / "DOC-100002.txt").write_text("Ana Reyes earns $33,000 a year.")
    store = Store()
    sync = Sync(store, sources=[root])
    sync.onboard()
    item = sync.day(date(2026, 7, 1))["opened"][0]
    sync.gateway.move(store.actor("agent"), item, "SCREENING", "Checking")
    sync.gateway.ask(store.actor("agent"), item, "counselor", "Need proof of income")
    assert sync.day(date(2026, 7, 2))["reopened"] == [item]
    assert store.work_item(item)["state"] == "SCREENING"


def test_agency_requests_are_read_with_their_odd_formats(tmp_path):
    rows = dict(BASE)
    rows["agency/requests.csv"] = [dict(recorded_on="2026-07-01", request_id="GCR-R-00001", agency_ref="GCR-1",
                                        client_account="26000009", requested_action="LAWSUIT",
                                        requested_date="07/15/2026")]
    store = Store()
    sync = Sync(store, sources=[world(tmp_path, rows)])
    sync.onboard()
    opened = sync.day(date(2026, 7, 1))["opened"]
    request = store.one("SELECT * FROM agency_requests WHERE id = 'GCR-R-00001'")
    assert (request["account_id"], request["requested_on"], request["notice_sent_on"]) == \
        ("HB26000009", "2026-07-15", "2026-06-01")
    assert {store.work_item(i)["account_id"] for i in opened} >= {"HB26000009"}


def test_account_numbers_in_every_spelling():
    assert account_number("HB26107411") == account_number("26107411") == account_number("hb-2610-7411") == "HB26107411"
    assert account_number("2610741") is None


STATED_ONLY = lambda w: reading(w, household=("Household size: 3", 3),  # noqa: E731
                                income=[("Income", [("written by the applicant: 30000", 30000, "ANNUAL")])])
WITH_STUB = lambda w: reading(w, household=("Household size: 3", 3),  # noqa: E731
                              income=[("Wages", [("GROSS PAY  1,269.23", 1269.23, "BIWEEKLY")])])


def stub_arrives_on(tmp_path, day):
    rows = dict(BASE)
    rows["documents/index.csv"] = [dict(BASE["documents/index.csv"][0], recorded_on=day, received_on=day)]
    return world(tmp_path, rows)


def test_with_only_the_forms_numbers_the_agent_waits_for_documents(tmp_path):
    store = Store()
    sync = Sync(store, sources=[stub_arrives_on(tmp_path, "2026-07-02")])
    sync.onboard()
    item = sync.day(date(2026, 7, 1))["opened"][0]
    fake = ScriptedClaude({"HB26000001": STATED_ONLY, "HB26000002": STATED_ONLY})
    agent = Agent(store, sync.gateway, Reader(store, call=fake))
    assert agent.work(item).did == "WAITING"
    assert store.work_item(item)["state"] == "NEEDS_INFO"
    assert store.all("SELECT * FROM questions") == []                     # nobody was bothered

    assert item in sync.day(date(2026, 7, 2))["reopened"]                 # the stub came
    fake.scripts["HB26000001"] = WITH_STUB
    assert agent.work(item).did == "PROPOSED"
    assert store.one("SELECT pattern FROM proposals WHERE account_id = 'HB26000001'")["pattern"] is None


def test_after_the_wait_it_asks_for_documents_instead_of_proposing(tmp_path):
    store = Store()
    sync = Sync(store, sources=[stub_arrives_on(tmp_path, "2026-09-30")])
    sync.onboard()
    item = sync.day(date(2026, 7, 1))["opened"][0]
    agent = Agent(store, sync.gateway, Reader(store, call=ScriptedClaude({"HB26000001": STATED_ONLY})))
    agent.work(item)
    day = date(2026, 7, 2)
    while store.work_item(item)["state"] == "NEEDS_INFO":
        sync.day(day)
        day = date.fromordinal(day.toordinal() + 1)
    assert day == date(2026, 7, 16)                                        # back to work after 14 days
    assert agent.work(item).did == "ASKED"
    assert store.one("SELECT * FROM proposals WHERE account_id = 'HB26000001'") is None


def test_the_agent_works_a_synced_account_end_to_end(synced):
    store, sync = synced
    sync.day(date(2026, 7, 1))
    fake = ScriptedClaude({
        account_no: lambda w: reading(w, household=("Household size: 3", 3),
                                      income=[("Wages from Acme", [("GROSS PAY  1,269.23", 1269.23, "BIWEEKLY"),
                                                                   ("written by the applicant: 30000", 30000, "ANNUAL")])])
        for account_no in ("HB26000001", "HB26000002")
    })
    results = Agent(store, sync.gateway, Reader(store, call=fake)).work_open_items()
    assert {r.did for r in results} == {"PROPOSED"}
    proposal = store.one("SELECT * FROM proposals WHERE account_id = 'HB26000001'")
    assert proposal["kind"] == "FREE_CARE"                                # $33,000 for 3 in 2026 is 121%
    used = {e["document_id"] for e in proposal["evidence"]}
    assert "DOC-100001" in used and "FA-26-00001" in used                 # the stub's income, the form's household
    assert proposal["pattern"] is None                                    # documents beat what the form claimed


def test_coverage_lawful_requests_and_approved_accounts(tmp_path):
    rows = dict(BASE)
    rows["fa/applications.csv"] = [
        dict(recorded_on="2026-03-01", application_id="FA-26-00002", applicant_id="APL-2", mrn_given="M1000009",
             accounts_given="HB26000009", first_name="Lee", last_name="Kim", household_size="1", income_stated="9000",
             received_on="2026-02-20", form_version="2025", status="APPROVED", decision="FREE",
             decision_date="2026-03-01", decided_by="S-001"),
        dict(recorded_on="2026-01-10", application_id="FA-26-00003", applicant_id="APL-3", mrn_given="M1000001",
             accounts_given="HB26000001", first_name="Ana", last_name="Reyes", household_size="1",
             income_stated="120000", received_on="2026-01-05", form_version="2025", status="DENIED",
             decision="DENIED", decision_date="2026-01-10", decided_by="S-001"),
    ]
    rows["billing/accounts.csv"] = BASE["billing/accounts.csv"][1:2] + [
        account("2025-12-01", "HB26000001", "M1000001", "3300.00", status="IN_COLLECTIONS", first_bill="2025-12-01"),
        account("2026-05-01", "HB26000009", "M1000009", "1200.00", status="IN_COLLECTIONS"),
        dict(account("2026-07-01", "HB26000010", "M1000009", "800.00"), service_date="2026-06-28"),
    ]
    rows["billing/statements.csv"] = [
        dict(recorded_on="2026-05-01", statement_id="ST1", account_no="HB26000001", sent_on="2026-05-01",
             kind="FINAL_NOTICE", amount_due="3300.00"),
    ]
    rows["agency/requests.csv"] = [
        dict(recorded_on="2026-07-01", request_id="GCR-R-1", client_account="26000001", requested_action="LAWSUIT",
             requested_date="07/01/2026"),
        dict(recorded_on="2026-07-01", request_id="GCR-R-2", client_account="HB26000009", requested_action="LIEN",
             requested_date="07/01/2026"),
    ]
    rows["documents/index.csv"], rows["fa/notes.csv"] = [], []
    store = Store()
    sync = Sync(store, sources=[world(tmp_path, rows)])
    sync.onboard()
    sync.day(date(2026, 7, 1))
    results = {r.account_id: r for r in Agent(store, sync.gateway, Reader(store, call=ScriptedClaude({}))).work_open_items()}

    covered = store.one("SELECT * FROM proposals WHERE account_id = 'HB26000010'")
    assert (covered["kind"], covered["amount_cents"]) == ("FREE_CARE", 800_00)          # the March approval covers it
    referral = store.one("SELECT * FROM proposals WHERE account_id = 'HB26000001'")
    assert (referral["kind"], referral["subject"]) == ("COLLECTIONS_REFERRAL", "agency_request:GCR-R-1")
    assert store.one("SELECT status FROM agency_requests WHERE id = 'GCR-R-2'")["status"] == "BLOCKED"
    assert store.account("HB26000009")["collections_paused"] is True
    assert results["HB26000009"].did == "CLOSED"                                        # already approved: no change


def test_an_open_bankruptcy_stops_a_lawful_request_and_goes_to_the_director(tmp_path):
    rows = dict(BASE)
    rows["billing/patients.csv"] = [dict(BASE["billing/patients.csv"][1], ssn="666701007")]
    rows["billing/accounts.csv"] = [account("2025-12-01", "HB26000001", "M1000001", "3300.00",
                                            status="IN_COLLECTIONS", first_bill="2025-12-01")]
    rows["billing/statements.csv"] = [dict(recorded_on="2026-05-01", statement_id="ST1", account_no="HB26000001",
                                           sent_on="2026-05-01", kind="FINAL_NOTICE", amount_due="3300.00")]
    rows["fa/applications.csv"] = [dict(recorded_on="2026-01-10", application_id="FA-26-00003", mrn_given="M1000001",
                                        accounts_given="HB26000001", household_size="1", income_stated="120000",
                                        received_on="2026-01-05", status="DENIED", decision="DENIED",
                                        decision_date="2026-01-10")]
    rows["agency/requests.csv"] = [dict(recorded_on="2026-07-01", request_id="GCR-R-1", client_account="26000001",
                                        requested_action="LAWSUIT", requested_date="07/01/2026")]
    rows["documents/index.csv"], rows["fa/notes.csv"] = [], []
    store = Store()
    sync = Sync(store, sources=[world(tmp_path, rows)])
    sync.onboard()
    sync.day(date(2026, 7, 1))
    asked = []

    def fake_crs(person):
        asked.append(person["ssn"])
        return {"sent": True, "source": "recorded", "identity": {"result": "PASS", "problems": []}, "deceased": False,
                "bankruptcy": {"open": True, "records": [{"chapter": "13", "status": "OPEN", "case_number": "25-50877"}]},
                "contact": {"found": False}}

    agent = Agent(store, sync.gateway, Reader(store, call=ScriptedClaude({})), crs_check=fake_crs)
    result = agent.work_open_items()[0]
    assert store.one("SELECT status FROM agency_requests WHERE id = 'GCR-R-1'")["status"] == "BLOCKED"
    assert store.account("HB26000001")["collections_paused"] is True
    assert result.did == "ASKED" and "to the director" in result.detail
    assert store.one("SELECT * FROM proposals WHERE kind = 'COLLECTIONS_REFERRAL'") is None
    assert asked == ["666701007"]                                  # checked once, then from the saved record
    assert store.one("SELECT reason FROM audit_log WHERE action = 'crs_check'")["reason"].startswith("CRS (recorded)")
