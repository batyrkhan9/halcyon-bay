"""Fictional names, places and employers. Every person and business here is made up."""

from __future__ import annotations

import json
from pathlib import Path

PERSONAS_PATH = Path(__file__).resolve().parents[1] / "crs" / "personas.json"


def load_personas() -> dict[str, dict]:
    data = json.loads(PERSONAS_PATH.read_text(encoding="utf-8"))
    return {p["id"]: dict(p["identity"], name=p["name"]) for p in data["personas"]}


PERSONA_SURNAMES = frozenset({
    "OKAFOR", "WHITFIELD", "REYES", "LINDQVIST", "DALTON", "MORRISSEY", "BELLAMY",
    "VENKATESAN", "HOLLOWAY", "KOWALCZYK", "SZABO", "ANAND", "BRENNAN", "PETTIGREW",
    "FARRAGUT", "OYELARAN", "CASTELLANOS", "ABERNATHY", "NAKAMURA", "WHITCOMB",
})

FEMALE_FIRST = [
    "Maria", "Ana", "Rosa", "Guadalupe", "Elena", "Sofia", "Lucia", "Carmen", "Isabel", "Veronica",
    "Jennifer", "Jessica", "Ashley", "Amanda", "Sarah", "Emily", "Megan", "Rachel", "Lauren", "Nicole",
    "Linh", "Mai", "Thao", "Kim", "Hoa", "Mei", "Jia", "Yuki", "Aiko", "Min-ji",
    "Fatima", "Amina", "Leila", "Noor", "Zainab", "Priscilla", "Imani", "Keisha", "Tanisha", "Aaliyah",
    "Deborah", "Patricia", "Barbara", "Linda", "Susan", "Karen", "Donna", "Sharon", "Carol", "Brenda",
    "Marisol", "Yesenia", "Araceli", "Esperanza", "Leticia", "Graciela", "Paola", "Daniela", "Valeria", "Ximena",
    "Hannah", "Olivia", "Chloe", "Grace", "Abigail", "Madison", "Kayla", "Brianna", "Destiny", "Alyssa",
    "Rajni", "Anjali", "Deepa", "Kavya", "Sunita", "Malia", "Leilani", "Teresa", "Josefina", "Beatriz",
]
MALE_FIRST = [
    "Jose", "Juan", "Luis", "Carlos", "Miguel", "Jorge", "Francisco", "Antonio", "Manuel", "Ricardo",
    "Michael", "David", "James", "Robert", "John", "William", "Christopher", "Matthew", "Joshua", "Andrew",
    "Minh", "Tuan", "Duc", "Hung", "Bao", "Wei", "Jian", "Hiroshi", "Kenji", "Jae",
    "Omar", "Ahmed", "Yusuf", "Hassan", "Tariq", "Darnell", "Marquis", "Terrell", "Jamal", "Andre",
    "Gary", "Larry", "Dennis", "Ronald", "Kenneth", "Steven", "Donald", "Raymond", "Gregory", "Frank",
    "Alejandro", "Eduardo", "Ernesto", "Rogelio", "Arturo", "Ramon", "Hector", "Rafael", "Sergio", "Mario",
    "Ethan", "Tyler", "Brandon", "Austin", "Kyle", "Dylan", "Justin", "Caleb", "Logan", "Noah",
    "Arjun", "Rohan", "Vikram", "Sanjay", "Ravi", "Keoni", "Kai", "Tomasz", "Pedro", "Rodrigo",
]
NICKNAMES = {
    "Michael": "Mike", "David": "Dave", "James": "Jim", "Robert": "Bob", "John": "Jack",
    "William": "Bill", "Christopher": "Chris", "Matthew": "Matt", "Joshua": "Josh", "Andrew": "Andy",
    "Kenneth": "Ken", "Steven": "Steve", "Donald": "Don", "Raymond": "Ray", "Gregory": "Greg",
    "Frank": "Frankie", "Ronald": "Ron", "Larry": "Lawrence", "Dennis": "Denny", "Gary": "Gar",
    "Jennifer": "Jen", "Jessica": "Jess", "Amanda": "Mandy", "Patricia": "Patty", "Deborah": "Debbie",
    "Barbara": "Barb", "Susan": "Sue", "Rebecca": "Becky", "Elizabeth": "Liz", "Abigail": "Abby",
    "Francisco": "Paco", "Jose": "Pepe", "Guadalupe": "Lupe", "Josefina": "Josie", "Alejandro": "Alex",
    "Eduardo": "Eddie", "Antonio": "Tony", "Ricardo": "Rick", "Rafael": "Rafa", "Isabel": "Isa",
    "Teresa": "Terry", "Veronica": "Ronnie", "Daniela": "Dani", "Valeria": "Vale", "Samantha": "Sam",
    "Margaret": "Maggie", "Nicole": "Nikki", "Emily": "Em", "Hannah": "Hanna",
}
LAST_NAMES = [
    "Garcia", "Hernandez", "Lopez", "Martinez", "Gonzalez", "Rodriguez", "Perez", "Sanchez", "Ramirez", "Torres",
    "Flores", "Rivera", "Gomez", "Diaz", "Cruz", "Morales", "Ortiz", "Gutierrez", "Chavez", "Ramos",
    "Mendoza", "Ruiz", "Alvarez", "Castillo", "Jimenez", "Vasquez", "Romero", "Herrera", "Medina", "Aguilar",
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Wilson", "Anderson", "Taylor",
    "Thomas", "Moore", "Jackson", "Martin", "Lee", "Thompson", "White", "Harris", "Clark", "Lewis",
    "Robinson", "Walker", "Young", "Allen", "King", "Wright", "Scott", "Green", "Baker", "Adams",
    "Nguyen", "Tran", "Le", "Pham", "Huynh", "Vo", "Dang", "Bui", "Do", "Ho",
    "Wang", "Li", "Zhang", "Chen", "Liu", "Huang", "Wu", "Lin", "Zhou", "Xu",
    "Kim", "Park", "Choi", "Jung", "Kang", "Tanaka", "Suzuki", "Watanabe", "Sato", "Ito",
    "Patel", "Shah", "Singh", "Kumar", "Gupta", "Mehta", "Rao", "Iyer", "Desai", "Joshi",
    "Washington", "Jefferson", "Banks", "Coleman", "Freeman", "Bryant", "Hayes", "Mitchell", "Carter", "Bell",
    "Kealoha", "Kahananui", "Fonoti", "Tuiasosopo", "Faleolo", "Silva", "Souza", "Pereira", "Costa", "Almeida",
    "Novak", "Kowalski", "Petrov", "Ivanova", "Haddad", "Nasser", "Khalil", "Abdullah", "Rahman", "Hussain",
    "O'Brien", "Murphy", "Sullivan", "Kelly", "Walsh", "McCarthy", "Fitzgerald", "Doyle", "Quinn", "Gallagher",
    "Delgado", "Navarro", "Salazar", "Cortez", "Contreras", "Fuentes", "Espinoza", "Valencia", "Ibarra", "Zamora",
]

