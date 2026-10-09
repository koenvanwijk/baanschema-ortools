"""Baanschemaatje — generieke baanschema-planner voor elke tennisvereniging.

Staat bewust náást de bestaande stack (`scripts/ortools_planner.py`, de live
Pages-site): niets in dit package wijzigt of vervangt die bestanden.

Lagen:
- ``categories``  KNLTB-competitiecategorieën + generieke defaults (SPEC-core)
- ``profile``     clubprofiel (YAML/JSON) laden + valideren
- ``season``      seizoensinput (KNLTB-export als TSV) → genormaliseerd model
- ``planner``     CP-SAT-planner met configureerbaar aantal banen
- ``cli``         ``python -m baanschemaatje plan ...``
"""

__version__ = "0.1.0"
