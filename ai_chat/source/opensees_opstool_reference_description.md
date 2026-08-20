# Detailed Description: OpenSeesPy & opstool Reference Documents

This document provides an exhaustive, nothing-omitted description of two uploaded PDFs:
1. `opensees_reference.pdf` — opstool Models Library + OpenSeesPy Section 4 (Model Commands)
2. `opstool_reference.pdf` — Unified opstool & OpenSeesPy Workflow Handbook (v7.0)

---

# DOCUMENT 1: `opensees_reference.pdf`

## Part A.1: Standalone Example Script — `soil_foundation_fdm_fem.py`

Written by Salar Delavar Ghashghaei. Models a rectangular foundation (E=2.1e11 Pa, H=0.5m, B=5.0m, L=10.0m) resting on soil represented as springs (K=1e8 Pa/m subgrade modulus), under a center compression load (P=-1e6 N).

- Builds a 3D model (`ndm=3, ndf=6`)
- Uses `ENT` uniaxial material (elastic-no-tension) for soil springs, with `Elastic` given as a commented alternative
- Discretizes into a 50×25 grid (nx, ny), computing dx, dy
- For each grid node: creates a foundation node, a corresponding base spring node offset by `NZ=200000`, fixes the base node fully (all 6 DOFs), and connects them with a `zeroLength` spring element acting only in direction 3 (vertical)
- Defines material as `ElasticIsotropic` (nDMaterial) and section as `PlateFiber`
- Builds `ShellMITC4` elements over the (nx-1)×(ny-1) grid using 4 corner nodes each
- Applies a point load at the center node in the Z-direction using a `Linear` timeSeries and `Plain` pattern
- Solver setup: `Transformation` constraints, `RCM` numberer, `BandGeneral` system, `LoadControl` integrator, `Linear` algorithm, `Static` analysis, single `analyze(1)` step
- Plots width axis with matplotlib at the end

## Part A.2: opstool Models Library — Every Script Described

Curated, cleaned OpenSeesPy scripts converted from other software (Midas, CSiBridge, SAP2000, Tcl) via opstool's translators. Node/element coordinate blocks are truncated for readability, but modeling logic is intact.

### ArchBridge.py
Double-arch deck bridge converted from Midas/CSiBridge via "Midas2OPS translator."
- `mat_props` namedtuple (mat_name, E, v, G, r, gamma, rho) — one entry: material tag 40, E=33,057,000, v=0.167, G=14,163,239.07, rho=2.5493
- `sec_props` namedtuple (sec_name, A, Asy, Asz, Ixx, Iyy, Izz) with 8 sections: Main_Arch_Rib, Pillar_1.2_1.2, Pillar_0.9_1.2, Pillar_0.7_1.2, Cap_Beam, Slab_Girder, Arch_Cross_Tie, Pillar_Cross_Tie — each with explicit area/inertia values
- Nodes 1–1354 (bulk omitted; nodes 1–4 and node 1354 shown explicitly)
- Uses `elasticBeamColumn` elements with `Linear` geomTransf, referencing SecProps entries for A/E/G/Ixx/Iyy/Izz
- Elements 3–1000+ omitted

### ArchBridge2.py
Converted from DinoChen.com. Massive arch frame with 3D solid columns.
- `ndm=3, ndf=6`
- Explicit primary nodes 1–5 shown (large-scale coordinates, e.g. node 2 at x=125000); nodes 6–1799 omitted
- Lumped `mass` at node 1 (113.6, 113.6, 113.6); lumped mass distribution omitted elsewhere
- Fixes nodes 1–4 fully
- Materials: two `Elastic` uniaxial materials (206000.0 and 26000.0), an `ElasticIsotropic` nDMaterial (26000, 0.2), wrapped into `PlateFiber` nDMaterial (tag 601) and `PlateFiber` section (tag 701, thickness 260.0)
- Uses `Linear` geomTransf
- Elements 1–500+ omitted

### CableStayedBridge.py
Exported from SAP2000/CSiBridge.
- 6 geometric transforms: `Linear`(1), `PDelta`(3), `Corotational`(5) with direction (-1,0,0); and `Linear`(2), `PDelta`(4), `Corotational`(6) with direction (0,0,1)
- Variables `transf_Ver=1`, `transf_Other=2`
- `MatProp` namedtuple (UnitMass, E, G, v, rho) with 3 entries: "4000Psi" (concrete), "A416Gr270" (cable strand steel), "Pier_RC"
- Nodes 1–3 shown explicitly (tower base/cap/top at x=150000); nodes 4–1500+ omitted (anchorage points)
- Fixes nodes 1 and 4
- `Elastic` uniaxial material (206000.0) for cables
- Fiber pier section via `section("Fiber", 1, "-GJ", 10000.0)`
- Elements: `trussSection` for cable stays, beam columns for towers/deck — connectivity blocks omitted

### Dam.py
3D solid continuum concrete arch dam.
- `ndm=3, ndf=3`
- `MatProp` namedtuple with one entry "4000Psi" (UnitMass=2.402, E=24,855,578.06, G=10,356,490.85, v=0.2, rho=9.9e-06)
- Nodes 1–2 shown, 3–1400+ omitted (solid dam mesh coordinates)
- `Elastic` uniaxial material (199900.0) and `ElasticIsotropic` nDMaterial (24820.0, 0.2)
- Built from `stdBrick` (8-node solid) elements — example: element 1 connecting nodes [1,37,38,39,41,42,43,44] to material 2
- Remaining mesh omitted

