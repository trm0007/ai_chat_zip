"""
rcc_design.py
==============
Reinforced-Concrete Beam & Column Design Toolkit (ACI 318-14 basis,
BNBC 2020 numerically parallel) -- FUNCTION-BASED VERSION (no classes).

Implements the theoretical procedures of Part III of the
"RC Beam and Column Design Manual":
    - Singly reinforced rectangular beam (design & analysis)
    - Doubly reinforced rectangular beam (design)
    - T-beam (flanged section) design
    - Pure axial compression (short column)
    - Uniaxial bending + axial load (strain-compatibility, single point)
    - P-M interaction diagram (swept curve)
    - Biaxial bending (Bresler load-contour / reciprocal-load)
    - Shear design
    - Torsion design
    - Combined shear + torsion section-adequacy check
    - Net tensile strain -> phi factor (ACI Table 21.2.2)

Design conventions used throughout this module:
- Material properties are passed as a plain dict, e.g.:
      mat = make_materials(fc=4000.0, fy=60000.0, Es=29_000_000.0)
  which is itself just a dict with keys 'fc', 'fy', 'Es', 'lam',
  'beta1', 'ey', 'Ec' precomputed for convenience.
- Reinforcement layers for the strain-compatibility routines are passed
  as a list of plain dicts: {'As': area, 'd': depth_from_compression_face}.
- Every design/analysis routine returns a plain dict of results (no
  custom classes), so results can be used directly, printed, or dumped
  to JSON.

Units: US customary (in, lb, psi) unless noted; force x length results
generally quoted internally in lb-in and converted to ft-kip only in the
printed demo at the bottom. This is an engineering aid, not a substitute
for a licensed engineer's review -- always verify against the current
code edition before use in real design.
"""

from math import sqrt, tan, radians
from typing import List, Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Material properties (plain dict, no class)
# ---------------------------------------------------------------------------

def make_materials(fc: float = 4000.0, fy: float = 60000.0,
                    Es: float = 29_000_000.0, lam: float = 1.0) -> Dict:
    """
    Build a material-properties dict.
    fc  : f'c, psi
    fy  : fy = fyt, psi (Grade 60 default)
    Es  : steel modulus, psi
    lam : lightweight-concrete factor (1.0 = normal weight)
    """
    if fc <= 4000:
        beta1 = 0.85
    else:
        beta1 = max(0.85 - 0.05 * (fc - 4000) / 1000, 0.65)

    return {
        "fc": fc,
        "fy": fy,
        "Es": Es,
        "lam": lam,
        "beta1": beta1,          # ACI 318-14 Sec22.2.2.4.3
        "ey": fy / Es,           # yield strain
        "Ec": 57000.0 * sqrt(fc),
    }


# ---------------------------------------------------------------------------
# Phi factor (ACI 318-14 Table 21.2.2 / Sec21.2.2)
# ---------------------------------------------------------------------------

def phi_from_strain(et: float, mat: Dict, spiral: bool = False) -> float:
    """
    Net-tensile-strain -> strength reduction factor (Sec3.12).
    et : net tensile strain in extreme tension layer.
    """
    ety = mat["ey"]
    phi_cc = 0.75 if spiral else 0.65
    if et <= ety:
        return phi_cc
    if et >= 0.005:
        return 0.90
    return phi_cc + (et - ety) * (0.25 / (0.005 - ety))


# ---------------------------------------------------------------------------
# Sec3.2 -- Singly Reinforced Rectangular Beam
# ---------------------------------------------------------------------------

def singly_reinforced_analysis(b: float, d: float, As: float,
                                mat: Dict) -> Dict:
    """Given As, find phi*Mn (Sec3.2 analysis). Returns dict of results."""
    a = As * mat["fy"] / (0.85 * mat["fc"] * b)
    c = a / mat["beta1"]
    et = 0.003 * (d - c) / c
    phi = phi_from_strain(et, mat)
    Mn = As * mat["fy"] * (d - a / 2.0)
    return {
        "a": a, "c": c, "et": et, "phi": phi,
        "Mn": Mn, "phiMn": phi * Mn,
    }


