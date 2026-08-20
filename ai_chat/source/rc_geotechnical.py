"""
foundation_design.py
=====================
Soil Bearing Capacity, Pile Capacity, and Pile Foundation Design toolkit
(BNBC 2020 & ACI 318-14 basis) -- FUNCTION-BASED (no classes).

Implements the theoretical procedures of Part III of the companion
"Soil Bearing Capacity, Pile Capacity, and Pile Foundation Design Manual":

    - Bearing-capacity factors Nc, Nq, Ngamma (Meyerhof/Hansen/Vesic form)
    - General bearing capacity equation with shape/depth factors
    - Allowable bearing pressure (FS-based)
    - Footing plan-size sizing from unfactored loads
    - Elastic (Steinbrenner-type) and consolidation settlement
    - Driven pile capacity in sand (SPT correlation) with critical-depth cap
    - Bored pile capacity in clay (alpha method, layered profile)
    - Pile group sizing, group capacity, and group settlement
    - Single-pile settlement (axial shaft compression + tip + skin-friction
      components)
    - Pile-cap strut-and-tie forces (representative quadrant)

All material/soil properties and results are plain dicts -- no custom
classes anywhere in this module. Units: SI (m, kN, kPa) unless noted,
matching the manual's worked examples. This is an engineering aid, not
a substitute for a licensed engineer's review or an actual geotechnical
investigation -- every numeric input here is illustrative unless you
substitute your own site data.
"""

from math import exp, tan, atan, radians, degrees, sqrt, log10, ceil, pi
from typing import List, Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Part III.1.2 -- Bearing capacity factors (Meyerhof/Hansen/Vesic form)
# ---------------------------------------------------------------------------

def bearing_capacity_factors(phi_deg: float) -> Dict:
    """
    Nc, Nq, Ngamma per Das Eq. 16.33/16.35/16.37 (Meyerhof-type factors,
    phi in degrees). phi_deg = 0 is handled as the undrained (Nq=1, Nc=5.14)
    limit.
    """
    if phi_deg <= 0:
        return {"Nc": 5.14, "Nq": 1.0, "Ngamma": 0.0}

    phi = radians(phi_deg)
    Nq = exp(pi * tan(phi)) * (tan(radians(45 + phi_deg / 2))) ** 2
    Nc = (Nq - 1) / tan(phi)
    Ngamma = (Nq - 1) * tan(radians(1.4 * phi_deg))
    return {"Nc": Nc, "Nq": Nq, "Ngamma": Ngamma}


# ---------------------------------------------------------------------------
# Part III.1.2 -- General bearing capacity equation (with shape/depth
# factors), Part III.1.1 Terzaghi as a special (factors = 1) case
# ---------------------------------------------------------------------------

def shape_depth_factors(phi_deg: float, B: float, L: float,
                         Df: float) -> Dict:
    """
    Meyerhof shape and depth factors (Das Table 16.4). B <= L assumed.
    Returns lam_cs, lam_qs, lam_gs (shape) and lam_cd, lam_qd, lam_gd (depth).
    """
    if phi_deg < 10:
        lam_cs = 1 + 0.2 * (B / L)
        lam_qs = lam_gs = 1.0
        lam_cd = 1 + 0.2 * (Df / B)
        lam_qd = lam_gd = 1.0
        return {"lam_cs": lam_cs, "lam_qs": lam_qs, "lam_gs": lam_gs,
                "lam_cd": lam_cd, "lam_qd": lam_qd, "lam_gd": lam_gd}

    kp_term = tan(radians(45 + phi_deg / 2)) ** 2
    lam_cs = 1 + 0.2 * (B / L) * kp_term
    lam_qs = lam_gs = 1 + 0.1 * (B / L) * kp_term
    lam_cd = 1 + 0.2 * (Df / B) * tan(radians(45 + phi_deg / 2))
    lam_qd = lam_gd = 1 + 0.1 * (Df / B) * tan(radians(45 + phi_deg / 2))
    return {"lam_cs": lam_cs, "lam_qs": lam_qs, "lam_gs": lam_gs,
            "lam_cd": lam_cd, "lam_qd": lam_qd, "lam_gd": lam_gd}