### DamBreak.py
Fluid-Structure Interaction (FSI) dam break simulation using PFEM (Particle Finite Element Method).
- `ndm=2, ndf=2`
- Geometric params: L=0.146, H=2L, H2=0.3, h=0.005 (mesh size), alpha=1.4, tw=3h (wall thickness)
- Fluid physical properties: rho=1000 (density), mu=0.0001 (viscosity), b1=0 (X body force), b2=-9.81 (gravity), thk=0.012 (thickness), kappa=-1.0 (bulk modulus)
- Explicit nodes 1–11 given defining wall/water boundary geometry
- Mesh IDs: wall_id=1, water_bound_id=-1, water_body_id=-2, wall_tag=3, fluid_tag=4
- Uses `ops.mesh("line", ...)` to define 2D boundary line meshes for walls and water region
- Wall solid meshed with `tri31` (triangular plane-strain) elements using `ElasticIsotropic` nDMaterial (tag 10, E=3.45e7, v=0.2)
- Fluid domain meshed with `PFEMElementBubble` elements (bubble-function fluid elements) via `ops.mesh("tri", ...)`
- Boundary wall nodes fixed via a loop over `ops.getNodeTags("-mesh", wall_tag)`

### FiberSec.py
Circular bridge pier fiber cross-section definition.
- `ndm=3, ndf=6`
- Material constants: unconfined cover concrete (vc=0.2, fc=-20.1e3, ec=-2e-3, fcu=-16.5e3, ecu=-4e-3), confined core concrete (fccore=-26.8e3, eccore=-5.3e-3, fcucore=-23, ecucore=-0.0157), steel (Fys=300e3, Es=2.0e8, bs=0.01)
- Three materials: `Concrete01` for cover (matTagC=1), `Concrete01` for core (matTagCCore=2), `Steel01` for reinforcement (matTagSteel=3)
- Two nodes (base and top at height 8.0), lumped mass (100,100,100) at node 2, node 1 fully fixed
- Geometry: pier_d=1.3m diameter, cover=0.05m, bar_d=0.022m bar diameter, bar_ratio=0.01, mesh_size=0.1
- Computes pier_area, bar_area, and bar_num programmatically via numpy
- Builds `section("Fiber", 1, "-GJ", torsional_stiffness)`
- Adds a `patch("circ", ...)` for the concrete cover ring, a `patch("circ", ...)` for the confined core, and a `layer("circ", ...)` of steel reinforcement bars distributed circularly (0° to 360°−360/35°)
- Uses `Linear` geomTransf, `Lobatto` beamIntegration (1 section, 6 points), and a `forceBeamColumn` element connecting the two nodes

### Frame3D.py
3D multi-story frame building.
- `ndm=3, ndf=6`
- C40 concrete material via `mat_props` namedtuple: E=32,500,000, v=0.2, G=13,541,666.67, rho=2.5493
- One section: "Col_Sec" via `sec_props` namedtuple (A=0.25, Asy=0.2083, Asz=0.2083, Ixx=0.0088, Iyy=0.0052, Izz=0.0052)
- Nodes 1–2 shown, 3–380 omitted (building grid), node 384 shown at end (25,15,75)
- Node 1 fixed; other floor boundary constraints omitted
- `Linear` geomTransf
- Example `elasticBeamColumn` element (tag 6, nodes 7-8) using SecProps values
- Rest of building elements omitted

### Frame3D2.py
Alternative 3D multi-story frame ("idealized framework").
- `ndm=3, ndf=6`
- Explicit nodes 1–2 shown (large coordinates ~4500-13500), nodes 3–27 omitted, node 28 shown
- Mass (8.604×3) at node 1
- Loop fixing base nodes [23,24,25,26,27,28] fully
- Two `Elastic` uniaxial materials (199900.0, 26800.0)
- `Linear` geomTransf (direction 1,0,0)
- Example `elasticBeamColumn` element 1 connecting nodes 1-2 with explicit section properties (A=160000, E=26800, G=11170, Iz=3,605,000,000, Iy=2,133,000,000, J=2,133,000,000)
- Elements 2–100+ omitted

### GridFrame.py
Converted from DinoChen.com. Flat grid system of interconnected space trusses.
- `ndm=3, ndf=3`
- Nodes 1–2 shown (spacing 3200 in X), nodes up to 179 (last one shown)
- Fixes nodes 5 and 107 (translation-only, 3 DOFs)
- `Elastic` uniaxial material (199900.0)
- `Fiber` section with `-GJ` 10000.0 (used for truss section)
- `trussSection` elements — example element 1 connecting nodes 1-2
- Remaining grid elements omitted

### Igloo.py
Spatial dome geodesic structural network. Analyzes highly nonlinear spatial trusses under dome loads.
- `ndm=3, ndf=3`
- Geodesic spherical-projection nodes shown (135, 136 examples), up to node 1790 (final shown)
- `Elastic` uniaxial steel material (199900.0)
- `trussSection` elements, example element 1 (nodes 1-2)
- Full dome connectivity network omitted

### SuspensionBridge.py
Double-pylon spatial suspension bridge. Uses cable tension-only formulation with nonlinear geometric corotational transforms.
- `ndm=3, ndf=6`
- Three geomTransf types for pylon/cable directions: `Linear`(1), `PDelta`(3), `Corotational`(5), all with vector (-1,0,0)
- `MatProp` namedtuple with "4000Psi" entry (UnitMass=2.40, E=24,855,578.0, G=10,356,490.8, v=0.2, rho=9.9e-06)
- Nodes 1–2 shown (tower/anchor coordinates, e.g. node 1 at -60.0,-1.5,0.0), up to node 200 (shown, at 40.0,1.5,9.0)
- High-strength steel `Elastic` uniaxial material (199900.0)
- Example `elasticBeamColumn` element 1 (nodes 1-2) with A=0.0042, E=2.0e8, G=7.8e7, Iy=9.6e-08, Iz=6.5e-05, J=3.3e-06, transform 2
- Cables/hangers elements omitted

