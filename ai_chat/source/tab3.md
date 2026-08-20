this tab is for post processing.

1.read this opensees_opstool_reference_description.md, opensees_reference.pdf and opstool_reference.pdf very carfully.

2.ask user what results does he need as png file or html file or in xlx or docx file? then save those files into user output directory and make them zip file and render them for downloading

3. get the .ODB file from the user output directory and and extract the required results as per user demand.

4.use this command import subprocess, sys

def run_test_py(test_file):
    result = subprocess.run([sys.executable, test_file], capture_output=True, text=True)
    return result.stdout, result.stderr, result.returncode



# OpenSees / opstool Results Extraction Reference

## Chapter 1: Results Extraction Protocols 

### Nodal Responses
| Key | Description |
|---|---|
| `disp` | Displacement at the node |
| `vel` | Velocity at the node |
| `accel` | Acceleration at the node |
| `reaction` | Reaction forces at the node |
| `reactionIncInertia` | Reaction forces including inertial effects |
| `rayleighForces` | Forces resulting from Rayleigh damping |
| `pressure` | Pressure applied to the node |

### Frame Element Responses
- `localForces`
- `basicForces`
- `basicDeformations`
- `plasticDeformation`
- `sectionForces`
- `sectionDeformations`
- `sectionLocs`

### Truss Element Responses
- `axialForce`
- `axialDefo`
- `Stress`
- `Strain`

### Link Element Responses
- `basicDeformation`
- `basicForce`

### Fiber Section Responses
- `Stresses`
- `Strains`
- `secForce`
- `secDefo`

### Shell Element Responses
- `sectionForces`
- `sectionDeformations`
- `Stresses`
- `Strains`
- `sectionForcesAtNodes`
- `sectionDeformationsAtNodes`
- `StressesAtNodes`
- `StrainsAtNodes`

### Plane Element Responses
- `Stresses`
- `Strains`
- `StressesAtNodes`
- `StressAtNodesErr`
- `StrainsAtNodes`
- `StrainsAtNodesErr`
- `StressMeasures`
- `StrainMeasures`
- `StressMeasuresAtNodes`
- `StrainMeasuresAtNodes`

### Solid (Brick) Element Responses
- `Stresses`
- `Strains`
- `StressesAtNodes`
- `StressAtNodesErr`
- `StrainsAtNodes`
- `StrainsAtNodesErr`
- `StressMeasures`
- `StrainMeasures`
- `StressMeasuresAtNodes`
- `StrainMeasuresAtNodes`

### Contact Element Responses
- `globalForces`
- `localForces`
- `localDisp`
- `slips`

### Sensitivity Analysis Responses
- `disp`
- `vel`
- `accel`
- `pressure`
- `lambdas`

---

## Extraction Guide for opstool Analysis Results

Critical structural engineering parameters and results to extract and analyze for each main analysis type supported or enhanced by **opstool 1.0.26**.

### 1. Moment-Curvature Analysis (`MomentCurvature`)

Section-level analysis evaluating bending capacity, ductility, and material state transitions of a meshed fiber section under monotonic or cyclic curvature paths.

**Key results:**
- **Moment-curvature curves (φ–M)** — curvature vs. bending moment to construct the section's backbone curve.
  Retrieved via: `MC.get_M_phi()` or `MC.get_M()`
- **Fiber-level material state (stress & strain)** — uniaxial stress (σ) and strain (ε) histories for every sub-divided fiber.
  Retrieved via: `MC.get_fiber_data()` → returns an `xarray.DataArray` with coordinates `Steps`, `Fibers`, and properties `yloc`, `zloc`, `area`, `mat`, `stress`, `strain`
- **Key limit states:**
  - *First yield*: outermost tensile reinforcing steel yields
  - *Ultimate*: confined concrete core reaches ultimate compressive strain, or moment capacity drops below a set ratio (e.g., 80% of peak)
  - Retrieved via: `MC.get_limit_state(matTag, threshold)`
