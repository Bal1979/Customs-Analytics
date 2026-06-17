"""Tariferingslag — opslag af toldsatser pr. varekode og oprindelsesland.

Kernen i told-motoren: *givet en HS-kode og et oprindelsesland → hvad er
MFN-satsen (erga omnes), findes der en præferencesats via en aftale, og hvad er
dermed den "forventede" sats?* Tjekkene i `duty_checks.py` bygger oven på dette.

Datakilde: **officiel TARIC bulk** (DG TAXUD) er valgt produktionskilde og synkes
via `tools/sync_taric.py`. Indtil da kører laget på et **kurateret seed**
(`reference/tariff/`), så motoren er fuldt funktionel og testbar. Schemaet er det
samme, så seed udskiftes 1:1 med fuld TARIC-data uden ændringer i opslags-API'et.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional

REFERENCE = Path(__file__).resolve().parent.parent / "reference" / "tariff"

# Standard-GSP: forenklet reduktion (officielt: −3,5 pct.point for ikke-følsomme,
# −20 % for følsomme tekstiler). Erstattes af reelle TARIC-satser ved fuld sync.
GSP_STANDARD_REDUCTION = Decimal("0.035")


def _norm_date(date: Optional[str]) -> Optional[str]:
    """Normalisér importdato til ISO 'YYYY-MM-DD'. Håndterer både '2025-08-11' og
    DMS-kompakt '20260126130106+00'. None/uigenkendeligt → None (= aktuelt gældende)."""
    if not date:
        return None
    s = str(date).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return None


@dataclass
class DutyLookup:
    """Resultat af et tarif-opslag for (HS-kode, oprindelsesland)."""

    hs_code: Optional[str]
    origin: Optional[str]
    mfn_rate: Optional[Decimal]            # tredjelands-/erga omnes-sats
    preferential_rate: Optional[Decimal]   # bedste tilgængelige præferencesats
    arrangement: Optional[str]             # aftalens navn (fx "Vietnam", "GSP+")
    arrangement_type: Optional[str]        # fta/customs_union/gsp_plus/eba/gsp_standard
    is_quota: bool = False                  # præferencen gælder kun inden for et toldkontingent

    @property
    def has_preference(self) -> bool:
        return self.arrangement is not None and self.preferential_rate is not None

    @property
    def potential_saving_rate(self) -> Optional[Decimal]:
        """Forskellen mellem MFN og bedste præferencesats (mulig besparelse i pct.)."""
        if self.mfn_rate is None or self.preferential_rate is None:
            return None
        diff = self.mfn_rate - self.preferential_rate
        return diff if diff > 0 else Decimal(0)


class TariffDatabase:
    """Indlæser og slår op i tarif-referencedata (seed eller fuld TARIC)."""

    def __init__(self, reference_dir: Path = REFERENCE):
        self._mfn: dict[str, Decimal] = {}
        self._descriptions: dict[str, str] = {}
        self._arrangements: dict[str, dict] = {}
        self._no_preference: set[str] = set()
        self._load(reference_dir)

    def _load(self, ref: Path) -> None:
        # Foretræk synket TARIC-data (mfn_rates.csv / arrangements.json) hvis det
        # findes; ellers det kuraterede seed. Synket data skrives af sync_taric.py.
        mfn_file = ref / "mfn_rates.csv"
        if not mfn_file.exists():
            mfn_file = ref / "seed_mfn_rates.csv"
        arr_file = ref / "arrangements.json"
        if not arr_file.exists():
            arr_file = ref / "seed_arrangements.json"
        self.source = mfn_file.name

        with mfn_file.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                code = (row.get("hs6") or row.get("hs_code") or "").strip()
                if not code:
                    continue
                self._mfn[code] = Decimal(row["mfn_rate"])
                self._descriptions[code] = row.get("description", "")
        data = json.loads(arr_file.read_text(encoding="utf-8"))
        self._arrangements = data.get("arrangements", {})
        self._no_preference = set(data.get("no_preference", []))

        # Per-HS præferencer fra Trader Export (hvis synket). Vinder over de
        # kuraterede per-land-aftaler, da de er HS-specifikke og autoritative.
        self._pref: dict[str, dict[str, Decimal]] = {}
        self._country_groups: dict[str, list[str]] = {}
        self._area_name: dict[str, str] = {}
        pref_file = ref / "preferential_rates.csv"
        geo_file = ref / "geo_areas.json"
        if pref_file.exists() and geo_file.exists():
            # _pref[hs][area] = liste af (date_start, date_end, rate, is_quota) — alle perioder.
            with pref_file.open(encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    self._pref.setdefault(row["hs_code"], {}).setdefault(row["area"], []).append(
                        (row.get("date_start", ""), row.get("date_end", ""),
                         Decimal(row["rate"]), row.get("is_quota") == "1"))
            geo = json.loads(geo_file.read_text(encoding="utf-8"))
            self._country_groups = geo.get("country_groups", {})
            self._area_name = geo.get("area_name", {})

        # Temporal tredjelandssats (MFN 103 + autonom suspension 112), erga omnes.
        # Når til stede vinder den over det nuværende eVita-snapshot og er dato-bevidst,
        # så en suspenderet kode giver 0 % på importdatoen (EDR fejl-flagges ikke).
        self._tc: dict[str, list] = {}
        tc_file = ref / "third_country_rates.csv"
        if tc_file.exists():
            with tc_file.open(encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    self._tc.setdefault(row["hs_code"], []).append(
                        (row.get("date_start", ""), row.get("date_end", ""), Decimal(row["rate"])))

    @staticmethod
    def _valid_at(date_start: str, date_end: str, date: Optional[str]) -> bool:
        """Er en gyldighedsperiode aktiv på importdatoen? date=None → gældende (åben slut)."""
        if date is None:
            return date_end == ""        # ingen dato → kun gældende (ikke-udløbne) measures
        return (not date_start or date_start <= date) and (not date_end or date <= date_end)

    def _pref_lookup(self, hs_code: str, origin: str, date: Optional[str]):
        """Bedste HS-specifikke præferencesats for oprindelsen **gældende på importdatoen**.

        Kode-arv (10→8→6→4→2): measures hænger ofte på forældrekoden; børn arver.
        En FTA der trådte i kraft efter importdatoen anvendes IKKE. Returnerer
        (rate, arrangement-navn, is_quota) for det mest specifikke niveau med gældende præference.
        """
        # Grupper landet tilhørte PÅ importdatoen (medlemskab kan være ophørt/begyndt).
        membership = self._country_groups.get(origin, [])
        areas = {g for g, ds, de in membership if self._valid_at(ds, de, date)} | {origin}
        digits = "".join(ch for ch in hs_code if ch.isdigit()).ljust(10, "0")[:10]
        for length in (10, 8, 6, 4, 2):
            cand = digits[:length] + "0" * (10 - length)
            pr = self._pref.get(cand)
            if pr:
                best = None  # (rate, name, is_quota)
                for area, periods in pr.items():
                    if area not in areas:
                        continue
                    for ds, de, rate, is_quota in periods:
                        if self._valid_at(ds, de, date) and (best is None or rate < best[0]):
                            best = (rate, self._area_name.get(area, area), is_quota)
                if best is not None:
                    return best
        return None, None, False

    def mfn_rate(self, hs_code: Optional[str], date: Optional[str] = None) -> Optional[Decimal]:
        """Effektiv tredjelandssats for en varekode **gældende på importdatoen**.

        Når temporal data findes (third_country_rates.csv): laveste gældende af MFN (103)
        og autonom suspension (112) på datoen → en suspenderet kode giver 0 %. Ellers
        nutidssnapshot (eVita). Matcher på faldende prefix (10→8→6→4 cifre)."""
        if not hs_code:
            return None
        digits = "".join(ch for ch in hs_code if ch.isdigit())
        if self._tc:
            d = _norm_date(date)
            for length in (10, 8, 6, 4):
                periods = self._tc.get(digits[:length])
                if periods:
                    valid = [r for ds, de, r in periods if self._valid_at(ds, de, d)]
                    if valid:
                        return min(valid)
        for length in (10, 8, 6, 4):  # fallback: nutidssnapshot
            if self._mfn.get(digits[:length]) is not None:
                return self._mfn[digits[:length]]
        return None

    def lookup(self, hs_code: Optional[str], origin: Optional[str],
               date: Optional[str] = None) -> DutyLookup:
        """Fuldt tarif-opslag: MFN + bedste præferencesats gældende **på importdatoen**.

        `date` (ISO 'YYYY-MM-DD') = angivelsens dato, så kun de FTA'er/præferencer der
        var i kraft dengang matches. None → kun aktuelt gældende præferencer.
        """
        mfn = self.mfn_rate(hs_code, date)
        org = (origin or "").upper()
        pref_rate: Optional[Decimal] = None
        name = atype = None
        is_quota = False

        if self._pref and hs_code:  # HS-specifikke præferencer (Trader Export)
            pref_rate, name, is_quota = self._pref_lookup(hs_code, org, _norm_date(date))
            if pref_rate is not None:
                atype = "preference"
        else:  # fallback: kurateret per-land-aftale (seed)
            arr = self._arrangements.get(org)
            if arr:
                name, atype = arr.get("name"), arr.get("type")
                if atype == "gsp_standard":
                    pref_rate = max(Decimal(0), (mfn or Decimal(0)) - GSP_STANDARD_REDUCTION)
                else:
                    pref_rate = Decimal(str(arr.get("rate", 0.0)))
        return DutyLookup(
            hs_code=hs_code, origin=origin, mfn_rate=mfn,
            preferential_rate=pref_rate, arrangement=name, arrangement_type=atype,
            is_quota=is_quota,
        )

    def has_known_arrangement(self, origin: Optional[str]) -> bool:
        org = (origin or "").upper()
        return org in self._arrangements or org in self._country_groups

    def is_no_preference(self, origin: Optional[str]) -> bool:
        """Eksplicit kendt som uden præference (fx CN) — adskiller fra 'ukendt land'."""
        return (origin or "").upper() in self._no_preference

    def describe(self, hs_code: Optional[str]) -> Optional[str]:
        if not hs_code:
            return None
        digits = "".join(ch for ch in hs_code if ch.isdigit())
        for length in (10, 8, 6, 4):
            if digits[:length] in self._descriptions:
                return self._descriptions[digits[:length]]
        return None
