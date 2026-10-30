# Review Paper Outline (Assignment)

> **Assignment spec**: English narrative review (~3,000 words) that systematically
> surveys how Artificial Intelligence is applied within the author's area of interest,
> and critically discusses it.
>
> **Author's area of interest**: data-plane control of resource-constrained,
> cloud-native 5G core (UPF / CNI), and the use of learning-based methods for it.
>
> **Reuse note**: Sections 3–5 double as the Related Work draft for the main thesis.
> Section 5 (synthesis & gap) becomes the main thesis' Introduction gap paragraph.
> Reference material already organized in `REFERENCES.md` groups [C1]–[C6] and
> `READING_LIST.md` section C. Use `references.bib` keys for citation.

---

## Working Title (choose one)

1. "Artificial Intelligence for Data-Plane Control in Cloud-Native 5G:
   A Review of Learning-Based CNI Performance Optimization and Runtime Adaptation"
2. "Learning to Adapt the 5G User Plane: A Review of AI-Driven Datapath and
   Network-Function Control at the Resource-Constrained Edge"

---

## Section plan & word budget (total ~3,000)

| # | Section | ~Words | Purpose | Key refs (bib keys) |
|---|---------|--------|---------|---------------------|
| — | Abstract | 150 | Scope + what AI is reviewed + takeaway | — |
| 1 | Introduction | 450 | Why UPF data plane matters; AI as enabler | TS23.501, A1–A3 |
| 2 | Background | 500 | UPF datapath; CNI; what "AI control" means here | C1, C2, B1 |
| 3 | AI Theme 1: Learning-based network/K8s control | 700 | Core of the review — RL/ML for allocation, scaling, migration | C3, C4, C6-3, READING_LIST C |
| 4 | AI Theme 2: AI-driven runtime datapath/NF adaptation | 600 | Switching UPF impl / path / CNI at runtime | C6-1, C6-2, C6-4 |
| 5 | Discussion: synthesis, gaps, open challenges | 450 | Cross-cut the two themes → what is missing | C-summary, C6-summary |
| 6 | Conclusion & future directions | 150 | Honest limits + where the field should go | — |

---

## Abstract (~150 words)

- 1 sentence: cloud-native 5G moved network functions to software → data-plane
  performance now depends on container networking (CNI) and orchestration.
- 1 sentence: this creates a control problem that AI/ML is increasingly applied to.
- 1 sentence: this review surveys AI use across two themes — (i) learning-based
  resource/flow/scaling control, and (ii) AI-driven runtime adaptation of the
  datapath / network functions.
- 1 sentence: synthesize trends, identify a gap (traffic-aware, cost-aware runtime
  datapath switching under resource constraints is under-explored).
- Keywords: 5G core, User Plane Function, Container Network Interface,
  reinforcement learning, edge computing.

---

## 1. Introduction (~450 words)

**1.1 Context (the "essential nature", mirrors TBI intro)**
- 5G core is now cloud-native: NFs run as containers on Kubernetes (TS 23.501).
- The User Plane Function (UPF) governs packet forwarding, GTP-U, QoS → its
  data-plane throughput/latency is critical (cite A1 Mishra, A2).
- In software UPFs, performance depends on the packet I/O path and the CNI driver.

**1.2 Why this is hard (the problem)**
- At the resource-constrained edge, hardware acceleration (SR-IOV/DPDK) is often
  unavailable or impractical → only software CNIs remain.
- Traffic is heterogeneous and time-varying (small control packets vs bulk video),
  so a single static configuration is rarely optimal.

**1.3 Why AI (the enabler)**
- Hand-tuned rules struggle with uncertainty and heterogeneity → learning-based
  control (RL/ML) is increasingly proposed for network/orchestration decisions.

**1.4 Scope & contribution of this review**
- State explicitly: review focuses on AI applied to UPF/CNI data-plane and
  orchestration control; excludes RAN PHY-layer AI, security AI, etc.
- Two themes (Sec 3, 4), synthesis (Sec 5).
- 1 sentence roadmap.

---

## 2. Background (~500 words)

**2.1 UPF data plane in cloud-native 5G**
- Packet path: N3 (gNB) → UPF (GTP-U decap, PDR/FAR) → N6 (DN).
- Software forwarding modes and their cost (brief; cite I/O-mode comparison work).

**2.2 Container Network Interfaces (CNI)**
- Role of CNI; ipvlan vs macvlan (packet distribution: IP-based vs MAC-based) [B1].
- Empirical finding: optimal CNI depends on packet size / workload [C1 dakic2024cni,
  C2 kang2021cni]. → motivates adaptivity.

**2.3 What "AI control" means in this domain**
- Framing decisions (allocation, scaling, placement, switching) as
  prediction (supervised, e.g. LSTM) or sequential decision-making (RL/MDP).
- Define terms briefly: state/action/reward, MDP/POMDP, simulation-based training.

---

## 3. AI Theme 1 — Learning-based network & Kubernetes control (~700 words)
*(This is the review's analytical core — group by sub-theme, use causal narrative,
not a paper list.)*