def singly_reinforced_design(b: float, d: float, Mu: float, mat: Dict,
                              phi_target: float = 0.90,
                              tol: float = 1e-6, max_iter: int = 100
                              ) -> Dict:
    """
    Given Mu (lb-in, consistent with b, d, fy), find As (Sec3.2 design).
    Iterative solution starting from jd ~= 0.9d.
    Returns dict with 'As_required', 'As_min', and the analysis dict
    for the converged As under 'result'.
    """
    As = Mu / (phi_target * mat["fy"] * 0.9 * d)
    for _ in range(max_iter):
        a = As * mat["fy"] / (0.85 * mat["fc"] * b)
        As_new = Mu / (phi_target * mat["fy"] * (d - a / 2.0))
        if abs(As_new - As) < tol:
            As = As_new
            break
        As = As_new

    As_min = max(3 * sqrt(mat["fc"]) / mat["fy"], 200.0 / mat["fy"]) * b * d
    result = singly_reinforced_analysis(b, d, As, mat)
    return {"As_required": As, "As_min": As_min, "result": result}


# ---------------------------------------------------------------------------
# Sec3.3 -- Doubly Reinforced Rectangular Beam
# ---------------------------------------------------------------------------

def doubly_reinforced_design(b: float, d: float, dprime: float, Mu: float,
                              mat: Dict, c_over_d_limit: float = 0.375
                              ) -> Dict:
    """
    Sec3.3 step-by-step design. c_over_d_limit = 0.375 corresponds to the
    tension-controlled limit (et = 0.005) giving full phi = 0.90.
    """
    phi = 0.90
    c_max = c_over_d_limit * d
    a_max = mat["beta1"] * c_max

    As1 = 0.85 * mat["fc"] * a_max * b / mat["fy"]
    Mn1 = As1 * mat["fy"] * (d - a_max / 2.0)

    Mn_req = Mu / phi
    Mn2 = Mn_req - Mn1
    As2 = Mn2 / (mat["fy"] * (d - dprime))

    eps_s_prime = 0.003 * (c_max - dprime) / c_max
    ey = mat["ey"]
    if eps_s_prime >= ey:
        fps = mat["fy"]
        Aps = As2
        yields = True
    else:
        fps = mat["Es"] * eps_s_prime
        Aps = As2 * mat["fy"] / fps
        yields = False

    As_total = As1 + As2
    phiMn = phi * (Mn1 + As2 * mat["fy"] * (d - dprime))

    return {
        "As1": As1, "As2": As2, "As_total": As_total,
        "Aps_required": Aps, "fps": fps,
        "Mn1": Mn1, "Mn2": Mn2, "phiMn": phiMn,
        "compression_steel_yields": yields,
    }


# ---------------------------------------------------------------------------
# Sec3.4 -- T-Beam (Flanged Section)
# ---------------------------------------------------------------------------

def t_beam_analysis(bf: float, bw: float, hf: float, d: float, As: float,
                     mat: Dict) -> Dict:
    """Sec3.4 -- check rectangular vs. true flanged behaviour, then analyze."""
    a_trial = As * mat["fy"] / (0.85 * mat["fc"] * bf)
    if a_trial <= hf:
        res = singly_reinforced_analysis(bf, d, As, mat)
        res["behaves_as"] = "rectangular"
        res["a_trial"] = a_trial
        return res

    Asf = 0.85 * mat["fc"] * hf * (bf - bw) / mat["fy"]
    Mn1 = Asf * mat["fy"] * (d - hf / 2.0)
    Asw = As - Asf
    aw = Asw * mat["fy"] / (0.85 * mat["fc"] * bw)
    Mn2 = Asw * mat["fy"] * (d - aw / 2.0)
    Mn = Mn1 + Mn2
    c = aw / mat["beta1"]
    et = 0.003 * (d - c) / c
    phi = phi_from_strain(et, mat)

    return {
        "behaves_as": "flanged", "a_trial": a_trial,
        "Asf": Asf, "Mn1": Mn1, "Asw": Asw, "aw": aw, "Mn2": Mn2,
        "Mn": Mn, "c": c, "et": et, "phi": phi, "phiMn": phi * Mn,
    }