### TrussBridge.py
3D Warren steel truss girder bridge.
- `ndm=3, ndf=3`
- Nodes 1–2 shown, up to node 28 (shown, 18000,6000,3000)
- Fixed supports at nodes 1 and 2 (translation constrained, rotations free)
- `Elastic` uniaxial steel material (199900.0)
- `Fiber` section (tag1, GJ=100000000.0) with two example `fiber()` calls at coordinates (-80,-94) and (-40,-94), both area 480.0, material 1
- `trussSection` elements, example element 1 (nodes 1-2)
- Web brace connectivity list omitted

### shell3D.py
Spatial shell plate model, originally from dinochen.com, converted via opstool.
- `ndm=3, ndf=6`
- Nodes 1–2 shown, up to node 121 (shown at 6000,0,2700)
- Mass (0.324×3) at node 1; node 1 fully fixed
- `ElasticIsotropic` nDMaterial (tag 2, E=24820.0, v=0.2), wrapped as `PlateFiber` nDMaterial (tag 601), then `PlateFiber` section (tag 701, thickness 300.0)
- Two example `ShellMITC4` elements shown (element 1: nodes 1,37,38,39 + section 701; element 2: nodes 39,38,40,7 + section 701)
- Remaining shell mesh omitted

---

## Part B: Section 4 — Model Commands (Complete Reference)

### 4.1 `model()`
Sets spatial dimension (`ndm`: 1, 2, or 3) and DOFs per node (`ndf`, defaults to ndm*(ndm+1)/2 → 3 DOFs for 2D, 6 for 3D). Must precede all node/element/material/section definitions.
Examples: 2D frame (`ndm=2, ndf=3`), 3D solid (`ndm=3, ndf=3`).

### 4.2 `element()`
General syntax: `element(eleType, eleTag, *eleNodes, *eleArgs)`. Example: `Truss` element with Area=10.0, materialTag=1.

**4.2.1 Zero-Length Elements** (8 variants):
- `zeroLength` — connects coincident nodes via 1D materials in specified directions, optional `-doRayleigh`/`-orient`
- `zeroLengthND` — connects nodes using a multidirectional nDMaterial (contact, multidirectional friction)
- `zeroLengthSection` — connects nodes using a fiber/aggregated cross-section
- `CoupledZeroLength` — coupled translational-rotational spring between two DOFs
- `zeroLengthContact2D` — 2D frictional node-to-node contact (Kn, Kt, mu)
- `zeroLengthContactNTS2D` — node-to-segment 2D contact for boundary sliding
- `zeroLengthInterface2D` — frictional slip interface between planar entities
- `zeroLengthImpact3D` — 3D impact spring modeling closing gaps, initGap, normal/tangential stiffness
- Example: `element('zeroLength', 101, 1, 2, '-mat', 1, 1, '-dir', 1, 2)`

**4.2.2 Truss Elements** (3 variants):
- `Truss` — classical 1D axial bar, neglects bending/shear, optional `-rho`, `-cMass`, `-doRayleigh`
- `TrussSection` — truss using a defined cross-section tag instead of raw area
- `corotTruss` — truss with large-displacement/finite-rotation corotational kinematics
- Examples given for both Truss and corotTruss with Area=2.5, matTag=3

**4.2.3 Beam-Column Elements** (9 variants):
- `elasticBeamColumn` — standard elastic prismatic Euler-Bernoulli beam
- `ModElasticBeam2d` — elastic beam with stiffness modifiers K1, K2 (models cracking/damage)
- `ElasticTimoshenkoBeam` — elastic beam capturing shear deformation (short/stubby members)
- `dispBeamColumn` — displacement-based fiber-discretized inelastic beam
- `forceBeamColumn` — force-based fiber beam, exact force fields, inelasticity at integration points
- `nonlinearBeamColumn` — spread-plasticity nonlinear beam using sectional definitions
- `dispBeamColumnInt` — inelastic displacement-based beam tracking cyclic flexure-shear coupling
- `MVLEM` — Multiple-Vertical-Line-Element-Model for planar shear wall bending/cyclic response
- `SFI_MVLEM` — MVLEM variant coupled with shear-flexure interaction via multidirectional concrete models
- Example: elasticBeamColumn with Area=0.5, E=2.0e11, I=0.0012, transf=1

**4.2.4–4.2.10 Specialized Elements** (10 variants):
- `Joint2D` — planar structural joint with discrete rotational springs at shear panel
- `twoNodeLink` — generic dual-node multidirectional connector with `-mat`/`-dir`/`-orient`
- `elastomericBearingPlasticity` — seismic isolation bearing with coupled horizontal bilinear plasticity
- `singleFPBearing` — Single Friction Pendulum bearing with spherical sliding friction model
- `quad` — 2D continuum quadrilateral (Plane Stress or Plane Strain)
- `ShellMITC4` — 4-node thin plate/shell with Mixed Interpolation shear-lock correction
- `SSPquad` — Stabilized Single-Point Quadrilateral preventing volumetric shear locking
- `tri31` — planar 3-node linear triangular continuum element for irregular geometry
- `stdBrick` — standard 8-node 3D brick solid element

**4.2.11–4.2.16 Soil, Fluid & Contact Elements** (7 variants):
- `quadUP` — 2-phase 4-node quad modeling saturated soil pore-pressure (u-p) interaction
- `brickUP` — 3D solid brick u-p element coupling soil skeleton deformation and fluid flow
- `SimpleContact2D` — 2D contact enforcing non-penetration and frictional sliding
- `BeamContact2D` — 2D beam-to-soil boundary contact interface
- `CatenaryCable` — computes exact static equilibrium of a catenary cable under self-weight
- `PFEMElementBubble` — PFEM fluid element with bubble functions for velocity-pressure stability
- `SurfaceLoad` — distributes normal forces/hydrostatic pressure over a quadrilateral area

### 4.3 `node()`
`node(nodeTag, *crds, '-ndf', ndf, '-mass', *mass, '-disp', *disp, '-vel', *vel, '-accel', *accel)`. Defines coordinates, optional per-node DOF override, mass, and initial kinematic state. Two examples: plain 2D node, and node with lumped mass.

