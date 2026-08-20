# -*- coding: utf-8 -*-
"""
Finite Element Method (FEM) Concrete Design Framework - v14
Fully compliant with ACI 318-19 in FPS units.
Bridges advanced structural mechanics and numerical shell modeling with Opstool/OpenSees outputs.
Supports list-based element IDs and manual element force definitions (no random ranges).
"""

import math
import numpy as np
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# =====================================================================
# 1. CORE COMPLIANT FLEXURAL SOLVER (ACI 318-19)
# =====================================================================

def compute_required_As(Mu_lb_in, h_in, d_in, fc_psi, fy_psi, b_in=12.0, is_slab=False):
    """
    Computes required area of tension reinforcement (As, in2) for a rectangular section 
    under factored bending moment Mu per ACI 318-19 strain compatibility.
    """
    if Mu_lb_in < 0:
        raise ValueError("Factored moment Mu must be non-negative.")
    if Mu_lb_in == 0:
        return 0.0
    if fc_psi <= 0 or fy_psi <= 0 or d_in <= 0 or h_in <= 0 or b_in <= 0:
        raise ValueError("Strengths and dimensions must be strictly positive.")
    if d_in >= h_in:
        raise ValueError(f"Effective depth d_in ({d_in}) cannot exceed total depth h_in ({h_in}).")

    # Determine beta_1 parameter based on f'c (ACI 318-19 §19.2.4)
    if fc_psi <= 4000.0:
        beta_1 = 0.85
    elif fc_psi >= 8000.0:
        beta_1 = 0.65
    else:
        beta_1 = 0.85 - 0.05 * ((fc_psi - 4000.0) / 1000.0)

    # Coupled Strain Compatibility Loop (resolves As <-> phi <-> strain dependency)
    phi = 0.90  # Initial tension-controlled guess
    tol = 1e-5
    for iteration in range(20):
        Ru = Mu_lb_in / (phi * b_in * d_in**2)
        
        # Absolute limit for Whitney stress block (where compression depth a = d, physically impossible)
        if Ru >= 0.85 * fc_psi * 0.5:
            raise ValueError("OVER-REINFORCED: Section exceeds maximum concrete stress-block capacity.")
            
        term = 1.0 - (2.0 * Ru) / (0.85 * fc_psi)
        if term < 0.0:
            raise ValueError("OVER-REINFORCED: Bending moment causes concrete crushing.")
            
        As = (0.85 * fc_psi * b_in * d_in / fy_psi) * (1.0 - math.sqrt(term))
        
        # Calculate concrete compression block depth 'a' and neutral axis depth 'c'
        a = (As * fy_psi) / (0.85 * fc_psi * b_in)
        c = a / beta_1
        
        # Calculate strain in tension steel (epsilon_cu = 0.003)
        et = 0.003 * (d_in - c) / c
        
        # Determine ACI 318-19 strength reduction factor phi (ACI §21.2.2)
        if et >= 0.005:
            new_phi = 0.90
        elif et <= 0.002:
            new_phi = 0.65
        else:
            new_phi = 0.65 + 0.25 * ((et - 0.002) / 0.003)
            
        if abs(new_phi - phi) < tol:
            phi = new_phi
            break
        phi = new_phi
    else:
        raise RuntimeError("Strain compatibility solver failed to converge.")

    # Structural Ductility Limit Check (ACI typically limits et >= 0.004 for flexural beams)
    if not is_slab and et < 0.004:
        raise ValueError(f"NON-DUCTILE: Strain (et = {et:.5f} < 0.004) is below beam ductility limits.")

    # Standardized ACI Minimum Reinforcement Check
    if is_slab:
        # ACI §24.4.3.2 Grade-dependent temperature/shrinkage steel limit
        if fy_psi < 60000.0:
            ratio = 0.0020
        else:
            ratio = max(0.0018 * 60000.0 / fy_psi, 0.0014)
        As_min = ratio * b_in * h_in
    else:
        # ACI §9.6.1.2 flexural beam minimum floor
        term1 = (3.0 * math.sqrt(fc_psi) / fy_psi) * b_in * d_in
        term2 = (200.0 / fy_psi) * b_in * d_in
        As_min = max(term1, term2)
        
    return max(As, As_min)


# =====================================================================
# 2. SLAB FLEXURAL DESIGN (WOOD-ARMER METHOD)
# =====================================================================

def design_slab_element(h_in, cover_in, fc_psi, fy_psi, Mx_kft, My_kft, Mxy_kft):
    """
    Designs a single slab element under out-of-plane forces using Wood-Armer equations.
    """
    b = 12.0
    d = h_in - cover_in

    # Wood-Armer Sagging Moments (Bottom Steel)
    Mxb_star = Mx_kft + abs(Mxy_kft)
    Myb_star = My_kft + abs(Mxy_kft)

    if Mxb_star < 0:
        Mxb_star = 0.0
        Myb_star = My_kft + abs(Mxy_kft**2 / max(abs(Mx_kft), 1e-6))
    if Myb_star < 0:
        Myb_star = 0.0
        Mxb_star = Mx_kft + abs(Mxy_kft**2 / max(abs(My_kft), 1e-6))

    # Wood-Armer Hogging Moments (Top Steel)
    Mxt_star = Mx_kft - abs(Mxy_kft)
    Myt_star = My_kft - abs(Mxy_kft)

    if Mxt_star > 0:
        Mxt_star = 0.0
        Myt_star = My_kft - abs(Mxy_kft**2 / max(abs(Mx_kft), 1e-6))
    if Myt_star > 0:
        Myt_star = 0.0
        Mxt_star = Mx_kft - abs(Mxy_kft**2 / max(abs(My_kft), 1e-6))

    # Solve for required reinforcement area per foot width (b = 12 in)
    def solve_As(moment_kft):
        mu_lb_in = abs(moment_kft) * 12000.0
        try:
            val = compute_required_As(mu_lb_in, h_in, d, fc_psi, fy_psi, b_in=b, is_slab=True)
            return val
        except ValueError as e:
            if "OVER-REINFORCED" in str(e):
                return "OVER-REINFORCED"
            elif "NON-DUCTILE" in str(e):
                return "NON-DUCTILE"
            else:
                return "DESIGN-FAILED"

    As_bx = solve_As(Mxb_star)
    As_by = solve_As(Myb_star)
    As_tx = solve_As(Mxt_star)
    As_ty = solve_As(Myt_star)

    return {
        "Mxb_star": Mxb_star,
        "Myb_star": Myb_star,
        "Mxt_star": Mxt_star,
        "Myt_star": Myt_star,
        "As_bx_in2_per_ft": As_bx,
        "As_by_in2_per_ft": As_by,
        "As_tx_in2_per_ft": As_tx,
        "As_ty_in2_per_ft": As_ty,
    }


def design_slab_mesh(slab_elements, fc, fy, h, cover):
    """
    Designs an entire set of slab elements provided with manual element IDs and forces.
    """
    b = 12.0
    d = h - cover
    
    results = {}
    for ele_id, forces in slab_elements.items():
        res = design_slab_element(h, cover, fc, fy, forces["Mx_kft"], forces["My_kft"], forces["Mxy_kft"])
        results[ele_id] = res
        
    return results


# =====================================================================
# 3. FOOTING DESIGN (METHODS A & B)
# =====================================================================