# Fictional towns around Halcyon Bay, CA, with plausible California ZIPs.
TOWNS = [
    ("HALCYON BAY", "95081", 30), ("HALCYON BAY", "95082", 18), ("PORT ELLERY", "95084", 14),
    ("MIRADOR", "95086", 12), ("SANTA LUCITA", "95091", 11), ("CYPRESS FLATS", "95094", 10),
    ("ARROYO VERDE", "95097", 7), ("LAS BRISAS", "95099", 6), ("POINT CORRIN", "95103", 5),
    ("VISTA SERENA", "95107", 4),
]
STREET_NAMES = [
    "HARBOR", "SEAGULL", "TIDEWATER", "CYPRESS", "MAGNOLIA", "LIGHTHOUSE", "BAYVIEW", "SANDPIPER",
    "MARINER", "PELICAN", "CORAL", "DRIFTWOOD", "KELP", "OTTER", "SALT MARSH", "ESTERO", "LAGUNA",
    "MONTEREY", "SEQUOIA", "MANZANITA", "OAKWOOD", "ALDER", "WILLOW", "CHESTNUT", "JUNIPER",
    "PALOMA", "LOS ROBLES", "VALLE VERDE", "ALTA MIRA", "EL CAMINO", "MISSION", "FRONT", "MAIN",
    "FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "SIXTH", "ELLERY", "CORRIN", "MIRADOR", "LUCITA",
]
STREET_SUFFIX = [("ST", "Street"), ("AVE", "Avenue"), ("DR", "Drive"), ("RD", "Road"), ("LN", "Lane"),
                 ("CT", "Court"), ("WAY", "Way"), ("BLVD", "Boulevard"), ("PL", "Place")]
SHELTERS = [
    ("HARBOR LIGHT SHELTER 210 FRONT ST", "HALCYON BAY", "95081"),
    ("SAFE HARBOR FAMILY CENTER 88 MISSION ST", "PORT ELLERY", "95084"),
]