### 4.4 Single-Point (SP) Constraints
- `fix(nodeTag, *constrValues)` — 0=free, 1=constrained, per DOF
- `fixX(xCoord, *constrValues)` — constrains all nodes at given X coordinate
- `fixY(yCoord, *constrValues)` — constrains all nodes at given Y coordinate
- `fixZ(zCoord, *constrValues)` — constrains all nodes at given Z coordinate
- Examples: fully fixed node 1 in 2D; `fixY(0.0, *[1,1])` for a base line

### 4.5 Multi-Point (MP) Constraints (4 variants)
- `equalDOF(rNodeTag, cNodeTag, *dofs)` — equal displacement field between retained/constrained node
- `equalDOF_Mixed` — variant allowing equal DOFs between nodes with different DOF environments
- `rigidDiaphragm(perpDirn, rNodeTag, *cNodeTags)` — rigid floor diaphragm about a perpendicular axis
- `rigidLink(type, rNodeTag, cNodeTag)` — rigid kinematic link; type is `'bar'` (translation only) or `'beam'` (translation+rotation)

### 4.6 `pressureConstraint(nodeTag, pNodeTag)`
Links a soil/frame boundary node to a fluid pressure node for hydrostatic boundary coupling.

### 4.7 `timeSeries()` Commands (7 variants)
- `Constant` — constant load multiplier over time
- `Linear` — F(t) = factor × t
- `Trigonometric` — harmonic wave between tStart/tEnd with a period
- `Triangular` — repeating triangular cyclic impulses
- `Rectangular` — box-constrained active load window between tStart/tEnd
- `Pulse` — localized dynamic pulses at set intervals, given a width
- `Path` — load multipliers from explicit value lists or file (`-dt`, `-values`, `-filePath`) — used for seismic accelerograms
- Examples: Linear for gravity; Path reading `elCentro.txt` at dt=0.01 scaled by 9.81

### 4.8 `pattern()` Commands
General types: `Plain` (static), `UniformExcitation` (global dynamic base motion), `MultipleSupport`/`MultiSupport` (differential multi-support excitation).

Nested Plain subcommands:
- `load(nodeTag, *loadValues)` — concentrated static nodal load/moment
- `eleLoad('-ele', *eleTags, '-type', '-beamUniform', Wy, ..., <'-beamPoint', Py, x_L>)` — uniform or point transverse loads on beam elements
- `sp(nodeTag, dof, value)` — non-homogeneous SP constraint (e.g. support settlement)

Other pattern types:
- `UniformExcitation(patternTag, dir, '-accel', tsTag, <'-vel0', v0>)` — uniform seismic acceleration, dir=1/2/3
- `MultiSupport(patternTag)` — container for differential ground motions
- `groundMotion(tag, 'Plain', <'-accel', tsTag>, <'-vel', tsTag>)` — registers a seismic motion curve
- `imposedMotion(nodeTag, dir, gmTag)` — applies registered ground motion to a node
- Examples: static lateral load pattern; UniformExcitation base acceleration in X

### 4.9–4.12 Physical Domain Utilities (4 commands)
- `mass(nodeTag, *massValues)` — lumped translational/rotational mass at a node
- `region(regTag, <'-ele', *eleTags>, <'-node', *nodeTags>, <'-rayleigh', rFlag>)` — groups elements/nodes for recorders/damping
- `rayleigh(alphaM, betaK, betaKinit, betaKcomm)` — global Rayleigh damping: C = αM·M + βK·K_curr + βK_init·K_init + βK_comm·K_last
- `block2D(numX, numY, startNode, startEle, eleType, *eleArgs, *nodeCoords)` — programmatic 2D quad/tri mesh block generator
- `block3D(numX, numY, numZ, startNode, startEle, eleType, *eleArgs, *nodeCoords)` — programmatic 3D brick mesh block generator
- Example: rayleigh damping at 5% ratio on modes 1-2

### 4.13 `beamIntegration()` (5 variants)
- `Lobatto(biTag, secTag, numIP)` — Gauss-Lobatto, integration points at element ends, good for cracking analysis
- `Legendre(biTag, secTag, numIP)` — Gauss-Legendre, points not at endpoints
- `NewtonCotes(biTag, secTag, numIP)` — equally spaced integration points
- `HingeMidpoint(biTag, secTagI, lpI, secTagJ, lpJ, secTagCol)` — plastic hinge integration at beam ends with hinge lengths lpI/lpJ
- `HingeRadau(biTag, secTagI, lpI, secTagJ, lpJ, secTagCol)` — Radau integration localized at elastic-plastic ends
- Example: 5-point Lobatto rule with section tag 2

### 4.14 `uniaxialMaterial()`

Steel/reinforcing (4 variants): `Steel01` (bilinear kinematic hardening), `Steel02` (Giuffre-Menegotto-Pinto cyclic transition), `ReinforcingSteel` (strain-hardening + bar buckling), `RambergOsgoodSteel` (nonlinear Ramberg-Osgood cyclic curve)

Concrete (4 variants): `Concrete01` (zero tensile strength, parabolic compression, Kent-Scott-Park base), `Concrete02` (adds linear tension softening slope Ets and tensile strength ft), `Concrete04` (Popovics compression curve + exponential tension softening), `ConfinedConcrete01` (Mander-based confined concrete generator from transverse steel config)

Standard/other (7 variants): `Elastic` (linear elastic, optional damping η and compression-only Eneg), `ElasticPP` (elastic-perfectly-plastic, epsYp yield strain), `ElasticPPGap` (elastic-PP with a discrete gap), `Hysteretic` (trilinear with pinching/damage/stiffness degradation), `Parallel` (materials combined in parallel — forces sum), `Series` (materials in series — strains sum), `PySimple1`/`TzSimple1` (p-y lateral pile resistance / t-z skin friction soil springs)