def general_bearing_capacity(c: float, phi_deg: float, gamma: float,
                              Df: float, B: float, L: float,
                              factors: Optional[Dict] = None,
                              use_shape_depth: bool = True) -> Dict:
    """
    Part III.1.2 general bearing capacity equation:
        qu = c*lam_cs*lam_cd*Nc + q*lam_qs*lam_qd*Nq
             + 0.5*gamma*B*lam_gs*lam_gd*Ngamma
    c        : cohesion (kPa)
    phi_deg  : friction angle (deg)
    gamma    : unit weight of soil above founding level (kN/m^3)
    Df       : founding depth (m)
    B, L     : footing width, length (m); B <= L
    Returns dict with Nc, Nq, Ngamma, shape/depth factors, q (surcharge),
    and qu (ultimate bearing pressure, kPa).
    """
    if factors is None:
        factors = bearing_capacity_factors(phi_deg)
    Nc, Nq, Ngamma = factors["Nc"], factors["Nq"], factors["Ngamma"]

    q = gamma * Df

    if use_shape_depth:
        sd = shape_depth_factors(phi_deg, B, L, Df)
    else:
        sd = {"lam_cs": 1.0, "lam_qs": 1.0, "lam_gs": 1.0,
              "lam_cd": 1.0, "lam_qd": 1.0, "lam_gd": 1.0}

    qu = (c * sd["lam_cs"] * sd["lam_cd"] * Nc
          + q * sd["lam_qs"] * sd["lam_qd"] * Nq
          + 0.5 * gamma * B * sd["lam_gs"] * sd["lam_gd"] * Ngamma)

    result = dict(factors)
    result.update(sd)
    result.update({"q": q, "qu": qu})
    return result


# ---------------------------------------------------------------------------
# Part III.1.5 -- Factor of safety and allowable bearing pressure
# ---------------------------------------------------------------------------

def allowable_bearing_pressure(qu: float, q: float, FS: float,
                                net: bool = True) -> float:
    """
    Part III.1.5.
    net=True  -> q_all,net = (qu - q)/FS               (net-to-gross form)
    net=False -> q_all     = (qu - q)/FS + q
    """
    q_all_net = (qu - q) / FS
    return q_all_net if net else q_all_net + q


# ---------------------------------------------------------------------------
# Part III.1.4 -- BNBC presumptive bearing capacity table (Table 6.3.7)
# ---------------------------------------------------------------------------

PRESUMPTIVE_BEARING_KPA = {
    "soft_rock_or_shale": 440,
    "dense_gravel_sandy_gravel": 400,
    "sand_gravelly_sand_silty_sand_dry": 200,
    "fine_sand_loose_dry": 100,
    "silt_clayey_silt_clayey_sand_dry_firm": 150,
    "clay_sandy_clay_stiff": 150,
    "soft_clay": 100,
    "very_soft_clay": 50,
}


def presumptive_bearing_capacity(soil_key: str,
                                  water_table_within_influence: bool = False
                                  ) -> float:
    """
    Part III.1.4, BNBC Table 6.3.7. Halved if the water table is above the
    base, or within one footing-least-dimension below it, for the soils
    marked with an asterisk in the table (all except the clay/silt rows,
    per the table footnote as applied in this module -- verify against the
    actual gazette text for edge cases).
    """
    base = PRESUMPTIVE_BEARING_KPA[soil_key]
    halved_categories = {"dense_gravel_sandy_gravel",
                          "sand_gravelly_sand_silty_sand_dry",
                          "fine_sand_loose_dry"}
    if water_table_within_influence and soil_key in halved_categories:
        return base * 0.5
    return base


# ---------------------------------------------------------------------------
# Part III.2.1 -- Minimum depth of foundation (Rankine)
# ---------------------------------------------------------------------------

def sin_deg(deg: float) -> float:
    from math import sin
    return sin(radians(deg))


def rankine_minimum_depth(q_all: float, gamma: float, phi_deg: float) -> float:
    """Part III.2.1."""
    k = ((1 - sin_deg(phi_deg)) / (1 + sin_deg(phi_deg))) ** 2
    return (q_all / gamma) * k


# ---------------------------------------------------------------------------
# Part III.2.2 -- Footing plan size from unfactored loads
# ---------------------------------------------------------------------------

