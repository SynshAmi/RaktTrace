"""Compatibility for shortlisting stock and donors (DOMAIN_RULES §3). The centre's crossmatch decides."""

from rakt.models import BloodGroup as G
from rakt.models import Product

# Patient → donor groups for red cells, in preference order (DOMAIN_RULES §3.1).
RED_CELL_DONORS = {
    G.O_NEG: [G.O_NEG],
    G.O_POS: [G.O_POS, G.O_NEG],
    G.A_NEG: [G.A_NEG, G.O_NEG],
    G.A_POS: [G.A_POS, G.A_NEG, G.O_POS, G.O_NEG],
    G.B_NEG: [G.B_NEG, G.O_NEG],
    G.B_POS: [G.B_POS, G.B_NEG, G.O_POS, G.O_NEG],
    G.AB_NEG: [G.AB_NEG, G.A_NEG, G.B_NEG, G.O_NEG],
    G.AB_POS: [G.AB_POS, G.AB_NEG, G.A_POS, G.A_NEG, G.B_POS, G.B_NEG, G.O_POS, G.O_NEG],
}


def o_neg_unlocked(escalation_level: int) -> bool:
    """O− protection (DOMAIN_RULES §3.3): O− is used for non-O− patients only after L2."""
    return escalation_level >= 2


def compatible_groups(patient: G, product: Product, escalation_level: int = 0) -> list[G]:
    """Donor/stock groups to search, exact group first. SDP: identical group only (§3.2)."""
    if product == Product.SDP:
        return [patient]
    groups = RED_CELL_DONORS[patient]
    if patient != G.O_NEG and not o_neg_unlocked(escalation_level):
        groups = [g for g in groups if g != G.O_NEG]
    return list(groups)


def is_compatible(patient: G, donor: G, product: Product, escalation_level: int = 0) -> bool:
    return donor in compatible_groups(patient, product, escalation_level)