# ---------------------------------------------------------------------------
# Sec3.5 -- Pure Axial Compression (Short Column)
# ---------------------------------------------------------------------------

def pure_axial_capacity(b: float, h: float, Ast: float, mat: Dict,
                         tied: bool = True) -> Dict:
    """Sec3.5"""
    Ag = b * h
    rho_g = Ast / Ag
    if not (0.01 <= rho_g <= 0.08):
        raise ValueError(f"rho_g = {rho_g:.4f} outside ACI 318-14 "
                          f"Sec10.6.1.1 limits [0.01, 0.08]")
    Po = 0.85 * mat["fc"] * (Ag - Ast) + mat["fy"] * Ast
    Pn_max = (0.80 if tied else 0.85) * Po
    phi = 0.65 if tied else 0.75
    return {
        "Ag": Ag, "rho_g": rho_g, "Po": Po,
        "Pn_max": Pn_max, "phi": phi, "phiPn_max": phi * Pn_max,
    }


# ---------------------------------------------------------------------------
# Sec3.6 -- Uniaxial Bending + Axial Load (strain compatibility)
# ---------------------------------------------------------------------------

def make_rebar_layer(As: float, d: float) -> Dict:
    """
    Helper to build a reinforcement-layer dict.
    As : area of steel in this layer
    d  : distance from extreme compression fibre to this layer
    """
    return {"As": As, "d": d}


def pm_point(b: float, h: float, layers: List[Dict], c: float, mat: Dict,
             spiral: bool = False) -> Dict:
    """
    One point on the strain-compatibility interaction surface for a
    rectangular section, uniaxial bending about one axis (Sec3.6).

    b, h    : section width and total depth
    layers  : list of {'As':..., 'd':...} dicts (d measured from the
              extreme *compression* fibre)
    c       : trial neutral-axis depth (from extreme compression fibre)

    Returns a dict with Pn, Mn (taken about section mid-depth), et, phi,
    phiPn, phiMn.
    """
    a = mat["beta1"] * c
    a_eff = min(a, h)
    Cc = 0.85 * mat["fc"] * a_eff * b
    y_centroid_conc = h / 2.0 - a_eff / 2.0

    Pn = Cc
    Mn = Cc * y_centroid_conc

    dt = max(layer["d"] for layer in layers)
    for layer in layers:
        strain = 0.003 * (c - layer["d"]) / c
        stress = mat["Es"] * strain
        stress = max(min(stress, mat["fy"]), -mat["fy"])
        if layer["d"] <= a_eff:
            stress_net = stress - 0.85 * mat["fc"]
        else:
            stress_net = stress
        force = layer["As"] * stress_net
        Pn += force
        lever = h / 2.0 - layer["d"]
        Mn += force * lever

    et = 0.003 * (dt - c) / c
    phi = phi_from_strain(et, mat, spiral=spiral)
    return {
        "c": c, "Pn": Pn, "Mn": Mn, "et": et, "phi": phi,
        "phiPn": phi * Pn, "phiMn": phi * Mn,
    }


def pm_interaction_diagram(b: float, h: float, layers: List[Dict],
                            mat: Dict, n_points: int = 40,
                            tied: bool = True) -> List[Dict]:
    """
    Sweep c from near-zero (pure tension) to a very large value (pure
    compression) to build the full nominal + design interaction curve
    (Sec3.13). Returns a list of pm_point dicts sorted by increasing c.
    """
    dt = max(layer["d"] for layer in layers)
    c_min = 0.05 * dt
    c_max = 20.0 * h

    points = []
    for i in range(n_points):
        frac = i / (n_points - 1)
        c = c_min + (c_max - c_min) * (frac ** 2)
        points.append(pm_point(b, h, layers, c, mat, spiral=not tied))

    points.sort(key=lambda p: p["c"])
    return points


# ---------------------------------------------------------------------------
# Sec3.7 -- Biaxial Bending (Bresler methods)
# ---------------------------------------------------------------------------