Examples: Steel01 (Fy=355.0, E=2.1e5, b=0.01); Concrete01 (fpc=-30.0, epsc0=-0.002, fpcu=-5.0, epsU=-0.006)

### 4.15 `nDMaterial()` (7 variants)
- `ElasticIsotropic` — standard isotropic elastic (E, v)
- `ElasticOrthotropic` — orthotropic elastic constants across all axes (Ex,Ey,Ez,vxy,vyz,vzx,Gxy,Gyz,Gzx)
- `J2Plasticity` — Von Mises plasticity with isotropic/kinematic hardening
- `DruckerPrager` — elastoplastic geofrictional soil model with volumetric yield
- `PM4Sand` — critical-state plasticity for sand liquefaction
- `PressureDependMultiYield` — UCSD multi-yield soil model coupling shear/volumetric pressure
- `FluidSolidPorousMaterial` — porous saturated soil skeleton under dynamic pore pressure
- Example: ElasticIsotropic (E=2.0e11, v=0.3)

### 4.16 `section()` (5 main types + nested)
- `Elastic` — prismatic elastic section (E, A, Iz)
- `Fiber` — begins fiber-discretized section, with `-GJ` torsional stiffness; nests patches/layers
- `WideFlange` — programmatic steel I-section fiber generator (d, tw, bf, tf, nfd, nft)
- `RC` — generates rectangular RC section with integrated rebars
- `SectionAggregator` — aggregates shear/torsion uniaxial materials onto an existing bending section

Nested fiber subcommands:
- `fiber(yCrds, zCrds, A, matTag)` — single fiber
- `patch('quad', matTag, numSubCol, numSubRow, *vertexCoords)` — quad patch grid of fibers
- `layer('straight', matTag, numFiber, area, *endCoords)` — straight rebar line
- Example: Fiber section with a quad concrete patch and two straight rebar layers (top/bottom)

### 4.17 `frictionModel()` (3 variants)
- `Coulomb(frnTag, mu)` — constant coefficient friction
- `VelDependent(frnTag, muSlow, muFast, transCoeff)` — velocity-dependent friction coefficient
- `VelNormal(frnTag, muSlow, muFast, transCoeff, ...)` — friction coupling sliding velocity and normal axial force

### 4.18 `geomTransf()` (3 variants)
- `Linear` — small-deformation linear transform (Euler-Bernoulli mapping)
- `PDelta` — captures second-order axial-bending coupling (P-Delta effects)
- `Corotational` — large finite-rotation corotational theory
- Examples: Linear 3D transform with direction cosines; PDelta transform

---

# DOCUMENT 2: `opstool_reference.pdf` — Unified Structural Workflow Manual (v7.0)

## Chapter 1: The Chronological 10-Step Modeling Pipeline

A strict ordered pipeline — deviating (e.g. calling `element()` before `geomTransf()`, or loading before boundary fixity) breaks OpenSeesPy's state registration.

| Step | Phase | Command | Purpose |
|---|---|---|---|
| 1 | Wipe Domain Memory | `ops.wipe()` | Purges numerical memory, closes recorder streams |
| 2 | Initialize Dimension | `ops.model('basic', '-ndm', ndm, '-ndf', ndf)` | Sets spatial dimension & DOF maps |
| 3 | Map Spatial Nodes | `ops.node(nodeTag, *coords)` | Registers joints |
| 4 | Enforce Boundary Fixity | `ops.fix(nodeTag, *fixity)` | Locks DOFs |
| 5 | Constitutive Material Registry | `ops.uniaxialMaterial()`, `ops.nDMaterial()` | Steel/concrete/soil/fiber properties |
| 6 | Define Section & Transformations | `ops.section()`, `ops.geomTransf()` | Cross-sections + local-global axes |
| 7 | Assemble Connectivity | `ops.element(eleType, eleTag, *nodes, *args)` | Links nodes into elements |
| 8 | TimeSeries & Loading | `ops.timeSeries()`, `ops.pattern()` | Static/seismic load definitions |
| 9 | Configure Solver Suite | `ops.system()`, `ops.integrator()`, `ops.analysis()` | Constraint handlers, numberer, integration |
| 10 | Solve & Record | `ops.analyze()` | Runs steps, commits results |

**1.1 Sample Script Architecture** — full skeleton example walking through all 10 steps: wipe → 3D model (ndm=3,ndf=6) → 2 nodes → fix node 1 fully → Steel01 material (Fy=355, E=210000, b=0.01) → Linear geomTransf + Lobatto beamIntegration (5 pts) → forceBeamColumn element → Linear timeSeries + Plain pattern + point load at node 2 → solver stack (`BandGeneral` system, `RCM` numberer, `Transformation` constraints, `NormDispIncr` test at 1e-8/10 iterations, `Newton` algorithm, `LoadControl` integrator at 0.1, `Static` analysis) → `analyze(10)`.

## Chapter 2: Core Command Catalog & Selection Logic

**2.1 Rayleigh Damping** — D = αM·M + βK·K_curr + βK_init·K_init + βK_comm·K_comm. Recommends K_init damping to avoid spurious non-physical damping forces when tangent stiffness drops due to yielding.

**2.2 Boundary SP Constraints** — `fix()` targets unique node tags; `fixX/Y/Z()` restrains entire coordinate planes at once. Examples: lock translations/release rotations; clamp an entire X=0.0 plane.

**2.3 Boundary MP Constraints** — `equalDOF` couples specific DOFs between master/slave (e.g. soil boundary columns); `rigidDiaphragm` models infinite in-plane slab stiffness; `rigidLink` enforces rigid beam/bar offsets (axial+flexural rigid connection).