- **Equivalent bilinear parameters** — equivalent yield curvature (φ_eq), ultimate curvature (φ_u), yield moment (M_y), elastic/post-yield stiffness.
  Retrieved via: `MC.bilinearize()`

### 2. Linear Buckling Analysis

Stability analysis determining critical load multipliers and corresponding bifurcation modes.

**Key results:**
- **Buckling factors (eigenvalues)** — load scale factors (λ_i) indicating how many times the reference load must be multiplied to trigger elastic instability.
  Retrieved via: `eigenvalues, eigenvectors = opst.post.get_linear_buckling_data(odb_tag)`
- **Buckling modes (eigenvectors)** — normalized displacement fields (Φ_i) for each critical factor; useful for PyVista 3D visualization of weak planes or lateral-torsional vulnerability.

### 3. Response Spectrum Analysis

Dynamic analysis calculating peak elastic design envelopes by combining modal responses under a specified ground motion spectrum.

**Key results:**
- **Combined peak responses (time = 0)** — peak demands combined via CQC or SRSS, extracted at `time=0` for nodal displacement, drift, base shear, and member forces
- **Individual modal contributions (time = 1, 2, …)** — uncombined response per mode; step *n* corresponds to Mode *n*
- **Tracked design demands** — axial forces (P), shear forces (V_y, V_z), torsion (T), bending moments (M_y, M_z) at frame elements/sections.
  Retrieved via: `opst.post.get_element_responses(odb_tag, ele_type="Frame")`

### 4. Eigen Analysis (Modal Analysis)

Determines the inherent dynamic properties of an undisturbed structural system.

**Key results:**
- **Natural periods (T_i) & frequencies (ω_i)** — used to estimate seismic force demands and verify stiffness.
  Retrieved via: `opst.post.get_eigen_data(odb_tag)`
- **Eigenvectors / mode shapes** — normalized displacement profiles (translational, torsional, or mixed).
  Visualized via: `plot_eigen()` (Plotly or PyVista)
- **Modal participating mass ratios** — proportion of mass activated per mode along global axes; confirms enough modes extracted to meet regulatory criteria (typically >90%)

### 5. Pushover Analysis (Nonlinear Static)

Subjects a nonlinear model to a progressive lateral displacement pattern to evaluate inelastic capacity and collapse mechanisms.

**Key results:**
- **Capacity curve (force vs. displacement)** — base shear (sum of bottom node reaction forces in the lateral direction) vs. lateral displacement of the master control node (e.g., roof node)
- **Inelastic member demands** — plastic rotations, yielding distributions, plastic curvatures.
  Retrieved via: `plasticDeformation` and `sectionDeformations` fields from frame element responses
- **Localized material cracking and crushing** — sections where concrete fibers reach crushing strain or steel exceeds yield strain, pinpointing the sequence of plastic hinge formation

### 6. Time History Analysis (Transient Analysis)

Simulates explicit time-varying structural response under transient dynamic loads (e.g., earthquake ground motions).

**Key results:**
- **Nodal response histories** — time-dependent displacement (`disp`), velocity (`vel`), acceleration (`accel`); dynamic support reactions (`reaction`) and Rayleigh damping forces (`rayleighForces`)
- **Hysteretic energy dissipation** — force-deformation plots (e.g., moment-curvature at plastic hinges, member shear vs. drift) to analyze energy dissipation loop sizes and stiffness degradation
- **Dynamic material damage** — uniaxial stress-strain hysteresis loops at highly-stressed fibers, examining fatigue, yield cycles, and residual plastic strain

### 7. Linear Analysis (Static)

Baseline static analysis evaluating structural performance under standard, elastic service loading.

**Key results:**
- **Deformed shape** — nodal elastic displacements (`disp`) to check drift limits and serviceability
- **Internal force envelopes** — bending moments, axial forces, shear forces across frame/shell/solid elements.
  Retrieved via: `localForces` or `basicForces`
- **Support reactions** — base reactions (`reaction`) for vertical/lateral equilibrium checks against gravity and static load patterns

---

## Section-by-Section API Reference

opstool uses `xarray` labeled Datasets/DataArrays for slicing and numpy-style math.