def bresler_reciprocal_load(Pnx0: float, Pny0: float, Po: float) -> float:
    """Method A, Sec3.7. Valid only for Pni >= 0.10*Po."""
    inv = 1.0 / Pnx0 + 1.0 / Pny0 - 1.0 / Po
    if inv <= 0:
        raise ValueError("Non-physical result -- check inputs (Pni <= 0).")
    Pni = 1.0 / inv
    if Pni < 0.10 * Po:
        raise ValueError("Bresler reciprocal-load method is unconservative "
                          "below Pn ~= 0.10*Po; use bresler_load_contour "
                          "instead.")
    return Pni


def bresler_load_contour(Mux: float, Muy: float, phiMnx0: float,
                          phiMny0: float, alpha1: float = 1.5,
                          alpha2: float = 1.5) -> Tuple[float, bool]:
    """
    Method B, Sec3.7. Returns (interaction_value, is_ok).
    is_ok = True if interaction_value <= 1.0 (section adequate).
    """
    value = (Mux / phiMnx0) ** alpha1 + (Muy / phiMny0) ** alpha2
    return value, value <= 1.0


# ---------------------------------------------------------------------------
# Sec3.8 -- Shear Design
# ---------------------------------------------------------------------------

def shear_design(bw: float, d: float, Vu: float, mat: Dict,
                  Av_trial: Optional[float] = None,
                  phi: float = 0.75) -> Dict:
    """Sec3.8"""
    Vc = 2 * mat["lam"] * sqrt(mat["fc"]) * bw * d
    phiVc = phi * Vc
    Vn_req = Vu / phi
    Vs_req = Vn_req - Vc
    Vs_max = 8 * sqrt(mat["fc"]) * bw * d
    section_ok = Vs_req <= Vs_max
    stirrups_required = Vu > 0.5 * phiVc

    s_required = None
    Av_min = None
    if Av_trial is not None and Vs_req > 0:
        s_required = Av_trial * mat["fy"] * d / Vs_req
        Av_min = max(0.75 * sqrt(mat["fc"]) * bw * s_required / mat["fy"],
                     50.0 * bw * s_required / mat["fy"])

    s_max_allow = min(d / 2.0, 24.0) if Vs_req <= 4 * sqrt(mat["fc"]) * bw * d \
        else min(d / 4.0, 12.0)

    return {
        "Vc": Vc, "phiVc": phiVc, "Vn_req": Vn_req, "Vs_req": Vs_req,
        "Vs_max": Vs_max, "section_ok": section_ok,
        "s_required": s_required, "Av_min": Av_min,
        "s_max_allow": s_max_allow,
        "stirrups_required": stirrups_required,
    }


# ---------------------------------------------------------------------------
# Sec3.9 -- Torsion Design
# ---------------------------------------------------------------------------

def torsion_design(b: float, h: float, Tu: float, mat: Dict, cover: float,
                    stirrup_dia: float, theta_deg: float = 45.0,
                    phi: float = 0.75) -> Dict:
    """
    Sec3.9. Solid rectangular section.
    cover: clear cover to stirrup; stirrup_dia: bar diameter of the
    closed stirrup (used to locate the stirrup centreline for x1, y1).
    """
    Acp = b * h
    pcp = 2 * (b + h)
    Tth = mat["lam"] * sqrt(mat["fc"]) * (Acp ** 2 / pcp)
    phiTth = phi * Tth

    result = {
        "Acp": Acp, "pcp": pcp, "Tth": Tth, "phiTth": phiTth,
        "torsion_reinforcement_required": Tu > phiTth,
    }

    if not result["torsion_reinforcement_required"]:
        return result

    offset = cover + stirrup_dia / 2.0
    x1 = b - 2 * offset
    y1 = h - 2 * offset
    Aoh = x1 * y1
    ph = 2 * (x1 + y1)
    Ao = 0.85 * Aoh
    Tn = Tu / phi
    theta = radians(theta_deg)
    At_over_s = Tn / (2 * Ao * mat["fy"] * (1.0 / tan(theta)))
    Al = At_over_s * ph * (1.0 / tan(theta)) ** 2   # fyt == fy assumed equal

    result.update({
        "Aoh": Aoh, "ph": ph, "Ao": Ao, "Tn": Tn,
        "At_over_s": At_over_s, "Al": Al,
    })
    return result


