# LegionTrap TI — Phase 4 Architecture Blueprint

**Document type:** Pre-implementation architecture blueprint
**Status:** Approved — implementation-risk corrections applied; PR 1 is cleared to begin
**Audience:** Engineers, contributors
**Date:** 2026-05-25

---

## 1. Phase 4 Mission

Phase 3 answered two questions: *what happened*, and *where did it come from*. Every event has a timestamp, a source IP, a GeoIP context, and a mapped ATT&CK technique. The system can tell you that 1,247 events arrived from ASN 12345 in the last 30 days and that they map to T1110 and T1046. That is useful. It is not intelligence.

Phase 4 answers a harder question: **who is doing this, how do they operate, and have we seen them before?**

The gap between those two questions is the gap between raw telemetry and behavioral memory. Telemetry is infinite; memory is selective. A system that only accumulates telemetry grows linearly in data volume and sub-linearly in intelligence value. A system with behavioral memory grows in intelligence faster than it grows in data, because each new observation is interpreted in the context of everything the system has previously learned about actor patterns.

The specific capability Phase 4 is building is this: given a new event sequence from an IP the system has never seen, determine whether the behavioral pattern behind that sequence has been observed before — possibly months ago, from different infrastructure, with a different tool version, targeting a different service. If it has been seen before, link the new observation to the historical record. If it has not, start a new record.

This capability — behavioral actor recognition across infrastructure changes — is what separates a honeypot intelligence backend from an adaptive defense platform. It cannot be built by adding features to an IP-centric schema. It requires a deliberate architectural shift.

---

## 2. Core Architectural Shift

### The current model

LegionTrap's current data model centers on three entities: raw events, normalized events, and source IPs. The source IP is the primary identity. Intelligence about an actor is stored as metadata on the IP: event count, reputation score, country, ASN, tags.

This model has a structural ceiling. As soon as an actor rotates their IP — which may happen in hours for cloud-hosted tooling, or days for botnet infrastructure — the accumulated intelligence is orphaned on the old IP and the new IP starts fresh with no history.

The model is:

```
event_type → source_ip → geographic/ASN metadata
                      → reputation score
                      → tags
```

Intelligence ages at the speed of IP rotation, which is fast.

### The Phase 4 model

Phase 4 introduces a layer of abstraction above the IP: the **behavioral fingerprint** and the **campaign**. An IP is now an observed infrastructure node, not an actor identity. The actor's identity is encoded in their behavioral fingerprint — the structured representation of how they operate.

The model becomes:

```
event_type → source_ip → behavioral_fingerprint → campaign
                      ↓
              geographic/ASN metadata (still valuable as infrastructure context)
```

The behavioral fingerprint persists even when the IP changes. The campaign record accumulates observations across multiple IPs and across time. Intelligence ages at the speed of behavioral change — which, for most actors, is slow. Operational habits, tool choices, timing patterns, and target selection logic are rarely changed because they're rarely perceived as risks. This is the attacker's blind spot: they change their IP but not their behavior.

### What this means concretely

| Dimension | Phase 3 model | Phase 4 model |
|-----------|--------------|--------------|
| Primary identity | Source IP | Behavioral fingerprint |
| Actor continuity | Lost on IP rotation | Preserved across infrastructure changes |
| Intelligence lifetime | Hours to days | Months to years |
| Query primitive | "What did this IP do?" | "Is this actor known? What is their history?" |
| Match type | Equality (same IP) | Similarity (similar behavior) |
| Campaign concept | Absent | First-class entity |
| Dormancy handling | IP goes cold; record is abandoned | Campaign enters dormant state; reactivated on new match |

This shift does not discard anything built in Phases 0–3. IPs, GeoIP enrichment, reputation scores, and ATT&CK mappings remain. They become attributes of observations, not primary identities.

---

## 3. What Phase 4 Includes

### 3.1 Behavioral fingerprint schema

A behavioral fingerprint is a structured document encoding the observable behavioral characteristics of an actor's current toolset and methodology. It is computed from a window of events associated with a source IP and stored as a structured record.

A fingerprint encodes dimensions across six categories:

**Timing features**
- Inter-probe interval distribution (min, max, mean, stddev of milliseconds between probes in a session)
- Session duration distribution (length of distinct scanning sessions)
- Time-of-day distribution (which UTC hours are active, encoded as a 24-bucket histogram)
- Day-of-week distribution (which days of the week are active)
- Burst pattern (whether probes arrive in tight clusters or at even spacing)

**Sequence features**
- Port probe order (the canonical ordering of ports targeted in reconnaissance)
- Credential pair ordering (the first N credential pairs attempted and in what order)
- Exploit attempt sequence (which exploit types are tried, in what order, and with what fallback behavior)
- Service discovery sequence (which service types are probed before others)
- Post-success behavior (what the actor does after a successful probe response)

**Protocol features**
- TLS fingerprint (JA3-style: cipher suite ordering, extension ordering, elliptic curve preferences)
- HTTP header ordering and values (User-Agent patterns, Accept-* header presence/ordering)
- SSH KEX preferences (key exchange algorithm ordering, host key algorithm ordering)
- TCP behavior (SYN window size, IP TTL distribution, TCP options ordering)
- Protocol version preferences (which TLS version, SSH protocol version is tried first)

**Credential features**
- Username pattern (literal values, character class distribution, top-N most common usernames)
- Password pattern (length distribution, character class distribution, pattern families)
- Credential mutation behavior (does the actor mutate variants: admin/admin1/admin123?)
- Credential list overlap with known wordlists (what percentage of tried credentials appear in known lists like rockyou, SecLists)

**Target selection features**
- Port distribution (which ports are probed, with what frequency weighting)
- Service targeting preference (SSH-first vs. HTTP-first vs. port-sweep behavior)
- Horizontal vs. vertical scanning pattern (many ports on few IPs vs. few ports on many IPs)
- High-value port sensitivity (does the actor probe unusual high-value ports suggesting specific intelligence?)

**Infrastructure features**
- ASN diversity (does the actor use a single ASN or rotate across many?)
- Geographic diversity of infrastructure (single country vs. distributed)
- Timing between infrastructure rotations (estimated from observed IP changes during a campaign)

Not every fingerprint will have all fields populated. Fields are populated from available evidence and left null when there is insufficient data. A sparse fingerprint is valid; it simply produces a lower-confidence campaign match.

### 3.2 Campaign clustering foundation

A campaign is a collection of behavioral fingerprints that are sufficiently similar to be attributed to a coordinated actor or actor group. Campaign identity persists independently of IP infrastructure.

Phase 4 implements a first-generation campaign clustering approach using deterministic rules rather than ML. This is deliberate: deterministic rules are explainable, debuggable, and don't require training data. ML-based clustering is a Phase 5/6 enhancement once the fingerprint data volume justifies it.

**Phase 4 clustering heuristics:**