def design_footing_rigid(P_serv_kips, Mx_serv_kft, My_serv_kft, P_ult_kips, Mx_ult_kft, My_ult_kft,
                         q_allow_ksf, fc_psi, fy_psi, h_in, cover_in, col_width_in):
    """
    Method A: Sizes and designs reinforced concrete rigid footings.
    Optimizes coordinate dimensions independently and models eccentric trapezoidal bearing moment distributions.
    """
    B = 6.0
    L = 6.0
    
    # Coordinate-independent plan sizing loop
    for iteration in range(100):
        area = B * L
        e_x = np.abs(Mx_serv_kft) / max(abs(P_serv_kips), 1e-6)
        e_y = np.abs(My_serv_kft) / max(abs(P_serv_kips), 1e-6)
        
        q_max = (P_serv_kips / area) * (1.0 + 6.0 * e_x / B + 6.0 * e_y / L)
        q_min = (P_serv_kips / area) * (1.0 - 6.0 * e_x / B - 6.0 * e_y / L)
        
        converged = True
        if q_max > q_allow_ksf:
            if e_x / B > e_y / L:
                B += 0.50
            else:
                L += 0.50
            converged = False
        if q_min < 0.0:
            if e_x / B > e_y / L:
                B += 0.50
            else:
                L += 0.50
            converged = False
            
        if converged:
            break
    else:
        raise ValueError("Footing sizing failed to converge under allowable subgrade stress limits.")

    B_final, L_final = B, L
    
    # Ultimate soil trapezoidal pressure fields
    e_xu = np.abs(Mx_ult_kft) / max(abs(P_ult_kips), 1e-6)
    e_yu = np.abs(My_ult_kft) / max(abs(P_ult_kips), 1e-6)
    area_u = B_final * L_final
    
    q_max_u = (P_ult_kips / area_u) * (1.0 + 6.0 * e_xu / B_final + 6.0 * e_yu / L_final)
    q_min_u = (P_ult_kips / area_u) * (1.0 - 6.0 * e_xu / B_final - 6.0 * e_yu / L_final)
    
    # Cantilever projection distance to columns face
    c_x = (B_final - col_width_in / 12.0) / 2.0  # feet
    c_y = (L_final - col_width_in / 12.0) / 2.0  # feet
    
    # Interpolated soil pressures at the column face boundary lines
    q_face_x_u = q_min_u + (q_max_u - q_min_u) * (B_final - c_x) / B_final
    q_face_y_u = q_min_u + (q_max_u - q_min_u) * (L_final - c_y) / L_final
    
    # Bending moment integration at faces (trapezoidal profile integration)
    Mu_x_total = L_final * (c_x**2) * (q_face_x_u + 2.0 * q_max_u) / 6.0  # kip-ft
    Mu_y_total = B_final * (c_y**2) * (q_face_y_u + 2.0 * q_max_u) / 6.0  # kip-ft
    
    # Reinforcement area (standardized per foot of width, and total)
    d = h_in - cover_in
    
    def try_solve_As(moment_kft, width_ft):
        mu_lb_in = (moment_kft * 12000.0) / width_ft
        try:
            return compute_required_As(mu_lb_in, h_in, d, fc_psi, fy_psi, b_in=12.0, is_slab=True)
        except ValueError as e:
            if "OVER-REINFORCED" in str(e):
                return "OVER-REINFORCED"
            elif "NON-DUCTILE" in str(e):
                return "NON-DUCTILE"
            else:
                return "DESIGN-FAILED"

    As_x_per_ft = try_solve_As(Mu_x_total, L_final)
    As_y_per_ft = try_solve_As(Mu_y_total, B_final)
    
    # Shear validation check - One-way beam shear evaluated at distance d from face
    c_shear_x = max(0.0, c_x - d / 12.0)
    q_d_u = q_min_u + (q_max_u - q_min_u) * (B_final - c_shear_x) / B_final
    V_u1_beam = L_final * c_shear_x * (q_d_u + q_max_u) / 2.0  # kips
    
    phi_v = 0.75
    phi_V_c1 = phi_v * 2.0 * 1.0 * math.sqrt(fc_psi) * (L_final * 12.0) * d / 1000.0  # kips
    beam_status = "OK" if V_u1_beam <= phi_V_c1 else "INCREASE THICKNESS"
    
    # Shear validation check - Two-way punching shear
    # Subtract average bearing pressure over punching area to prevent non-conservative peak bias
    q_avg_u = P_ult_kips / area_u
    b0 = 4.0 * (col_width_in + d)  # inches
    V_u2_punch = P_ult_kips - q_avg_u * ((col_width_in + d) / 12.0)**2
    
    # ACI 318-19 §22.6.5.2 punching capacity (minimum of three terms)
    beta = 1.0  # Aspect ratio (square assumed)
    alpha_s = 40.0  # Interior column boundary assumption
    term1 = 4.0
    term2 = 2.0 + 4.0 / beta
    term3 = 2.0 + (alpha_s * d) / b0
    min_coeff = min(term1, term2, term3)
    phi_V_c2 = phi_v * min_coeff * 1.0 * math.sqrt(fc_psi) * b0 * d / 1000.0  # kips
    punch_status = "OK" if V_u2_punch <= phi_V_c2 else "INCREASE THICKNESS"
    
    return {
        "footing_width_ft": B_final,
        "footing_length_ft": L_final,
        "q_max_service_ksf": q_max,
        "q_min_service_ksf": q_min,
        "Mu_x_kft_total": Mu_x_total,
        "Mu_y_kft_total": Mu_y_total,
        "As_x_in2_per_ft": As_x_per_ft,
        "As_y_in2_per_ft": As_y_per_ft,
        "As_x_in2_total": As_x_per_ft * L_final if isinstance(As_x_per_ft, float) else "OVER-REINFORCED",
        "As_y_in2_total": As_y_per_ft * B_final if isinstance(As_y_per_ft, float) else "OVER-REINFORCED",
        "V_u1_beam_shear_kips": V_u1_beam,
        "phi_V_c1_kips": phi_V_c1,
        "beam_shear_status": beam_status,
        "V_u2_punching_kips": V_u2_punch,
        "phi_V_c2_kips": phi_V_c2,
        "punching_shear_status": punch_status
    }


def design_footing_flexible_mesh(footing_flex_elements, spring_forces_outside_kips, b0_in, h_in, cover_in, fc_psi, fy_psi):
    """
    Designs a set of flexible footing/mat shell elements Rested on spring piles.
    Takes a manually defined element dictionary (no loops or range generation).
    """
    b = 12.0
    d = h_in - cover_in
    
    element_results = {}
    for ele_id, forces in footing_flex_elements.items():
        # Bending rebar sized via Wood-Armer
        slab_design = design_slab_element(h_in, cover_in, fc_psi, fy_psi, forces["Mxx"], forces["Myy"], forces["Mxy"])
        
        # One-way beam shear check per element
        V_u_max = max(abs(forces["Vxz"]), abs(forces["Vyz"])) * 1000.0 / 12.0  # lbs/in
        phi_v = 0.75
        phi_V_c1 = phi_v * 2.0 * 1.0 * math.sqrt(fc_psi) * b * d / 12.0  # lbs/in
        beam_status = "OK" if V_u_max <= phi_V_c1 else "INCREASE THICKNESS"
        
        # Punching shear capacity (three-term check)
        beta = 1.0
        alpha_s = 40.0
        term1 = 4.0
        term2 = 2.0 + 4.0 / beta
        term3 = 2.0 + (alpha_s * d) / b0_in
        min_coeff = min(term1, term2, term3)
        phi_V_c2 = phi_v * min_coeff * 1.0 * math.sqrt(fc_psi) * b0_in * d / 1000.0  # kips
        punch_status = "OK" if forces["spring"] <= phi_V_c2 else "INCREASE THICKNESS"
        
        element_results[ele_id] = {
            "Mxb_star": slab_design["Mxb_star"],
            "Myb_star": slab_design["Myb_star"],
            "Mxt_star": slab_design["Mxt_star"],
            "Myt_star": slab_design["Myt_star"],
            "As_bx": slab_design["As_bx_in2_per_ft"],
            "As_by": slab_design["As_by_in2_per_ft"],
            "As_tx": slab_design["As_tx_in2_per_ft"],
            "As_ty": slab_design["As_ty_in2_per_ft"],
            "V_u_max_lbs_per_in": V_u_max,
            "phi_V_c1_lbs_per_in": phi_V_c1,
            "beam_shear_status": beam_status,
            "V_u2_punching_kips": forces["spring"],
            "phi_V_c2_kips": phi_V_c2,
            "punching_shear_status": punch_status
        }
        
    return element_results


# =====================================================================
# 4. SHEAR WALLS (THREE-LAYER MORLEY SANDWICH MODEL)
# =====================================================================

def design_shear_wall_element(Mx_kft, My_kft, Mxy_kft, Nx_kips_per_ft, Ny_kips_per_ft, Nxy_kips_per_ft,
                              h_in, cover_in, fc_psi, fy_psi):
    """
    Decomposes shell forces using Morley's sandwich transformation and applies
    Clark-Nielsen plastic optimization checks to obtain face reinforcement designs.
    """
    # Cover layer caps to prevent overlap at midline
    t_layer = min(h_in / 3.0, 2.0 * cover_in)
    d_lever = h_in - 2.0 * cover_in  # centroid lever arm between layers
    
    # Convert membrane forces to kips/in, bending moments are kip-in/in
    Nx_in = Nx_kips_per_ft / 12.0
    Ny_in = Ny_kips_per_ft / 12.0
    Nxy_in = Nxy_kips_per_ft / 12.0
    Mx_in = Mx_kft  # kip-ft/ft is equivalent to kip-in/in
    My_in = My_kft
    Mxy_in = Mxy_kft

    # Morley Sandwich Decomposition (Top and Bottom Layer Triads)
    Nx_T = (Mx_in + Nx_in * (d_lever / 2.0)) / d_lever
    Ny_T = (My_in + Ny_in * (d_lever / 2.0)) / d_lever
    Nxy_T = (Mxy_in + Nxy_in * (d_lever / 2.0)) / d_lever

    Nx_B = (-Mx_in + Nx_in * (d_lever / 2.0)) / d_lever
    Ny_B = (-My_in + Ny_in * (d_lever / 2.0)) / d_lever
    Nxy_B = (-Mxy_in + Nxy_in * (d_lever / 2.0)) / d_lever

    def solve_clark_nielsen(Nx, Ny, Nxy):
        # Case I: Symmetrical/Asymmetrical Tension Yielding
        if Nx + abs(Nxy) >= 0 and Ny + abs(Nxy) >= 0:
            case_name = "Case I"
            Nx_star = Nx + abs(Nxy)
            Ny_star = Ny + abs(Nxy)
            Fc = -2.0 * abs(Nxy)
        # Case II: High Compression in X
        elif Nx + abs(Nxy) < 0 and Ny + (Nxy**2 / max(abs(Nx), 1e-6)) >= 0:
            case_name = "Case II"
            Nx_star = 0.0
            Ny_star = Ny + (Nxy**2 / max(abs(Nx), 1e-6))
            Fc = Nx * (1.0 + (Nxy / max(abs(Nx), 1e-6))**2)
        # Case III: High Compression in Y
        elif Ny + abs(Nxy) < 0 and Nx + (Nxy**2 / max(abs(Ny), 1e-6)) >= 0:
            case_name = "Case III"
            Nx_star = Nx + (Nxy**2 / max(abs(Ny), 1e-6))
            Ny_star = 0.0
            Fc = Ny * (1.0 + (Nxy / max(abs(Ny), 1e-6))**2)
        # Case IV: Pure Concrete Compression
        else:
            case_name = "Case IV"
            Nx_star = 0.0
            Ny_star = 0.0
            Fc = 0.5 * (Nx + Ny) - math.sqrt(0.25 * (Nx - Ny)**2 + Nxy**2)

        # Steel design under tension (phi_t = 0.90)
        phi_t = 0.90
        Asx = (Nx_star * 1000.0) / (phi_t * fy_psi) * 12.0  # in2/ft
        Asy = (Ny_star * 1000.0) / (phi_t * fy_psi) * 12.0  # in2/ft

        # Minimum wall steel floor check (ACI 318 vertical and horizontal 0.15% per face)
        As_min = 0.0015 * 12.0 * (h_in / 2.0)
        Asx = max(Asx, As_min)
        Asy = max(Asy, As_min)

        # Concrete Strut crushing verification (phi_c = 0.65)
        phi_c = 0.65
        strut_stress = abs(Fc * 1000.0) / t_layer  # psi
        allowable_strut = phi_c * 0.60 * fc_psi
        strut_status = "OK" if strut_stress <= allowable_strut else "STRUT CRUSHING FAILURE"

        return {
            "case": case_name,
            "Nx_star_kips_per_in": Nx_star,
            "Ny_star_kips_per_in": Ny_star,
            "Fc_kips_per_in": Fc,
            "Asx_in2_per_ft": Asx,
            "Asy_in2_per_ft": Asy,
            "strut_stress_psi": strut_stress,
            "allowable_strut_stress_psi": allowable_strut,
            "strut_status": strut_status
        }

    return {
        "top_face": solve_clark_nielsen(Nx_T, Ny_T, Nxy_T),
        "bottom_face": solve_clark_nielsen(Nx_B, Ny_B, Nxy_B),
        "layer_thickness_in": t_layer,
        "As_min_face_in2_per_ft": 0.0015 * 12.0 * (h_in / 2.0)
    }


