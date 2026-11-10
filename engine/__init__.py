"""
Moteur d'entity resolution déterministe (POC Mécanova).

`build/` fabrique le catalogue, `engine/` répond aux questions. Étape 1 : résolveur exact ; étape 2 : Jaro-Winkler borné (ResolveurApproche).

    from engine import Catalogue, ResolveurExact
    res = ResolveurExact(Catalogue.charger()).resoudre("Liège")
    res.statut, res.ids, res.trace
"""
from engine.catalogue import Catalogue
from engine.approche import SeuilFixe, SeuilsCalibres
from engine.resolveur import Resolution, ResolveurApproche, ResolveurExact

__all__ = ["Catalogue", "Resolution", "ResolveurApproche", "ResolveurExact", "SeuilFixe", "SeuilsCalibres"]