**2.4 Fluid Pressure Constraints** — `pressureConstraint` integrates fluid velocity nodes with dedicated pressure DOFs to mitigate volumetric locking in incompressible FSI. Example shows a fluid velocity node (2 DOF) paired with an extra pressure node (1 DOF, via `'-ndf',1`).

**2.5 TimeSeries Scaling Models table**:
| Type | Syntax | Application |
|---|---|---|
| Constant | `ops.timeSeries('Constant', tag)` | Static gravity self-weights |
| Linear | `ops.timeSeries('Linear', tag)` | Monotonic pushover drift increments |
| Trigonometric | `ops.timeSeries('Trig', tag, tStart, tEnd, period, '-factor', f)` | Resonant cycle fatigue testing |
| Path | `ops.timeSeries('Path', tag, '-dt', dt, '-values', list(vals))` | Seismic acceleration time-histories |

**2.6 Load Patterns** — `Plain` (point loads/element forces under timeSeries scaling), `UniformExcitation` (uniform seismic base acceleration), `MultiSupport` (differential wave propagation). Shows `load()` and `eleLoad('-ele',...,'-type','-beamUniform',Wy,Wz)` syntax plus a UniformExcitation dynamic base shear example.

**2.7 Distributed & Hinged Beam Integration** — distributed rules (e.g. Lobatto) permit plasticity anywhere along member length; hinge integrations (e.g. HingeRadau) confine nonlinearity to localized plastic-hinge zones for efficiency. Both syntaxes shown side by side.

**2.8 Geometric Transformations** — selection guidance: `Linear` for standard small-deflection states, `PDelta` for lateral stability/gravity sway, `Corotational` for buckling and flexible cable members. 3D examples given with local-z vector arguments.

## Chapter 3: Exhaustive Structural Cross-Section Reference

15 section types with syntax and selection criteria:

| Type | Syntax | Selection Criteria |
|---|---|---|
| Elastic | `ops.section('Elastic', tag, E, A, Iz, G, J)` | Prismatic linear frame components |
| Fiber | `ops.section('Fiber', tag, '-GJ', GJ)` | Non-linear columns and flexural members |
| NDFiber | `ops.section('NDFiber', tag)` | 3D multiaxial fiber sections |
| WideFlange | `ops.section('WFSection2d', tag, mat, d, tw, bf, tf, nfw, nff)` | Steel I-beams with built-in meshing |
| RC | `ops.section('RCSection2d', tag, mat, d, b, cover, coreMat, rebarMat, rebarArea, nRebars)` | RC beams with discrete rebars |
| RCCircular | `ops.section('RCCircularSection2d', tag, mat, d, cover, coreMat, rebarMat, rebarArea, nRebars)` | Circular RC bridge piers/columns |
| Parallel | `ops.section('Parallel', tag, *secTags)` | Compiles parallel resistance section components |
| SectionAggregator | `ops.section('Aggregator', tag, *mats, '-section', secTag)` | Aggregates elastic shear/torsion with fiber models |
| Uniaxial | `ops.section('Uniaxial', tag, uniMatTag, forceDir)` | Translates uniaxial material to force-deformation |
| ElasticMembranePlate | `ops.section('ElasticMembranePlateSection', tag, E, nu, h, rho)` | Linear thin plate/membrane panels |
| PlateFiber | `ops.section('PlateFiber', tag, matTag, h)` | Nonlinear solid concrete floor/slab modeling |
| Bidirectional | `ops.section('Bidirectional', tag, E, G, sigY, Hiso, Hkin)` | Multiaxial plasticity yield surfaces |
| Isolator2spring | `ops.section('Isolator2spring', tag, k1, k2, fy, u)` | Seismic elastomeric rubber base isolators |
| LayeredShell | `ops.section('LayeredShell', tag, nLayers, *mats, *thick)` | Multi-layer reinforced shear wall core systems |
| Pipe | `ops.section('Pipe', tag, mat, d, t, nR, nC)` | Prismatic hollow steel pipelines/tubulars |

## Chapter 4: Comprehensive Uniaxial Materials Catalog

**4.1 Steel & Reinforcing Steel** (7 types): `Steel01` (bilinear kinematic hardening), `Steel02` (Giuffre-Menegotto-Pinto with transitions), `Steel4` (isotropic hardening + degradation params), `ReinforcingSteel` (fatigue/buckling envelopes), `Dodd_Restrepo` (cyclic Bauschinger effects), `RambergOsgoodSteel` (continuous power-law curves), `SteelMPF` (Menegotto-Pinto with distinct tension/compression limits), `Steel01Thermal` (temperature-dependent yield).

**4.2 Concrete Materials** (16 types): `Concrete01` (Kent-Scott-Park, zero tensile strength), `Concrete02` (adds linear tension softening), `Concrete02IS` (modified for stiffness interpolation), `Concrete04` (Popovics curve + tension softening), `Concrete06` (Thorenfeldt compressive + tensile softening), `Concrete07` (Chang-Mander formulation), `Concrete01WithSITC` (adds stiffness transformation variables), `ConfinedConcrete01` (unified Mander confined envelope), `ConcreteD` (Karsan-Jirsa cyclic hysteresis), `FRPConfinedConcrete` (FRP-confined circular columns), `FRPConfinedConcrete02` (FRP-confined polygonal columns), `ConcreteCM` (full Chang-Mander cyclic model), `TDConcrete` (creep/shrinkage time-dependent), `TDConcreteEXP` (exponential shrinkage envelope), `TDConcreteMC10` (Model Code 2010 creep), `TDConcreteMC10NL` (nonlinear creep under high stress ratios).

**4.3 Standard Uniaxial Materials** (7 types): `Elastic` (linear, supports different Eneg), `ElasticPP` (elastic-perfectly-plastic with kinematic limits, epsYn defaults to -epsYp), `ElasticPPGap` (adds compression gap limits + damage flag), `ENT` (elastic-no-tension, unilateral contact), `Hysteretic` (tri-linear with pinch/damage coefficients), `Parallel` (sums forces), `Series` (sums deformations).