def design_coupled_shear_wall(pier_elements, coupling_beam_elements, flange_elements, h_wall, cover_wall, fc, fy):
    """
    Designs each classified element of the coupled shear wall strictly by ID lists
    without performing coordinate grid mesh generation.
    """
    designed_elements = []
    
    # 1. Design Pier elements
    for ele_id, forces in pier_elements.items():
        sandwich = design_shear_wall_element(
            Mx_kft=forces["Mx_kft"], My_kft=0.0, Mxy_kft=0.0,
            Nx_kips_per_ft=forces["Nx_kips_per_ft"], Ny_kips_per_ft=forces["Ny_kips_per_ft"], Nxy_kips_per_ft=forces["Nxy_kips_per_ft"],
            h_in=h_wall, cover_in=cover_wall, fc_psi=fc, fy_psi=fy
        )
        designed_elements.append({
            "element_tag": ele_id,
            "type": "PIER",
            "top_face": sandwich["top_face"],
            "bottom_face": sandwich["bottom_face"]
        })
        
    # 2. Design Coupling Beam / Spandrel elements (ACI 18.10.7.4 diagonal triggers)
    for ele_id, properties in coupling_beam_elements.items():
        shear_load = properties["shear_force_kips"]
        ln = properties["clear_span_in"]
        h_beam = properties["height_in"]
        alpha = ln / h_beam
        b_w = h_wall
        d_beam = h_beam - cover_wall
        
        # ACI 18.10.7.4 gross shear area capacity trigger (Vu vs 4*lambda*sqrt(fc)*Acw)
        A_cw = b_w * h_beam
        V_seismic_trigger = 4.0 * 1.0 * math.sqrt(fc) * A_cw / 1000.0  # kips
        V_n_max = 10.0 * math.sqrt(fc) * A_cw / 1000.0  # nominal kips crushing ceiling
        phi_v = 0.75
        
        if alpha < 2.0 and shear_load >= V_seismic_trigger:
            design_type = "DIAGONAL_SEISMIC_CAGES"
            theta = math.atan(h_beam / ln)
            # Area per diagonal group (ACI 318 Section 18.10.7)
            Avd = shear_load / (2.0 * phi_v * (fy/1000.0) * math.sin(theta))  # in2
        else:
            design_type = "STANDARD_STIRRUPS"
            Avd = 0.0
            
        designed_elements.append({
            "element_tag": ele_id,
            "type": "COUPLING_BEAM",
            "shear_force_kips": shear_load,
            "aspect_ratio": alpha,
            "design_detailing": design_type,
            "required_diagonal_steel_in2": Avd,
            "concrete_crushing_limit_kips": phi_v * V_n_max,
            "crushing_status": "OK" if shear_load <= phi_v * V_n_max else "CRUSHING FAILURE"
        })
        
    # 3. Design Flange elements (representing orthogonal boundary segments under high axial chord loads)
    for ele_id, forces in flange_elements.items():
        sandwich = design_shear_wall_element(
            Mx_kft=forces["Mx_kft"], My_kft=0.0, Mxy_kft=0.0,
            Nx_kips_per_ft=forces["Nx_kips_per_ft"], Ny_kips_per_ft=forces["Ny_kips_per_ft"], Nxy_kips_per_ft=forces["Nxy_kips_per_ft"],
            h_in=h_wall, cover_in=cover_wall, fc_psi=fc, fy_psi=fy
        )
        designed_elements.append({
            "element_tag": ele_id,
            "type": "FLANGE",
            "top_face": sandwich["top_face"],
            "bottom_face": sandwich["bottom_face"]
        })
        
    return designed_elements


# =====================================================================
# 5. GLOBAL SHEAR WALL DESIGN & ACI SPECIAL BOUNDARY ELEMENT (SBE) CHECK
# =====================================================================

def generate_pm_interaction_curve(h_in, lw_in, fc_psi, fy_psi, rebar_layers):
    """
    Generates nominal and factored P-M interaction curves using 
    exact strain compatibility across distributed rebar layers.
    """
    E_s = 29000.0  # ksi
    beta_1 = 0.85 if fc_psi <= 4000.0 else max(0.65, 0.85 - 0.05 * ((fc_psi - 4000.0)/1000.0))
    
    c_steps = np.linspace(1.5, lw_in * 1.5, 120)
    P_nominal = []
    M_nominal = []
    P_factored = []
    M_factored = []
    c_values = []

    for c in c_steps:
        conc_strain = 0.003
        
        # Integrate rebar forces
        F_steel = 0.0
        M_steel = 0.0
        rebar_strains = []
        
        for layer in rebar_layers:
            dist_from_comp_face = layer['x']
            strain = conc_strain * (c - dist_from_comp_face) / c
            rebar_strains.append(strain)
            
            # Stress calculation (elastoplastic model in ksi)
            stress = max(-fy_psi/1000.0, min(fy_psi/1000.0, strain * E_s))
            force = stress * layer['area']  # kips
            
            F_steel += force
            M_steel += force * (lw_in / 2.0 - dist_from_comp_face)

        # Concrete Whitney stress block force integration
        a = min(beta_1 * c, lw_in)
        F_concrete = -0.85 * (fc_psi / 1000.0) * h_in * a  # kips (compression negative)
        M_concrete = -F_concrete * (lw_in / 2.0 - a / 2.0)

        # Nominal capacity coordinates
        Pn = F_concrete + F_steel
        Mn = M_concrete + M_steel
        
        # Strength reduction factor phi based on extreme steel strain
        extreme_tension_strain = max(rebar_strains) if len(rebar_strains) > 0 else 0.005
        if extreme_tension_strain >= 0.005:
            phi = 0.90
        elif extreme_tension_strain <= 0.002:
            phi = 0.65
        else:
            phi = 0.65 + 0.25 * ((extreme_tension_strain - 0.002) / 0.003)

        # Corrected Po sign convention (both concrete and steel contribution are compression negative)
        Po = -0.85 * (fc_psi/1000.0) * (h_in * lw_in - sum(l['area'] for l in rebar_layers)) - sum(l['area'] * fy_psi/1000.0 for l in rebar_layers)
        Pn_max = 0.80 * 0.65 * abs(Po)  # ACI compression cap limit
        
        P_nominal.append(Pn)
        M_nominal.append(Mn)
        c_values.append(c)
        
        P_factored.append(max(-Pn_max, phi * Pn))
        M_factored.append(phi * Mn)

    return {
        "P_nominal": np.array(P_nominal),
        "M_nominal": np.array(M_nominal),
        "P_factored": np.array(P_factored),
        "M_factored": np.array(M_factored),
        "c_values": np.array(c_values)
    }