EMPLOYERS = [
    ("BAYLINE LOGISTICS INC", "Warehouse associate"),
    ("PORT ELLERY CANNERY CO", "Line worker"),
    ("MIRADOR GROCERY CO-OP", "Cashier"),
    ("CYPRESS FLATS AUTO BODY", "Technician"),
    ("SUNSET COAST HOME CARE", "Home care aide"),
    ("PACIFIC RIM JANITORIAL", "Custodian"),
    ("SANTA LUCITA FARMS", "Field supervisor"),
    ("GOLDEN HOUR SENIOR LIVING", "Caregiver"),
    ("HARBOR POINT HOTEL", "Housekeeper"),
    ("TIDEWATER CONSTRUCTION", "Laborer"),
    ("SEASIDE DENTAL GROUP", "Dental assistant"),
    ("CALDER FREIGHT LINES", "Driver"),
    ("MARISOL CLEANING SERVICES", "Cleaner"),
    ("HALCYON BAY UNIFIED SCHOOL DIST", "Instructional aide"),
    ("ARROYO VERDE NURSERY", "Nursery worker"),
    ("POINT CORRIN BOATWORKS", "Mechanic"),
    ("LAS BRISAS RESTAURANT GROUP", "Line cook"),
    ("VISTA SERENA MEDICAL OFFICES", "Medical receptionist"),
    ("BLUE KELP SOFTWARE LLC", "Software engineer"),
    ("COASTAL VALLEY ENERGY", "Field technician"),
    ("ELLERY HARDWARE SUPPLY", "Sales associate"),
    ("MIRADOR PUBLIC LIBRARY", "Library assistant"),
    ("SANDPIPER CHILD CARE CENTER", "Teacher"),
    ("OTTER BAY AQUARIUM", "Guest services"),
]
BANKS = ["SEASIDE COMMUNITY CREDIT UNION", "HALCYON BAY FEDERAL CREDIT UNION", "PACIFIC TIDE BANK",
         "COASTLINE SAVINGS BANK"]

INSURERS = ["BLUE PACIFIC PPO", "GOLDEN STATE HEALTH HMO", "COASTAL CARE PLAN", "MEDICARE", "MEDI-CAL"]

# Staff (HR export). S-001..S-004 match core/dev_seed.py ids and roles.
STAFF = [
    # id, first, last, role, limit, dob, address, city, zip, hired, active
    ("S-001", "Dana", "Morales", "FINANCIAL_COUNSELOR", "5000.00", "1986-04-22", "331 SEAGULL WAY", "HALCYON BAY", "95081"),
    ("S-002", "Luis", "Ferreira", "REVENUE_CYCLE_DIRECTOR", "", "1971-09-13", "18 LIGHTHOUSE CT", "POINT CORRIN", "95103"),
    ("S-003", "Priya", "Raman", "COMPLIANCE_OFFICER", "0.00", "1979-02-07", "902 MAGNOLIA AVE", "MIRADOR", "95086"),
    ("S-004", "Tomas", "Brandt", "FINANCIAL_COUNSELOR", "5000.00", "1983-11-29", "4417 DRIFTWOOD LN", "PORT ELLERY", "95084"),
    ("S-005", "Gloria", "Hutchins", "FINANCIAL_COUNSELOR", "5000.00", "1961-06-30", "77 OAKWOOD DR", "SANTA LUCITA", "95091"),
    ("S-006", "Walter", "Pruitt", "FINANCIAL_COUNSELOR", "5000.00", "1958-12-03", "1290 ALDER ST", "CYPRESS FLATS", "95094"),
    ("S-007", "Keanu", "Makoa", "BILLING_SPECIALIST", "0.00", "1992-03-18", "560 CORAL ST", "HALCYON BAY", "95082"),
    ("S-008", "Renee", "Okonkwo-Hale", "BILLING_SPECIALIST", "0.00", "1988-08-09", "41 PELICAN PL", "HALCYON BAY", "95081"),
    ("S-009", "Marco", "Bellini", "BILLING_SPECIALIST", "0.00", "1990-01-25", "2215 ESTERO RD", "LAS BRISAS", "95099"),
    ("S-010", "Shirin", "Farahani", "BILLING_SPECIALIST", "0.00", "1995-10-14", "7 SANDPIPER CT", "ARROYO VERDE", "95097"),
    ("S-011", "Beatriz", "Ochoa", "PATIENT_ACCESS", "0.00", "1997-05-02", "1408 MISSION ST", "PORT ELLERY", "95084"),
    ("S-012", "Dmitri", "Volkov", "PATIENT_ACCESS", "0.00", "1993-07-21", "350 KELP AVE", "HALCYON BAY", "95082"),
    ("S-013", "Hana", "Yoshida", "PATIENT_ACCESS", "0.00", "1999-12-11", "89 OTTER LN", "MIRADOR", "95086"),
    ("S-014", "Curtis", "Langley", "BILLING_SPECIALIST", "0.00", "1984-04-04", "613 JUNIPER WAY", "VISTA SERENA", "95107"),
]
STAFF_SURNAMES = frozenset(s[2].upper() for s in STAFF)
COUNSELORS_NEW = ("S-001", "S-004")        # follow the current policy
COUNSELORS_OLD = ("S-005", "S-006")        # old habits
BILLING_STAFF = ("S-007", "S-008", "S-009", "S-010", "S-014")
ACCESS_STAFF = ("S-011", "S-012", "S-013")