def footing_required_area(P_service: float, q_all_net: float) -> Dict:
    """Part III.2.2. Returns required area and an equivalent square side."""
    A_req = P_service / q_all_net
    B_req = sqrt(A_req)
    return {"A_req": A_req, "B_req_square": B_req}


# ---------------------------------------------------------------------------
# Part III.3.1 -- Elastic (immediate) settlement (Steinbrenner-type)
# ---------------------------------------------------------------------------

def elastic_settlement(q_net: float, B: float, mu_s: float, Es: float,
                        Is: float, If: float, centre: bool = True) -> float:
    """
    Part III.3.1, Das Eq. 11.1 (simplified -- Is, If supplied directly
    rather than looked up from Das Tables 11.1-11.3, since those require
    a 2D table lookup outside the scope of this module).
    q_net : net applied pressure (kPa)
    B     : footing width (m)
    Es    : soil modulus (kPa)
    Returns settlement in mm (Se in metres * 1000).
    """
    B_prime = B / 2.0 if centre else B
    Se_m = q_net * B_prime * (1 - mu_s ** 2) / Es * Is * If
    return Se_m * 1000.0


# ---------------------------------------------------------------------------
# Part III.3.2 -- Consolidation settlement (clay)
# ---------------------------------------------------------------------------

def consolidation_settlement(Cc: float, H: float, e0: float,
                              sigma0_prime: float, delta_sigma_prime: float,
                              over_consolidated: bool = False,
                              Cr: Optional[float] = None) -> float:
    """
    Part III.3.2. H in metres, stresses in kPa. Returns settlement in mm.
    """
    C = Cr if (over_consolidated and Cr is not None) else Cc
    Sc_m = (C * H / (1 + e0)) * log10(
        (sigma0_prime + delta_sigma_prime) / sigma0_prime)
    return Sc_m * 1000.0


def stress_increase_2v1h(q_net: float, A_provided: float, B: float,
                          z: float) -> float:
    """
    Simple 2V:1H (approximate) stress-spread estimate at depth z below the
    footing base, as used in the manual's Example 2, Step 4:
        delta_sigma' = q_net * A_provided / (B + z)^2
    """
    return q_net * A_provided / (B + z) ** 2


# ---------------------------------------------------------------------------
# Part III.4.4 / III.4.5 -- Driven pile capacity, sand (SPT correlation)
# with critical-depth plateau
# ---------------------------------------------------------------------------

def driven_pile_capacity_spt_sand(D: float, L: float, N60: float,
                                   N60_tip: float, perimeter: Optional[float] = None,
                                   Ap: Optional[float] = None,
                                   FS: float = 3.5,
                                   silt: bool = False) -> Dict:
    """
    Part III.4.4, BNBC Eq. 6.3.25-6.3.28 (SPT correlation, driven pile,
    sand or non-plastic silt). Caps applied per Part III.4.5.

    D          : pile diameter/side (m) -- used to derive perimeter/Ap for
                 a square or circular section if not given explicitly.
    L          : embedded length (m)
    N60        : average SPT blow count along the shaft
    N60_tip    : SPT blow count near the tip
    perimeter  : pile perimeter (m); computed from D (square) if omitted
    Ap         : pile tip area (m^2); computed from D (square) if omitted
    """
    if perimeter is None:
        perimeter = 4 * D          # square pile default
    if Ap is None:
        Ap = D ** 2                # square pile default

    if silt:
        fs = min(1.7 * N60, 60.0)
        fp = min(30.0 * N60_tip * (L / D), 300.0 * N60_tip, 11000.0)
    else:
        fs = min(2.0 * N60, 60.0)
        fp = min(40.0 * N60_tip * (L / D), 400.0 * N60_tip, 11000.0)

    Qs = fs * perimeter * L
    Qp = fp * Ap
    Qu = Qs + Qp
    Qall = Qu / FS

    return {"fs": fs, "fp": fp, "Qs": Qs, "Qp": Qp, "Qu": Qu, "Qall": Qall,
            "perimeter": perimeter, "Ap": Ap}