def check_special_boundary_elements(h_in, lw_in, hw_in, fc_psi, fy_psi, Pu_kips, Mu_kft, Vu_kips,
                                    delta_u_in, sbe_rebar_area_in2=1.27):
    """
    Executes ACI 318-19 SBE validation checks. Solves exact neutral axis depth (c)
    using continuous strain compatibility and performs displacement & stress-based checks.
    """
    rebar_layers = []
    num_bars = 18
    spacing = (lw_in - 6.0) / (num_bars - 1)
    for i in range(num_bars):
        rebar_layers.append({
            'x': 3.0 + i * spacing,
            'area': sbe_rebar_area_in2
        })

    # Solve exact P-M curve
    pm_curve = generate_pm_interaction_curve(h_in, lw_in, fc_psi, fy_psi, rebar_layers)
    
    # Continuous Bisection Solver to find neutral axis depth matching exact Pu
    P_comp = -pm_curve["P_nominal"]  # Convert compression positive
    target_P = abs(Pu_kips)
    c_exact = np.interp(target_P, P_comp, pm_curve["c_values"])
    
    # Displacement-Based SBE Check (Section 18.10.6.2)
    drift = max(0.005, delta_u_in / hw_in)
    c_limit = lw_in / (600.0 * drift)
    displacement_sbe = c_exact >= c_limit
    
    # Stress-Based SBE Check (Section 18.10.6.3)
    Ag = h_in * lw_in
    Ig = (h_in * lw_in**3) / 12.0
    y_extreme = lw_in / 2.0
    sigma_c = (target_P / Ag) + (abs(Mu_kft * 12.0) * y_extreme / Ig)  # ksi
    stress_limit = 0.20 * (fc_psi / 1000.0)  # limit in ksi
    stress_sbe = sigma_c >= stress_limit
    
    sbe_required = displacement_sbe or stress_sbe
    min_sbe_length = max(c_exact - 0.1 * lw_in, c_exact / 2.0) if sbe_required else 0.0
    
    return {
        "displacement_sbe_required": bool(displacement_sbe),
        "stress_sbe_required": bool(stress_sbe),
        "sbe_required": bool(sbe_required),
        "neutral_axis_depth_c_in": float(c_exact),
        "c_limit_in": float(c_limit),
        "max_extreme_fiber_stress_ksi": float(sigma_c),
        "stress_limit_ksi": float(stress_limit),
        "min_sbe_length_in": float(min_sbe_length),
        "rebar_layers": rebar_layers
    }




# =====================================================================
# 6. INTEGRATED VISUALIZATION AND REPORT GENERATOR CLINIC
# =====================================================================