| Section | Function(s) | Dimensions | Notes |
|---|---|---|---|
| **9.1 Eigenvalue Extraction** | `save_eigen_data(odb_tag=1)`, `get_eigen_data(odb_tag=1)` | — | Returns periods, modes |
| **9.2 Node Response Extraction** | `get_nodal_responses(odb_tag=1)` | `time`, `nodeTags`, `DOFs` | Examples: slice vertical displacement for specific nodes; sum reaction forces across all nodes |
| **9.3 Frame Element Response Extraction** | `get_element_responses(odb_tag=1, ele_type="Frame")` | `time`, `eleTags`, `localDofs` or `time`, `eleTags`, `secPoints`, `secDofs` | Examples: pull local end forces; sectional moment about local Y-axis |
| **9.4 Fiber Section Response Extraction** | `ele_type="FiberSection"` | `time`, `eleTags`, `secPoints`, `fiberPoints` | Examples: concrete stress at last time step; rebar strain history |
| **9.5 Truss Element Response Extraction** | `ele_type="Truss"` | `time`, `eleTags` | Pulls axial force and axial strain |
| **9.6 Shell Element Response Extraction** | `ele_type="Shell"` | `time`, `eleTags`, `GaussPoints`, `secDOFs` (or nodal variant) | Examples: membrane force FXX; nodal stress sigma11 |
| **9.7 Planar Element Response Extraction** | `ele_type="Plane"` | includes `stressDOFs` | Examples: Von Mises stress at nodes; pore pressure at nodes (saturated soils) |
| **9.8 Solid Brick Element Response Extraction** | `ele_type="Solid"` | — | Examples: maximum shear stress (τ_max); vertical stress σ33 at Gauss points |
| **9.9 Load-Controlled Cantilever Sensitivity Analysis** | `parameter` / `addToParameter` + `sensitivityAlgorithm('-computeAtEachStep')`; results via `get_sensitivity_responses(odb_tag="sensitivity")` | `time`, `paraTags`, `nodeTags`, `DOFs` | Example: slice Y-displacement sensitivity at node 2 |
| **9.10 Post-Analysis Unit Conversions** | `update_unit_system(pre={...}, post={...})`; `reset_unit_system()` | — | Converts stored results across the whole relational database (e.g., N-mm base → kN-m output); reset restores base units |

---

## Chapter 2: Plotly-Based Interactive 3D Visualizations

| Section | Function | Description |
|---|---|---|
| **10.1 Model Geometry Wireframe** | `opst.vis.plotly.plot_model(show_outline=True, show_nodal_loads=True, show_ele_loads=True)` | Renders model wireframe with outlines and applied loads |
| **10.2 Eigen Mode Shape Vibrations** | `plot_eigen_animation(odb_tag=1, mode_tag=1, scale=10.0)` | Animates modal vibration in 3D WebGL |
| **10.3 Transient Nodal Responses Visualization** | `plot_nodal_responses_animation(odb_tag=1, resp_type="disp", scale=5.0)` | Animates displacement drift over time |
| **10.4 Frame Bending Moments/Axial Forces Animation** | `plot_frame_responses_animation(odb_tag=1, resp_type="sectionForces", force_dir="MY")` | Animates internal force distribution along frame elements |
| **10.5 Continuum Element Stress Field Contours** | `plot_unstruct_responses_animation(odb_tag=1, ele_type="Solid"/"Shell"/"Plane", resp_type="Stresses", stress_dof="sigma_vm", scale=2.0)` | Animates stress contours for continuum elements |
| **10.6 PyVista-Based Visualization Backend** | `set_plot_props(point_size=1, line_width=4)`, `set_plot_colors(truss="black", node="red")`, `plot_model()` | Mirrors all Plotly/WebGL functions for local/headless rendering; `plot_model()` returns a `pyvista.Plotter` for interactive local windows |

---

*Document compiled from `opensees_reference.pdf` and `opstool_reference.pdf`, covering every script, command, parameter table, and example present in the source material.*