**4.4 Geotechnical SSI Soil-Spring Materials** (6 types, used in zeroLength elements for pile-soil interaction): `PySimple1` (nonlinear lateral p-y curves), `TzSimple1` (nonlinear skin friction t-z curves), `QzSimple1` (nonlinear tip bearing q-z curves), `PyLiq1` (PySimple1 + pore-pressure/liquefaction degradation, Ru param), `TzLiq1` (TzSimple1 + pore-pressure limits), `QzLiq1` (QzSimple1 + pore-pressure degradation).

**4.5 Hysteretic, Limit-State & Other Materials** (36 types): `Hardening` (isotropic/kinematic linear hardening), `CastFuse` (cast steel damper fuse links), `Damper` (F=Cd·v^α viscous), `ViscousDamper` (adds thermal degradation), `BilinearOilDamper` (high-capacity with relief threshold Fr,p), `Bilin` (modified IMK bilinear deterioration), `ModIMKPeakOriented` (modified IMK peak-oriented hysteresis), `ModIMKPinching` (modified IMK pinched hysteresis), `SAWS` (seismic wood-sheathed shear wall panels), `BarSlip` (rebar bar-slip at beam-column joints), `Bond_SP01` (strain penetration of anchored rebars), `Fatigue` (tracks low-cycle strain fatigue damage via `-DI`), `Multiplier` (scales nested material force/stress by a factor), `ImpactMaterial` (contact impact elastic-PP gap), `HyperbolicGapMaterial` (hyperbolic soil gap for bridge abutments), `LimitState` (tracks flexural/shear failure limit states), `MinMax` (triggers failure outside min/max strain bounds), `ElasticBilin` (bilinear elastic with tension/compression gap), `ElasticMultiLinear` (custom multi-point elastic envelope), `MultiLinear` (multi-linear cyclic hysteretic envelope), `InitStrainMaterial` (sets initial strain, e.g. prestressed tendons), `InitStressMaterial` (sets initial stress, e.g. axial prestressing), `PenaltyUni` (high-stiffness penalty offsets at rigid limits), `PathIndependent` (forces nested material path-independence), `SimpleFracture` (zeroes stress at fracture strain), `TensionOnly` (zero compressive strength on nested material), `Pinching4` (highly nonlinear pinching hysteresis, e.g. shear panels), `ECC01` (Engineered Cementitious Composites strain-hardening), `SelfCentering` (flag-shaped self-centering damper), `Viscous` (F=C·v^α), `BoucWen` (continuous Bouc-Wen hysteretic loops), `BWBN` (Bouc-Wen with pinching/degradation, adds q,p params), `KikuchiAikenHDR` (High Damping Rubber bearing), `KikuchiAikenLRB` (Lead Rubber Bearing isolator), `AxialSp` (axial load-deformation with degradation thresholds), `AxialSpHD` (axial load-deformation with pinch envelope), `PinchingLimitStateMaterial` (limit-state with pinched cycles), `CFSWSWP` (Cold-Formed Steel Wood-Sheathed shear wall panel), `CFSSSWP` (Cold-Formed Steel Steel-Sheathed shear wall panel), `Backbone` (converts a multilinear backbone def to a material), `Masonry` (infilled masonry envelope for shear panels), `pipeMaterial` (pipeline material under geotechnical pressure).

## Chapter 5: Comprehensive nD Materials Catalog (30 types)

`ElasticIsotropic` (standard 3D tensor), `ElasticOrthotropic` (9-variable orthotropic tensor), `J2Plasticity` (Von Mises multiaxial with isotropic/kinematic hardening), `DruckerPrager` (shear-yield for concrete/geotechnical columns), `PlaneStress` (wraps a 3D material to enforce plane stress), `PlaneStrain` (wraps a 3D material to enforce plane strain), `MultiaxialCyclicPlasticity` (multiaxial cyclic steel/concrete model), `BoundingCamClay` (cohesive soil, critical state mechanics), `PlateFiber` (wraps 3D material to plate-fiber shear wall models), `FSAM` (Tsinghua RC shear wall cyclic model), `ManzariDafalias` (UCSD stress-ratio sand model), `PM4Sand` (Boulanger & Ziotopoulou sand liquefaction model), `PM4Silt` (clay/silt liquefaction model), `StressDensityModel` (Takahashi high-fidelity sand model), `AcousticMedium` (infinite shear-wave speed, models water basins), `CycLiqCP` (Tsinghua cyclic plastic sand liquefaction), `CycLiqCPSP` (Tsinghua cyclic sand with shear-stress scaling), `PlateFromPlaneStress` (converts plane stress to shell plate formulation), `PlateRebar` (wraps uniaxial rebar steel into shell rebar layers), `PlasticDamageConcretePlaneStress` (multiaxial plastic damage for RC walls under cyclic drift), `ContactMaterial2D` (2D frictional boundary contact), `ContactMaterial3D` (3D frictional boundary contact), `InitialStateAnalysisWrapper` (locks in in-situ gravity stress fields for geotechnical soils), `InitStressNDMaterial` (applies initial multiaxial stresses), `InitStrainNDMaterial` (applies initial multiaxial strains), `PressureIndependMultiYield`/PIMY (UCSD pressure-independent model for cohesive clays), `PressureDependMultiYield`/PDMY (UCSD pressure-dependent sand model with dilatancy), `PressureDependMultiYield02`/PDMY02 (nested yield surfaces), `PressureDependMultiYield03`/PDMY03 (advanced nonlinear shear-volume coupling), `FluidSolidPorousMaterial` (UCSD coupled fluid-solid porous material for saturated SSI soil).

## Chapter 6: Elements & Discretization Formulations (30 element types)