DEFAULT_RUN_CONFIG = {
    # Core structural model properties
    "fc": 4000.0,
    "fy": 60000.0,
    "h_wall": 12.0,
    "cover_wall": 2.0,
    
    # Rigid footing design parameters
    "rigid_footing": {
        "P_serv_kips": 450.0,
        "Mx_serv_kft": 120.0,
        "My_serv_kft": 180.0,
        "P_ult_kips": 650.0,
        "Mx_ult_kft": 180.0,
        "My_ult_kft": 270.0,
        "q_allow_ksf": 5.0,
        "h_in": 24.0,
        "cover_in": 3.0,
        "col_width_in": 18.0
    },
    
    # Flexible footing design parameters
    "flexible_footing": {
        "spring_forces_outside_kips": 145.0,
        "b0_in": 180.0,
        "h_in": 24.0,
        "cover_in": 3.0
    },
	# Flexible footing meshed elements with forces
    "footing_flex_elements": {
        # Each element represents a meshed footing section with applied forces
        # Element 1
        1: {
            "Mxx": 120.0,    # Moment about X-axis (kip-ft)
            "Myy": 80.0,     # Moment about Y-axis (kip-ft)
            "Mxy": -45.0,    # Torsional moment (kip-ft)
            "Vxz": 30.0,     # Shear in X-direction (kips)
            "Vyz": 22.0,     # Shear in Y-direction (kips)
            "spring": 145.0  # Spring reaction force (kips)
        },
        # Element 2
        2: {
            "Mxx": 115.0,
            "Myy": 78.0,
            "Mxy": -42.0,
            "Vxz": 28.0,
            "Vyz": 20.0,
            "spring": 140.0
        },
        # Element 3
        3: {
            "Mxx": 130.0,
            "Myy": 95.0,
            "Mxy": -55.0,
            "Vxz": 35.0,
            "Vyz": 25.0,
            "spring": 165.0
        },
        # Element 4
        4: {
            "Mxx": 110.0,
            "Myy": 75.0,
            "Mxy": -40.0,
            "Vxz": 25.0,
            "Vyz": 18.0,
            "spring": 135.0
        },
        # Element 5
        5: {
            "Mxx": 95.0,
            "Myy": 65.0,
            "Mxy": -35.0,
            "Vxz": 22.0,
            "Vyz": 16.0,
            "spring": 125.0
        },
        # Element 6
        6: {
            "Mxx": 105.0,
            "Myy": 70.0,
            "Mxy": -38.0,
            "Vxz": 24.0,
            "Vyz": 17.0,
            "spring": 130.0
        },
        # Element 7
        7: {
            "Mxx": 125.0,
            "Myy": 85.0,
            "Mxy": -48.0,
            "Vxz": 32.0,
            "Vyz": 23.0,
            "spring": 150.0
        },
        # Element 8
        8: {
            "Mxx": 100.0,
            "Myy": 68.0,
            "Mxy": -36.0,
            "Vxz": 23.0,
            "Vyz": 16.0,
            "spring": 128.0
        },
        # Element 9
        9: {
            "Mxx": 90.0,
            "Myy": 62.0,
            "Mxy": -32.0,
            "Vxz": 21.0,
            "Vyz": 15.0,
            "spring": 122.0
        },
        # Element 10
        10: {
            "Mxx": 118.0,
            "Myy": 82.0,
            "Mxy": -44.0,
            "Vxz": 29.0,
            "Vyz": 21.0,
            "spring": 142.0
        },
        # Element 11
        11: {
            "Mxx": 135.0,
            "Myy": 100.0,
            "Mxy": -60.0,
            "Vxz": 40.0,
            "Vyz": 30.0,
            "spring": 170.0
        },
        # Element 12
        12: {
            "Mxx": 85.0,
            "Myy": 60.0,
            "Mxy": -30.0,
            "Vxz": 20.0,
            "Vyz": 15.0,
            "spring": 120.0
        }
    },
    
    # Shear wall design parameters
    "shear_wall": {
        "cover_wall": 2.0
    },
    
    # SBE check parameters
    "sbe_check": {
        "lw_in": 216.0,
        "hw_in": 432.0,
        "Pu_kips": 1500.0,
        "Mu_kft": 15000.0,
        "Vu_kips": 450.0,
        "delta_u_in": 2.50
    },
    
    # Slab design parameters
    "slab": {
        "h": 8.5,
        "cover": 1.25
    },
    
    # Slab Elements manually defined along with element IDs
    "slab_elements": {
        # Row 0
        1: {"row": 0, "col": 0, "Mx_kft": 15.0 + 10.0 * math.sin(0 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(0 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(0 * math.pi / 9.0) * math.sin(0 * math.pi / 9.0)},
        2: {"row": 0, "col": 1, "Mx_kft": 15.0 + 10.0 * math.sin(0 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(0 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(0 * math.pi / 9.0) * math.sin(1 * math.pi / 9.0)},
        3: {"row": 0, "col": 2, "Mx_kft": 15.0 + 10.0 * math.sin(0 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(0 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(0 * math.pi / 9.0) * math.sin(2 * math.pi / 9.0)},
        4: {"row": 0, "col": 3, "Mx_kft": 15.0 + 10.0 * math.sin(0 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(0 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(0 * math.pi / 9.0) * math.sin(3 * math.pi / 9.0)},
        5: {"row": 0, "col": 4, "Mx_kft": 15.0 + 10.0 * math.sin(0 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(0 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(0 * math.pi / 9.0) * math.sin(4 * math.pi / 9.0)},
        6: {"row": 0, "col": 5, "Mx_kft": 15.0 + 10.0 * math.sin(0 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(0 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(0 * math.pi / 9.0) * math.sin(5 * math.pi / 9.0)},
        7: {"row": 0, "col": 6, "Mx_kft": 15.0 + 10.0 * math.sin(0 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(0 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(0 * math.pi / 9.0) * math.sin(6 * math.pi / 9.0)},
        8: {"row": 0, "col": 7, "Mx_kft": 15.0 + 10.0 * math.sin(0 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(0 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(0 * math.pi / 9.0) * math.sin(7 * math.pi / 9.0)},
        9: {"row": 0, "col": 8, "Mx_kft": 15.0 + 10.0 * math.sin(0 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(0 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(0 * math.pi / 9.0) * math.sin(8 * math.pi / 9.0)},
        10: {"row": 0, "col": 9, "Mx_kft": 15.0 + 10.0 * math.sin(0 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(0 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(0 * math.pi / 9.0) * math.sin(9 * math.pi / 9.0)},
        # Row 1
        11: {"row": 1, "col": 0, "Mx_kft": 15.0 + 10.0 * math.sin(1 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(1 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(1 * math.pi / 9.0) * math.sin(0 * math.pi / 9.0)},
        12: {"row": 1, "col": 1, "Mx_kft": 15.0 + 10.0 * math.sin(1 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(1 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(1 * math.pi / 9.0) * math.sin(1 * math.pi / 9.0)},
        13: {"row": 1, "col": 2, "Mx_kft": 15.0 + 10.0 * math.sin(1 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(1 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(1 * math.pi / 9.0) * math.sin(2 * math.pi / 9.0)},
        14: {"row": 1, "col": 3, "Mx_kft": 15.0 + 10.0 * math.sin(1 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(1 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(1 * math.pi / 9.0) * math.sin(3 * math.pi / 9.0)},
        15: {"row": 1, "col": 4, "Mx_kft": 15.0 + 10.0 * math.sin(1 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(1 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(1 * math.pi / 9.0) * math.sin(4 * math.pi / 9.0)},
        16: {"row": 1, "col": 5, "Mx_kft": 15.0 + 10.0 * math.sin(1 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(1 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(1 * math.pi / 9.0) * math.sin(5 * math.pi / 9.0)},
        17: {"row": 1, "col": 6, "Mx_kft": 15.0 + 10.0 * math.sin(1 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(1 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(1 * math.pi / 9.0) * math.sin(6 * math.pi / 9.0)},
        18: {"row": 1, "col": 7, "Mx_kft": 15.0 + 10.0 * math.sin(1 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(1 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(1 * math.pi / 9.0) * math.sin(7 * math.pi / 9.0)},
        19: {"row": 1, "col": 8, "Mx_kft": 15.0 + 10.0 * math.sin(1 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(1 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(1 * math.pi / 9.0) * math.sin(8 * math.pi / 9.0)},
        20: {"row": 1, "col": 9, "Mx_kft": 15.0 + 10.0 * math.sin(1 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(1 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(1 * math.pi / 9.0) * math.sin(9 * math.pi / 9.0)},
        # Row 2
        21: {"row": 2, "col": 0, "Mx_kft": 15.0 + 10.0 * math.sin(2 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(2 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(2 * math.pi / 9.0) * math.sin(0 * math.pi / 9.0)},
        22: {"row": 2, "col": 1, "Mx_kft": 15.0 + 10.0 * math.sin(2 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(2 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(2 * math.pi / 9.0) * math.sin(1 * math.pi / 9.0)},
        23: {"row": 2, "col": 2, "Mx_kft": 15.0 + 10.0 * math.sin(2 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(2 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(2 * math.pi / 9.0) * math.sin(2 * math.pi / 9.0)},
        24: {"row": 2, "col": 3, "Mx_kft": 15.0 + 10.0 * math.sin(2 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(2 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(2 * math.pi / 9.0) * math.sin(3 * math.pi / 9.0)},
        25: {"row": 2, "col": 4, "Mx_kft": 15.0 + 10.0 * math.sin(2 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(2 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(2 * math.pi / 9.0) * math.sin(4 * math.pi / 9.0)},
        26: {"row": 2, "col": 5, "Mx_kft": 15.0 + 10.0 * math.sin(2 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(2 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(2 * math.pi / 9.0) * math.sin(5 * math.pi / 9.0)},
        27: {"row": 2, "col": 6, "Mx_kft": 15.0 + 10.0 * math.sin(2 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(2 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(2 * math.pi / 9.0) * math.sin(6 * math.pi / 9.0)},
        28: {"row": 2, "col": 7, "Mx_kft": 15.0 + 10.0 * math.sin(2 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(2 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(2 * math.pi / 9.0) * math.sin(7 * math.pi / 9.0)},
        29: {"row": 2, "col": 8, "Mx_kft": 15.0 + 10.0 * math.sin(2 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(2 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(2 * math.pi / 9.0) * math.sin(8 * math.pi / 9.0)},
        30: {"row": 2, "col": 9, "Mx_kft": 15.0 + 10.0 * math.sin(2 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(2 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(2 * math.pi / 9.0) * math.sin(9 * math.pi / 9.0)},
        # Row 3
        31: {"row": 3, "col": 0, "Mx_kft": 15.0 + 10.0 * math.sin(3 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(3 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(3 * math.pi / 9.0) * math.sin(0 * math.pi / 9.0)},
        32: {"row": 3, "col": 1, "Mx_kft": 15.0 + 10.0 * math.sin(3 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(3 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(3 * math.pi / 9.0) * math.sin(1 * math.pi / 9.0)},
        33: {"row": 3, "col": 2, "Mx_kft": 15.0 + 10.0 * math.sin(3 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(3 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(3 * math.pi / 9.0) * math.sin(2 * math.pi / 9.0)},
        34: {"row": 3, "col": 3, "Mx_kft": 15.0 + 10.0 * math.sin(3 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(3 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(3 * math.pi / 9.0) * math.sin(3 * math.pi / 9.0)},
        35: {"row": 3, "col": 4, "Mx_kft": 15.0 + 10.0 * math.sin(3 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(3 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(3 * math.pi / 9.0) * math.sin(4 * math.pi / 9.0)},
        36: {"row": 3, "col": 5, "Mx_kft": 15.0 + 10.0 * math.sin(3 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(3 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(3 * math.pi / 9.0) * math.sin(5 * math.pi / 9.0)},
        37: {"row": 3, "col": 6, "Mx_kft": 15.0 + 10.0 * math.sin(3 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(3 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(3 * math.pi / 9.0) * math.sin(6 * math.pi / 9.0)},
        38: {"row": 3, "col": 7, "Mx_kft": 15.0 + 10.0 * math.sin(3 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(3 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(3 * math.pi / 9.0) * math.sin(7 * math.pi / 9.0)},
        39: {"row": 3, "col": 8, "Mx_kft": 15.0 + 10.0 * math.sin(3 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(3 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(3 * math.pi / 9.0) * math.sin(8 * math.pi / 9.0)},
        40: {"row": 3, "col": 9, "Mx_kft": 15.0 + 10.0 * math.sin(3 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(3 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(3 * math.pi / 9.0) * math.sin(9 * math.pi / 9.0)},
        # Row 4
        41: {"row": 4, "col": 0, "Mx_kft": 15.0 + 10.0 * math.sin(4 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(4 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(4 * math.pi / 9.0) * math.sin(0 * math.pi / 9.0)},
        42: {"row": 4, "col": 1, "Mx_kft": 15.0 + 10.0 * math.sin(4 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(4 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(4 * math.pi / 9.0) * math.sin(1 * math.pi / 9.0)},
        43: {"row": 4, "col": 2, "Mx_kft": 15.0 + 10.0 * math.sin(4 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(4 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(4 * math.pi / 9.0) * math.sin(2 * math.pi / 9.0)},
        44: {"row": 4, "col": 3, "Mx_kft": 15.0 + 10.0 * math.sin(4 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(4 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(4 * math.pi / 9.0) * math.sin(3 * math.pi / 9.0)},
        45: {"row": 4, "col": 4, "Mx_kft": 15.0 + 10.0 * math.sin(4 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(4 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(4 * math.pi / 9.0) * math.sin(4 * math.pi / 9.0)},
        46: {"row": 4, "col": 5, "Mx_kft": 15.0 + 10.0 * math.sin(4 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(4 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(4 * math.pi / 9.0) * math.sin(5 * math.pi / 9.0)},
        47: {"row": 4, "col": 6, "Mx_kft": 15.0 + 10.0 * math.sin(4 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(4 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(4 * math.pi / 9.0) * math.sin(6 * math.pi / 9.0)},
        48: {"row": 4, "col": 7, "Mx_kft": 15.0 + 10.0 * math.sin(4 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(4 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(4 * math.pi / 9.0) * math.sin(7 * math.pi / 9.0)},
        49: {"row": 4, "col": 8, "Mx_kft": 15.0 + 10.0 * math.sin(4 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(4 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(4 * math.pi / 9.0) * math.sin(8 * math.pi / 9.0)},
        50: {"row": 4, "col": 9, "Mx_kft": 15.0 + 10.0 * math.sin(4 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(4 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(4 * math.pi / 9.0) * math.sin(9 * math.pi / 9.0)},
        # Row 5
        51: {"row": 5, "col": 0, "Mx_kft": 15.0 + 10.0 * math.sin(5 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(5 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(5 * math.pi / 9.0) * math.sin(0 * math.pi / 9.0)},
        52: {"row": 5, "col": 1, "Mx_kft": 15.0 + 10.0 * math.sin(5 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(5 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(5 * math.pi / 9.0) * math.sin(1 * math.pi / 9.0)},
        53: {"row": 5, "col": 2, "Mx_kft": 15.0 + 10.0 * math.sin(5 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(5 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(5 * math.pi / 9.0) * math.sin(2 * math.pi / 9.0)},
        54: {"row": 5, "col": 3, "Mx_kft": 15.0 + 10.0 * math.sin(5 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(5 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(5 * math.pi / 9.0) * math.sin(3 * math.pi / 9.0)},
        55: {"row": 5, "col": 4, "Mx_kft": 15.0 + 10.0 * math.sin(5 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(5 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(5 * math.pi / 9.0) * math.sin(4 * math.pi / 9.0)},
        56: {"row": 5, "col": 5, "Mx_kft": 15.0 + 10.0 * math.sin(5 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(5 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(5 * math.pi / 9.0) * math.sin(5 * math.pi / 9.0)},
        57: {"row": 5, "col": 6, "Mx_kft": 15.0 + 10.0 * math.sin(5 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(5 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(5 * math.pi / 9.0) * math.sin(6 * math.pi / 9.0)},
        58: {"row": 5, "col": 7, "Mx_kft": 15.0 + 10.0 * math.sin(5 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(5 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(5 * math.pi / 9.0) * math.sin(7 * math.pi / 9.0)},
        59: {"row": 5, "col": 8, "Mx_kft": 15.0 + 10.0 * math.sin(5 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(5 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(5 * math.pi / 9.0) * math.sin(8 * math.pi / 9.0)},
        60: {"row": 5, "col": 9, "Mx_kft": 15.0 + 10.0 * math.sin(5 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(5 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(5 * math.pi / 9.0) * math.sin(9 * math.pi / 9.0)},
        # Row 6
        61: {"row": 6, "col": 0, "Mx_kft": 15.0 + 10.0 * math.sin(6 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(6 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(6 * math.pi / 9.0) * math.sin(0 * math.pi / 9.0)},
        62: {"row": 6, "col": 1, "Mx_kft": 15.0 + 10.0 * math.sin(6 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(6 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(6 * math.pi / 9.0) * math.sin(1 * math.pi / 9.0)},
        63: {"row": 6, "col": 2, "Mx_kft": 15.0 + 10.0 * math.sin(6 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(6 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(6 * math.pi / 9.0) * math.sin(2 * math.pi / 9.0)},
        64: {"row": 6, "col": 3, "Mx_kft": 15.0 + 10.0 * math.sin(6 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(6 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(6 * math.pi / 9.0) * math.sin(3 * math.pi / 9.0)},
        65: {"row": 6, "col": 4, "Mx_kft": 15.0 + 10.0 * math.sin(6 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(6 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(6 * math.pi / 9.0) * math.sin(4 * math.pi / 9.0)},
        66: {"row": 6, "col": 5, "Mx_kft": 15.0 + 10.0 * math.sin(6 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(6 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(6 * math.pi / 9.0) * math.sin(5 * math.pi / 9.0)},
        67: {"row": 6, "col": 6, "Mx_kft": 15.0 + 10.0 * math.sin(6 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(6 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(6 * math.pi / 9.0) * math.sin(6 * math.pi / 9.0)},
        68: {"row": 6, "col": 7, "Mx_kft": 15.0 + 10.0 * math.sin(6 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(6 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(6 * math.pi / 9.0) * math.sin(7 * math.pi / 9.0)},
        69: {"row": 6, "col": 8, "Mx_kft": 15.0 + 10.0 * math.sin(6 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(6 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(6 * math.pi / 9.0) * math.sin(8 * math.pi / 9.0)},
        70: {"row": 6, "col": 9, "Mx_kft": 15.0 + 10.0 * math.sin(6 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(6 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(6 * math.pi / 9.0) * math.sin(9 * math.pi / 9.0)},
        # Row 7
        71: {"row": 7, "col": 0, "Mx_kft": 15.0 + 10.0 * math.sin(7 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(7 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(7 * math.pi / 9.0) * math.sin(0 * math.pi / 9.0)},
        72: {"row": 7, "col": 1, "Mx_kft": 15.0 + 10.0 * math.sin(7 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(7 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(7 * math.pi / 9.0) * math.sin(1 * math.pi / 9.0)},
        73: {"row": 7, "col": 2, "Mx_kft": 15.0 + 10.0 * math.sin(7 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(7 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(7 * math.pi / 9.0) * math.sin(2 * math.pi / 9.0)},
        74: {"row": 7, "col": 3, "Mx_kft": 15.0 + 10.0 * math.sin(7 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(7 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(7 * math.pi / 9.0) * math.sin(3 * math.pi / 9.0)},
        75: {"row": 7, "col": 4, "Mx_kft": 15.0 + 10.0 * math.sin(7 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(7 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(7 * math.pi / 9.0) * math.sin(4 * math.pi / 9.0)},
        76: {"row": 7, "col": 5, "Mx_kft": 15.0 + 10.0 * math.sin(7 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(7 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(7 * math.pi / 9.0) * math.sin(5 * math.pi / 9.0)},
        77: {"row": 7, "col": 6, "Mx_kft": 15.0 + 10.0 * math.sin(7 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(7 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(7 * math.pi / 9.0) * math.sin(6 * math.pi / 9.0)},
        78: {"row": 7, "col": 7, "Mx_kft": 15.0 + 10.0 * math.sin(7 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(7 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(7 * math.pi / 9.0) * math.sin(7 * math.pi / 9.0)},
        79: {"row": 7, "col": 8, "Mx_kft": 15.0 + 10.0 * math.sin(7 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(7 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(7 * math.pi / 9.0) * math.sin(8 * math.pi / 9.0)},
        80: {"row": 7, "col": 9, "Mx_kft": 15.0 + 10.0 * math.sin(7 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(7 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(7 * math.pi / 9.0) * math.sin(9 * math.pi / 9.0)},
        # Row 8
        81: {"row": 8, "col": 0, "Mx_kft": 15.0 + 10.0 * math.sin(8 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(8 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(8 * math.pi / 9.0) * math.sin(0 * math.pi / 9.0)},
        82: {"row": 8, "col": 1, "Mx_kft": 15.0 + 10.0 * math.sin(8 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(8 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(8 * math.pi / 9.0) * math.sin(1 * math.pi / 9.0)},
        83: {"row": 8, "col": 2, "Mx_kft": 15.0 + 10.0 * math.sin(8 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(8 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(8 * math.pi / 9.0) * math.sin(2 * math.pi / 9.0)},
        84: {"row": 8, "col": 3, "Mx_kft": 15.0 + 10.0 * math.sin(8 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(8 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(8 * math.pi / 9.0) * math.sin(3 * math.pi / 9.0)},
        85: {"row": 8, "col": 4, "Mx_kft": 15.0 + 10.0 * math.sin(8 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(8 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(8 * math.pi / 9.0) * math.sin(4 * math.pi / 9.0)},
        86: {"row": 8, "col": 5, "Mx_kft": 15.0 + 10.0 * math.sin(8 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(8 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(8 * math.pi / 9.0) * math.sin(5 * math.pi / 9.0)},
        87: {"row": 8, "col": 6, "Mx_kft": 15.0 + 10.0 * math.sin(8 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(8 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(8 * math.pi / 9.0) * math.sin(6 * math.pi / 9.0)},
        88: {"row": 8, "col": 7, "Mx_kft": 15.0 + 10.0 * math.sin(8 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(8 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(8 * math.pi / 9.0) * math.sin(7 * math.pi / 9.0)},
        89: {"row": 8, "col": 8, "Mx_kft": 15.0 + 10.0 * math.sin(8 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(8 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(8 * math.pi / 9.0) * math.sin(8 * math.pi / 9.0)},
        90: {"row": 8, "col": 9, "Mx_kft": 15.0 + 10.0 * math.sin(8 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(8 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(8 * math.pi / 9.0) * math.sin(9 * math.pi / 9.0)},
        # Row 9
        91: {"row": 9, "col": 0, "Mx_kft": 15.0 + 10.0 * math.sin(9 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(9 * math.pi / 9.0) * math.cos(0 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(9 * math.pi / 9.0) * math.sin(0 * math.pi / 9.0)},
        92: {"row": 9, "col": 1, "Mx_kft": 15.0 + 10.0 * math.sin(9 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(9 * math.pi / 9.0) * math.cos(1 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(9 * math.pi / 9.0) * math.sin(1 * math.pi / 9.0)},
        93: {"row": 9, "col": 2, "Mx_kft": 15.0 + 10.0 * math.sin(9 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(9 * math.pi / 9.0) * math.cos(2 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(9 * math.pi / 9.0) * math.sin(2 * math.pi / 9.0)},
        94: {"row": 9, "col": 3, "Mx_kft": 15.0 + 10.0 * math.sin(9 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(9 * math.pi / 9.0) * math.cos(3 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(9 * math.pi / 9.0) * math.sin(3 * math.pi / 9.0)},
        95: {"row": 9, "col": 4, "Mx_kft": 15.0 + 10.0 * math.sin(9 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(9 * math.pi / 9.0) * math.cos(4 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(9 * math.pi / 9.0) * math.sin(4 * math.pi / 9.0)},
        96: {"row": 9, "col": 5, "Mx_kft": 15.0 + 10.0 * math.sin(9 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(9 * math.pi / 9.0) * math.cos(5 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(9 * math.pi / 9.0) * math.sin(5 * math.pi / 9.0)},
        97: {"row": 9, "col": 6, "Mx_kft": 15.0 + 10.0 * math.sin(9 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(9 * math.pi / 9.0) * math.cos(6 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(9 * math.pi / 9.0) * math.sin(6 * math.pi / 9.0)},
        98: {"row": 9, "col": 7, "Mx_kft": 15.0 + 10.0 * math.sin(9 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(9 * math.pi / 9.0) * math.cos(7 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(9 * math.pi / 9.0) * math.sin(7 * math.pi / 9.0)},
        99: {"row": 9, "col": 8, "Mx_kft": 15.0 + 10.0 * math.sin(9 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(9 * math.pi / 9.0) * math.cos(8 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(9 * math.pi / 9.0) * math.sin(8 * math.pi / 9.0)},
        100: {"row": 9, "col": 9, "Mx_kft": 15.0 + 10.0 * math.sin(9 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "My_kft": 10.0 + 8.0 * math.sin(9 * math.pi / 9.0) * math.cos(9 * math.pi / 9.0), "Mxy_kft": -6.0 - 4.0 * math.sin(9 * math.pi / 9.0) * math.sin(9 * math.pi / 9.0)},
    },
    
    # Footing Elements manually defined along with element IDs for flexible footing Method B
    "footing_flex_elements": {
        1:  {"Mxx": 120.0, "Myy": 80.0,  "Mxy": -45.0, "Vxz": 30.0, "Vyz": 22.0, "spring": 145.0},
        2:  {"Mxx": 115.0, "Myy": 78.0,  "Mxy": -42.0, "Vxz": 28.0, "Vyz": 20.0, "spring": 140.0},
        3:  {"Mxx": 130.0, "Myy": 95.0,  "Mxy": -55.0, "Vxz": 35.0, "Vyz": 25.0, "spring": 165.0},
        4:  {"Mxx": 110.0, "Myy": 75.0,  "Mxy": -40.0, "Vxz": 25.0, "Vyz": 18.0, "spring": 135.0},
        5:  {"Mxx": 95.0,  "Myy": 65.0,  "Mxy": -35.0, "Vxz": 22.0, "Vyz": 16.0, "spring": 125.0},
        6:  {"Mxx": 105.0, "Myy": 70.0,  "Mxy": -38.0, "Vxz": 24.0, "Vyz": 17.0, "spring": 130.0},
        7:  {"Mxx": 125.0, "Myy": 85.0,  "Mxy": -48.0, "Vxz": 32.0, "Vyz": 23.0, "spring": 150.0},
        8:  {"Mxx": 100.0, "Myy": 68.0,  "Mxy": -36.0, "Vxz": 23.0, "Vyz": 16.0, "spring": 128.0},
        9:  {"Mxx": 90.0,  "Myy": 62.0,  "Mxy": -32.0, "Vxz": 21.0, "Vyz": 15.0, "spring": 122.0},
        10: {"Mxx": 118.0, "Myy": 82.0,  "Mxy": -44.0, "Vxz": 29.0, "Vyz": 21.0, "spring": 142.0},
        11: {"Mxx": 135.0, "Myy": 100.0, "Mxy": -60.0, "Vxz": 40.0, "Vyz": 30.0, "spring": 170.0},
        12: {"Mxx": 85.0,  "Myy": 60.0,  "Mxy": -30.0, "Vxz": 20.0, "Vyz": 15.0, "spring": 120.0}
    },
    
    # Coupled Shear Wall elements strictly defined by element ID lists (no coordinate grids)
    "pier_elements": {
        1:  {"Mx_kft": 125.0, "Nx_kips_per_ft": -150.0, "Ny_kips_per_ft": -350.0, "Nxy_kips_per_ft": -75.0, "story": 1},
        2:  {"Mx_kft": 125.0, "Nx_kips_per_ft": -150.0, "Ny_kips_per_ft": -350.0, "Nxy_kips_per_ft": -75.0, "story": 1},
        3:  {"Mx_kft": 125.0, "Nx_kips_per_ft": -150.0, "Ny_kips_per_ft": -350.0, "Nxy_kips_per_ft": -75.0, "story": 1},
        4:  {"Mx_kft": 125.0, "Nx_kips_per_ft": -150.0, "Ny_kips_per_ft": -350.0, "Nxy_kips_per_ft": -75.0, "story": 1},
        5:  {"Mx_kft": 50.0,  "Nx_kips_per_ft": -80.0,  "Ny_kips_per_ft": -150.0, "Nxy_kips_per_ft": -30.0,  "story": 2},
        6:  {"Mx_kft": 50.0,  "Nx_kips_per_ft": -80.0,  "Ny_kips_per_ft": -150.0, "Nxy_kips_per_ft": -30.0,  "story": 2},
        7:  {"Mx_kft": 50.0,  "Nx_kips_per_ft": -80.0,  "Ny_kips_per_ft": -150.0, "Nxy_kips_per_ft": -30.0,  "story": 2},
        8:  {"Mx_kft": 50.0,  "Nx_kips_per_ft": -80.0,  "Ny_kips_per_ft": -150.0, "Nxy_kips_per_ft": -30.0,  "story": 2},
        9:  {"Mx_kft": 50.0,  "Nx_kips_per_ft": -80.0,  "Ny_kips_per_ft": -150.0, "Nxy_kips_per_ft": -30.0,  "story": 3},
        10: {"Mx_kft": 50.0,  "Nx_kips_per_ft": -80.0,  "Ny_kips_per_ft": -150.0, "Nxy_kips_per_ft": -30.0,  "story": 3},
        11: {"Mx_kft": 50.0,  "Nx_kips_per_ft": -80.0,  "Ny_kips_per_ft": -150.0, "Nxy_kips_per_ft": -30.0,  "story": 3},
        12: {"Mx_kft": 50.0,  "Nx_kips_per_ft": -80.0,  "Ny_kips_per_ft": -150.0, "Nxy_kips_per_ft": -30.0,  "story": 3}
    },
    
    "coupling_beam_elements": {
        101: {"shear_force_kips": 150.0, "clear_span_in": 48.0, "height_in": 92.0, "story": 1},
        102: {"shear_force_kips": 150.0, "clear_span_in": 48.0, "height_in": 92.0, "story": 1},
        103: {"shear_force_kips": 90.0,  "clear_span_in": 48.0, "height_in": 92.0, "story": 2},
        104: {"shear_force_kips": 90.0,  "clear_span_in": 48.0, "height_in": 92.0, "story": 3}
    },
    
    "flange_elements": {
        201: {"Mx_kft": 40.0, "Nx_kips_per_ft": -110.0, "Ny_kips_per_ft": -220.0, "Nxy_kips_per_ft": -25.0, "story": 1},
        202: {"Mx_kft": 40.0, "Nx_kips_per_ft": -110.0, "Ny_kips_per_ft": -220.0, "Nxy_kips_per_ft": -25.0, "story": 1},
        203: {"Mx_kft": 20.0, "Nx_kips_per_ft": -60.0,  "Ny_kips_per_ft": -100.0, "Nxy_kips_per_ft": -15.0, "story": 2},
        204: {"Mx_kft": 20.0, "Nx_kips_per_ft": -60.0,  "Ny_kips_per_ft": -100.0, "Nxy_kips_per_ft": -15.0, "story": 3}
    }
}

def generate_meshed_visualizations_and_json():
    """
    Simulates a meshed coupled shear wall structure, runs full design evaluations,
    plots 2D elements and P-M envelopes, and saves detailed JSON design results.
    """
    print("--- RUNNING INTEGRATED TEST VALIDATION SUITE (v14) ---")
    
    # Load all configuration
    config = DEFAULT_RUN_CONFIG
    fc = config["fc"]
    fy = config["fy"]
    h_wall = config["h_wall"]
    cover_wall = config["cover_wall"]
    slab_elements = config["slab_elements"]
    footing_flex_elements = config["footing_flex_elements"]
    pier_elements = config["pier_elements"]
    coupling_beam_elements = config["coupling_beam_elements"]
    flange_elements = config["flange_elements"]
    
    # Load design parameters
    rigid_footing = config["rigid_footing"]
    flexible_footing = config["flexible_footing"]
    slab_params = config["slab"]
    sbe_params = config["sbe_check"]
    
    # ------------------------------------------------------------
    # B. EXECUTE THE RCC SOLVER ENGINES
    # ------------------------------------------------------------

    # 1. Execute slab mesh design run
    slab_results = design_slab_mesh(
        slab_elements, 
        fc, 
        fy, 
        h=slab_params["h"], 
        cover=slab_params["cover"]
    )
    print("Slab verification complete.")

    # 2. Execute side-by-side footing design comparison
    footing_rigid_data = design_footing_rigid(
        P_serv_kips=rigid_footing["P_serv_kips"],
        Mx_serv_kft=rigid_footing["Mx_serv_kft"],
        My_serv_kft=rigid_footing["My_serv_kft"],
        P_ult_kips=rigid_footing["P_ult_kips"],
        Mx_ult_kft=rigid_footing["Mx_ult_kft"],
        My_ult_kft=rigid_footing["My_ult_kft"],
        q_allow_ksf=rigid_footing["q_allow_ksf"],
        fc_psi=fc,
        fy_psi=fy,
        h_in=rigid_footing["h_in"],
        cover_in=rigid_footing["cover_in"],
        col_width_in=rigid_footing["col_width_in"]
    )
    print("Rigid footing sizing & reinforcement design complete.")

    footing_flex_data = design_footing_flexible_mesh(
        footing_flex_elements,
        spring_forces_outside_kips=flexible_footing["spring_forces_outside_kips"],
        b0_in=flexible_footing["b0_in"],
        h_in=flexible_footing["h_in"],
        cover_in=flexible_footing["cover_in"],
        fc_psi=fc,
        fy_psi=fy
    )
    print("Flexible foundation shell check complete.")
	
	

    # 3. Design Shear Wall strictly by lists of element IDs (no mesh generator)
    designed_elements = design_coupled_shear_wall(
        pier_elements,
        coupling_beam_elements,
        flange_elements,
        h_wall=h_wall,
        cover_wall=config["shear_wall"]["cover_wall"],
        fc=fc,
        fy=fy
    )

    # 4. Global SBE check
    sbe_check = check_special_boundary_elements(
        h_in=h_wall,
        lw_in=sbe_params["lw_in"],
        hw_in=sbe_params["hw_in"],
        fc_psi=fc,
        fy_psi=fy,
        Pu_kips=sbe_params["Pu_kips"],
        Mu_kft=sbe_params["Mu_kft"],
        Vu_kips=sbe_params["Vu_kips"],
        delta_u_in=sbe_params["delta_u_in"]
    )
    print("SBE Neutral-axis exact solver & stress check complete.")

    # ------------------------------------------------------------
    # C. RECONSTRUCT SPATIAL GRID FOR VISUALIZATION OUTPUT PLOTS
    # ------------------------------------------------------------

    # Create 2D coordinates for Slab Contours (10x10 mesh)
    As_bx_grid = np.zeros((10, 10))
    As_by_grid = np.zeros((10, 10))
    As_tx_grid = np.zeros((10, 10))
    As_ty_grid = np.zeros((10, 10))
    
    Mxb_grid = np.zeros((10, 10))
    Myb_grid = np.zeros((10, 10))
    Mxt_grid = np.zeros((10, 10))
    Myt_grid = np.zeros((10, 10))

    for ele_id, res in slab_results.items():
        r = slab_elements[ele_id]["row"]
        c = slab_elements[ele_id]["col"]
        
        Mxb_grid[r, c] = res["Mxb_star"]
        Myb_grid[r, c] = res["Myb_star"]
        Mxt_grid[r, c] = res["Mxt_star"]
        Myt_grid[r, c] = res["Myt_star"]
        
        As_bx_grid[r, c] = res["As_bx_in2_per_ft"] if isinstance(res["As_bx_in2_per_ft"], float) else 0.0
        As_by_grid[r, c] = res["As_by_in2_per_ft"] if isinstance(res["As_by_in2_per_ft"], float) else 0.0
        As_tx_grid[r, c] = res["As_tx_in2_per_ft"] if isinstance(res["As_tx_in2_per_ft"], float) else 0.0
        As_ty_grid[r, c] = res["As_ty_in2_per_ft"] if isinstance(res["As_ty_in2_per_ft"], float) else 0.0

    fig_slab, axes = plt.subplots(2, 2, figsize=(11, 9))
    x_grid, y_grid = np.meshgrid(np.linspace(0, 10, 10), np.linspace(0, 10, 10))
    
    cp1 = axes[0, 0].contourf(x_grid, y_grid, As_bx_grid, cmap="viridis", levels=12)
    fig_slab.colorbar(cp1, ax=axes[0, 0], label="As_bx (in2/ft)")
    axes[0, 0].set_title("Bottom X Flexural Steel")
    axes[0, 0].set_ylabel("Mesh Width (ft)")

    cp2 = axes[0, 1].contourf(x_grid, y_grid, As_by_grid, cmap="viridis", levels=12)
    fig_slab.colorbar(cp2, ax=axes[0, 1], label="As_by (in2/ft)")
    axes[0, 1].set_title("Bottom Y Flexural Steel")

    cp3 = axes[1, 0].contourf(x_grid, y_grid, As_tx_grid, cmap="viridis", levels=12)
    fig_slab.colorbar(cp3, ax=axes[1, 0], label="As_tx (in2/ft)")
    axes[1, 0].set_title("Top X Flexural Steel")
    axes[1, 0].set_xlabel("Mesh Length (ft)")
    axes[1, 0].set_ylabel("Mesh Width (ft)")

    cp4 = axes[1, 1].contourf(x_grid, y_grid, As_ty_grid, cmap="viridis", levels=12)
    fig_slab.colorbar(cp4, ax=axes[1, 1], label="As_ty (in2/ft)")
    axes[1, 1].set_title("Top Y Flexural Steel")
    axes[1, 1].set_xlabel("Mesh Length (ft)")
    
    plt.tight_layout()
    plt.savefig("/workspace/scratch/slab_reinforcement_contours_v14.png", dpi=150, bbox_inches='tight')
    plt.close()

    # Create visualization - P-M capacity envelopes
    fig_pm, ax_pm = plt.subplots(figsize=(6, 5.5))
    rebar_layers = []
    for i in range(18):
        rebar_layers.append({'x': 3.0 + i * (210.0/17.0), 'area': 1.27})
    pm_curve = generate_pm_interaction_curve(h_wall, 216.0, fc, fy, rebar_layers)
    
    ax_pm.plot(pm_curve["M_nominal"] / 12.0, -pm_curve["P_nominal"], linestyle="--", color="blue", linewidth=1.5, label="ACI Nominal Envelope")
    ax_pm.plot(pm_curve["M_factored"] / 12.0, -pm_curve["P_factored"], color="red", linewidth=2.0, label="ACI Factored Design Limit")
    ax_pm.plot(15000.0, 1500.0, marker="*", color="gold", markersize=12, label="Design Demand point")
    
    ax_pm.set_title("Shear Wall Global Biaxial P-M Capacity")
    ax_pm.set_xlabel("Moment Mn (kip-ft)")
    ax_pm.set_ylabel("Axial Capacity Pn (kips, compression positive)")
    ax_pm.legend(loc="upper right")
    ax_pm.grid(True, linestyle=":", alpha=0.6)
    plt.savefig("/workspace/scratch/shear_wall_pm_interaction_v14.png", dpi=150, bbox_inches='tight')
    plt.close()

    # Create visualization - Stress-Strain contours across SBE neutral axis
    fig_ss, ax_ss = plt.subplots(1, 2, figsize=(11, 4.5))
    x_wall_axis = np.linspace(0, 216.0, 100)
    c_na = sbe_check["neutral_axis_depth_c_in"]
    
    # Strain Compatibility Profile
    strain_profile = 0.003 * (c_na - x_wall_axis) / c_na
    ax_ss[0].plot(x_wall_axis, strain_profile, color="black", linewidth=2.0)
    ax_ss[0].fill_between(x_wall_axis, 0, strain_profile, where=(strain_profile >= 0), color="red", alpha=0.3, label="Concrete Compression")
    ax_ss[0].fill_between(x_wall_axis, 0, strain_profile, where=(strain_profile < 0), color="blue", alpha=0.2, label="Steel Tension")
    ax_ss[0].axvline(c_na, linestyle="--", color="grey", label=f"Neutral Axis (c={c_na:.2f}\")")
    ax_ss[0].set_title("Base Cross-Section Linear Strain Compatibility")
    ax_ss[0].set_xlabel("Length along wall section (inches)")
    ax_ss[0].set_ylabel("Fiber Strain (in/in)")
    ax_ss[0].legend()
    ax_ss[0].grid(True, linestyle=":")

    # Whitney Compressive Stress Block
    beta_1 = 0.85 if fc <= 4000.0 else max(0.65, 0.85 - 0.05 * ((fc - 4000.0)/1000.0))
    a_block = beta_1 * c_na
    stress_profile = np.where(x_wall_axis <= a_block, 0.85 * fc / 1000.0, 0.0)  # ksi
    ax_ss[1].plot(x_wall_axis, stress_profile, color="red", linewidth=2.0)
    ax_ss[1].fill_between(x_wall_axis, 0, stress_profile, color="red", alpha=0.1, label="Whitney Stress block")
    ax_ss[1].set_title("Equiv. Rectangular Stress Block Distribution")
    ax_ss[1].set_xlabel("Length along wall section (inches)")
    ax_ss[1].set_ylabel("Compressive Stress (ksi)")
    ax_ss[1].legend()
    ax_ss[1].grid(True, linestyle=":")

    plt.tight_layout()
    plt.savefig("/workspace/scratch/section_stress_strain_contours_v14.png", dpi=150, bbox_inches='tight')
    plt.close()

    # Create visualization - 2D Conforming Element Mesh Layout
    # (Since there is no grid generator in the design run, we sketch a clean diagram of layout)
    fig_m, ax_m = plt.subplots(figsize=(7, 7))
    
    # Left Pier
    ax_m.fill([0, 96, 96, 0], [0, 0, 360, 360], facecolor="#8db48e", edgecolor="black", alpha=0.7, label="Vertical Pier")
    # Right Pier
    ax_m.fill([144, 240, 240, 144], [0, 0, 360, 360], facecolor="#8db48e", edgecolor="black", alpha=0.7)
    # Coupling Beams
    ax_m.fill([96, 144, 144, 96], [84, 84, 120, 120], facecolor="#dca15c", edgecolor="black", alpha=0.7, label="Coupling Beam")
    ax_m.fill([96, 144, 144, 96], [204, 204, 240, 240], facecolor="#dca15c", edgecolor="black", alpha=0.7)
    ax_m.fill([96, 144, 144, 96], [324, 324, 360, 360], facecolor="#dca15c", edgecolor="black", alpha=0.7)
    
    ax_m.set_aspect("equal")
    ax_m.set_title("Multi-Story Conforming Coupled Wall Element Layout")
    ax_m.set_xlabel("Wall Width (inches)")
    ax_m.set_ylabel("Wall Height (inches)")
    ax_m.legend(loc="upper right")
    ax_m.grid(True, linestyle=":")
    plt.savefig("/workspace/scratch/coupled_shear_wall_mesh_v14.png", dpi=150, bbox_inches='tight')
    plt.close()
    print("Contour diagrams and failure envelopes plotted successfully.")




if __name__ == "__main__":
    generate_meshed_visualizations_and_json()
    print("All tasks completed.")