def driven_pile_capacity_vs_depth(D: float, lengths: List[float],
                                   N60_profile: List[float],
                                   N60_tip_profile: List[float],
                                   FS: float = 3.5,
                                   silt: bool = False) -> List[Dict]:
    """
    Convenience wrapper: run driven_pile_capacity_spt_sand at a series of
    trial embedment lengths (Part III.4, Example 3 style table).
    lengths, N60_profile, N60_tip_profile must be the same length, each
    entry corresponding to one trial length L.
    """
    results = []
    for L, N60, N60_tip in zip(lengths, N60_profile, N60_tip_profile):
        r = driven_pile_capacity_spt_sand(D, L, N60, N60_tip, FS=FS,
                                           silt=silt)
        r["L"] = L
        results.append(r)
    return results


# ---------------------------------------------------------------------------
# Part III.4.2 / III.4.6 -- Bored pile capacity, clay (alpha method,
# layered profile)
# ---------------------------------------------------------------------------

def alpha_factor(cu: float) -> float:
    """Part III.4.2, BNBC Eq. 6.3.16."""
    if cu <= 25:
        return 1.0
    if cu >= 70:
        return 0.5
    return 1 - (cu - 25) / 90.0


def bored_pile_alpha_method(D: float, layers: List[Dict], cu_tip: float,
                             FS: float = 3.0,
                             perimeter: Optional[float] = None,
                             Ap: Optional[float] = None) -> Dict:
    """
    Part III.4.2 (alpha method) with the bored-pile reduction of Part
    III.4.6 (skin friction = 2/3 of driven-pile value, end bearing = 1/3).

    D      : pile diameter (m)
    layers : list of {'thickness': dz (m), 'cu': cu at that sub-layer (kPa)}
             -- summed to give total shaft resistance over the full length.
    cu_tip : undrained shear strength at/near the pile tip (kPa)
    """
    if perimeter is None:
        perimeter = pi * D
    if Ap is None:
        Ap = pi * D ** 2 / 4.0

    L = sum(layer["thickness"] for layer in layers)
    Qs = 0.0
    for layer in layers:
        alpha = alpha_factor(layer["cu"])
        fs = (2.0 / 3.0) * alpha * layer["cu"]
        Qs += fs * perimeter * layer["thickness"]

    Nc = min(6 * (1 + 0.2 * (L / D)), 9.0)
    fp = (1.0 / 3.0) * cu_tip * Nc
    Qp = fp * Ap
    Qu = Qs + Qp
    Qall = Qu / FS

    return {"L": L, "Nc": Nc, "fp": fp, "Qs": Qs, "Qp": Qp, "Qu": Qu,
            "Qall": Qall, "perimeter": perimeter, "Ap": Ap}


def uniform_cu_layers(cu_at_z, L: float, n_layers: int = 20) -> List[Dict]:
    """
    Helper: discretize a depth-varying cu(z) function into n_layers equal
    sub-layers of thickness L/n_layers, each assigned the cu at its
    mid-depth. cu_at_z: callable, cu_at_z(z) -> cu in kPa.
    """
    dz = L / n_layers
    layers = []
    for i in range(n_layers):
        z_mid = (i + 0.5) * dz
        layers.append({"thickness": dz, "cu": cu_at_z(z_mid)})
    return layers


# ---------------------------------------------------------------------------
# Part III.4.9 -- Pile group sizing and capacity
# ---------------------------------------------------------------------------

def pile_group_number_required(P_service: float, Qall_single: float,
                                efficiency: float = 1.0) -> Dict:
    """Part III.4.9 / Example 5a."""
    n_req = ceil(P_service / (efficiency * Qall_single))
    Qgroup_all = efficiency * n_req * Qall_single
    return {"n_required": n_req, "Qgroup_all": Qgroup_all}


def pile_group_capacity(n_piles: int, Qall_single: float,
                         efficiency: float = 1.0) -> float:
    """Part III.4.9."""
    return efficiency * n_piles * Qall_single


def minimum_pile_spacing(D: float, factor: float = 2.5) -> float:
    """Part III.4.9, BNBC 3.10.1.19: min spacing = 2.5D centre-to-centre."""
    return factor * D


# ---------------------------------------------------------------------------
# Part III.5.1 -- Single-pile settlement (three components)
# ---------------------------------------------------------------------------