# ---------------------------------------------------------------------------
# Sec3.10 -- Combined Shear + Torsion (section adequacy, solid section)
# ---------------------------------------------------------------------------

def combined_shear_torsion_check(Vu: float, Tu: float, bw: float, d: float,
                                  Aoh: float, ph: float, mat: Dict,
                                  phi: float = 0.75,
                                  Av_over_s: Optional[float] = None,
                                  At_over_s: Optional[float] = None
                                  ) -> Dict:
    """Sec3.10, Sec22.7.7.1 solid rectangular section adequacy check."""
    Vc = 2 * mat["lam"] * sqrt(mat["fc"]) * bw * d
    lhs = sqrt((Vu / (bw * d)) ** 2 + (Tu * ph / (1.7 * Aoh ** 2)) ** 2)
    rhs = phi * (Vc / (bw * d) + 8 * sqrt(mat["fc"]))
    adequate = lhs <= rhs

    combined = None
    if Av_over_s is not None and At_over_s is not None:
        combined = Av_over_s + 2 * At_over_s

    return {
        "lhs": lhs, "rhs": rhs, "adequate": adequate,
        "Av_over_s": Av_over_s, "At_over_s": At_over_s,
        "combined_stirrup_area_over_s": combined,
    }


# ---------------------------------------------------------------------------
# Beam/Column classification (Part II)
# ---------------------------------------------------------------------------

def classify_member(Pu: float, Ag: float, mat: Dict,
                     eta_limit: float = 0.10) -> str:
    """Part II force-based classification test."""
    eta = Pu / (Ag * mat["fc"])
    return "column (beam-column)" if eta >= eta_limit else "beam"