**3.1 RL for autoscaling / resource allocation**
- RL-based HPA; cost-efficient RL autoscaling (READING_LIST C-1).
- DRL resource allocation for cloud-native wireless (slicing/MEC).
- Narrative link: these treat "how much resource" — scaling, not datapath.

**3.2 RL for flow allocation inside the UPF**
- PDS-based online learning for delay-energy flow allocation across UPFs
  [C6-3 bhat2026flowalloc]. MDP formulation, sim-based, beats Q-learning.
- Link: controls "which UPF gets the flow" — scheduling, still not the datapath.

**3.3 RL for migration / placement under cost**
- FIRE: digital-twin (sim) training, migration cost in the objective, vs greedy/
  vanilla-RL baselines [C3 siew2022fire].
- Layer-aware container migration, cost vs latency, policy-gradient RL
  [C4 liu2024migration].
- Control-plane placement via contextual-bandit RL (multi-region).
- Narrative link: establishes the *method pattern* — "cost-aware sequential
  decision, trained in simulation, evaluated against baselines."

**3.4 Takeaway for Theme 1**
- The field has matured a reusable recipe: MDP + RL + simulation training +
  cost-in-objective. But the controlled *object* has been resources, flows,
  placement — never the datapath driver itself.

---

## 4. AI Theme 2 — AI-driven runtime datapath / NF adaptation (~600 words)

**4.1 Switching the UPF implementation**
- Dynamic AI-based UPF switching: SPGW-U ↔ VPP, LSTM throughput prediction,
  throughput-vs-energy tradeoff [C6-1 christakis2025upfswitching].
- Analysis: this is *prediction-driven* switching at the application layer (L7).

**4.2 Selecting the forwarding path**
- Intelligent eUPF: DQN + POMDP for MEC↔cloud path selection, eBPF passive
  delay measurement [C6-2 moreira2026eupf].
- Analysis: controls the *endpoint path*, not the in-node datapath driver.

**4.3 Mechanisms for runtime CNI change (tools, not policy)**
- Multus dynamic-networks-controller; CNI-Genie [C6-4].
- Analysis: they provide *how to change* a CNI at runtime, but say nothing about
  *when* — no learned policy.

**4.4 Takeaway for Theme 2**
- Runtime adaptation of the user plane is emerging, but existing AI work targets
  app implementation or path, and CNI-level work is mechanism-only.

---

## 5. Discussion — synthesis, gaps, open challenges (~450 words)

**5.1 Cross-cutting the two themes**
- Theme 1 gives a mature *method* (cost-aware RL, sim-trained).
- Theme 2 gives emerging *runtime adaptation targets*.
- Their intersection — applying cost-aware RL to the *CNI datapath* at runtime —
  is essentially empty (C-summary, C6-summary tables).

**5.2 Why the gap persists (be analytical, not just descriptive)**
- Switching cost (Pod-recreation downtime) historically made the problem moot.
- High-end environments bypass it with hardware → problem only matters at the
  constrained edge.
- Cross-disciplinary (CNI internals + 5G core + RL) → few sit at the intersection.

**5.3 Open challenges for AI in this space**
- Sim-to-real gap for network RL (training in simulators, deploying on real cores).
- Cost modeling: encoding downtime/disruption into the reward.
- Evaluation beyond accuracy: effective gain (goodput), false-positive suppression.
- Generalization across traffic patterns and hardware.

---

## 6. Conclusion & future directions (~150 words)

- Restate: AI has matured for *resource/flow/placement* control; runtime *datapath*
  adaptation is the frontier, especially at the resource-constrained edge.
- Honest limitation of the literature: little real-testbed, mostly simulation;
  cost-of-switching under-modeled.
- Future: traffic-aware, cost-aware, learning-based datapath selection validated on
  real cloud-native cores — directly motivating the author's thesis.

---

## Writing checklist (lessons from the sample TBI review)

- [ ] Use **causal narrative** within each section (A enables B, failure of B causes
      C), not "Author X did Y; Author Z did W."
- [ ] End each theme section with an explicit **"takeaway / relation to the field."**
- [ ] Keep one consistent vocabulary (define MDP/RL/CNI once, reuse).
- [ ] Discussion must state the **gap** and **why it persists** (analytical depth =
      higher grade).
- [ ] Conclusion: admit limitations honestly (sample review admits rodent≠human).
- [ ] Citation style: match course requirement (numbered, like the sample) — confirm.
- [ ] Word count target per section (table above); total ~3,000.

## Candidate reference pool (from references.bib)

- Data-plane / CNI: dakic2024cni, kang2021cni, (I/O-mode comparison — add)
- RL method pattern: siew2022fire, liu2024migration, bhat2026flowalloc,
  + READING_LIST C-1 (RL-HPA, cost-efficient RL)
- Runtime adaptation: christakis2025upfswitching, moreira2026eupf,
  multus_dynamic_networks, cnigenie
- 5G core context: TS 23.501, 23.288; A1 (Mishra UPF latency)
- (Optional domain color) seliem2025smartfactory, 5gacia2022machinevision
