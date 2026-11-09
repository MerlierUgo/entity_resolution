"""
Moteur d'entity resolution déterministe (POC Mécanova).

`build/` fabrique le catalogue, `engine/` répond aux questions. Étape 1 : résolveur exact.

    from engine import Catalogue, ResolveurExact
    res = ResolveurExact(Catalogue.charger()).resoudre("Liège")
    res.statut, res.ids, res.trace
"""
from engine.catalogue import Catalogue
from engine.resolveur import Resolution, ResolveurExact

__all__ = ["Catalogue", "Resolution", "ResolveurExact"]