`zeroLength` (flexible springs/bearings/SSI piles), `truss` (pin-ended axial-only), `corotTruss` (large geometric motion), `elasticBeamColumn` (linear elastic prismatic), `dispBeamColumn` (displacement-based nonlinear), `forceBeamColumn` (force-based accurate nonlinear), `ShellMITC4` (4-node shell with shear-lock correction), `quad` (2D plane stress/strain continuum, with optional pressures), `stdBrick` (8-node 3D solid), `bbarBrick` (8-node brick for incompressible materials), `SSPquad` (stabilized single-point quad for fast meshes), `SSPbrick` (stabilized single-point 3D brick), `FourNodeTetrahedron` (unstructured tetrahedron mesh), `quadUP` (2D coupled displacement-pore pressure, saturated soil), `brickUP` (3D coupled displacement-pore pressure), `bbarQuadUP` (2D coupled soil with volumetric locking correction), `bbarBrickUP` (3D coupled soil with volumetric locking correction), `9_4_QuadUP` (9-node displacement/4-node pressure coupling), `20_8_BrickUP` (20-node displacement/8-node pressure coupling), `SSPquadUP` (stabilized coupled 2D soil), `SSPbrickUP` (stabilized coupled 3D soil), `SimpleContact2D` (2D frictional boundary contact), `SimpleContact3D` (3D frictional boundary contact), `BeamContact2D` (beam-to-quad-solid contact), `BeamContact3D` (beam-to-brick-solid contact), `CatenaryCableElement` (nonlinear slack/taut cable), `PFEMElementBubble` (PFEM FSI fluid element), `SurfaceLoad` (surface pressure application), `AC3D8` (acoustic water basin/wave propagation), `ASI3D8` (acoustic-structural boundary coupling), `MasonPan12` (12-node cyclic masonry panel).

## Chapter 7: Advanced Pre-Processing Modules

**7.1 Fiber Section Meshing** (`opstool.pre.section`) — `SecMesh`/`FiberSecMesh` classes auto-mesh concrete geometry + rebar lines. Example workflow: define outer polygon points → offset by cover distance via `opst.pre.section.offset()` → create cover/core patches via `create_polygon_patch()` → build a `SecMesh()` object → assign material tags via `set_ops_mat_tag()` → set mesh size → add a rebar line via `add_rebar_line()` → call `.mesh()` → inject directly into OpenSeesPy via `.to_opspy_cmds(secTag=1, GJ=1e6)`.

**7.2 GMSH Finite Element Integration** (`opstool.pre.Gmsh2OPS`) — parses `.msh` files, generates nodes/physical groups/boundary connectivity. Example: `Gmsh2OPS("soil_basin.msh")`, then `.to_opspy_nodes()` and `.to_opspy_elements(ele_type="SSPquad", mat_tag=1, thick=1.0)`.

**7.3 Legacy Tcl-to-Python Translation** (`opstool.pre.tcl2py`) — compiles old Tcl scripts to Python OpenSeesPy syntax. Example: `opst.pre.tcl2py("legacy_model.tcl", "modern_model.py")`.

**7.4 Dimensional Unit Standardization** (`opstool.pre.UnitSystem`) — standardizes dimensionless OpenSeesPy inputs to a target unit base. Example: `UnitSystem(length="m", force="kN", time="sec")`, then `5.0 * UNIT.m`, `210.0 * UNIT.GPa`, `150.0 * UNIT.kN`.

**7.5 Architectural Load Processing & Distribution** — `transform_beam_uniform_load`, `transform_beam_point_load`, `apply_load_distribution` APIs auto-solve localized end reactions. Example: `transform_surface_uniform_load(span_lengths=[6.0,6.0], load_intensity=5.0, tributary_width=3.0)`.

**7.6 Self-Weight Gravity Load** (`opstool.pre.gen_grav_load`) — retrieves nodal masses/coords to auto-apply self-weight. Example: Linear timeSeries + Plain pattern, then `gen_grav_load(direction="Z", factor=-9.81)`.

**7.7 System Matrices Extraction** (`opstool.pre.get_mck`) — pulls unified Mass/Damping/Stiffness matrices for external solving/eigenvalue work. Example: `M, C, K = opst.pre.get_mck()`.

**7.8 Nodal Audit, Masses, Floating Nodes Cleanup** — `ModelMass()` for mass distribution audit; `find_void_nodes()` identifies isolated unconnected nodes (solver singularity risk); `remove_void_nodes()` purges them.

## Chapter 8: Database Management & Solver Rescue

**8.1 Relational Saving with ODB** (`opstool.post.CreateODB`) — relational NetCDF database instead of manual recorders. Params: `odb_tag`, `project_gauss_to_nodes` (Averaging/Copy/Extrapolate), `save_fiber_sec_resp`, `fiber_ele_tags`. Workflow: loop `ops.analyze(1)` + `ODB.fetch_response_step()` each step, then `ODB.save_response()`.

**8.2 Convergence Rescue** (`opstool.anlys.SmartAnalyze`) — auto-subdivides step sizes, switches algorithms (Newton-Raphson → KrylovNewton/BFGS), adjusts tolerances on the fly. Example: `SmartAnalyze(analysis_type="Static")`, `.set_load_control(0.1, max_steps=100)`, `.analyze()`.

**8.3 Section Moment-Curvature Analysis** (`opstool.anlys.MomentCurvature`) — automates nonlinear fiber section evaluation under constant axial load, returns yield/post-yield/curvature history. Example: `MomentCurvature(secTag=1, axial_load=-180.0, max_curvature=0.05)`, `.analyze()`, `.plot()`.

**8.4 Spectral Dynamics and Buckling Analysis** — prebuilt routines for Response Spectrum Analysis (RSA) and linear buckling load factors. Example: `save_linear_buckling_data(odb_tag=1)`, `get_linear_buckling_data(odb_tag=1)`.