A new fingerprint is compared against all existing active campaigns. If the comparison produces a similarity score above a configurable threshold against an existing campaign, the fingerprint is associated with that campaign. If no campaign exceeds the threshold, a new campaign is created.

The comparison algorithm in Phase 4 uses weighted feature matching:
- Timing features: 20% of total similarity weight
- Sequence features: 35% of total similarity weight
- Protocol features: 25% of total similarity weight
- Credential features: 10% of total similarity weight
- Target selection features: 10% of total similarity weight

These weights are configurable and will need empirical tuning. They are initial estimates based on relative durability of each feature type across infrastructure changes.

### 3.3 Event sequence extraction

Before fingerprints can be computed, raw events must be assembled into behavioral sequences. This requires:

- Grouping events by source IP within a time window (configurable; default: 24 hours)
- Ordering events chronologically within each group
- Computing inter-event timing intervals
- Identifying session boundaries (configurable gap threshold; default: 30 minutes of inactivity)
- Extracting the ordered sequence of event types within each session

This extraction runs as a background process triggered after each ingest batch. It does not block the ingest path.

### 3.4 Timing and cadence feature extraction

Timing features require statistical summarization of raw intervals, not just storage of raw timing data. The extraction process computes:
- Descriptive statistics over inter-probe interval distributions
- Session duration statistics
- Time-of-day histograms (bucketed to the hour)
- Day-of-week histograms
- Burst detection (coefficient of variation of inter-probe intervals; low CV indicates metronomic automated tooling)

### 3.5 Tool and protocol fingerprints

Where the raw event data contains observable protocol-level information (captured in the `raw_json` field of `raw_events`), Phase 4 should extract tool-level signals. The specific fields available depend on what the ingest source provides. Cowrie-generated events include SSH KEX parameters. HTTP-aware sensors include User-Agent and header data. Where this data exists, it should be extracted into the fingerprint. Where it does not exist, the corresponding fingerprint fields are null.

This means fingerprint quality is bounded by sensor capability. Phase 4 should not require sensor upgrades to function; it should use whatever protocol-level data is available and leave unobservable fields sparse.

### 3.6 Campaign identity model

A campaign has a stable UUID that does not change when new member IPs are added, when infrastructure rotates, or when the campaign goes dormant and is later reactivated. This stability is a design requirement: downstream systems (STIX exports, dashboard, future federation) must be able to reference a campaign by ID and receive consistent data across time.

Campaign status lifecycle:
- `active`: observed activity within the last N days (configurable; default: 7 days)
- `dormant`: no observed activity for N–M days (configurable; default: 7–90 days)
- `historical`: no observed activity for more than M days (configurable; default: 90 days)
- `reactivated`: a dormant or historical campaign that has received a new matching fingerprint

Reactivation is a first-class event. When a dormant campaign is matched by a new fingerprint, the system records a reactivation event with the gap duration, the new infrastructure details, and any behavioral delta between the historical fingerprint and the new one.

### 3.7 Campaign API endpoints

Phase 4 adds the following endpoints under `/api/campaigns`:

| Endpoint | Description |
|----------|-------------|
| `GET /api/campaigns` | Paginated list of campaigns, filterable by status, tag, date range |
| `GET /api/campaigns/{id}` | Full campaign detail: member IPs, timeline, fingerprint summary, behavioral notes |
| `GET /api/campaigns/{id}/timeline` | Ordered list of observations for this campaign |
| `GET /api/campaigns/{id}/members` | All source IPs attributed to this campaign |
| `GET /api/campaigns/active` | Shortcut for active campaigns ordered by most recent activity |
| `GET /api/campaigns/reactivated` | Campaigns that have reactivated within the last N days |

All endpoints require `require_jwt_or_api_key` authentication. All endpoints respect `PRIVACY_MODE` by masking IPs in responses when enabled.

### 3.8 Dashboard campaign visibility

A new dashboard panel shows:
- Active campaigns with member IP count, first/last seen, and confidence score
- Reactivation alerts (campaigns that reactivated within the last 7 days)
- Campaign detail view: timeline of observations, member IPs, behavioral summary

The campaign panel should be conservative in what it shows. Uncertain matches and low-confidence clusters should be marked as such rather than presented with false confidence.

### 3.9 Campaign export implications

The existing STIX export (`GET /api/exports/stix`) currently produces Indicator and IPv4-Addr objects. Once campaign data exists, the exporter can be extended to include:
- `campaign` SDOs linked to Indicator objects via `relationship` SDOs
- `attack-pattern` SDOs derived from the campaign's ATT&CK technique distribution

This extension should be implemented in PR 7 of the Phase 4 sequence, after the campaign data layer is stable. It must not be built speculatively before campaign data exists to populate it.

---

## 4. What Phase 4 Explicitly Excludes

These items are explicitly out of scope for Phase 4. They appear in this document because they are reasonable things to build and will likely be requested. Saying no to them during Phase 4 is an architectural discipline decision, not a permanent rejection.

