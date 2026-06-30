"""Uafhængig valideringssuite for Customs Analytics.

Formålet er at bevise, at hver IMPLEMENTERET kontrol i regelkataloget faktisk
fyrer på et scenarie med præcis ÉN plantet defekt — og at en ren angivelse ikke
udløser fund. Suiten kører kontrollerne via deres RIGTIGE indgange (ingen
genimplementering) og er gated i CI via ``tests/test_validation_suite.py``.

Kør rapporten: ``python -m validation.run_validation``
CI-gate (kun exit-kode): ``python -m validation.run_validation --quiet``
"""
