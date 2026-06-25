"""Placowe stale i progi. Aktualizowac raz/rok (kwota bazowa zmienia sie 1 lipca)."""

# Etat: ustawa o najnizszym wynagrodzeniu zasadniczym w podmiotach leczniczych.
ETAT_BASE = 8181.72  # kwota bazowa od 1.07.2025 (przecietne wynagrodzenie 2024, GUS)
ETAT_COEFF = {
    "specialist": 1.45,  # lekarz ze specjalizacja
    "no_specialization": 1.19,  # lekarz bez specjalizacji
    "intern": 0.95,  # stazysta
}
ETAT_MONTHLY_HOURS = 168  # pelny etat ~168 h/mc

# B2B/kontrakt: rynkowe stawki zl/h (zakresy), implied hours liczymy od mediany.
B2B_RATES = {
    "general_shift": (150, 280),  # dyzur ogolny
    "sor": (170, 300),  # medycyna ratunkowa
    "anesthesiology": (250, 500),  # anestezjologia / OIT
    "radiology": (250, 350),
    "pathology": (250, 350),
}

# Progi implied hours [h/mc]. ponytail: heurystyka ze strojeniem, podnies jesli za czula.
THRESHOLD_HEAVY = 300  # ciezkie dyzury, ale mozliwe
THRESHOLD_IMPLAUSIBLE = 400  # >13 h kazdego dnia miesiaca -> ponad model godzinowy

# Prog kandydata: roczna SUMA dochodu musi PRZEKRACZAC te kwote, inaczej drobnica.
# Sledzimy naduzycia -> nie interesuja nas slabo zarabiajacy. ponytail: tunable.
MIN_INCOME = 300_000