| Item | Reason for exclusion | When it belongs |
|------|---------------------|----------------|
| AI/LLM reasoning | Requires clean, stable behavioral data to reason over; data layer must be proven before reasoning is added | Phase 5 |
| Autonomous response/blocking | Not a threat intelligence function; creates legal and operational risk | Never (out of scope for LegionTrap's mission) |
| Vector database | Not justified until fingerprint volume produces measurable similarity search latency; SQLite + JSON is sufficient for Phase 4 | Phase 5/6 if needed |
| Graph database | Campaign relationships in Phase 4 fit comfortably in relational tables; graph DB adds infrastructure complexity without current benefit | Phase 6/7 if justified |
| Async worker infrastructure | FastAPI `BackgroundTasks` is sufficient for fingerprint computation in Phase 4; Celery/asyncio workers only when task volume or latency requires them | Phase 5/6 if needed |
| Metamorphic deception runtime | Architecture defined in this document; implementation deferred | Phase 5/6 |
| Federation | Fingerprint schema must be stable before designing shareable format | Phase 7 |
| MISP export | Requires campaign attribution to be meaningful; MISP packages without campaign context are IP lists in XML | Phase 5 (post-campaign data) |
| Sigma rules | Sigma rules encode behavioral patterns; campaign layer must be stable before encoding those patterns as detection rules | Phase 5 |
| External scanning or active reconnaissance | Not a threat intelligence function; creates legal liability | Never |
| STIX Campaign/Relationship objects | Correct to build, but only after campaign data is populated and stable; do not build speculatively | PR 7 of Phase 4 (late, data-gated) |
| Operator-configurable similarity thresholds via API | Useful, but premature optimization before thresholds are empirically tuned | Post-Phase 4 |

---

## 5. Adaptive Deception Doctrine

Phase 4 defines the architectural direction for deception infrastructure. It does not implement a deception runtime. The implementation belongs to a later phase after the behavioral memory layer is operational, because deception without behavioral memory produces poor intelligence — you know an attacker probed your decoy, but you can't link that probe to a known campaign or actor pattern.

### 5.1 Core principle: deception is an intelligence extraction mechanism

Deception in LegionTrap is not a defensive response. It is not retaliation. It is not a way to harm attackers or disrupt their operations. It is an intelligence collection mechanism — a way to learn more about attacker behavior than passive observation of real infrastructure would reveal.

This distinction matters architecturally because it defines what deception surfaces are allowed to do:
- They may present false information to an attacker
- They may collect behavioral intelligence from an attacker's interaction
- They may extend an attacker's engagement time to collect more data
- They may not initiate contact with any external system
- They may not execute payloads, even in an analysis sandbox
- They may not serve as a pivot point to real infrastructure under any circumstances

### 5.2 Metamorphic infrastructure means controlled surface mutation

"Metamorphic" does not mean random. Random mutation defeats its own purpose: if the deception surface is incoherent, an attacker identifies it as a honeypot immediately and the intelligence collection opportunity is lost.

Metamorphic infrastructure means the deception surface mutates in ways that are:
- **Internally consistent**: a decoy SSH server that presents Ubuntu 20.04 banners should also present filesystems and user artifacts consistent with Ubuntu 20.04
- **Externally plausible**: the surface should be indistinguishable from legitimate infrastructure of its claimed type
- **Controllably variable**: specific surface parameters (banner strings, protocol version advertisements, timing behavior) can be adjusted without breaking the overall deception narrative
- **Seeded from behavioral intelligence**: when a campaign is detected, the deception surface can be tuned to present artifacts that are specifically interesting to that campaign's observed targeting patterns

The mutation loop in Phase 5+:
```
Observe attacker behavior → Update behavioral fingerprint → Identify campaign pattern
→ Select surface configuration maximizing intelligence yield for this campaign type
→ Mutate decoy surface → Continue observation
```

### 5.3 Safety constraints on mutation

Mutation must never compromise safety. These constraints are absolute:

- Deceptive surfaces must be **network-isolated from real infrastructure** by firewall rules, not just software logic. A software misconfiguration should never create a path from deceptive to real infrastructure.
- Deceptive services must **never execute untrusted input**. They may log it; they may not run it. This includes shell commands, SQL, scripts, or payloads of any kind.
- Deceptive services must **never respond with real credentials, keys, or sensitive data** regardless of what the attacker requests.
- All deceptive infrastructure must be **labeled and tracked** in a configuration registry. An undocumented deceptive surface is a real risk: it can be mistaken for real infrastructure during incident response.

### 5.4 Deception feeds behavioral memory

The primary product of a deceptive interaction is not detection — it is behavioral data. A deceptive surface that logs only "attacker connected and tried credentials" has wasted the interaction. A surface that logs the full session — exact credential pairs, timing intervals, command sequence, payload structure, post-auth behavior — is producing the raw material for behavioral fingerprinting.

This is why deception implementation belongs after the behavioral memory layer is operational. The intelligence value of deceptive interactions compounds when those interactions are compared against historical fingerprints. Without behavioral memory, each deceptive interaction is an isolated event. With behavioral memory, each interaction is an observation point in a longitudinal actor profile.

---

## 6. Behavioral Fingerprint Philosophy

### 6.1 What is worth fingerprinting and why

Not all observable behavior is equally diagnostic. The value of a fingerprint dimension is a function of two properties: **durability** (how rarely this dimension changes across infrastructure rotations) and **discriminability** (how well this dimension distinguishes different actors from each other).

IP address: low durability, high discriminability — useless as a fingerprint dimension.
Time-of-day pattern: high durability, moderate discriminability — valuable.
Specific tool binary hash: high discriminability but rarely observable — aspirational.
Port probe sequence: moderate durability, high discriminability — valuable.

The fingerprint dimensions in Section 3.1 are selected for their position in this durability-discriminability space. They are behaviors that operators rarely change because they don't perceive them as risks, and that are distinct enough to separate different actors.

### 6.2 Timing dimensions

Timing is one of the most durable behavioral signals because it is often outside conscious attacker control. Inter-probe intervals are largely determined by tool configuration defaults that operators rarely change. Time-of-day patterns reflect the attacker's timezone and work schedule. Day-of-week patterns reflect organizational or individual work rhythms.

**Inter-probe interval** is the time between consecutive connection attempts from the same IP in a session. Fully automated tools produce intervals clustered tightly around a configured value (low variance). Operator-directed tools produce higher-variance intervals reflecting human decision latency. Mixed (automated tool with human oversight) produces bimodal distributions.

**Session structure** is the pattern of activity bursts separated by inactivity gaps. An actor running scans on a cron job produces regular, evenly spaced sessions. An operator running manual reconnaissance produces irregular sessions correlated with work schedules.

**Cadence across days** reveals whether an actor is conducting sustained operations or targeted campaigns. A sustained-operations actor produces daily activity with low variance. A targeted-campaign actor produces dense activity during the campaign window and nothing before or after.

### 6.3 Sequence dimensions

Behavioral sequences encode methodology. The order in which an actor tries things reveals their mental model of a target. An actor who always probes port 22 before port 80 before port 443 is applying a consistent mental model of target priority. An actor who always tries `admin/admin` before `root/root` before `admin/password` has a specific credential priority model.

These sequences are surprisingly stable. They reflect training, tool defaults, and organizational playbooks. Actors who have used the same toolset for years produce nearly identical sequences across different campaigns.

**Port probe sequence** is most diagnostic for reconnaissance-phase fingerprinting. The full sequence of ports probed, in order, with the gaps and repetitions preserved, is a strong actor signal.

**Credential sequence** is most diagnostic for credential-attack fingerprinting. Not just which credentials were tried, but in what order, and what mutation patterns appear (does the actor try `admin`, then `admin1`, then `admin123`? Or do they go straight to a wordlist without variations?).

**Post-response behavior** is diagnostic for distinguishing automated scanners from operator-directed tools. An automated scanner moves to the next target immediately after a response. An operator-directed tool may pause, observe, and then make a contextual next decision. Observing what an actor does with a successful probe response reveals whether there is human judgment in the loop.

### 6.4 Protocol dimensions

Protocol-level fingerprints are strong because they reflect tool implementation choices that are almost never changed by operators. JA3 TLS fingerprints, SSH KEX preference ordering, HTTP header ordering — these are determined by the library versions and default configurations used by the attack tool, not by the operator's preferences.

The challenge is that protocol-level data is only observable if the sensor captures it. Cowrie captures SSH KEX parameters; a simple TCP honeypot does not. The fingerprint schema should treat protocol dimensions as optional fields, populated when available.

### 6.5 Credential and payload dimensions

Credential patterns are diagnostic when an actor is conducting credential attacks. The specific set of credentials tried, their ordering, and the mutation patterns reveal:
- Whether the actor is using a known wordlist (and which one)
- Whether the actor is generating credentials algorithmically
- What target-specific intelligence the actor has (trying company-name-derived passwords indicates external research)

Payload structure is diagnostic when payloads can be captured. The encoding style, size distribution, obfuscation patterns, and C2 communication patterns of a payload are determined by the tool that generated it and are extremely stable across campaigns. However, payload capture requires sensor capability beyond what basic honeypots provide. Phase 4 should support payload fields in the fingerprint schema but not require them.

### 6.6 Target selection dimensions

What an actor targets — and what they do not target — reveals their intelligence and objectives. An actor who probes exclusively for ports associated with industrial control systems has prior knowledge of target type. An actor who skips well-known defensive services (IDS sensors, honeypot-associated ports) has anti-detection intelligence.

Target selection also reveals attacker efficiency. A low-sophistication actor runs broad port sweeps. A high-sophistication actor targets specific ports based on prior intelligence. The ratio of targeted to total probes is a sophistication signal.

### 6.7 Retry and error-handling dimensions

How an actor responds to failure is highly diagnostic. Tool error-handling code is written once and rarely modified because operators focus on success paths, not failure paths. An actor who always retries exactly 3 times before moving on, or who always waits exactly 500ms after a connection refused before the next attempt, is exhibiting a durable behavioral signature.

Retry behavior also distinguishes tool capabilities. A tool with credential stuffing logic retries with credential variations after an authentication failure. A tool without that logic simply moves to the next target. The presence or absence of retry logic narrows the candidate tool set significantly.

---

## 7. Schema Planning

These table definitions are proposed architecture. They must be refined during PR 1 implementation based on actual data shape from the existing schema and practical query requirements. **Do not implement these definitions verbatim** — use them as a design basis.

### 7.1 `behavioral_fingerprints`

Stores one fingerprint per source IP. Recomputed when new events push the IP's event count beyond a threshold or when a configurable recomputation interval is exceeded.

```sql
CREATE TABLE behavioral_fingerprints (
    id                         TEXT PRIMARY KEY,  -- UUID
    source_ip                  TEXT NOT NULL REFERENCES source_ips(ip),
    fingerprint_version        INTEGER NOT NULL DEFAULT 1,  -- schema version for migration safety
    computed_at                TEXT NOT NULL,      -- ISO timestamp of last computation
    event_count_at_computation INTEGER NOT NULL,   -- used to detect when recomputation is needed
    timing_features            TEXT,              -- JSON: inter-probe stats, session stats, time-of-day histogram
    sequence_features          TEXT,              -- JSON: port order, credential order, post-response behavior
    protocol_features          TEXT,              -- JSON: TLS JA3, SSH KEX order, HTTP header order
    credential_features        TEXT,              -- JSON: username patterns, password patterns, mutation types
    target_features            TEXT,              -- JSON: port distribution, service targeting ratios
    tool_signals               TEXT,              -- JSON: detected tool signatures, wordlist overlap %
    confidence                 REAL NOT NULL DEFAULT 0.5,  -- 0.0–1.0; increases with more data
    UNIQUE(source_ip)
);
```

**Design notes:**
- JSON columns for feature categories rather than individual columns: the feature set will evolve; JSON avoids constant schema migrations
- `fingerprint_version` allows the computation logic to change without invalidating stored fingerprints; old fingerprints can be flagged for recomputation
- `confidence` reflects data completeness: a fingerprint computed from 5 events has lower confidence than one computed from 500 events
- One row per IP: when a fingerprint is recomputed, the row is updated in place; historical fingerprints are not retained at this table (change history can be derived from `campaign_observations`)

**Phase 4 simplification — one fingerprint per source IP:**
The `UNIQUE(source_ip)` constraint encodes a deliberate Phase 4 simplification: one behavioral fingerprint per IP, updated in place. This is correct for the majority of observed traffic, where an IP represents a single actor's tool across a campaign window.

The limitation: an IP reused by different actors at different times (VPN exit nodes, cloud NAT gateways, Tor exit relays) will produce a fingerprint that is a blend of both actors' behavior. In Phase 4, this is an acceptable approximation — such IPs typically produce incoherent fingerprints that fail to cluster into any campaign, which is the correct outcome (uncertain data should not produce confident intelligence).

**Anticipated future migration:** Phase 6 or later will introduce temporal segmentation by adding `valid_from` and `valid_until` timestamp columns and relaxing the UNIQUE constraint to `UNIQUE(source_ip, valid_from)`. This allows multiple sequential fingerprints per IP, each covering a distinct observation window. The UNIQUE constraint on `source_ip` should not be enforced at the application level in ways that would make this migration harder — the constraint should live only at the database level where it can be altered cleanly.

### 7.2 `campaigns`

Stores one record per identified campaign. Campaign identity persists across IP rotation, dormancy, and reactivation.

```sql
CREATE TABLE campaigns (
    id                  TEXT PRIMARY KEY,  -- UUID, stable across campaign lifetime
    name                TEXT NOT NULL,     -- auto-generated human-readable name (e.g., "SHADOW-CRANE-7")
    status              TEXT NOT NULL DEFAULT 'active',  -- active / dormant / historical / reactivated
    confidence          REAL NOT NULL DEFAULT 0.5,       -- aggregate confidence across member fingerprints
    first_seen          TEXT NOT NULL,     -- ISO timestamp of first attributed observation
    last_seen           TEXT NOT NULL,     -- ISO timestamp of most recent attributed observation
    dormant_since       TEXT,              -- ISO timestamp when campaign entered dormant state; NULL if active
    reactivation_count  INTEGER NOT NULL DEFAULT 0,
    member_ip_count     INTEGER NOT NULL DEFAULT 0,  -- denormalized; updated on member changes
    attack_tactic_dist  TEXT,             -- JSON: distribution of ATT&CK tactic counts across campaign events
    top_target_ports    TEXT,             -- JSON: top 10 targeted ports by event count
    notes               TEXT,             -- operator-editable free text
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
```

**Design notes:**
- `name` is auto-generated using a two-word scheme (adjective + animal + number) for human communicability. Names are stable once assigned.
- `status` is derived from `last_seen` but stored explicitly for efficient filtering; updated by a maintenance routine, not in real time
- `attack_tactic_dist` and `top_target_ports` are denormalized aggregates for fast dashboard rendering; recomputed on observation addition
- `notes` is the only operator-editable field at this stage; future phases can expand to full annotation
- **No `tags` column on this table.** Tags are stored exclusively in the `campaign_tags` table (Section 7.5). Maintaining a JSON tags column here alongside a normalized tags table would create two authoritative sources for the same data, producing dual-write divergence over time. `campaign_tags` is the single authoritative source; query it directly.

### 7.3 `campaign_members`

Associates source IPs with campaigns with a confidence score.

```sql
CREATE TABLE campaign_members (
    campaign_id  TEXT NOT NULL REFERENCES campaigns(id),
    source_ip    TEXT NOT NULL REFERENCES source_ips(ip),
    confidence   REAL NOT NULL DEFAULT 0.5,  -- similarity score that triggered association
    added_at     TEXT NOT NULL,
    last_active  TEXT NOT NULL,
    PRIMARY KEY (campaign_id, source_ip)
);
```

**Design notes:**
- Many-to-one by design: one IP per campaign. An IP that matches multiple campaigns with similar scores should be placed in the highest-scoring one only (phase 4 simplification; multi-campaign attribution is a Phase 6 capability).
- `confidence` is the fingerprint similarity score that caused this IP to be attributed to this campaign.

### 7.4 `campaign_observations`

Time-series record of each point at which a campaign was observed active. One row per significant activity event for a campaign (defined as: a new IP added, a reactivation, or a configurable event count threshold crossed).

```sql
CREATE TABLE campaign_observations (
    id                  TEXT PRIMARY KEY,  -- UUID
    campaign_id         TEXT NOT NULL REFERENCES campaigns(id),
    source_ip           TEXT NOT NULL,
    observed_at         TEXT NOT NULL,
    event_count         INTEGER NOT NULL,
    is_reactivation     INTEGER NOT NULL DEFAULT 0,  -- boolean (0/1)
    dormancy_gap_days   REAL,                        -- non-null on reactivation rows
    notes               TEXT
);

CREATE INDEX idx_campaign_observations_campaign ON campaign_observations(campaign_id, observed_at);
```

**Design notes:**
- `dormancy_gap_days` is recorded at reactivation time. This field is the primary input for dormancy pattern analysis.
- **`fingerprint_delta` is intentionally absent.** Behavioral delta between observations is a valuable concept but requires a precisely defined computation algorithm before it can be stored reliably. "JSON representing what changed" is not an implementable spec — delta between nested JSON structures has multiple valid representations, and two implementations will produce incompatible results. Once there is a concrete operational use case and a deterministic algorithm, this field should be added in a future PR with a versioned definition. Do not add it speculatively.

### 7.5 `campaign_tags`

The single authoritative source for campaign tags. Structured with provenance tracking to support filtering by source (manual vs. automated). The `campaigns` table does not have a `tags` column — all tag reads and writes go through this table exclusively.

```sql
CREATE TABLE campaign_tags (
    campaign_id  TEXT NOT NULL REFERENCES campaigns(id),
    tag          TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT 'auto',  -- 'auto' or 'manual'
    created_at   TEXT NOT NULL,
    PRIMARY KEY (campaign_id, tag)
);
```

### 7.6 `similarity_vectors` (optional, deferred)

This table is defined here as a future option, not a Phase 4 requirement. If fingerprint similarity search becomes a performance bottleneck (this requires first having enough fingerprints that brute-force comparison is measurably slow — a real production problem, not a theoretical one), a vector column can be added.

```sql
-- Deferred: add only when similarity search performance is a measured problem
CREATE TABLE similarity_vectors (
    source_ip        TEXT PRIMARY KEY REFERENCES source_ips(ip),
    vector           BLOB NOT NULL,  -- serialized float array
    vector_version   INTEGER NOT NULL DEFAULT 1,
    computed_at      TEXT NOT NULL
);
```

Do not add this table in Phase 4. Add it when needed.

---

## 8. Similarity and Uncertainty Model

### 8.1 Fingerprints are similarity-comparable, not hash-comparable

A behavioral fingerprint must support the question "how similar are these two fingerprints?" with a numeric answer. It must not require equality for matching.

An actor who used Nmap 7.91 in March and upgraded to Nmap 7.93 in May will produce different protocol-level signatures. If fingerprint matching requires equality, they will appear as two different actors. If fingerprint matching uses similarity, the small difference in protocol behavior will produce a high similarity score (e.g., 0.94) and the actor will be correctly recognized as the same campaign.

The similarity function in Phase 4 is a weighted sum of per-dimension similarity scores:

```
similarity(f1, f2) = Σ weight_i × dim_similarity(f1.dim_i, f2.dim_i)
```

Where:
- `dim_similarity` for continuous distributions (timing intervals, port frequency) uses statistical distance measures (e.g., Jensen-Shannon divergence, inverted and normalized to [0,1])
- `dim_similarity` for sequences (port probe order, credential order) uses sequence alignment similarity (e.g., normalized edit distance)
- `dim_similarity` for categorical features (protocol preferences, tool signatures) uses set overlap ratios (Jaccard similarity)
- Null dimensions contribute zero to both numerator and denominator — sparse fingerprints do not artificially penalize similarity scores

### 8.2 Confidence thresholds and campaign decision policy

| Similarity score | Decision | Rationale |
|-----------------|----------|-----------|
| ≥ 0.80 | Automatic campaign association | High confidence; the behavioral similarity is strong enough that manual review is not warranted |
| 0.60–0.79 | Flagged as possible match; campaign association with `confidence < 0.80` | Significant similarity but not definitive; shown to operators for review |
| 0.40–0.59 | New campaign created; possible match noted in metadata | Below association threshold; the similarities may be coincidental |
| < 0.40 | New campaign created | No meaningful behavioral overlap |

These thresholds are initial values based on theoretical reasoning. They will need empirical tuning once real data is available. The threshold configuration should be a setting, not a hardcoded constant.

### 8.3 Reactivation uncertainty model

When a dormant campaign receives a new fingerprint match, the reactivation is recorded with a confidence score reflecting:
- The fingerprint similarity to the historical campaign fingerprint (primary signal)
- The dormancy gap duration (very long gaps lower confidence — more could have changed)
- The infrastructure overlap, if any (shared ASN or similar IP range increases confidence)
- The behavioral delta magnitude (large deltas lower confidence)

A reactivation with confidence < 0.60 should be treated as a possible reactivation, not a confirmed one. The operator should review these cases.

### 8.4 Explainability requirement

Every campaign association must be explainable in terms of specific feature dimensions. The system must be able to answer: "Why was this IP attributed to Campaign SHADOW-CRANE-7?" with a response like:

> "Port probe sequence similarity: 0.91. Credential ordering similarity: 0.87. Time-of-day histogram similarity: 0.83. Protocol TLS cipher ordering: 0.79. Overall weighted similarity: 0.85."

This explainability requirement applies even when overall confidence is high. It is the foundation for operator trust in the campaign clustering output. An operator who cannot understand why a match was made cannot act on that match with confidence.

---

## 9. Safety and Legal Boundaries

These are not guidelines. They are hard constraints. Any Phase 4 feature that would require crossing any of these lines must be rejected.

### 9.1 No active outbound operations

LegionTrap is a passive intelligence platform. It observes inbound probes and analyzes them. It does not:
- Initiate connections to any external IP address for any purpose
- Conduct reconnaissance or scanning of any kind
- Query external services in response to inbound events (this includes IP reputation APIs, WHOIS lookups, BGP queries, or any other lookups that would reveal the deployment's existence or trigger outbound connections attributable to the deployment)
- Transmit data about observed attackers to any external service without explicit operator consent

### 9.2 No automated response or blocking

LegionTrap does not modify firewall rules, block IPs, rate-limit connections, or take any action that affects the network environment it is observing. Analysis and action are strictly separated. Intelligence is produced; action decisions belong to the operator.

### 9.3 No deception-to-real-infrastructure pathways

Deceptive services must be isolated from real infrastructure by network controls (firewall rules, separate VLANs, or physical network separation) — not by software logic alone. A software bug in a deceptive service must not create a path to real infrastructure. This constraint must be enforced at the network level before any deception runtime is deployed.

### 9.4 No payload execution

Deceptive services log payloads. They do not execute them, detonate them in sandboxes, or analyze them through external services. Payload analysis belongs to a dedicated sandbox environment, not to an intelligence collection platform.

### 9.5 No individual attribution

Behavioral fingerprinting can attribute activity to a campaign or actor pattern. It must not be used to attempt identification of specific individuals. Attribution to a nation-state, criminal organization, or known threat actor group requires evidence standards beyond what automated fingerprinting can provide and carries legal and reputational risks if wrong.

### 9.6 Data retention

Behavioral fingerprints and campaign records contain aggregated sensitive information. The deployment operator is responsible for establishing a data retention policy appropriate for their jurisdiction. The platform should support configurable retention periods for all intelligence tables. The default retention period should be conservative.

### 9.7 These constraints apply to deception implementations

When deception runtime is implemented in a future phase, all constraints in this section apply to deceptive services. A deceptive service that logs payloads is not an exception to the no-execution rule. A deceptive environment that presents a fake internal network is not an exception to the no-real-infrastructure-pathway rule.

---

## 10. Phase 4 PR Sequencing

Phase 4 is implemented as eight PRs. Each PR is independently reviewable and deployable. No PR should depend on unreleased work from a future PR.

### PR 1 — Schema: behavioral and campaign tables

**Branch:** `feat/phase4-schema`
**Scope:** Alembic migration adding `behavioral_fingerprints`, `campaigns`, `campaign_members`, `campaign_observations`, `campaign_tags` tables. No application logic.

**Exit criteria:**
- `make db-migrate` creates all new tables
- `make db-validate` passes
- All new tables have indexes on their most common query patterns
- Migration is reversible (`make db-rollback` drops new tables cleanly)
- No application code changes in this PR

**Why first:** Schema migrations must be separate from application logic to be safely deployable to existing databases. A migration that bundles application code changes cannot be safely rolled back.

### PR 2 — Event sequence extraction utilities

**Branch:** `feat/phase4-sequence-extraction`
**Scope:** Pure Python utilities (no HTTP, no SQLAlchemy) for extracting behavioral sequences from a list of event dicts. Tests cover sequence ordering, session boundary detection, interval computation.

**Exit criteria:**
- Given a list of event dicts with timestamps and event types, produces ordered session sequences with timing intervals
- Pure functions with no side effects
- Full unit test coverage
- No integration with database or API layer yet

**Why second:** Sequence extraction is the foundation of fingerprint computation. It must be independently testable before being wired into the database layer.

### PR 3 — Behavioral fingerprint generation

**Branch:** `feat/phase4-fingerprints`
**Scope:** Repository method to compute and store behavioral fingerprints from accumulated events for a given source IP. Background computation triggered by a new `POST /api/ingest` completion. Unit tests for fingerprint computation logic; integration tests for fingerprint storage and retrieval.

**Exit criteria:**
- After ingesting events for an IP, a `behavioral_fingerprints` row is created or updated
- Fingerprint fields are populated from available data; sparse fingerprints are valid
- Fingerprint recomputation is triggered when `event_count` increases beyond a threshold
- `GET /api/intelligence/ips/{ip}` response includes a `fingerprint_summary` field (non-breaking addition)

**Why third:** Fingerprints must be generated and validated before campaign clustering can use them.

### PR 4 — Campaign clustering v1

**Branch:** `feat/phase4-campaign-clustering`
**Scope:** Campaign clustering algorithm, similarity function, and the routine that creates/updates campaign records based on new fingerprints. Triggered after fingerprint computation. Integration tests with seeded fingerprint data verifying campaign creation, association, and reactivation detection.

**Exit criteria:**
- Given two fingerprints with known similarity, campaign association produces correct confidence score
- New campaigns are created when no existing campaign meets the similarity threshold
- Dormant campaigns are reactivated when a new matching fingerprint appears
- Reactivation events are recorded in `campaign_observations`
- Clustering is deterministic (same input always produces same output)

**Why fourth:** Depends on stable fingerprint data from PR 3.

### PR 5 — Campaign API endpoints

**Branch:** `feat/phase4-campaign-api`
**Scope:** All campaign API endpoints defined in Section 3.7. Authentication via `require_jwt_or_api_key`. PRIVACY_MODE compliance (IP masking). Integration tests covering auth, empty state, populated state, filtering, and pagination.

**Exit criteria:**
- All endpoints defined in Section 3.7 are functional
- `GET /api/campaigns` paginates correctly at various page sizes
- Filtering by status, tag, and date range works
- IP masking in responses when PRIVACY_MODE is on
- Response schemas are documented in endpoint docstrings

**Why fifth:** Depends on campaign data from PR 4.

### PR 6 — Dashboard campaign visibility

**Branch:** `feat/phase4-dashboard-campaigns`
**Scope:** React component(s) for campaign display: active campaigns list, reactivation alerts, campaign detail view. Follows established dashboard patterns (dark prop, 30s polling, existing api.js helpers).

**Exit criteria:**
- Active campaigns render correctly with member count, date range, and confidence score
- Reactivation alerts are visually distinct from regular campaign entries
- Campaign detail view shows member IPs (masked if PRIVACY_MODE), timeline summary, and tags
- Empty state (no campaigns yet) renders without errors

**Why sixth:** Depends on campaign API from PR 5.

### PR 7 — Export maturity: STIX campaign enrichment

**Branch:** `feat/phase4-stix-campaigns`
**Scope:** Extend `GET /api/exports/stix` to include Campaign SDOs and Relationship SDOs when campaign data is available. Extend `GET /api/exports/attack-navigator` to annotate techniques with campaign context when available. Add unit tests for new STIX object types; add integration tests verifying campaign data appears in exports.

**Exit criteria:**
- When campaign data exists, STIX bundle includes Campaign SDOs
- When campaign data exists, Relationship SDOs link Indicator objects to Campaign objects
- When no campaign data exists, STIX output is identical to current behavior (no regression)
- ATT&CK Navigator layer includes campaign count metadata per technique where available

**Why seventh:** Depends on stable campaign data. Must not be built speculatively before campaign data exists to populate it.

### PR 8 — Phase 4 close-out documentation

**Branch:** `docs/phase4-closeout`
**Scope:** Update ROADMAP.md (Phase 4 marked complete), create PHASE_4_CLOSEOUT.md, update ARCHITECTURE.md and README.md. No application code.

---

## 11. Anti-Complexity Rules

Phase 4 must ship useful capabilities, not architectural aspirations. The following rules exist to prevent scope creep and infrastructure over-engineering.

**No AI or LLM in Phase 4.**
Any PR that adds an AI/LLM dependency is out of scope. This includes classification models, embedding models, and external AI API calls. The campaign clustering algorithm in Phase 4 is deterministic and explainable without AI.

**No graph database.**
Campaign relationships in Phase 4 are representable in relational tables. The relationship between a campaign and its member IPs is a simple many-to-one join. PostgreSQL's recursive CTEs can handle more complex graph queries if they become necessary. Introduce a graph database only when there is a concrete query that cannot be expressed in SQL without unacceptable performance cost.

**No vector database unless benchmarked.**
`similarity_vectors` is defined in the schema section as a deferred option. Do not add a vector database dependency (ChromaDB, Weaviate, Qdrant) unless a benchmark shows that brute-force fingerprint similarity comparison is actually slow at the volumes being processed. At Phase 4 scale (hundreds to low thousands of fingerprints), brute-force comparison in Python is fast enough. Measure first.

**No async worker infrastructure unless task backlog is measured.**
FastAPI `BackgroundTasks` is sufficient for fingerprint computation in Phase 4. Celery, Redis-backed queues, or asyncio workers add significant operational complexity. Do not add them until the fingerprint computation backlog is a measured operational problem.

**No external API calls.**
Fingerprint computation, campaign clustering, and all intelligence operations must work without any external network access. This is both a correctness requirement (no external dependency can block intelligence production) and an operational security requirement (outbound calls from the intelligence pipeline are an information leakage risk).

**No deception runtime implementation.**
The deception doctrine in Section 5 is architectural direction. Do not implement any deception service, decoy surface, or metamorphic infrastructure in Phase 4. Define the architecture; implement in Phase 5 or later.

**No offensive capability.**
This is an absolute constraint with no exceptions. See Section 9.

**Keep the ingestion path synchronous and fast.**
Fingerprint computation and campaign clustering happen asynchronously or in a scheduled maintenance routine. They must never block the `POST /api/ingest` response. If background tasks cannot complete before the next ingest batch, the system should queue them, not slow down ingestion.

---

## 12. Implementation Risk Controls

These controls emerge from a pre-implementation risk review conducted after the blueprint was approved. They do not change what Phase 4 builds — they define how it must be built to remain stable, trustworthy, and migratable.

### 12.1 Fingerprint JSON structure is a versioned API

The JSON schemas for `timing_features`, `sequence_features`, `protocol_features`, `credential_features`, `target_features`, and `tool_signals` must be specified and frozen before PR 3 is merged. The Appendix (Fingerprint Feature Encoding Reference) defines the encoding for each field; that definition is the spec, not a suggestion.

Once fingerprints are stored in production, any change to field names, nesting structure, or data types is a breaking change and requires:
1. Bumping `fingerprint_version`
2. A migration plan defining whether old fingerprints are recomputed lazily, batch-recomputed, or supported in parallel
3. Updates to the similarity function that reads those fields

Treat the fingerprint JSON structure as a public API. Changes are migrations, not refactors.

### 12.2 Thresholds and weights are launch defaults requiring empirical calibration

The similarity weights (20%/35%/25%/10%/10%) and confidence thresholds (0.80/0.60/0.40) have no empirical basis at launch. They are informed starting points that will produce wrong results for some deployment profiles. This is expected and acceptable as long as:

- All thresholds and weights are named constants in `app/core/config.py` or a dedicated constants module — never hardcoded inline
- The system logs enough data per clustering decision that post-hoc threshold calibration is possible from logs alone
- Documentation at deployment time explicitly states these are launch defaults and should be reviewed after the first 30 days of campaign data

**Do not change thresholds or weights after production campaigns are established without re-clustering.** Changing weights retroactively makes new fingerprints incommensurable with historical campaign profiles — existing campaigns were built under different weight distributions. A threshold change must either be accompanied by full re-clustering from raw fingerprints or scoped to future-only associations.

### 12.3 Temporal recency is a required component of campaign clustering

Behavioral similarity alone is not sufficient to associate a new fingerprint with an existing campaign. Two actors separated by years who happened to use similar tooling should not cluster into the same campaign.

The clustering algorithm must include a temporal recency component:

- Fingerprints more than 12 months older than the candidate fingerprint require similarity ≥ 0.90 to trigger automatic association (configurable)
- Fingerprints 6–12 months older require similarity ≥ 0.85 (configurable)
- Fingerprints within 6 months use the standard thresholds from Section 8.2

This temporal decay is applied as a pre-filter or as a threshold modifier — not as a separate similarity dimension. The similarity score measures behavioral match; the temporal component adjusts the association threshold based on how much time has passed.

**Campaign continuity is probabilistic, not absolute.** A reactivation event after a long dormancy gap is a hypothesis with a confidence score, not a certainty. The system must present it as such in the API response and dashboard.

### 12.4 Infrastructure features are informational context, not primary similarity signals

ASN and geographic distribution features in the fingerprint are useful for understanding an actor's infrastructure profile but are poor similarity signals for campaign clustering. Reasons:

- Common cloud providers (AWS, DigitalOcean, OVH) and VPN services mean many unrelated actors share identical ASN profiles
- Geographic features at country level are too coarse to discriminate actors
- Sophisticated actors deliberately diversify infrastructure to evade exactly this signal

**Infrastructure features must be assigned weight < 5% in the clustering similarity function, or excluded entirely.** They should appear in campaign profiles as informational annotations ("this campaign predominantly uses AWS us-east-1 infrastructure") but must not drive association decisions.

This is a correction to Section 3.1's "Infrastructure features" category: those fields belong in the fingerprint as metadata but must be excluded from the weighted similarity computation. The Section 3.2 weight table should be read with this constraint applied — infrastructure features are omitted from the similarity sum entirely.

### 12.5 Fingerprint computation must be asynchronous and deduplicated

Two invariants must be enforced in the BackgroundTask implementation:

**Asynchronous:** Fingerprint computation must never execute in the synchronous request/response cycle of `POST /api/ingest`. The ingest endpoint returns its response immediately after database writes; fingerprint computation runs afterward in a background context.

**Deduplicated:** If a fingerprint computation task for IP `X` is already pending or in progress, a second ingest batch containing IP `X` must not enqueue a second task. The deduplication check must cover both "pending in queue" and "currently executing" states. Without this, concurrent writes from two tasks for the same IP will race for the `behavioral_fingerprints` row, producing a result that reflects whichever task wrote last — which may be the task with fewer events.

The minimum event count gate (see Section 12.6) and the deduplication gate are both mandatory. Implement both before PR 3 is merged.

### 12.6 Sparse fingerprints must not enter campaign clustering

A fingerprint computed from fewer than a minimum event count is statistically unreliable. Sparse fingerprints compared against rich historical campaign fingerprints produce low similarity scores (because null dimensions contribute zero) and get incorrectly classified as new campaigns — even when they represent early activity from a known actor.

**Minimum event count before a fingerprint is submitted to campaign clustering: 10 events (configurable).** Below this threshold:
- The fingerprint is computed and stored (to preserve data)
- The `confidence` field is set to reflect the sparse data
- The fingerprint is flagged as `insufficient_for_clustering` (a boolean field or a confidence threshold check)
- It is excluded from the similarity scan in PR 4's clustering routine

This threshold may need deployment-specific tuning. Start at 10. If actors in your environment typically probe with 3–5 events before moving on, raise it. If actors probe with hundreds of events, lower it.

### 12.7 Explainability doctrine

Every campaign association decision produced by the Phase 4 clustering algorithm must be accompanied by a dimensional explanation. This is not optional for high-confidence matches — it applies to all associations.

The explanation must answer: "Why was IP `X` attributed to Campaign `Y`?"

The response format must include per-dimension similarity scores:

```
timing_similarity: 0.83
sequence_similarity: 0.91
protocol_similarity: 0.79
credential_similarity: 0.87
target_similarity: 0.72
weighted_total: 0.85
threshold_applied: 0.80
decision: automatic_association
```

This explanation is stored alongside the `campaign_members` record or in the `campaign_observations` row for the association event. It is surfaced in the campaign detail API response.

**Deterministic heuristics are preferred over opaque ML decisions in Phase 4.** A deterministic similarity function produces the same output for the same inputs every time and the reasoning is fully inspectable. An ML classifier produces a confidence score with no inspectable reasoning path. Phase 4 uses deterministic functions exclusively. Phase 5 may introduce ML-assisted similarity, but only if the explainability requirement is preserved.

### 12.8 PostgreSQL portability

All Alembic migrations written in Phase 4 must be compatible with PostgreSQL. LegionTrap's SQLite-to-PostgreSQL migration path was anticipated from Phase 1; Phase 4 schema decisions must not create new obstacles to that migration.

Specific patterns to avoid:

| SQLite-only pattern | PostgreSQL-compatible replacement |
|---------------------|----------------------------------|
| `INSERT OR REPLACE INTO` | `INSERT INTO ... ON CONFLICT DO UPDATE SET` |
| `INSERT OR IGNORE INTO` | `INSERT INTO ... ON CONFLICT DO NOTHING` |
| `json_extract(col, '$.field')` in hot-path queries | Extract in application layer; avoid in SQL WHERE clauses |
| `AUTOINCREMENT` keyword | Use `SERIAL` / `BIGSERIAL` in Postgres; use `WITHOUT ROWID` alternative in SQLite if needed |
| `datetime('now')` as column default | Use application-layer timestamp insertion; or accept that defaults differ |

The migration files are the primary concern. Application-layer SQL queries using SQLAlchemy Core will be portable if they avoid dialect-specific constructs. Review each new migration in PR 1 against this table before merging.

---

## 13. Roadmap Update Recommendation

After this blueprint is reviewed and approved, `docs/ROADMAP.md` should be updated as follows:

**Phase 4 section** should be replaced with a reference to this blueprint for detail, with a concise task list reflecting the PR sequence defined in Section 10. The current Phase 4 section in ROADMAP.md is a placeholder written before the blueprint existed; this document supersedes it.

**Phase 5** (currently "First AI Integration") should be updated to note its dependency on Phase 4's behavioral memory layer. Phase 5 AI reasoning is explicitly designed to reason over campaign data, not raw events. This dependency was implicit; it should be explicit.

**Phase 6** (currently "Behavioral Memory and Campaign Tracking") should be revisited. Phase 4 now delivers the foundational behavioral memory and campaign tracking layer. Phase 6 as currently written overlaps with what Phase 4 delivers. After Phase 4 is complete, Phase 6 should be reframed as behavioral memory maturation — deeper fingerprinting, ML-based similarity, multi-campaign attribution — rather than foundational behavioral memory, which Phase 4 establishes.

**The "What Must NOT Happen Too Early" section** in ROADMAP.md should be updated to reflect the Phase 4 constraint: do not build STIX Campaign/Relationship objects, Sigma rules, or MISP packages until campaign clustering is operational. This constraint exists but is not currently explicit in that section.

These roadmap updates should be a separate PR committed after this blueprint is approved and before Phase 4 implementation begins. They should not be committed alongside Phase 4 code.

---

## Appendix: Fingerprint Feature Encoding Reference

This appendix defines how each fingerprint dimension is encoded for storage and comparison. Implementations must follow these conventions for fingerprints to be comparable across computation runs and schema versions.

| Feature | Encoding | Comparison method |
|---------|----------|------------------|
| Inter-probe interval distribution | `{"mean": float, "stddev": float, "p25": float, "p75": float, "p95": float}` | Normalized distribution distance |
| Time-of-day histogram | Array of 24 floats (normalized frequencies, sum = 1.0) | Jensen-Shannon divergence |
| Day-of-week histogram | Array of 7 floats (normalized frequencies, sum = 1.0) | Jensen-Shannon divergence |
| Port probe sequence | Ordered array of integers (top-N ports, N ≤ 50) | Normalized edit distance |
| Credential sequence | Array of `{"username_pattern": str, "password_class": str}` | Sequence similarity over pattern classes |
| TLS cipher ordering | Ordered array of hex cipher suite IDs | Normalized edit distance |
| SSH KEX ordering | Ordered array of algorithm name strings | Normalized edit distance |
| Port frequency distribution | Object of `{port: frequency}` for top-20 ports | Jaccard similarity on top-10 intersection |
| Tool signals | Array of `{tool: str, confidence: float}` | Jaccard on tool name set |
| Credential list overlap | Float 0.0–1.0 (% of tried credentials in known wordlists) | Absolute difference, inverted |

All null fields contribute zero to both numerator and denominator in similarity computation. A fingerprint with 3 of 10 dimensions populated is compared only on the 3 available dimensions, not penalized for the missing 7.

---

*Cross-references: [ROADMAP.md](ROADMAP.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [PHASE_3_CLOSEOUT.md](PHASE_3_CLOSEOUT.md) · [AI_ROADMAP.md](AI_ROADMAP.md)*