def pile_settlement_single(Qp_service: float, Qs_service: float, L: float,
                            Ap: float, Ep: float, xi: float,
                            D: float, At: float, fp_service: float,
                            fs_avg_service: float) -> Dict:
    """
    Part III.5.1, BNBC Eq. 6.3.35a-c & 6.3.36.
    Qp_service, Qs_service : service-level tip and shaft load shares (kN)
    L    : pile length (m)
    Ap   : pile cross-sectional area (m^2)
    Ep   : pile (concrete) modulus (kPa)
    xi   : 0.5 (clay/silt) or 0.67 (sand)
    D    : pile diameter (m)
    At   : empirical tip-settlement coefficient (BNBC Table 6.3.13)
    fp_service     : mobilized unit tip resistance at service load (kPa)
    fs_avg_service : average mobilized unit skin friction at service load (kPa)
    Returns Sa, Spt, Ssf, Ssingle -- all in mm.
    """
    Sa_m = (Qp_service + xi * Qs_service) * L / (Ap * Ep)
    Spt_m = At * Qp_service * D / (Ap * fp_service) if fp_service else 0.0
    Asf = 0.93 + 0.16 * sqrt(L / D)
    Ssf_m = Asf * fs_avg_service * D / fp_service if fp_service else 0.0

    Sa = Sa_m * 1000.0
    Spt = Spt_m * 1000.0
    Ssf = Ssf_m * 1000.0
    return {"Sa": Sa, "Spt": Spt, "Ssf": Ssf, "Ssingle": Sa + Spt + Ssf,
            "Asf": Asf}


# ---------------------------------------------------------------------------
# Part III.5.2 -- Pile group settlement (short-term / elastic)
# ---------------------------------------------------------------------------

def pile_group_settlement(S_single: float, Bg: float, D: float,
                           n_piles: int) -> Dict:
    """
    Part III.5.2, BNBC Eq. 6.3.37/6.3.38. Returns both estimates and the
    governing (larger) value.
    """
    S_by_Bg = S_single * sqrt(Bg / D)
    S_by_n = S_single * sqrt(n_piles)
    return {"S_by_Bg_over_D": S_by_Bg, "S_by_sqrt_n": S_by_n,
            "S_group_governing": max(S_by_Bg, S_by_n)}


# ---------------------------------------------------------------------------
# Part III.6 -- Pile cap strut-and-tie (representative quadrant forces)
# ---------------------------------------------------------------------------

def pile_cap_strut_and_tie(P_per_pile: float, d_eff: float,
                            horiz_dist_col_to_pile: float, fc: float,
                            fy: float, beta_s: float = 0.60,
                            phi_strut: float = 0.75,
                            phi_tie: float = 0.75) -> Dict:
    """
    Part III.6 (representative single pile/strut of a symmetric cap).
    P_per_pile              : factored load carried by one pile (kN)
    d_eff                   : effective depth to tie steel level (m)
    horiz_dist_col_to_pile  : horizontal distance from column centre to
                              pile centre (m)
    fc, fy                  : MPa
    Returns strut angle, strut force, tie force, strut effective stress,
    required tie steel area (mm^2), and an applicability flag.
    """
    theta_rad = atan(d_eff / horiz_dist_col_to_pile)
    theta_deg = degrees(theta_rad)

    F_strut = P_per_pile / sin_deg(theta_deg)
    F_tie = P_per_pile / tan(theta_rad)

    f_ce = 0.85 * beta_s * fc          # MPa
    A_tie_req_mm2 = (F_tie * 1000.0) / (phi_tie * fy)  # F_tie in kN -> N

    applicable = horiz_dist_col_to_pile <= 2 * d_eff

    return {
        "theta_deg": theta_deg,
        "F_strut_kN": F_strut,
        "F_tie_kN": F_tie,
        "f_ce_MPa": f_ce,
        "A_tie_req_mm2": A_tie_req_mm2,
        "stm_applicable": applicable,
        "angle_ok_min_25deg": theta_deg >= 25.0,
    }


# ---------------------------------------------------------------------------
# Part III.7 -- Pile shaft P-M interaction and shear (reuses the strain-
# compatibility approach of the companion RC Beam & Column module; a
# simplified circular-section equivalent-rectangle shear check per
# Part III.7.4)
# ---------------------------------------------------------------------------