# ---------------------------------------------------------------------------
# Demo / validation against the manual's worked examples
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mat = make_materials(fc=4000.0, fy=60000.0, Es=29_000_000.0)

    print("=" * 70)
    print("Example 1 -- Singly Reinforced Rectangular Beam (design)")
    print("=" * 70)
    Mu1 = 250 * 12 * 1000  # 250 ft-kip -> lb-in
    des1 = singly_reinforced_design(b=12, d=21.5, Mu=Mu1, mat=mat)
    print(f"As required        = {des1['As_required']:.3f} in^2 (manual: 2.865)")
    print(f"As,min             = {des1['As_min']:.3f} in^2 (manual: 0.860)")
    res1 = singly_reinforced_analysis(12, 21.5, 3.16, mat)
    print(f"With 4#8 (As=3.16): a={res1['a']:.3f} c={res1['c']:.3f} "
          f"et={res1['et']:.4f} phi={res1['phi']:.2f} "
          f"phiMn={res1['phiMn']/12000:.1f} ft-kip (manual: 272.7)")

    print("\n" + "=" * 70)
    print("Example 2 -- Doubly Reinforced Rectangular Beam (design)")
    print("=" * 70)
    Mu2 = 460 * 12 * 1000
    des2 = doubly_reinforced_design(b=12, d=21.5, dprime=2.5, Mu=Mu2, mat=mat)
    print(f"As1 = {des2['As1']:.3f} in^2 (manual: 4.660)")
    print(f"As2 = {des2['As2']:.3f} in^2 (manual: 0.947)")
    print(f"A's required = {des2['Aps_required']:.3f} in^2, "
          f"yields={des2['compression_steel_yields']}")
    print(f"As total = {des2['As_total']:.3f} in^2 (manual: 5.607)")
    print(f"phiMn = {des2['phiMn']/12000:.1f} ft-kip (manual: 460.0)")

    print("\n" + "=" * 70)
    print("Example 3 -- T-Beam (true flanged behaviour)")
    print("=" * 70)
    tb = t_beam_analysis(bf=24, bw=12, hf=4, d=20, As=6.5, mat=mat)
    print(f"behaves_as = {tb['behaves_as']}")
    print(f"Asf = {tb['Asf']:.3f} in^2 (manual: 2.720)")
    print(f"Mn1 = {tb['Mn1']/12000:.1f} ft-kip (manual: 244.8)")
    print(f"Asw = {tb['Asw']:.3f} in^2 (manual: 3.780)")
    print(f"Mn2 = {tb['Mn2']/12000:.1f} ft-kip (manual: 325.5)")
    print(f"Mn total = {tb['Mn']/12000:.1f} ft-kip (manual: 570.3)")
    print(f"phiMn = {tb['phiMn']/12000:.1f} ft-kip (manual: 513.2)")

    print("\n" + "=" * 70)
    print("Example 4 -- Pure Axial Compression (Tied Column)")
    print("=" * 70)
    ax = pure_axial_capacity(b=16, h=16, Ast=6.32, mat=mat, tied=True)
    print(f"rho_g = {ax['rho_g']:.4f} (manual: 0.0247)")
    print(f"Po = {ax['Po']/1000:.1f} kip (manual: 1228.1)")
    print(f"Pn,max = {ax['Pn_max']/1000:.1f} kip (manual: 982.5)")
    print(f"phiPn,max = {ax['phiPn_max']/1000:.1f} kip (manual: 638.6)")

    print("\n" + "=" * 70)
    print("Example 5 -- Uniaxial Bending + Axial Load (single point)")
    print("=" * 70)
    layers = [make_rebar_layer(As=3 * 0.79, d=13.5),
              make_rebar_layer(As=3 * 0.79, d=2.5)]
    pt = pm_point(b=16, h=16, layers=layers, c=6.0, mat=mat)
    print(f"At c=6.0 in: Pn={pt['Pn']/1000:.1f} kip (manual ~247.5), "
          f"Mn={pt['Mn']/12000:.1f} ft-kip (manual ~242.6), "
          f"et={pt['et']:.4f} phi={pt['phi']:.3f}")
    pt_bal = pm_point(b=16, h=16, layers=layers, c=7.99, mat=mat)
    print(f"Near balanced c=7.99 in: Pn={pt_bal['Pn']/1000:.1f} kip "
          f"(manual ~360.9), Mn={pt_bal['Mn']/12000:.1f} ft-kip "
          f"(manual ~268.2)")

    print("\n" + "=" * 70)
    print("Example 6 -- Shear Design")
    print("=" * 70)
    sh = shear_design(bw=14, d=21, Vu=62000, mat=mat, Av_trial=0.22)
    print(f"Vc = {sh['Vc']/1000:.2f} kip (manual: 37.19)")
    print(f"phiVc = {sh['phiVc']/1000:.2f} kip (manual: 27.89)")
    print(f"Vs,req = {sh['Vs_req']/1000:.2f} kip (manual: 45.48)")
    print(f"s required = {sh['s_required']:.2f} in (manual: 6.10)")

    print("\n" + "=" * 70)
    print("Example 7 -- Torsion Design")
    print("=" * 70)
    tor = torsion_design(b=16, h=24, Tu=18 * 12000, mat=mat, cover=1.5,
                          stirrup_dia=0.375)
    print(f"Acp = {tor['Acp']:.0f} in^2 (manual: 384)")
    print(f"Tth = {tor['Tth']/12000:.2f} kip-ft (manual: 9.71)")
    print(f"phiTth = {tor['phiTth']/12000:.2f} kip-ft (manual: 7.29)")
    if tor["torsion_reinforcement_required"]:
        print(f"Aoh = {tor['Aoh']:.1f} in^2 (manual: 260.4)")
        print(f"At/s = {tor['At_over_s']:.5f} in^2/in (manual: 0.01084)")
        print(f"Al = {tor['Al']:.3f} in^2 (manual: 0.721)")

    print("\n" + "=" * 70)
    print("Example 11 -- Biaxial Bending (Bresler Load Contour)")
    print("=" * 70)
    value, ok = bresler_load_contour(Mux=150, Muy=95, phiMnx0=175.0,
                                      phiMny0=147.0, alpha1=1.5, alpha2=1.5)
    print(f"Interaction value = {value:.3f} (manual: 1.313), OK={ok}")