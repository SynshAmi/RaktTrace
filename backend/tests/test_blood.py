import pytest

from rakt.domain.blood import compatible_groups, is_compatible
from rakt.models import BloodGroup as G
from rakt.models import Product

# DOMAIN_RULES §3.1, written out independently of the implementation.
TABLE = {
    "O−": "O−",
    "O+": "O+ O−",
    "A−": "A− O−",
    "A+": "A+ A− O+ O−",
    "B−": "B− O−",
    "B+": "B+ B− O+ O−",
    "AB−": "AB− A− B− O−",
    "AB+": "AB+ AB− A+ A− B+ B− O+ O−",
}
SYMBOL = {"O−": G.O_NEG, "O+": G.O_POS, "A−": G.A_NEG, "A+": G.A_POS,
          "B−": G.B_NEG, "B+": G.B_POS, "AB−": G.AB_NEG, "AB+": G.AB_POS}


@pytest.mark.parametrize("patient", TABLE)
def test_full_red_cell_table_after_l2(patient):
    expected = [SYMBOL[s] for s in TABLE[patient].split()]
    assert compatible_groups(SYMBOL[patient], Product.PRBC, escalation_level=2) == expected


@pytest.mark.parametrize("patient", TABLE)
def test_red_cells_never_include_anything_outside_the_table(patient):
    allowed = {SYMBOL[s] for s in TABLE[patient].split()}
    for donor in G:
        if donor not in allowed:
            assert not is_compatible(SYMBOL[patient], donor, Product.PRBC, escalation_level=2)


@pytest.mark.parametrize("patient", list(G))
def test_sdp_identical_group_only(patient):
    for level in (0, 2):
        assert compatible_groups(patient, Product.SDP, level) == [patient]


@pytest.mark.parametrize("patient", [g for g in G if g != G.O_NEG])
def test_o_neg_hidden_before_l2(patient):
    for level in (0, 1):
        assert G.O_NEG not in compatible_groups(patient, Product.PRBC, level)
    assert G.O_NEG in compatible_groups(patient, Product.PRBC, 2)


def test_o_neg_patient_always_gets_o_neg():
    assert compatible_groups(G.O_NEG, Product.PRBC, 0) == [G.O_NEG]


def test_exact_group_first():
    for patient in G:
        assert compatible_groups(patient, Product.PRBC, 2)[0] == patient