def pile_shaft_axial_capacity(fc_MPa: float, fy_MPa: float, Ag_mm2: float,
                               Ast_mm2: float) -> Dict:
    """Part III.7 pure-axial reference point (tied, phi=0.65, 0.80 cap)."""
    Po_kN = (0.85 * fc_MPa * (Ag_mm2 - Ast_mm2) + fy_MPa * Ast_mm2) / 1000.0
    phi = 0.65
    phiPn_max_kN = phi * 0.80 * Po_kN
    return {"Po_kN": Po_kN, "phi": phi, "phiPn_max_kN": phiPn_max_kN}


def pile_shaft_min_reinforcement_ratio(Ag_m2: float) -> float:
    """Part III.7.3, BNBC 3.10.4.9."""
    if Ag_m2 <= 0.5:
        return 0.005
    if Ag_m2 <= 1.0:
        return 0.00375
    return 0.0025


def pile_shaft_shear_capacity(D_mm: float, fc_MPa: float,
                               phi: float = 0.75) -> Dict:
    """
    Part III.7.4. Circular section treated as an equivalent rectangle:
    b = D, d = 0.8*D (ACI 318-14 Sec22.5.2.2 equivalence).
    Returns Vc (kN) and phiVc (kN).
    """
    b_mm = D_mm
    d_mm = 0.8 * D_mm
    Vc_N = 0.17 * sqrt(fc_MPa) * b_mm * d_mm
    Vc_kN = Vc_N / 1000.0
    return {"b_mm": b_mm, "d_mm": d_mm, "Vc_kN": Vc_kN,
            "phiVc_kN": phi * Vc_kN}


# ---------------------------------------------------------------------------
# Part II -- Foundation-type decision helper (very simple screening aid)
# ---------------------------------------------------------------------------

def screen_foundation_type(q_all_shallow: float, q_demand: float,
                            settlement_shallow_mm: float,
                            settlement_tolerable_mm: float) -> str:
    """
    Very simplified Part II screening: if a shallow foundation satisfies
    both bearing pressure and settlement, recommend shallow; otherwise
    recommend evaluating piles (Part III.4 onward). Real practice runs
    both calculations explicitly (Part II.1) rather than relying on a
    single screening function -- this is a convenience wrapper only.
    """
    bearing_ok = q_demand <= q_all_shallow
    settlement_ok = settlement_shallow_mm <= settlement_tolerable_mm
    if bearing_ok and settlement_ok:
        return "shallow foundation adequate"
    return "evaluate pile foundation (Part III.4 onward)"


# ---------------------------------------------------------------------------
# Demo / validation against the manual's worked examples
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 78)
    print("Example 1 -- Bearing capacity vs. depth (square footing, sand)")
    print("=" * 78)
    phi = 33.0
    gamma = 18.0
    B = L = 2.0
    FS = 3.0
    factors = bearing_capacity_factors(phi)
    print(f"Nc={factors['Nc']:.2f} Nq={factors['Nq']:.2f} "
          f"Ngamma={factors['Ngamma']:.2f} "
          f"(manual: Nc=38.64, Nq=26.09, Ngamma=27.97 -- Ngamma differs "
          f"slightly, manual likely interpolated Das's tabulated values)")

    for Df in [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]:
        gbc = general_bearing_capacity(c=0.0, phi_deg=phi, gamma=gamma,
                                        Df=Df, B=B, L=L, factors=factors)
        qall = allowable_bearing_pressure(gbc["qu"], gbc["q"], FS, net=True)
        print(f"Df={Df:>4.1f} m  q={gbc['q']:>6.1f} kPa  "
              f"qu={gbc['qu']:>8.1f} kPa  qall,net={qall:>7.1f} kPa")

    print("\n" + "=" * 78)
    print("Example 2 -- Footing sizing and settlement")
    print("=" * 78)
    q_all_net = allowable_bearing_pressure(
        general_bearing_capacity(0.0, phi, gamma, 2.0, B, L, factors)["qu"],
        gamma * 2.0, FS, net=True)
    print(f"qall,net at Df=2.0m = {q_all_net:.1f} kPa (manual: 583.8)")

    sizing1 = footing_required_area(P_service=1300.0, q_all_net=q_all_net)
    print(f"Column 1: A_req = {sizing1['A_req']:.3f} m^2 "
          f"(manual: 2.227), B_req = {sizing1['B_req_square']:.3f} m "
          f"(manual: 1.492)")
    B_provided, A_provided = 1.50, 1.50 ** 2
    q_service = 1300.0 / A_provided
    print(f"Provide B=1.50 m, A={A_provided:.2f} m^2, "
          f"q_service = {q_service:.1f} kPa (manual: 577.8)")

    Se = elastic_settlement(q_net=q_service, B=B_provided, mu_s=0.30,
                             Es=25000.0, Is=0.56, If=0.80, centre=True)
    print(f"Se = {Se:.1f} mm (manual: 8.4)")

    d_sigma = stress_increase_2v1h(q_service, A_provided, B_provided, 7.0)
    print(f"delta_sigma' at clay mid-depth = {d_sigma:.1f} kPa (manual: 15.5)")
    Sc = consolidation_settlement(Cc=0.30, H=2.0, e0=0.90,
                                   sigma0_prime=110.0,
                                   delta_sigma_prime=d_sigma)
    print(f"Sc = {Sc:.1f} mm (manual: 20.9)")
    print(f"Total settlement column 1 = {Se + Sc:.1f} mm (manual: 29.3), "
          f"tolerable = 25 mm -> "
          f"{'EXCEEDS' if Se + Sc > 25 else 'OK'}")

    print("\n" + "=" * 78)
    print("Example 3 -- Driven pile capacity vs. depth (SPT method, sand)")
    print("=" * 78)
    D_pile = 0.4
    lengths = [3, 6, 9, 12, 15, 18, 21, 24, 27, 30]
    N60s = [9.8, 11.2, 13.0, 15.0, 17.3, 19.8, 22.5, 25.2, 28.0, 30.9]
    N60_tips = [11.0, 14.0, 18.5, 23.0, 29.0, 35.0, 41.0, 47.0, 53.0, 59.0]
    results3 = driven_pile_capacity_vs_depth(D_pile, lengths, N60s, N60_tips,
                                              FS=3.5)
    for r in results3:
        print(f"L={r['L']:>4.0f} m  fs={r['fs']:>5.1f}  Qs={r['Qs']:>8.1f}  "
              f"fp={r['fp']:>7.0f}  Qp={r['Qp']:>7.1f}  Qu={r['Qu']:>8.1f}  "
              f"Qall={r['Qall']:>7.1f}")
    print("(manual Qall at L=15: 740.2 kN -- computed above should be "
          "close, small differences from average-N60 vs. true layer-by-"
          "layer summation in the source manual)")

    print("\n" + "=" * 78)
    print("Example 4 -- Bored pile capacity, clay (alpha method)")
    print("=" * 78)
    D_bored = 0.6
    for L_trial in [8, 10, 12, 14, 16, 18, 20]:
        layers = uniform_cu_layers(lambda z: 35 + 4 * z, L_trial,
                                    n_layers=40)
        cu_tip = 35 + 4 * L_trial
        r4 = bored_pile_alpha_method(D_bored, layers, cu_tip, FS=3.0)
        print(f"L={L_trial:>3} m  Nc={r4['Nc']:.2f}  Qs={r4['Qs']:>8.1f}  "
              f"Qp={r4['Qp']:>7.1f}  Qu={r4['Qu']:>8.1f}  "
              f"Qall={r4['Qall']:>7.1f}")
    print("(manual Qu at L=8: 393.6 kN, L=20: 1125.5 kN -- layered "
          "integration here should track closely; small differences from "
          "discretization/rounding)")

    print("\n" + "=" * 78)
    print("Example 5a -- Pile group sizing")
    print("=" * 78)
    grp = pile_group_number_required(P_service=3000.0, Qall_single=740.2,
                                      efficiency=1.0)
    print(f"n_required = {grp['n_required']} (manual: 5, provide 6)")
    Qgroup = pile_group_capacity(6, 740.2, efficiency=1.0)
    print(f"Qgroup,all (n=6) = {Qgroup:.0f} kN (manual: 4441)")
    print(f"Min spacing = {minimum_pile_spacing(0.4):.2f} m (manual: 1.00)")

    print("\n" + "=" * 78)
    print("Example 5b -- Pile-cap strut-and-tie (representative quadrant)")
    print("=" * 78)
    stm = pile_cap_strut_and_tie(P_per_pile=700.0, d_eff=0.90,
                                  horiz_dist_col_to_pile=0.71,
                                  fc=28.0, fy=420.0, beta_s=0.60)
    print(f"theta = {stm['theta_deg']:.1f} deg (manual: 51.8)")
    print(f"F_strut = {stm['F_strut_kN']:.1f} kN (manual: 890.2)")
    print(f"F_tie = {stm['F_tie_kN']:.1f} kN (manual: 550.0)")
    print(f"f_ce = {stm['f_ce_MPa']:.2f} MPa (manual: 14.28)")
    print(f"A_tie_req = {stm['A_tie_req_mm2']:.0f} mm^2 (manual: 1746)")
    print(f"STM applicable: {stm['stm_applicable']} "
          f"(manual: yes, 0.71 <= 1.80)")

    print("\n" + "=" * 78)
    print("Example 6 -- Pile and pile-group settlement")
    print("=" * 78)
    Qu_single = 2590.8  # from Example 3, L=15 m row (manual value)
    FS_single = 3.5
    Qp_all = 1760.0  # from Example 3 table at L=15
    Qs_all = Qu_single - Qp_all
    Qp_service = Qp_all / FS_single
    Qs_service = Qs_all / FS_single
    Ap_pile = D_pile ** 2
    fp_service = Qp_service / Ap_pile
    perim = 4 * D_pile
    fs_avg_service = Qs_service / (perim * 15.0)

    single = pile_settlement_single(Qp_service=Qp_service,
                                     Qs_service=Qs_service, L=15.0,
                                     Ap=Ap_pile, Ep=25_000_000.0, xi=0.67,
                                     D=D_pile, At=0.02,
                                     fp_service=fp_service,
                                     fs_avg_service=fs_avg_service)
    print(f"Sa={single['Sa']:.2f} mm (manual: 2.48), "
          f"Spt={single['Spt']:.2f} mm (manual: 8.00), "
          f"Ssf={single['Ssf']:.2f} mm (manual: 2.40)")
    print(f"S_single = {single['Ssingle']:.2f} mm (manual: 12.89)")

    grp_settle = pile_group_settlement(single["Ssingle"], Bg=1.85,
                                        D=D_pile, n_piles=6)
    print(f"S by sqrt(Bg/D) = {grp_settle['S_by_Bg_over_D']:.1f} mm "
          f"(manual: 27.7)")
    print(f"S by sqrt(n) = {grp_settle['S_by_sqrt_n']:.1f} mm "
          f"(manual: 31.6)")
    print(f"Governing group settlement = "
          f"{grp_settle['S_group_governing']:.1f} mm (manual: 31.6)")

    print("\n" + "=" * 78)
    print("Example 7 -- Pile shaft: axial capacity, min steel, shear")
    print("=" * 78)
    Ag_mm2 = pi * 500 ** 2 / 4.0
    Ast_mm2 = 3142.0
    ax = pile_shaft_axial_capacity(fc_MPa=28.0, fy_MPa=420.0, Ag_mm2=Ag_mm2,
                                    Ast_mm2=Ast_mm2)
    print(f"Ag = {Ag_mm2:.0f} mm^2 (manual: 196,350)")
    print(f"Po = {ax['Po_kN']:.0f} kN (manual: 5918)")
    print(f"phiPn,max = {ax['phiPn_max_kN']:.0f} kN (manual: 3077)")

    rho_min = pile_shaft_min_reinforcement_ratio(Ag_mm2 / 1e6)
    print(f"rho_min = {rho_min:.4f} -> As,min = {rho_min * Ag_mm2:.0f} mm^2 "
          f"(manual: 982)")

    sh = pile_shaft_shear_capacity(D_mm=500.0, fc_MPa=28.0)
    print(f"Vc = {sh['Vc_kN']:.1f} kN (manual: 179.9), "
          f"phiVc = {sh['phiVc_kN']:.1f} kN (manual: 134.9)")