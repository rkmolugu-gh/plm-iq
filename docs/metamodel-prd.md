# PLM-IQ Graph-Based PLM Meta-Model

## 1. Core Model

PLM-IQ models Product Lifecycle Management as a configurable graph.

```text
GRAPH = (N, E, A)

N = Nodes / Vertices (business entities)
E = Edges / Directed connections
A = Edge Annotations / Edge-specific data
```

- Nodes represent PLM business vertices.
- Edges represent meaningful connections.
- Edge annotations represent facts specific to an edge.
- Node attributes represent facts about a vertex.
- Metadata definitions make vertex types, attributes, edge types, and annotations configurable.

The objective is to make BOM, Documents, Requirements, Change Management, Manufacturing, Quality, Suppliers, and AI Impact Analysis graph views and traversals rather than isolated subsystems.

---

## 2. Node Meta-Model

Every node has a common envelope:

```text
Node
├── id
├── tenant_id
├── vertex_type_id
├── number
├── name
├── description
├── lifecycle_state
├── revision_id
├── version
├── status
├── created_by
├── created_at
├── modified_by
├── modified_at
└── configurable attributes
```

### Core node types

| Type | Purpose |
|---|---|
| PRODUCT | Market/customer product |
| ASSEMBLY | Engineering assembly |
| PART | Physical component |
| COMPONENT | Generic reusable component |
| DOCUMENT | Logical document |
| FILE | Physical file/representation |
| REQUIREMENT | Product/system requirement |
| SPECIFICATION | Technical specification |
| CHANGE | Engineering change |
| REVISION | Version of a business vertex |
| SUPPLIER | Supplier/vendor |
| MATERIAL | Material definition |
| MANUFACTURING_ROUTE | Manufacturing process |
| OPERATION | Manufacturing operation |
| WORK_INSTRUCTION | Manufacturing instruction |
| TOOL | Manufacturing/tooling asset |
| QUALITY_RECORD | Quality information |
| TEST | Test definition/execution |
| TEST_RESULT | Test result |
| PROJECT | Development/project context |
| CUSTOMER | Customer |
| CONTRACT | Commercial/legal agreement |
| ISSUE | Problem/nonconformance |
| ECO_TASK | Engineering change task |
| LOCATION | Physical/logical location |

Additional types can be introduced through metadata without changing the graph architecture.

---

## 3. Edge Meta-Model

```text
Edge
├── id
├── tenant_id
├── edge_type_id
├── source_node_id
├── target_node_id
├── status
├── effective_from
├── effective_to
├── created_by
├── created_at
├── modified_at
└── annotations
```

Canonical representation:

```text
SOURCE ──EDGE_TYPE──> TARGET
```

Example:

```text
P-1024 ──USED_IN──> A-100
```

---

## 4. Core Edge Vocabulary

### Product and BOM

```text
PRODUCT ──HAS_ASSEMBLY──────> ASSEMBLY
ASSEMBLY ──HAS_COMPONENT────> PART
ASSEMBLY ──HAS_COMPONENT────> ASSEMBLY
PART ──USED_IN──────────────> ASSEMBLY
PRODUCT ──USES──────────────> PART
PART ──ALTERNATIVE_TO───────> PART
PART ──SUBSTITUTES──────────> PART
PART ──SUPERSEDES───────────> PART
```

`HAS_COMPONENT` is the fundamental BOM edge.

### Documents

```text
PART ──DOCUMENTED_BY────────> DOCUMENT
PRODUCT ──DOCUMENTED_BY────> DOCUMENT
ASSEMBLY ──DOCUMENTED_BY───> DOCUMENT
CHANGE ──DOCUMENTED_BY─────> DOCUMENT
REQUIREMENT ──DOCUMENTED_BY> DOCUMENT

DOCUMENT ──HAS_FILE────────> FILE
DOCUMENT ──HAS_REVISION────> REVISION
```

Specialized edges can serve as virtual folders:

```text
PART ──HAS_DRAWING─────────> DOCUMENT
PART ──HAS_CAD─────────────> DOCUMENT
PART ──HAS_SPECIFICATION───> DOCUMENT
PART ──HAS_TEST_REPORT─────> DOCUMENT
PART ──HAS_CERTIFICATE─────> DOCUMENT
```

### Requirements

```text
PRODUCT ──HAS_REQUIREMENT──> REQUIREMENT
PART ──SATISFIES───────────> REQUIREMENT
ASSEMBLY ──SATISFIES───────> REQUIREMENT
REQUIREMENT ──DERIVED_FROM─> REQUIREMENT
REQUIREMENT ──VERIFIED_BY──> TEST
REQUIREMENT ──ALLOCATED_TO─> PART
```

### Engineering Change

Use a generic `CHANGE` vertex rather than separate ECR/ECO/ECN schemas.

```text
CHANGE ──AFFECTS───────────> PART
CHANGE ──AFFECTS───────────> ASSEMBLY
CHANGE ──AFFECTS───────────> DOCUMENT
CHANGE ──AFFECTS───────────> REQUIREMENT

CHANGE ──REPLACES──────────> REVISION
CHANGE ──CREATES───────────> REVISION
CHANGE ──APPROVED_BY───────> USER
CHANGE ──ASSIGNED_TO───────> USER
CHANGE ──HAS_TASK──────────> ECO_TASK
CHANGE ──SUPPORTED_BY─────> DOCUMENT
CHANGE ──RESULTS_IN────────> REVISION
```

### Revision

```text
PART ──HAS_REVISION────────> REVISION
REVISION ──PREVIOUS_VERSION> REVISION
REVISION ──SUPERSEDES──────> REVISION
REVISION ──REPRESENTS──────> PART
```

### Manufacturing

```text
PART ──MANUFACTURED_BY─────> MANUFACTURING_ROUTE
MANUFACTURING_ROUTE ──HAS_OPERATION──> OPERATION
OPERATION ──USES_TOOL──────> TOOL
OPERATION ──USES_MATERIAL──> MATERIAL
OPERATION ──DOCUMENTED_BY──> WORK_INSTRUCTION
PART ──REQUIRES_MATERIAL───> MATERIAL
```

### Supplier

```text
PART ──SUPPLIED_BY─────────> SUPPLIER
SUPPLIER ──SUPPLIES────────> PART
SUPPLIER ──HAS_CONTRACT────> CONTRACT
PART ──HAS_SUPPLIER_PART───> PART
```

### Quality

```text
PART ──HAS_ISSUE───────────> ISSUE
PART ──TESTED_BY───────────> TEST
TEST ──PRODUCES────────────> TEST_RESULT
TEST_RESULT ──EVIDENCE_FOR─> REQUIREMENT
ISSUE ──AFFECTS────────────> PART
ISSUE ──RESOLVED_BY────────> CHANGE
```

### Project and Customer

```text
PROJECT ──DEVELOPS─────────> PRODUCT
PROJECT ──CONTAINS─────────> CHANGE
CUSTOMER ──OWNS────────────> PRODUCT
CUSTOMER ──HAS_CONTRACT────> CONTRACT
PRODUCT ──DELIVERED_TO─────> CUSTOMER
```

---

## 5. Edge Annotations

An annotation describes the edge itself, not either endpoint.

```text
EdgeAnnotation
├── key
├── value
├── datatype
├── unit
├── source
├── confidence
├── effective_from
├── effective_to
└── note
```

Example:

```text
A-100 ──HAS_COMPONENT──> P-1024

quantity = 2
find_number = "20"
reference_designator = "BRK-01"
unit = "EA"
effectivity = "2026-01-01"
note = "Used on left and right mounting positions"
```

Supplier example:

```text
P-1024 ──SUPPLIED_BY──> SUP-22

supplier_part_number = "MB-8831"
unit_cost = 14.20
currency = "USD"
lead_time_days = 21
minimum_order_qty = 100
preferred = true
```

### Edge note

Standardize a human-readable annotation:

```text
note
```

Example:

```text
P-1024 ──HAS_DRAWING──> D-1024

note = "Defines released mounting geometry."
```

Do not overload `note`; structured business properties should remain separate annotations.

---

## 6. Effectivity

Important edges should optionally support temporal effectivity:

```text
effective_from
effective_to
```

Advanced effectivity can use:

```text
effectivity_type
effectivity_value
```

Possible types:

```text
DATE_RANGE
SERIAL_RANGE
LOT
CONFIGURATION
MODEL_YEAR
```

Example:

```text
P-1024 ──USED_IN──> A-100

effective_from = 2026-01-01
effective_to = null
```

---

## 7. Provenance and Confidence

Important edges should be traceable:

```text
source
source_type
source_id
confidence
created_by
created_at
```

Example:

```text
P-1024 ──SATISFIES──> REQ-182

source_type = "engineering_analysis"
source_id = "EA-44"
confidence = 0.97
```

This allows PLM-IQ to distinguish:

- verified edges
- imported edges
- manually authored edges
- AI-inferred edges

AI-generated edges must carry provenance and confidence and must not silently become authoritative.

---

## 8. Edge Families

| Family | Examples |
|---|---|
| Structure | HAS_COMPONENT, PART_OF |
| Traceability | SATISFIES, VERIFIED_BY, DOCUMENTED_BY |
| Lifecycle | SUPERSEDES, REPLACES, AFFECTS |
| Commercial | SUPPLIED_BY, OWNED_BY |
| Manufacturing | MANUFACTURED_BY, USES_TOOL |
| Semantic | RELATED_TO, ALTERNATIVE_TO, DERIVED_FROM |

---

## 9. Configurable Vertex Types

Vertex types are metadata rather than hard-coded schemas.

```text
vertex_type
------------
id
tenant_id
name
label
description
parent_type_id
icon
is_system
version
effective_from
effective_to
```

Example:

```text
PART
 |
 +-- MECHANICAL_PART
 |
 +-- ELECTRICAL_PART
```

Vertex types can inherit attributes.

---

## 10. Configurable Attribute Definitions

```text
attribute_definition
--------------------
id
tenant_id
vertex_type_id
name
label
description
data_type
required
default_value
multi_value
searchable
filterable
sortable
unit
validation_rule
display_order
version
effective_from
effective_to
```

Supported types:

```text
STRING
TEXT
INTEGER
DECIMAL
BOOLEAN
DATE
DATETIME
ENUM
REFERENCE
MULTI_REFERENCE
JSON
```

Example:

```text
PART

material        STRING
weight          DECIMAL
make_buy        ENUM
criticality     ENUM
coating_type    STRING
```

---

## 11. Node Attribute Storage

Keep stable system fields structured:

```text
node
----
id
tenant_id
vertex_type_id
number
name
lifecycle_state
revision_id
created_at
modified_at
```

Store configurable attributes separately:

```text
node_attribute
--------------
node_id
attribute_definition_id
value_string
value_number
value_boolean
value_date
value_json
```

Only the appropriate value column is populated for the attribute data type.

This is a hybrid model:

```text
Stable PLM system fields
        +
Configurable domain attributes
```

---

## 12. Configurable Edge Types

```text
edge_type
---------
id
tenant_id
name
label
description
source_vertex_type_id
target_vertex_type_id
inverse_name
edge_family
cardinality
is_system
is_virtual_folder
virtual_folder_label
virtual_folder_icon
display_order
version
effective_from
effective_to
```

Example:

```text
HAS_DRAWING

source = PART
target = DOCUMENT
inverse = DRAWING_FOR
edge_family = TRACEABILITY

is_virtual_folder = true
virtual_folder_label = "Drawings"
virtual_folder_icon = "drawing"
```

---

## 13. Configurable Edge Annotations

```text
edge_attribute_definition
-------------------------
id
tenant_id
edge_type_id
name
label
data_type
required
default_value
multi_value
searchable
filterable
unit
validation_rule
display_order
```

Example:

```text
HAS_COMPONENT

quantity
find_number
reference_designator
unit
effectivity
note
```

---

## 14. Virtual Folders

Virtual folders are UI views generated from selected edge types. They are not physical containment.

```text
edge_type
    |
    +-- is_virtual_folder = true
    |
    v
Virtual Document View
```

Example:

```text
P-1024
 |
 +-- HAS_CAD -------------> CAD
 |
 +-- HAS_DRAWING ---------> Drawings
 |
 +-- HAS_SPECIFICATION ---> Specifications
 |
 +-- HAS_TEST_REPORT -----> Test Reports
 |
 +-- HAS_CERTIFICATE -----> Certificates
```

The same document can appear in multiple views without duplication.

---

## 15. Graph-Driven UI

Every graph node has a canonical workspace.

Example:

```text
/vertices/PART/P-1024
```

The workspace can dynamically expose sections based on configured edge types:

```text
P-1024 Mounting Bracket

Connected Vertices
-----------------
Drawings          4
Specifications    3
Requirements      3
Manufacturing     2
Suppliers         1
Changes           2
Used In           7
```

The user sees familiar PLM concepts; the graph provides the underlying structure.

---

## 16. Graph-Driven PLM Capabilities

| PLM capability | Graph implementation |
|---|---|
| BOM | HAS_COMPONENT traversal |
| Where Used | Reverse HAS_COMPONENT traversal |
| Documents | DOCUMENTED_BY, HAS_DRAWING, etc. |
| Virtual folders | Selected edge types |
| Requirements traceability | SATISFIES, VERIFIED_BY, DERIVED_FROM |
| Change impact | AFFECTS + downstream traversal |
| Supplier management | SUPPLIED_BY |
| Manufacturing | MANUFACTURED_BY, HAS_OPERATION |
| Quality | HAS_ISSUE, TESTED_BY |
| Product genealogy | Graph traversal |
| Configuration management | Revision/effectivity |
| AI Impact Analysis | Multi-hop graph traversal |
| AI Search | Graph + text/vector retrieval |
| AI Assistant | Graph-aware tools |

---

## 17. AI Graph Tools

AI agents should operate through controlled graph tools rather than unrestricted database access.

Examples:

```text
find_related_objects(vertex_id, edge_type, depth)
find_downstream_impact(vertex_id)
find_upstream_dependencies(vertex_id)
find_where_used(part_id)
find_documents(vertex_id)
find_requirements(vertex_id)
find_changes(vertex_id)
trace_requirement(requirement_id)
```

Example:

```text
EC-1042
   |
   +--AFFECTS--> P-1024
                    |
                    +--USED_IN--> A-100
                    |
                    +--SATISFIES--> REQ-182
```

The agent can report:

```text
Directly affected:
P-1024

Potential downstream impact:
A-100
REQ-182

Evidence:
EC-1042 -> AFFECTS -> P-1024
P-1024 -> USED_IN -> A-100
P-1024 -> SATISFIES -> REQ-182
```

---

## 18. Configuration Versioning

The following metadata must be versioned:

```text
VERTEX_TYPE
ATTRIBUTE_DEFINITION
EDGE_TYPE
EDGE_ATTRIBUTE_DEFINITION
```

Use:

```text
version
effective_from
effective_to
```

Do not destructively change historical definitions.

If a `PART.material` attribute changes from `STRING` to `ENUM`, historical data must retain the semantics applicable at the time it was created.

---

## 19. Tenant Customization

PLM-IQ should provide a standard meta-model plus tenant-specific extensions.

```text
PLM-IQ STANDARD
        |
        +-- PART
        +-- PRODUCT
        +-- DOCUMENT
        +-- REQUIREMENT
        +-- CHANGE
        +-- SUPPLIER
        |
        +-------------------+
                            |
                       TENANT EXTENSION
                            |
                 +----------+----------+
                 |                     |
             Attributes            Edge Types
                 |                     |
          Certification          HAS_CERTIFICATION
          Criticality            APPROVED_BY
          Customer Code          OWNED_BY
```

Tenant-specific extensions must not require application-code changes.

---

## 20. Recommended Logical Services

```text
Meta-Model Service
    |
    +-- Vertex Types
    +-- Attribute Definitions
    +-- Edge Types
    +-- Edge Attribute Definitions
    +-- Configuration Versioning

Graph Service
    |
    +-- Nodes
    +-- Edges
    +-- Traversals
    +-- Effectivity
    +-- Provenance

Vertex Service
    |
    +-- CRUD
    +-- Lifecycle
    +-- Revision

Document Service
    |
    +-- Documents
    +-- Revisions
    +-- Files
    +-- Object Storage

Query Service
    |
    +-- Graph Queries
    +-- Search
    +-- Filters

AI / Agent Layer
    |
    +-- Graph Tools
    +-- Search Tools
    +-- Impact Analysis
    +-- Assistant
```

---

## 21. Canonical Example

```text
PRODUCT
A-100
 |
 +--HAS_COMPONENT--------> P-1024
 |                           |
 |                           +--HAS_DRAWING-------> D-1024
 |                           |
 |                           +--SATISFIES--------> REQ-182
 |                           |
 |                           +--SUPPLIED_BY------> SUP-22
 |                           |
 |                           +--MANUFACTURED_BY-> ROUTE-55
 |                           |
 |                           +--AFFECTED_BY-----> EC-1042
 |
 +--HAS_COMPONENT--------> P-1031
```

BOM annotation:

```text
A-100 --HAS_COMPONENT--> P-1024

quantity = 2
find_number = "20"
unit = "EA"
note = "LH/RH mounting"
```

Supplier annotation:

```text
P-1024 --SUPPLIED_BY--> SUP-22

supplier_part_number = "MB-8831"
unit_cost = 14.20
currency = "USD"
lead_time_days = 21
preferred = true
```

Change provenance:

```text
P-1024 --AFFECTED_BY--> EC-1042

source_type = "engineering_change"
source_id = "EC-1042"
confidence = 1.0
note = "Mounting hole diameter changed"
```

---

## 22. Design Rules

1. Business vertices are nodes.
2. Business connections are edges.
3. Edge-specific data belongs to edge annotations.
4. Vertex-specific data belongs to node attributes.
5. Stable system fields remain structured.
6. Domain-specific attributes are configurable.
7. Edge types are configurable.
8. Edge annotation definitions are configurable.
9. Virtual folders are views, never physical containment.
10. Documents can participate in multiple edges.
11. Every node has one canonical identity.
12. Effectivity is supported for lifecycle-sensitive edges.
13. Important edges carry provenance.
14. AI-inferred edges carry confidence and provenance.
15. Meta-model configuration is versioned.
16. Tenant extensions require no application-code changes.
17. Graph traversal respects tenant and authorization boundaries.
18. AI agents access the graph through controlled tools.

---

## 23. Target Architecture

```text
                         PLM-IQ
                           |
                    META-MODEL
                           |
          +----------------+----------------+
          |                                 |
    VERTEX TYPES                       EDGE TYPES
          |                                 |
    ATTRIBUTES                        ANNOTATIONS
          |                                 |
          +----------------+----------------+
                           |
                         GRAPH
                           |
        +------------------+------------------+
        |                  |                  |
      VERTICES           EDGES      DOCUMENTS
        |                  |                  |
        +------------------+------------------+
                           |
                     GRAPH QUERIES
                           |
          +----------------+----------------+
          |                |                |
          UI             SEARCH             AI
          |                |                |
     PLM Views        Semantic Search      Agents
          |
   +------+------+------+------+
   |      |      |      |      |
  BOM  Docs  Change  Req  Manufacturing
```

## 24. Implementation Principle

The graph meta-model is the canonical semantic layer of PLM-IQ.

Modules should be implemented as **views, workflows, queries, and traversals over the graph**, not as independent edge systems.

The next implementation artifact should translate this meta-model into a concrete PostgreSQL/SQLite schema for:

```text
node
edge
vertex_type
attribute_definition
node_attribute
edge_type
edge_attribute_definition
edge_annotation
```

while preserving the graph semantics defined in this document.

---

# 26. Industry Profiles

PLM-IQ should support multiple PLM solutions without creating separate products or forks of the core graph model.

Use:

```text
PLM-IQ CORE
    +
INDUSTRY PROFILE
    +
TENANT EXTENSION
    =
CUSTOM PLM SOLUTION
```

Profiles can define vertex types, attributes, edge types, edge annotations, lifecycle definitions, workflows, document views, validation rules, UI views, and AI agent behavior.

```text
                    PLM-IQ PLATFORM
                          |
                    PLM CORE PROFILE
                          |
              +-----------+-----------+
              |                       |
       DISCRETE PLM PROFILE      PHARMA PLM PROFILE
              |                       |
       Automotive / Aerospace    Pharma / Biotech
              |                       |
        Tenant Extensions         Tenant Extensions
```

---

# 27. Profile Inheritance

Profiles should support inheritance.

```text
PLM_CORE
   |
   +-- DISCRETE_MANUFACTURING
   |       |
   |       +-- AUTOMOTIVE
   |       +-- AEROSPACE
   |       +-- INDUSTRIAL
   |
   +-- LIFE_SCIENCES
           |
           +-- PHARMA
           +-- BIOTECH
           +-- MEDICAL_DEVICE
```

A child profile inherits the parent profile and adds or overrides definitions.

---

# 28. Industry-Specific Graph Semantics

The same graph engine can support very different industries.

## Discrete PLM

```text
ASSEMBLY ──HAS_COMPONENT────> PART
PART ──MANUFACTURED_BY──────> MANUFACTURING_ROUTE
PART ──SUPPLIED_BY──────────> SUPPLIER
PART ──DOCUMENTED_BY────────> DOCUMENT
PART ──SATISFIES────────────> REQUIREMENT
```

## Pharma PLM

```text
DRUG_PRODUCT ──HAS_FORMULATION──────────> FORMULATION
FORMULATION ──CONTAINS──────────────────> ACTIVE_INGREDIENT
FORMULATION ──CONTAINS──────────────────> EXCIPIENT
BATCH ──MANUFACTURED_FROM───────────────> FORMULATION
DRUG_PRODUCT ──HAS_STABILITY_STUDY──────> STABILITY_STUDY
DRUG_PRODUCT ──HAS_REGULATORY_SUBMISSION> REGULATORY_SUBMISSION
```

The graph engine remains the same. Only domain metadata and rules change.

---

# 29. Profile-Aware AI Agents

AI agents should be generic reasoning engines whose behavior is specialized by the active PLM profile.

```text
                         USER
                           |
                           v
                     AI ASSISTANT
                           |
                           v
                    AGENT HARNESS
                           |
             +-------------+-------------+
             |             |             |
          Tenant       PLM Profile   Permissions
          Context          |
                            v
                      Agent Profile
                            |
                 +----------+----------+
                 |          |          |
             Traversal   Priority     Risk
               Rules      Rules       Rules
                 |          |          |
                 +----------+----------+
                            |
                            v
                     GENERIC AGENT
                            |
                       Graph Tools
                            |
                            v
                        PLM GRAPH
```

The agent should not contain hard-coded industry logic such as:

```text
if pharma:
    traverse MANUFACTURED_FROM
```

Instead, the active profile supplies this knowledge declaratively.

---

# 30. Agent Profile

Each agent can have profile-specific configuration.

Example:

```yaml
profile: pharma
agent: IMPACT_ANALYSIS

important_edges:

  - edge: MANUFACTURED_FROM
    priority: critical

  - edge: HAS_REGULATORY_SUBMISSION
    priority: critical

  - edge: SATISFIES
    priority: high

  - edge: VERIFIED_BY
    priority: high

  - edge: HAS_STABILITY_STUDY
    priority: high

traversal_rules:

  - from: BATCH
    edge: MANUFACTURED_FROM
    to: FORMULATION
    depth: 1

  - from: FORMULATION
    edge: CONTAINS
    to: ACTIVE_INGREDIENT
    depth: 2

impact_rules:

  - changed: ACTIVE_INGREDIENT
    affects:
      - FORMULATION
      - BATCH
      - SPECIFICATION
      - REGULATORY_SUBMISSION

risk_rules:

  - vertex_type: REGULATORY_SUBMISSION
    risk: HIGH
```

The exact storage format may be YAML, JSON, or normalized metadata tables. The semantic model is what matters.

---

# 31. Generic Impact Analysis Agent

The Impact Analysis Agent provides generic capabilities:

```text
Impact Analysis Agent
    |
    +-- identify affected vertices
    +-- traverse edges
    +-- evaluate lifecycle
    +-- collect evidence
    +-- rank impact
    +-- calculate risk
    +-- explain findings
```

The agent asks the active profile:

```text
Which edges matter?
How far should I traverse?
Which vertex types are high risk?
Which edges are critical?
How should findings be ranked?
What evidence is required?
```

---

# 32. Example: Pharma Impact Analysis

User:

```text
"Analyze the impact of changing API-102."
```

Graph:

```text
API-102
   |
   v
FORM-44
   |
   +--MANUFACTURED_AS--> BATCH-2026-001
   |
   +--HAS_SPECIFICATION-> SPEC-44
   |
   +--USED_IN-----------> DRUG-100
                              |
                              +--HAS_REGULATORY_SUBMISSION--> SUB-55
```

The Pharma profile tells the generic agent that the following edges are important:

```text
CONTAINS
MANUFACTURED_FROM
HAS_SPECIFICATION
USED_IN
HAS_REGULATORY_SUBMISSION
HAS_STABILITY_STUDY
```

The agent traverses those paths and produces:

```text
Impact
----------------------------

Critical
REGULATORY_SUBMISSION SUB-55
FORMULATION FORM-44

High
BATCH-2026-001
SPEC-44

Medium
STABILITY-STUDY-22
```

Each result should include graph evidence:

```text
API-102
  -> CONTAINS
FORM-44
  -> USED_IN
DRUG-100
  -> HAS_REGULATORY_SUBMISSION
SUB-55
```

---

# 33. Example: Discrete Impact Analysis

The same generic agent receives:

```text
"Analyze the impact of changing P-1024."
```

Discrete profile rules may prioritize:

```text
USED_IN
SATISFIES
MANUFACTURED_BY
DOCUMENTED_BY
SUPPLIED_BY
```

Graph:

```text
P-1024
   |
   +--USED_IN----------> A-100
   |
   +--SATISFIES--------> REQ-182
   |
   +--MANUFACTURED_BY--> ROUTE-55
   |
   +--DOCUMENTED_BY---> D-1024
```

The agent uses the same reasoning engine but follows the Discrete profile's semantics.

---

# 34. Edge Priority

Not every graph edge has equal impact significance.

Profile rules can assign priority:

```yaml
edge_priorities:

  AFFECTS:
    priority: 100

  HAS_REGULATORY_SUBMISSION:
    priority: 100

  SATISFIES:
    priority: 90

  VERIFIED_BY:
    priority: 90

  DOCUMENTED_BY:
    priority: 40

  RELATED_TO:
    priority: 10
```

This prevents an agent from presenting hundreds of weakly related vertices as equally important.

---

# 35. Traversal Rules

Profiles should constrain graph traversal.

Example:

```yaml
traversal:

  BATCH:
    MANUFACTURED_FROM: 1
    RELATED_TO: 0

  FORMULATION:
    CONTAINS: 2

  PRODUCT:
    HAS_REGULATORY_SUBMISSION: 2
```

This creates bounded, explainable graph reasoning. The agent should not blindly traverse the entire graph.

---

# 36. Risk Semantics

Profiles can define domain-specific risk.

Example:

```yaml
risk_rules:

  - vertex_type: REGULATORY_SUBMISSION
    risk: CRITICAL

  - vertex_type: STABILITY_STUDY
    risk: HIGH

  - vertex_type: DOCUMENT
    risk: MEDIUM
```

Discrete PLM could instead define:

```yaml
risk_rules:

  - vertex_type: SAFETY_CRITICAL_PART
    risk: CRITICAL

  - vertex_type: PRODUCT
    risk: HIGH

  - vertex_type: DRAWING
    risk: MEDIUM
```

Risk should be configuration, not hard-coded agent logic.

---

# 37. Profile-Aware AI Search

The same profile mechanism should be used by AI Search.

Generic search:

```text
"everything related to API-102"
```

Core retrieval finds graph neighbors and semantic matches.

The Pharma profile organizes the result:

```text
API-102

Direct
  FORM-44

Manufacturing
  BATCH-2026-001

Quality
  SPEC-44
  STABILITY-22

Regulatory
  SUB-55
```

The result is both semantically relevant and domain-aware.

---

# 38. Profile-Aware AI Assistant

The AI Assistant uses the same profile configuration.

```text
User:
"What could be affected if this API changes?"
```

Processing:

```text
Agent Harness
    |
    +-- identifies tenant
    +-- identifies active profile = PHARMA
    +-- loads permissions
    +-- loads agent configuration
    +-- loads traversal rules
    |
    v
Impact Analysis Agent
    |
    v
Graph Tools
    |
    v
PLM Graph
```

The assistant does not need a separate Pharma codebase.

---

# 39. Agent Harness Responsibilities

The Agent Harness is the control boundary.

It should:

1. Identify the tenant.
2. Identify the active PLM profile.
3. Load applicable agent configuration.
4. Load traversal rules.
5. Load risk and priority rules.
6. Apply authorization.
7. Apply tenant isolation.
8. Enforce maximum traversal depth.
9. Select permitted graph tools.
10. Record agent actions and evidence.
11. Prevent unauthorized graph access.
12. Return structured evidence to the assistant.

The generic agent supplies reasoning; the harness supplies constraints and context.

---

# 40. Declarative Agent Configuration

Do not put industry-specific behavior in application code.

Prefer metadata:

```text
agent_rule
----------

profile
agent
edge_type
source_vertex_type
target_vertex_type
priority
max_depth
risk_level
enabled
```

Example:

```text
profile = PHARMA
agent = IMPACT_ANALYSIS
edge_type = MANUFACTURED_FROM
priority = 90
max_depth = 2
risk_level = HIGH
enabled = true
```

This makes agent behavior configurable without changing the agent implementation.

---

# 41. Agent Profile Hierarchy

Agents can be specialized through inheritance:

```text
CORE AGENTS
    |
    +-- Impact Analysis
    +-- Change Analysis
    +-- Document Assistant
    +-- Requirement Traceability
    +-- BOM Assistant
    +-- Supplier Analysis
    +-- Compliance Assistant
    |
    +------------------------------+
                                   |
                        Industry Profiles
                                   |
              +--------------------+--------------------+
              |                    |                    |
          DISCRETE              PHARMA             MEDICAL DEVICE
              |                    |                    |
          BOM/CAD              Batches              UDI
          Suppliers            Regulatory           Risk
          Manufacturing        Stability            Design Controls
          Quality              Formulation           Verification
```

The goal is:

```text
ONE reasoning engine
+
DOMAIN KNOWLEDGE CONFIGURATION
+
GRAPH
=
PROFILE-AWARE AI
```

---

# 42. AI Agent Tool Boundary

Agents should interact with the graph through controlled tools.

```text
find_related_objects(vertex_id, edge_type, depth)
find_downstream_impact(vertex_id)
find_upstream_dependencies(vertex_id)
find_where_used(vertex_id)
find_documents(vertex_id)
find_requirements(vertex_id)
find_changes(vertex_id)
trace_requirement(requirement_id)
find_effectivity(vertex_id)
get_edge_evidence(edge_id)
```

The profile determines which tools and traversals are relevant.

---

# 43. Profile-Aware Agent Architecture

```text
                         USER
                           |
                           v
                     AI ASSISTANT
                           |
                           v
                    AGENT HARNESS
                           |
        +------------------+------------------+
        |                  |                  |
      TENANT          PLM PROFILE       PERMISSIONS
        |                  |
        |                  v
        |            AGENT PROFILE
        |                  |
        |        +---------+---------+
        |        |         |         |
        |    Traversal  Priority    Risk
        |      Rules      Rules     Rules
        |        |         |         |
        +--------+---------+---------+
                           |
                           v
                    GENERIC AGENT
                           |
                       GRAPH TOOLS
                           |
                           v
                       PLM GRAPH
```

---

# 44. Strategic Principle

Separate four concerns:

```text
GRAPH
What exists and how things are connected.

PROFILE
What those connections mean in a particular industry.

AGENT
How to reason over the information.

HARNESS
What the agent is allowed and expected to do.
```

Therefore:

```text
                 GRAPH
                   |
             Facts / Structure
                   |
                   v
                PROFILE
                   |
       Domain Meaning / Priority
                   |
                   v
                 AGENT
                   |
             Reasoning / Planning
                   |
                   v
                HARNESS
                   |
        Security / Controls / Tools
                   |
                   v
              AI ASSISTANT
                   |
                   v
                  USER
```

This allows PLM-IQ to support Discrete PLM, Pharma PLM, Medical Device PLM, Aerospace PLM, and future domains without creating separate agent implementations or separate graph engines.


---

# 45. Workflow Meta-Model

Workflows sit one layer above the graph and operate on graph nodes, edges, lifecycle state, and graph-based conditions.

A workflow is a declarative lifecycle process, not a database operation.

```text
                 PLM PROFILE
                      |
        +-------------+-------------+
        |             |             |
      Vertices       Edges       Workflows
        |             |             |
        +-------------+-------------+
                      |
                 PLM RUNTIME
                      |
          +-----------+-----------+
          |                       |
        GRAPH                 WORKFLOW
          |                       |
       Part P-1024             Release
```

The workflow engine remains generic. The profile supplies the PLM-specific meaning.

---

# 46. Workflow Definition

A workflow should define:

```text
Workflow
├── id
├── name
├── vertex_type
├── trigger
├── states
├── stages
├── conditions
├── assignments
├── approvals
├── actions
└── transitions
```

Example:

```yaml
workflows:

  - id: part_release
    name: Release Part
    vertex_type: part

    trigger:
      action: submit_for_release

    states:
      - DRAFT
      - IN_REVIEW
      - RELEASED

    stages:

      - id: engineering_review
        name: Engineering Review
        type: approval

        assignee:
          type: role
          value: ENGINEERING_REVIEWER

        approvals_required: 1

        entry_conditions:

          - type: lifecycle
            state: DRAFT

          - type: graph
            query: release_readiness

        on_approve:
          transition_to: RELEASED

        on_reject:
          transition_to: DRAFT
```

---

# 47. Graph-Based Workflow Conditions

Workflow conditions should be graph queries rather than hard-coded application logic.

Do not implement:

```python
if no_documents:
    reject()
```

Instead define a reusable query:

```yaml
queries:

  - id: release_readiness

    from: PART

    conditions:

      - lifecycle_state: DRAFT

    required_edges:

      - edge: HAS_DRAWING
        min_count: 1

      - edge: DOCUMENTED_BY
        min_count: 1

      - edge: SATISFIES
        min_count: 1

    child_conditions:

      - edge: HAS_COMPONENT
        target:
          lifecycle_state: RELEASED
```

The workflow invokes:

```text
release_readiness(P-1024)
```

and receives structured results:

```json
{
  "ready": false,
  "failures": [
    {
      "rule": "HAS_DRAWING",
      "message": "Released part requires a drawing"
    },
    {
      "rule": "HAS_COMPONENT",
      "message": "P-1031 is still in DRAFT"
    }
  ]
}
```

---

# 48. Workflow State and Graph State

The workflow operates on:

```text
Node State
    +
Graph State
    +
Workflow State
```

Example:

```text
P-1024
lifecycle_state = DRAFT

Graph:
  HAS_DRAWING -> D-1024
  HAS_COMPONENT -> P-1031
  SATISFIES -> REQ-182

Workflow:
  current_stage = ENGINEERING_REVIEW
  approval_status = PENDING
```

A release transition is permitted only when the workflow conditions evaluate successfully.

---

# 49. Recursive Graph Conditions

Workflows can traverse the graph recursively.

Example:

> A part cannot be released if any descendant component is unreleased.

```yaml
- id: all_components_released

  query:
    from: PART
    id: "$vertex.id"

    traverse:
      edge: HAS_COMPONENT
      direction: outgoing
      recursive: true

    where:
      lifecycle_state:
        not_equals: RELEASED
```

Example:

```text
P-1024
   |
   +-- P-1031 RELEASED       ✓
   +-- P-1032 RELEASED       ✓
   +-- P-1033 DRAFT          ✗
```

The workflow blocks the release.

---

# 50. Workflow Actions

Workflow actions can operate on the graph and lifecycle state.

```yaml
actions:

  - type: create_edge
    edge: APPROVED_BY
    source: "$vertex.id"
    target: "$approval.user_id"

  - type: create_edge
    edge: RESULTS_IN
    source: "$change.id"
    target: "$revision.id"

  - type: transition_lifecycle
    vertex: "$vertex.id"
    state: RELEASED

  - type: create_revision
    vertex: "$vertex.id"

  - type: notify
    role: ENGINEERING_REVIEWER
```

Workflow execution should therefore create an auditable graph history.

---

# 51. Workflow Evidence

Every significant workflow decision should produce evidence.

```text
P-1024
  |
  +-- APPROVED_BY --> USER-42
  |
  +-- RESULTS_IN --> REV-C
  |
  +-- RELEASED_BY_WORKFLOW --> PART_RELEASE
```

Workflow execution should retain:

```text
workflow_id
workflow_instance_id
vertex_id
stage_id
action
actor
timestamp
decision
evidence
```

This is important for auditability and AI explanations.

---

# 52. Profile-Specific Workflows

The same workflow engine can support different industries.

## Discrete PLM

```text
PART
  |
  v
Engineering Review
  |
  v
Drawing Check
  |
  v
BOM Check
  |
  v
Approval
  |
  v
RELEASED
```

## Pharma PLM

```text
FORMULATION
  |
  v
Scientific Review
  |
  v
Quality Review
  |
  v
Stability Check
  |
  v
Regulatory Review
  |
  v
Approval
  |
  v
RELEASED
```

Same runtime engine. Different profile definitions.

---

# 53. AI-Assisted Workflows

AI can participate in workflow activities without replacing authorization controls.

```text
Part Release
      |
      +-- Graph Validation
      +-- AI Impact Analysis
      +-- Human Engineering Approval
      +-- Lifecycle Transition
```

AI can produce:

```text
Release Readiness

✓ BOM complete
✓ Drawing present
✓ Requirements traced
✓ All child parts released

⚠ Potential duplicate:
  P-1024 may be similar to P-2044

Impact:
  3 downstream assemblies
```

The AI provides analysis and recommendations. The workflow engine and authorization model control the actual lifecycle transition.

---

# 54. Workflow and Agent Separation

Keep these responsibilities distinct:

```text
WORKFLOW ENGINE
----------------
Controls:
- state
- transition
- assignment
- approval
- authorization
- deterministic conditions
- audit trail

AI AGENT
----------------
Provides:
- analysis
- recommendations
- interpretation
- anomaly detection
- evidence summarization
- optional candidate actions
```

AI should not silently bypass workflow authorization.

---

# 55. Workflow Query Model

Reusable graph queries should be first-class metadata.

Examples:

```text
release_readiness
all_components_released
required_documents_present
requirements_traced
open_changes
downstream_impact
regulatory_impact
supplier_impact
```

A workflow references queries by ID:

```yaml
entry_conditions:

  - type: graph
    query: release_readiness
```

This avoids embedding graph traversal logic directly into workflow definitions.

---

# 56. Complete PLM-IQ Declarative Model

The profile YAML now defines the major semantic layers:

```text
PLM PROFILE
    |
    +-- VERTEX TYPES
    |      |
    |      +-- ATTRIBUTES
    |
    +-- EDGE TYPES
    |      |
    |      +-- EDGE ANNOTATIONS
    |
    +-- QUERIES
    |
    +-- LIFECYCLES
    |
    +-- WORKFLOWS
    |      |
    |      +-- CONDITIONS
    |      +-- APPROVALS
    |      +-- ASSIGNMENTS
    |      +-- ACTIONS
    |
    +-- UI
    |
    +-- API
    |
    +-- SEARCH
    |
    +-- AI AGENTS
           |
           +-- TRAVERSAL RULES
           +-- PRIORITY
           +-- RISK
```

---

# 57. Target Runtime Architecture

```text
                         PLM-IQ
                           |
                    PROFILE ENGINE
                           |
        +------------------+------------------+
        |                  |                  |
      GRAPH             WORKFLOW             UI
      ENGINE             ENGINE            ENGINE
        |                  |                  |
        +------------------+------------------+
                           |
                    CONCRETE STORAGE
                           |
                       PostgreSQL
```

AI sits alongside these engines and uses controlled tools:

```text
                         AI ASSISTANT
                              |
                         AGENT HARNESS
                              |
                    +---------+---------+
                    |                   |
                 AI AGENTS        WORKFLOW TOOLS
                    |                   |
                    +---------+---------+
                              |
                     GRAPH / QUERY ENGINE
                              |
                         PLM GRAPH
```

The central principle is:

> **Graph defines what exists and how it is connected. Workflow defines how vertices move through controlled business processes. Queries define reusable graph conditions. AI analyzes and assists. The profile defines the domain semantics.**

---

# 58. Resulting Meta-Model

PLM-IQ can therefore be viewed as five semantic layers:

```text
1. VERTEX MODEL
   What things exist?

2. GRAPH MODEL
   How are things connected?

3. QUERY MODEL
   How do we interrogate the graph?

4. WORKFLOW MODEL
   How do things move through controlled lifecycle processes?

5. AI MODEL
   How can agents reason over the graph and assist workflows?
```

All five are configurable through the active PLM profile.

```text
                 PLM PROFILE
                      |
       +--------------+--------------+
       |              |              |
     VERTEX         GRAPH         WORKFLOW
       |              |              |
   Attributes      Edges         States
                                  |
                                Queries
                                  |
                               Approvals
                                  |
                                Actions
       |              |              |
       +--------------+--------------+
                      |
                    AI
                      |
                 Agent Rules
                      |
                  AI Assistant
```

This gives PLM-IQ a single declarative foundation for multiple industries while allowing each profile to define its own domain vertices, edges, queries, workflows, UI, and AI behavior.


---

# 59. Implementation Roadmap

The PLM-IQ implementation should use ten major phases, with three iterations per phase.

Every iteration follows:

```text
ITERATION 1
Foundation
Can we define it?

        ↓

ITERATION 2
Implementation
Can we build it?

        ↓

ITERATION 3
Validation
Does it actually work?
```

The implementation should also include an early **Vertical Slice PoC** so that the central YAML-to-running-PLM concept is proven before building the full platform.

---

# 60. Phase 0 - Vertical Slice PoC

The PoC is intentionally small and should be completed before full-scale implementation.

## Objective

Prove:

```text
YAML Profile
    ↓
Meta-Model Compiler
    ↓
Concrete Database Schema
    ↓
Python Backend
    ↓
Jinja UI
    ↓
Graph Edge
    ↓
Working PLM
```

The PoC should implement only:

```text
PART
DOCUMENT
HAS_COMPONENT
DOCUMENTED_BY
DRAFT
RELEASED
```

## PoC Iteration 1 - Define

Tasks:

- Create minimal `poc-profile.yaml`.
- Define PART vertex.
- Define DOCUMENT vertex.
- Define HAS_COMPONENT edge.
- Define DOCUMENTED_BY edge.
- Define DRAFT and RELEASED lifecycle.
- Define basic Part list/detail UI.
- Define basic BOM UI.
- Define SQLite development schema.
- Define generated API endpoints.
- Define acceptance criteria.

Expected result:

```text
poc-profile.yaml
```

## PoC Iteration 2 - Generate

Tasks:

- Build YAML validator.
- Build profile intermediate representation.
- Generate database tables.
- Generate vertex models.
- Generate repositories.
- Generate services.
- Generate REST endpoints.
- Generate Jinja templates.
- Generate navigation.
- Generate edge views.
- Generate seed data.
- Run generated application.

Expected result:

```text
YAML
 ↓
Generated PLM
 ↓
Running application
```

## PoC Iteration 3 - Validate

Tasks:

- Create P-100.
- Create P-200.
- Create A-100 assembly.
- Add P-100 and P-200 to A-100.
- Upload/link a document.
- Move part through lifecycle.
- Display BOM.
- Display Documents.
- Verify generated API.
- Verify graph traversal.
- Verify database schema.
- Regenerate after changing YAML.
- Confirm application still works.

### PoC Exit Criteria

The PoC passes when:

```text
Add vertex to YAML
        ↓
Regenerate
        ↓
Database changes
        ↓
API changes
        ↓
Jinja UI changes
        ↓
Working PLM feature
```

This is the most important early architectural proof.

---

# 61. Phase 1 - Requirements & Scope

## Objective

Define what PLM-IQ must do and establish the boundary between Core PLM and Industry Profiles.

### Iteration 1 - Core Requirements

Tasks:

- Define PLM personas.
- Define core business capabilities.
- Define core business vertices.
- Define lifecycle requirements.
- Define revision requirements.
- Define document requirements.
- Define edge requirements.
- Define workflow requirements.
- Define search requirements.
- Define AI requirements.
- Define multi-tenancy requirements.
- Define authorization requirements.
- Define audit requirements.
- Define non-functional requirements.

Deliverables:

```text
PRD.md
CORE_REQUIREMENTS.md
DOMAIN_GLOSSARY.md
ACCEPTANCE_CRITERIA.md
```

### Iteration 2 - Industry Requirements

Tasks:

- Define Discrete PLM profile.
- Define Pharma PLM profile.
- Identify common vertices.
- Identify profile-specific vertices.
- Identify profile-specific edges.
- Identify profile-specific workflows.
- Identify profile-specific AI semantics.
- Identify regulatory requirements where applicable.

### Iteration 3 - Scope Freeze

Tasks:

- Define MVP.
- Define post-MVP.
- Define future roadmap.
- Resolve requirement conflicts.
- Finalize acceptance criteria.
- Approve PRD.

Exit:

```text
Approved Requirements Baseline
```

---

# 62. Phase 2 - Technology Stack & Platform

## Objective

Select and validate the technical foundation.

### Iteration 1 - Technology Selection

Tasks:

- Confirm Python backend.
- Confirm FastAPI.
- Confirm Jinja server-side rendering.
- Confirm Bootstrap/minimal JavaScript.
- Confirm PostgreSQL.
- Confirm SQLite development mode.
- Select vector technology: pgvector or Qdrant.
- Select object storage.
- Select authentication.
- Select background worker.
- Select monitoring/logging.
- Select JT/3D viewer integration approach.
- Document technology decisions.

Deliverable:

```text
TECH_STACK.md
```

### Iteration 2 - Container Platform

Tasks:

- Create Dockerfile.
- Create development Compose file.
- Create test Compose file.
- Create production Compose file.
- Configure PostgreSQL.
- Configure object storage.
- Configure worker.
- Configure reverse proxy.
- Configure environment variables.
- Configure health checks.
- Configure persistent volumes.

### Iteration 3 - CI/CD

Tasks:

- Configure GitHub repository workflow.
- Build Docker image.
- Run automated tests.
- Run database migrations.
- Build production image.
- Deploy test environment.
- Add smoke tests.
- Add rollback procedure.

Exit:

```text
Repeatable build → test → deploy pipeline
```

---

# 63. Phase 3 - Architecture & Design

## Objective

Define the complete platform architecture.

### Iteration 1 - System Architecture

Tasks:

- Define application boundaries.
- Define service boundaries.
- Define API architecture.
- Define database architecture.
- Define object storage architecture.
- Define graph service.
- Define query engine.
- Define workflow engine.
- Define UI architecture.
- Define authentication.
- Define authorization.
- Define tenancy.
- Define audit.

Deliverable:

```text
ARCHITECTURE.md
```

### Iteration 2 - Graph Architecture

Tasks:

- Define node model.
- Define edge model.
- Define edge annotations.
- Define attributes.
- Define revisions.
- Define lifecycle.
- Define graph traversal.
- Define profile inheritance.
- Define tenant extensions.
- Define query abstraction.
- Define graph-to-SQL mapping.

### Iteration 3 - AI/RAG/Workflow Architecture

Tasks:

- Define Agent Harness.
- Define AI Assistant.
- Define AI Search.
- Define GraphRAG.
- Define vector indexing.
- Define document chunking.
- Define Impact Analysis Agent.
- Define workflow engine.
- Define workflow conditions.
- Define AI/workflow boundary.
- Define AI permissions.

Exit:

```text
Architecture Baseline
```

---

# 64. Phase 4 - User Stories & Mockups

## Objective

Turn requirements into usable product behavior.

### Iteration 1 - User Stories

Tasks:

- Define personas.
- Define Part stories.
- Define BOM stories.
- Define Document stories.
- Define Requirement stories.
- Define Change stories.
- Define Workflow stories.
- Define Search stories.
- Define AI Assistant stories.
- Define Impact Analysis stories.
- Define Administration stories.

Each story should contain:

```text
Actor
Goal
Preconditions
Steps
Acceptance Criteria
Permissions
Expected Result
```

### Iteration 2 - Mockups

Create mockups for:

```text
Dashboard
Part List
Part Workspace
BOM
Document Workspace
Requirements
Engineering Change
Workflow
Search
AI Assistant
Impact Analysis
Administration
```

### Iteration 3 - UX Validation

Tasks:

- Review navigation.
- Review vertex workspace.
- Review BOM usability.
- Review document navigation.
- Review graph visualization.
- Review AI interaction.
- Review workflow interaction.
- Review accessibility.
- Resolve usability defects.
- Freeze UI specifications.

---

# 65. Phase 5 - YAML PLM Definition

## Objective

Create the declarative PLM Profile Definition Language.

### Iteration 1 - Core YAML

Tasks:

- Define profile metadata.
- Define vertex types.
- Define attributes.
- Define edge types.
- Define edge annotations.
- Define lifecycles.
- Define revisions.
- Define queries.
- Define workflows.
- Define UI.
- Define API.
- Define search.
- Define AI.

Example:

```yaml
profile:
vertex_types:
edge_types:
lifecycles:
queries:
workflows:
ui:
api:
search:
ai:
```

### Iteration 2 - Discrete Profile

Tasks:

- Define PART.
- Define DOCUMENT.
- Define REQUIREMENT.
- Define CHANGE.
- Define SUPPLIER.
- Define MANUFACTURING_ROUTE.
- Define BOM edges.
- Define document edges.
- Define requirement edges.
- Define change edges.
- Define release workflow.
- Define AI impact rules.

### Iteration 3 - YAML Compiler

Tasks:

- Build YAML parser.
- Build schema validator.
- Validate references.
- Validate inheritance.
- Validate edge endpoints.
- Validate lifecycle references.
- Validate workflow queries.
- Validate UI references.
- Validate AI rules.
- Generate intermediate representation.

Deliverable:

```text
profile-ir.json
```

---

# 66. Phase 6 - Database Definition & Scripts

## Objective

Compile profiles into concrete, optimized storage.

### Iteration 1 - Core Database

Tasks:

- Create tenant tables.
- Create user tables.
- Create organization tables.
- Create vertex tables.
- Create revision tables.
- Create document metadata tables.
- Create edge tables.
- Create lifecycle tables.
- Create workflow tables.
- Create audit tables.
- Create permissions tables.
- Create indexes.
- Create foreign keys.

### Iteration 2 - Profile Database

Tasks:

- Generate PART table.
- Generate DOCUMENT table.
- Generate REQUIREMENT table.
- Generate CHANGE table.
- Generate BOM edge table.
- Generate document edge table.
- Generate requirement edge table.
- Generate change edge table.
- Generate profile-specific attributes.
- Generate profile-specific indexes.

### Iteration 3 - Database Tooling

Create:

```text
create_db.py
drop_db.py
migrate.py
seed.py
reset.py
validate_schema.py
```

Tasks:

- Migration versioning.
- Migration rollback.
- Index validation.
- Foreign-key validation.
- Tenant isolation validation.
- Seed/reset support.
- Development SQLite support.
- Production PostgreSQL support.

---

# 67. Phase 7 - Code Generation & Runtime

## Objective

Generate a functioning PLM application from the compiled profile.

### Iteration 1 - Generator Framework

Tasks:

- Build generator architecture.
- Create template system.
- Generate models.
- Generate repositories.
- Generate services.
- Generate validators.
- Generate API schemas.
- Generate routers.
- Generate permissions.
- Generate Jinja templates.
- Generate navigation.
- Generate forms.
- Generate list views.
- Generate edge views.

### Iteration 2 - Backend Generation

Generate:

```text
models/
repositories/
services/
routers/
schemas/
validators/
permissions/
```

Tasks:

- CRUD.
- Edges.
- Search.
- Revision.
- Lifecycle.
- Workflow integration.
- Audit.
- File metadata.

### Iteration 3 - UI Generation

Generate:

```text
list.html
detail.html
create.html
edit.html
workspace.html
```

Tasks:

- Navigation generation.
- Vertex pages.
- Edge tables.
- BOM views.
- Document views.
- Forms.
- Search.
- Workflow actions.
- Dashboard widgets.

Exit:

```text
YAML → generated backend + database + Jinja UI
```

---

# 68. Phase 8 - Seed Data & Testing

## Objective

Create realistic data and establish automated quality gates.

### Iteration 1 - Seed Data

Create:

```text
10 products
50 assemblies
500 parts
200 documents
100 requirements
50 changes
100 suppliers
1000+ edges
```

Tasks:

- Create revision history.
- Create lifecycle states.
- Create BOM depth.
- Create document edges.
- Create requirement traceability.
- Create change edges.
- Create realistic timestamps.
- Create user assignments.

### Iteration 2 - Automated Testing

Test:

```text
Unit
Integration
API
Database
Graph traversal
Workflow
Authorization
Tenant isolation
UI
```

Tasks:

- Create test fixtures.
- Create API tests.
- Create database tests.
- Create graph tests.
- Create workflow tests.
- Create UI smoke tests.
- Add regression suite.

### Iteration 3 - AI/RAG Testing

Tasks:

- Create RAG test corpus.
- Create embedding tests.
- Test metadata filtering.
- Test revision filtering.
- Test tenant isolation.
- Test graph retrieval.
- Test hybrid retrieval.
- Test reranking.
- Test Impact Analysis.
- Create golden question/answer dataset.
- Measure groundedness and citation accuracy.

---

# 69. Phase 9 - Production Validation & UAT

## Objective

Validate the complete application in a production-like environment.

### Iteration 1 - Production-Like Environment

Tasks:

- Deploy production PostgreSQL.
- Deploy application containers.
- Deploy object storage.
- Deploy worker.
- Configure reverse proxy.
- Configure TLS.
- Configure backups.
- Configure monitoring.
- Configure logging.
- Test database restore.
- Test vertex-storage restore.
- Test migrations.
- Test rollback.

### Iteration 2 - UAT

Execute business scenarios:

```text
Create Part
Create BOM
Upload Drawing
Create Revision
Create Requirement
Create Change
Submit Change
Approve Change
Release Part
Search
AI Search
Impact Analysis
Document retrieval
Workflow approval
```

Tasks:

- Capture UAT evidence.
- Record defects.
- Prioritize defects.
- Retest fixes.
- Obtain business sign-off.

### Iteration 3 - Production Readiness

Validate:

```text
0 critical defects
0 release-blocking major defects
UAT sign-off
Security sign-off
Backup validation
Rollback validation
Monitoring validation
Performance acceptance
```

Deliverable:

```text
PRODUCTION_READINESS.md
```

---

# 70. Phase 10 - Go-Live & Production Load Testing

## Objective

Deploy safely and prove production scalability.

### Iteration 1 - Go-Live Rehearsal

Tasks:

- Backup production database.
- Run migrations.
- Deploy application.
- Run health checks.
- Run smoke tests.
- Validate object storage.
- Validate authentication.
- Validate workflows.
- Validate AI services.
- Validate rollback.
- Measure deployment duration.

### Iteration 2 - Production Go-Live

Sequence:

```text
Backup
   ↓
Migration
   ↓
Application deployment
   ↓
Health checks
   ↓
Smoke tests
   ↓
Enable users
   ↓
Monitor
```

Tasks:

- Deploy production version.
- Enable tenant.
- Create users.
- Verify permissions.
- Verify data.
- Verify workflows.
- Verify search.
- Verify documents.
- Monitor errors.

### Iteration 3 - Production Load Validation

Test:

```text
Concurrent users
API throughput
BOM traversal
Graph queries
AI Search
GraphRAG
Document downloads
3D viewer
Workflow execution
Database load
Vector search
```

Suggested initial test targets:

```text
100 concurrent users
1,000 concurrent users
10,000+ vertices
1M+ edges
100K documents
```

Measure:

```text
API latency
Database CPU
Database connections
Query latency
Graph traversal latency
Search latency
Vector search latency
RAG latency
LLM latency
Memory
CPU
Object storage throughput
```

Then optimize:

```text
SQL indexes
Graph traversal
Caching
Search indexes
Vector retrieval
Connection pools
Background workers
Object storage
```

---

# 71. Phase Exit-Gate Model

Every phase should have an explicit exit gate.

```text
Phase
  |
  +-- Iteration 1
  |
  +-- Iteration 2
  |
  +-- Iteration 3
  |
  v
Exit Gate
  |
  +-- Deliverables complete
  +-- Acceptance criteria passed
  +-- Defects acceptable
  +-- Architecture decisions recorded
  +-- Artifacts versioned
```

No phase should be considered complete merely because development work has stopped.

---

# 72. Overall Implementation Flow

```text
                    PHASE 0
                 Vertical PoC
                      |
                      v
                 PHASE 1
               Requirements
                      |
                      v
                 PHASE 2
             Technology/Containers
                      |
                      v
                 PHASE 3
             Architecture/Design
                      |
                      v
                 PHASE 4
             Stories/Mockups
                      |
                      v
                 PHASE 5
              YAML Definition
                      |
                      v
                 PHASE 6
           Database + Scripts
                      |
                      v
                 PHASE 7
              Code Generation
                      |
                      v
                 PHASE 8
             Seed + Testing
                      |
                      v
                 PHASE 9
              UAT + Validation
                      |
                      v
                 PHASE 10
            Go-Live + Load Test
```

The **Vertical Slice PoC should be deliberately early**. It is the architectural litmus test for PLM-IQ: if `profile.yaml → schema → Python backend → Jinja UI → graph edge → lifecycle` works cleanly, the rest of the platform can be built incrementally around that foundation.

---

# 59A. Part, Assembly, Component and Product Modeling

PLM-IQ should avoid treating `PRODUCT`, `ASSEMBLY`, `PART`, and `COMPONENT` as four unrelated physical vertex concepts when they represent overlapping engineering concepts.

The recommended model is:

```text
                         PART
                          |
              +-----------+-----------+
              |                       |
          COMPONENT                ASSEMBLY
              |                       |
       physical/reusable        structured part
          element                  hierarchy
```

A Product is a business/market-level concept that may reference one or more engineering assemblies or parts:

```text
PRODUCT
   |
   +-- REPRESENTED_BY --> ASSEMBLY
                              |
                              +-- HAS_COMPONENT --> COMPONENT/PART
```

## Recommended Core Vertex Model

Use one fundamental engineering vertex:

```text
PART
```

and distinguish its structural role with a controlled attribute:

```yaml
vertex_types:

  - id: part
    name: Part

    attributes:

      - id: structure_type
        type: enum
        required: true

        values:
          - COMPONENT
          - ASSEMBLY
```

Thus both of these are `PART` nodes:

```text
P-1001
structure_type = COMPONENT
```

and:

```text
A-100
structure_type = ASSEMBLY
```

Both share number, name, description, revision, lifecycle, documents, requirements, changes, suppliers, and manufacturing information. An assembly additionally participates as the source of BOM edges.

```text
A-100
  |
  +-- HAS_COMPONENT --> P-101
  +-- HAS_COMPONENT --> P-102
  +-- HAS_COMPONENT --> A-200
```

This avoids duplicating the engineering data model into separate `PART` and `ASSEMBLY` tables unless a profile has a strong reason to do so.

## Component Semantics

`COMPONENT` should normally be treated as a **structural role**, not necessarily a separate database vertex.

```text
PART P-1024
structure_type = COMPONENT
```

When it is used inside an assembly:

```text
A-100
  |
  +-- HAS_COMPONENT --> P-1024
```

The edge annotation carries occurrence-specific information:

```yaml
edge_types:

  - id: has_component
    source: part
    target: part

    annotations:

      - id: quantity
        type: decimal
        required: true

      - id: find_number
        type: string

      - id: unit
        type: enum
        values:
          - EA
          - KG
          - M

      - id: note
        type: text
```

This allows the same Part to occur in many assemblies with different quantity, find number, unit, occurrence information, notes, and effectivity.

## Product Semantics

`PRODUCT` should generally be a separate business vertex when the organization needs to distinguish the market/customer offering from its engineering realization.

```text
PRODUCT
  |
  +-- REPRESENTED_BY --> A-100
  |
  +-- DOCUMENTED_BY --> Product Specification
  |
  +-- SATISFIES --> Market Requirement
```

Therefore:

```text
PART
 ├── COMPONENT
 └── ASSEMBLY

PRODUCT
 └── references engineering realization
```

This keeps engineering structure separate from commercial/product structure.

## Profile Extensions

A profile may introduce additional structural classifications without changing the Core model:

```yaml
structure_type:
  values:
    - COMPONENT
    - ASSEMBLY
    - PHANTOM
    - REFERENCE
```

A Pharma profile can add domain-specific classifications such as:

```yaml
part_class:
  values:
    - ACTIVE_INGREDIENT
    - EXCIPIENT
    - PACKAGING_COMPONENT
    - FORMULATION_COMPONENT
```

The underlying graph remains:

```text
Node
  +
Attributes
  +
Edges
```

while the profile supplies domain-specific classification.

---

# 59B. Recommended PLM-IQ Repository Structure

The repository should separate the PLM platform engine, profiles, generated artifacts, runtime application, database tooling, tests, and environment setup.

```text
plm-iq/
│
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
│
├── docs/
│   ├── requirements/
│   │   ├── PRD.md
│   │   ├── core-requirements.md
│   │   ├── discrete-plm-requirements.md
│   │   └── pharma-plm-requirements.md
│   ├── architecture/
│   │   ├── architecture.md
│   │   ├── graph-meta-model.md
│   │   ├── query-engine.md
│   │   ├── workflow-engine.md
│   │   ├── agent-harness.md
│   │   ├── rag-architecture.md
│   │   └── indexing.md
│   ├── ux/
│   │   ├── user-stories.md
│   │   ├── navigation.md
│   │   └── mockups/
│   └── implementation/
│       └── roadmap.md
│
├── profiles/
│   ├── core/
│   │   ├── profile.yaml
│   │   ├── vertices.yaml
│   │   ├── edges.yaml
│   │   ├── lifecycles.yaml
│   │   ├── queries.yaml
│   │   ├── workflows.yaml
│   │   ├── ui.yaml
│   │   └── ai.yaml
│   ├── discrete/
│   │   ├── profile.yaml
│   │   ├── vertices.yaml
│   │   ├── edges.yaml
│   │   ├── lifecycles.yaml
│   │   ├── queries.yaml
│   │   ├── workflows.yaml
│   │   ├── ui.yaml
│   │   └── ai.yaml
│   └── pharma/
│       ├── profile.yaml
│       ├── vertices.yaml
│       ├── edges.yaml
│       ├── lifecycles.yaml
│       ├── queries.yaml
│       ├── workflows.yaml
│       ├── ui.yaml
│       └── ai.yaml
│
├── engine/
│   ├── meta_model/
│   ├── compiler/
│   ├── graph/
│   ├── query/
│   ├── workflow/
│   ├── search/
│   ├── rag/
│   └── agents/
│
├── generators/
│   ├── database/
│   ├── backend/
│   └── ui/
│
├── templates/
│   ├── backend/
│   ├── api/
│   ├── jinja/
│   │   ├── layouts/
│   │   ├── components/
│   │   ├── pages/
│   │   └── workspaces/
│   └── migrations/
│
├── app/
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py
│   ├── api/
│   ├── services/
│   ├── repositories/
│   ├── models/
│   ├── workflows/
│   └── web/
│
├── generated/
│   ├── discrete/
│   │   ├── db/
│   │   ├── backend/
│   │   └── ui/
│   └── pharma/
│       ├── db/
│       ├── backend/
│       └── ui/
│
├── database/
│   ├── migrations/
│   ├── scripts/
│   │   ├── create_db.py
│   │   ├── reset_db.py
│   │   ├── seed_db.py
│   │   └── validate_schema.py
│   └── seeds/
│       ├── core/
│       ├── discrete/
│       └── pharma/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── api/
│   ├── graph/
│   ├── workflow/
│   ├── generators/
│   ├── ui/
│   ├── search/
│   ├── rag/
│   └── agents/
│
├── test-data/
│   ├── discrete/
│   ├── pharma/
│   ├── documents/
│   └── golden-rag/
│
├── scripts/
│   ├── generate.py
│   ├── validate-profile.py
│   ├── build-profile.py
│   ├── run-dev.py
│   └── test-all.py
│
└── setup/
    ├── docker/
    │   ├── Dockerfile
    │   ├── docker-compose.dev.yml
    │   ├── docker-compose.test.yml
    │   └── docker-compose.prod.yml
    ├── postgres/
    │   ├── init/
    │   └── config/
    ├── nginx/
    │   ├── dev/
    │   └── prod/
    ├── caddy/
    │   └── Caddyfile
    ├── monitoring/
    │   ├── prometheus/
    │   └── grafana/
    ├── scripts/
    │   ├── install.sh
    │   ├── setup-dev.sh
    │   ├── setup-test.sh
    │   └── setup-prod.sh
    └── README.md
```

## Repository Responsibilities

```text
profiles/       What PLM are we building?
engine/         How does PLM-IQ work?
generators/     How do we generate it?
templates/      What does generated code look like?
app/            What runs?
generated/      What was generated?
database/       How is data initialized and migrated?
tests/          Does it work?
test-data/      What data do we test with?
scripts/        Developer automation
setup/          How do we run and operate the platform?
docs/           Why and how was it designed?
```

## Generated Code Rule

Nothing under `generated/` should be manually edited.

Generated files should carry:

```text
# AUTO-GENERATED BY PLM-IQ
# DO NOT EDIT
# Source: profiles/discrete/
```

Customer-specific behavior should be represented through profile extensions:

```text
profiles/
    discrete/
    pharma/
    customers/
        acme/
```

rather than modifying generated Python or Jinja files.

## Repository Generation Flow

```text
profiles/discrete/
        |
        v
   Profile Compiler
        |
        v
   profile-ir.json
        |
   +----+----+
   |    |    |
   v    v    v
  DB   API   UI
   |    |    |
   +----+----+
        |
        v
   PLM-IQ Runtime
```

The repository structure intentionally keeps the **declarative PLM definition**, **runtime engine**, **code generator**, and **generated application** as separate concerns.

PRD
# PLM-IQ — Product Requirements Document (SaaS)

## Document Control

| | |
|---|---|
| Product | PLM-IQ |
| Document | SaaS Product Requirements Document |
| Version | 1.0 |
| Status | Draft for review |
| Source model | `plm-iq-graph-based-plm-meta-model.md` |
| Related deliverables | `CORE_REQUIREMENTS.md`, `DOMAIN_GLOSSARY.md`, `ACCEPTANCE_CRITERIA.md` |

---

## 1. Executive Summary

PLM-IQ is a multi-tenant, cloud-native Product Lifecycle Management (PLM) platform built on a single configurable **graph meta-model**. Instead of shipping isolated BOM, document, requirement, change, manufacturing, quality, and supplier subsystems, PLM-IQ models the entire product lifecycle as one configurable directed graph (digraph) of nodes (vertices) and meaningful edges.

The defining architectural idea is the **profile** — a declarative, YAML-defined layer that turns the same generic graph engine into a Discrete PLM, Pharma PLM, Medical Device PLM, or any future industry solution **without forking the code**. Node types, attributes, edge types, edge annotations, lifecycles, queries, workflows, UI, search behavior, and AI agent rules are all configuration, not application logic.

PLM-IQ is delivered as a **SaaS**:
- Customers subscribe to a tenant.
- A platform administrator assigns a PLM profile (Discrete, Pharma, custom).
- The platform compiles the profile into database schema, APIs, and UI at runtime.
- Optional AI capabilities (Impact Analysis, AI Search, AI Assistant) are provided as controlled, profile-aware tools.

This document defines the product scope, personas, capabilities, SaaS architecture, functional and non-functional requirements, AI boundaries, security, and roadmap for the first generally available (GA) release.

---

## 2. Vision & Positioning

### 2.1 Vision

> Graph-native. AI-native. AI-first. One declarative graph foundation, many industry PLM solutions — configured, not coded, and reasoned over by governed agents from day one.

PLM-IQ is built **graph-native** so the product structure, documents, requirements, change, manufacturing, quality, and suppliers live in one connected model rather than disconnected tables. It is **AI-native** because AI is not bolted on — the graph, provenance, and agent tools are designed together. It is **AI-first** because every user workflow (search, impact analysis, release readiness, traceability) is conceived with an intelligent, profile-aware assistant as the primary interface, not an afterthought.

### 2.2 Positioning

Traditional PLM systems are monolithic, industry-specific, and expensive to customize; their AI features are generic chatbots layered over inaccessible data. PLM-IQ separates four concerns so each can evolve independently:

```text
GRAPH      What exists and how things are connected.
PROFILE    What those connections mean in a particular industry.
AGENT      How to reason over the information.
HARNESS    What the agent is allowed and expected to do.
```

This lets PLM-IQ serve Discrete Manufacturing, Life Sciences, and future domains from one engine, dramatically reducing time-to-value and total cost of ownership while making governed AI the default way users interact with their product data.

### 2.3 Key Differentiators

- **Graph-native, not table-siloed.** BOM, documents, requirements, change, manufacturing, quality, and suppliers are traversals over one directed graph (digraph) — the canonical semantic layer of PLM-IQ.
- **AI-native and AI-first.** AI is designed into the core: profile-aware agents, provenance, confidence, and controlled graph tools are first-class. The assistant is the primary interface for search, impact analysis, traceability, and release readiness.
- **Built ground-up on three configurable layers.** PLM-IQ is composed from the bottom up as **Core** (standard meta-model) → **Industry-specific** (Discrete, Pharma, Food, Medical Device profiles) → **Tenant-configurable** (per-customer attributes, edge types, workflows, and AI rules) — all declarative, requiring no application-code changes.
- **Best-of-2026 component architecture.** PLM-IQ is assembled from the best-in-class 2026 market components: a robust **relational database** for authoritative structured data, a **search engine** for fast structured/full-text retrieval, a **RAG** pipeline (vector + hybrid retrieval with reranking and citations) for semantic understanding, and an **agent framework** for governed multi-hop reasoning — composed into one platform rather than reinvented.
- **Profile-configured, code-free customization.** Industry and tenant semantics are declarative metadata.
- **Built-in AI with guardrails.** AI is profile-aware and operates only through controlled graph tools with provenance and confidence.
- **Revision control & audit history built in.** Every node is revision-tracked (immutable historical revisions, supersede chains) and every mutation, workflow decision, and AI action is captured in an immutable audit trail — making the platform explainable and compliance-ready by default.
- **Vertical-slice proven.** The architecture is validated early via a minimal `profile.yaml → schema → API → UI → graph → lifecycle` PoC.

---

## 3. Problem & Market Context

### 3.1 Problems with current PLM approaches

1. **Siloed subsystems.** BOM, documents, requirements, and change are separate databases, breaking traceability.
2. **Industry forks.** Adapting a PLM system to a new domain requires code changes or a separate product.
3. **Slow customization.** Adding a single attribute or edge often needs engineering change in the vendor's codebase.
4. **Opaque AI.** Generic LLM/chat integrations access data without provenance, authorization, or explainability.
5. **High TCO.** Per-seat licensing, long implementation, and rigid data models.

### 3.2 Target Markets

| Segment | Profile | Example tenants |
|---|---|---|
| Discrete manufacturing | Discrete | Automotive, aerospace, industrial equipment |
| Life sciences | Pharma / Biotech / Medical Device | Drug product, formulation, regulatory |
| Food & beverage | Food | Recipe, ingredient, formulation, batch, labeling |
| Future | Extensible core | Energy, consumer electronics |

### 3.3 SaaS Business Model

- **Tenants** subscribe per plan.
- Plans differ by profile availability, node/edge volume, storage, AI feature tier, and support.
- Tenant extensions (attributes, edge types, workflows) are self-service within an assigned profile and require no application-code changes; the underlying profiles themselves are created and published by the platform administrator, not by customers.

---

## 4. Personas

| Persona | Role | Primary goals |
|---|---|---|
| Plant Engineer / Designer | Creates parts, BOMs, drawings | Fast data entry, correct structure, traceability |
| BOM Manager | Maintains product structure | Where-used, effectivity, change impact |
| Quality Engineer | Manages issues, tests, NCRs | Trace defects to parts, requirements |
| Configuration / Release Manager | Controls lifecycle | Enforce release readiness via workflows |
| Change Manager | Runs engineering changes | Impact analysis, approvals |
| Manufacturing Engineer | Defines routes, operations | Link parts to manufacturing |
| Regulatory / Compliance Officer | Pharma/life sciences | Regulatory submissions, stability, audits |
| Platform Administrator | Creates profile-based PLM solutions (Discrete, Pharma, Food, Medical Device, custom) from the core meta-model and publishes them to tenants. Customers do not author profiles. |
| PLM Administrator | Tenant config | Manage users, permissions, and tenant extensions within an assigned profile |
| Platform Operator | Runs SaaS | Tenancy, scaling, backups, observability |
| AI User / Engineer | Uses assistant | Ask impact, search, trace requirements |

---

## 5. Product Scope (MVP → GA)

### 5.1 In Scope (MVP)

- Multi-tenant SaaS foundation (tenant isolation, auth, billing hooks).
- Core graph meta-model services: Meta-Model, Graph, Node, Document, Query.
- Discrete profile with PART/COMPONENT/ASSEMBLY/PRODUCT, DOCUMENT, REQUIREMENT, CHANGE, SUPPLIER, MANUFACTURING_ROUTE, QUALITY nodes.
- BOM (HAS_COMPONENT), Where-Used (reverse traversal), Documents & virtual folders.
- Requirements traceability (SATISFIES, VERIFIED_BY, DERIVED_FROM).
- Engineering Change (generic CHANGE, AFFECTS, impact traversal).
- Lifecycle states (DRAFT → IN_REVIEW → RELEASED) and revisions.
- Configurable attributes and edge annotations.
- Basic search (structured + text).
- Graph-driven node workspace UI (Jinja server-rendered).
- Workflow engine: release readiness graph conditions, approvals, audit.
- AI tier (optional add-on): Impact Analysis Agent, AI Search, AI Assistant via controlled graph tools.

### 5.2 Post-MVP

- Pharma profile (formulation, API, batch, stability, regulatory).
- Food profile (recipe, ingredient, formulation, batch, labeling, compliance).
- Medical Device profile (UDI, design controls).
- Workflow actions that mutate graph (create edges, revisions, notify).
- 3D/JT viewer integration.
- Vector/hybrid AI Search with reranking and citations.
- Advanced effectivity (serial, lot, configuration, model year).
- Public API & webhooks for integrations (ERP, MES, CAD).
- Tenant branding and custom domains.

### 5.3 Out of Scope (v1)

- On-premises deployment (cloud SaaS only for v1).
- Custom code plugins (only profile/metadata extensions allowed).
- Real-time co-authoring of documents.
- Native CAD authoring.

---

## 6. Core Capabilities

Each capability is a **view, query, traversal, or workflow over the graph**, per the meta-model's implementation principle.

| # | Capability | Graph implementation |
|---|---|---|
| C1 | BOM management | `HAS_COMPONENT` traversal + occurrence annotations (qty, find number, unit, effectivity) |
| C2 | Where-Used | Reverse `HAS_COMPONENT` / `USED_IN` traversal |
| C3 | Document management | `DOCUMENTED_BY`, `HAS_FILE`, virtual folders (`HAS_DRAWING`, `HAS_SPECIFICATION`, etc.) |
| C4 | Requirement traceability | `SATISFIES`, `VERIFIED_BY`, `DERIVED_FROM`, `ALLOCATED_TO` |
| C5 | Engineering change | Generic `CHANGE` + `AFFECTS` + downstream/upstream traversal |
| C6 | Manufacturing | `MANUFACTURED_BY`, `HAS_OPERATION`, `USES_TOOL`, `USES_MATERIAL` |
| C7 | Quality | `HAS_ISSUE`, `TESTED_BY`, `PRODUCES` → `TEST_RESULT`, `EVIDENCE_FOR` |
| C8 | Supplier management | `SUPPLIED_BY`, `SUPPLIES`, `HAS_CONTRACT`, annotations (cost, lead time, MOQ) |
| C9 | Configuration mgmt | Revisions, `PREVIOUS_VERSION`, `SUPERSEDES`, effectivity |
| C10 | Workflow / lifecycle | Declarative workflows over graph + lifecycle state |
| C11 | Search | Structured + text + (post-MVP) vector/hybrid |
| C12 | AI Impact Analysis | Multi-hop graph traversal with profile priority/risk rules |
| C13 | AI Search & Assistant | Graph-aware retrieval + profile-organized answers |
| C14 | Profiles & tenant extensions | Declarative metadata; no app-code changes |

---

## 7. SaaS Architecture Overview

### 7.1 Layers

```text
                 PLM-IQ SaaS PLATFORM
                          |
                   PROFILE ENGINE
                          |
     +--------------------+--------------------+
     |                    |                    |
   GRAPH ENGINE      WORKFLOW ENGINE        UI ENGINE
     |                    |                    |
     +--------------------+--------------------+
                          |
                   CONCRETE STORAGE
                          |
                 PostgreSQL (+ SQLite dev)
                 Object storage (files)
                 Vector store (post-MVP)
```

### 7.2 Tenant Model

- Every node, edge, and metadata row carries `tenant_id`.
- Tenant isolation enforced at the database, service, query, and AI layers.
- A tenant activates one or more **profiles** (Discrete default; Pharma/Medical as add-ons).
- Tenant extensions overlay the profile as additional attributes/edge types without modifying platform code.

### 7.3 Declarative Profile Pipeline

```text
profiles/discrete/
        |
        v
  Profile Compiler  (validate, resolve inheritance, build IR)
        |
        v
  profile-ir.json
        |
   +----+----+
   v    v    v
  DB   API   UI
        |
        v
  PLM-IQ Runtime
```

### 7.4 Technology Stack (per meta-model Phase 2)

- Backend: Python + FastAPI.
- UI: Jinja server-side rendering, Bootstrap, minimal JS.
- Primary DB: PostgreSQL; SQLite for local development.
- Object storage: local filesystem for v1 (single-node/dev and small tenants); S3-compatible object storage and Gitea-based artifact storage planned post-MVP for scale, redundancy, and versioned artifacts.
- Auth: OAuth2/OIDC with RBAC.
- Background worker: for indexing, workflow jobs, AI tasks.
- Vector (post-MVP): pgvector or Qdrant.
- Container: Docker + Compose for dev/test; Kubernetes or equivalent for prod.
- CI/CD: GitHub Actions (build → test → migrate → deploy).

### 7.5 Logical Services

- **Meta-Model Service** — node types, attribute definitions, edge types, edge annotations, versioning.
- **Graph Service** — nodes, edges, traversals, effectivity, provenance.
- **Node Service** — CRUD, lifecycle, revision.
- **Document Service** — documents, revisions, files, object storage.
- **Query Service** — graph queries, search, filters.
- **Workflow Engine** — states, stages, conditions (graph queries), approvals, actions, audit.
- **AI / Agent Layer** — graph tools, search tools, impact analysis, assistant (profile-aware).

---

## 8. Functional Requirements

### 8.1 Multi-Tenancy (FR-TEN)

- FR-TEN-1: The system MUST isolate all data by `tenant_id` at storage and query layers.
- FR-TEN-2: Cross-tenant data access MUST be impossible via API, query, search, or AI tools.
- FR-TEN-3: A tenant MUST be able to activate a platform-published profile and apply tenant extensions without code deployment. Profiles are authored by the platform administrator, not by customers.
- FR-TEN-4: The platform MUST support per-tenant configuration versioning (node types, attributes, edge types, edge annotations) with `version`, `effective_from`, `effective_to`.

### 8.2 Graph & Nodes (FR-GRAPH)

- FR-GRAPH-1: Nodes (vertices) model business entities; edges model the edges between them.
- FR-GRAPH-2: Every node has a stable system envelope (id, tenant_id, node_type_id, number, name, lifecycle_state, revision_id, timestamps) plus configurable attributes.
- FR-GRAPH-3: Edge annotations store edge-specific facts (quantity, find number, unit, effectivity, note, cost) in typed columns.
- FR-GRAPH-4: Edge types and edge annotation definitions MUST be configurable and versioned.
- FR-GRAPH-5: Effects such as `HAS_COMPONENT` MUST support occurrence annotations (qty, find number, reference designator, effectivity).
- FR-GRAPH-6: Virtual folders MUST be generated views (selected edge types), never physical duplication.
- FR-GRAPH-7: Traversals MUST support upstream/downstream/where-used with bounded depth.

### 8.3 BOM & Structure (FR-BOM)

- FR-BOM-1: `HAS_COMPONENT` is the fundamental BOM edge; assemblies and components are `PART` nodes distinguished by `structure_type`.
- FR-BOM-2: The same part MAY appear in multiple assemblies with different occurrence annotations.
- FR-BOM-3: Where-Used MUST return all upstream parents with path evidence.
- FR-BOM-4: Effectivity (date/serial/lot/configuration/model-year) MUST optionally constrain BOM edges.

### 8.4 Documents (FR-DOC)

- FR-DOC-1: A document node MAY connect via multiple edges (drawing, spec, test report, certificate) through distinct edge types.
- FR-DOC-2: Files are stored in object storage; metadata in the graph.
- FR-DOC-3: Document revisions MUST be tracked (`HAS_REVISION`, `PREVIOUS_VERSION`).

### 8.5 Requirements (FR-REQ)

- FR-REQ-1: Requirements MUST be traceable via `SATISFIES`, `VERIFIED_BY`, `DERIVED_FROM`, `ALLOCATED_TO`.
- FR-REQ-2: Requirement coverage and verification status MUST be computable by graph query.

### 8.6 Change Management (FR-CHG)

- FR-CHG-1: Use a generic `CHANGE` node; `AFFECTS` targets parts, assemblies, documents, requirements.
- FR-CHG-2: Change impact MUST be computed via downstream and upstream graph traversal.
- FR-CHG-3: Change edges MUST carry provenance and confidence.

### 8.7 Lifecycle & Revision (FR-LC)

- FR-LC-1: Lifecycle states are profile-defined (e.g., DRAFT, IN_REVIEW, RELEASED).
- FR-LC-2: Revisions MUST be immutable historical states; superseding creates a new revision node.
- FR-LC-3: Lifecycle transition MUST be governed by workflows.

### 8.8 Workflow (FR-WF)

- FR-WF-1: Workflows are declarative (states, stages, conditions, approvals, actions, transitions).
- FR-WF-2: Conditions MUST be reusable graph queries (e.g., `release_readiness`, `all_components_released`), not hard-coded logic.
- FR-WF-3: Recursive graph conditions MUST be supported (e.g., "no unreleased descendant").
- FR-WF-4: Every significant workflow decision MUST produce auditable evidence (workflow_id, instance, stage, actor, decision, evidence).
- FR-WF-5: Workflow execution MAY create edges/transitions/revisions/notifications as configured actions.

### 8.9 Search (FR-SEARCH)

- FR-SEARCH-1: Structured filtering and full-text search over nodes and annotations.
- FR-SEARCH-2 (post-MVP): Vector + hybrid retrieval with tenant and revision filtering.
- FR-SEARCH-3: AI Search results MUST be organized by the active profile's semantic grouping.

### 8.10 AI Agents (FR-AI)

- FR-AI-1: AI agents access the graph ONLY through controlled tools (e.g., `find_downstream_impact`, `find_where_used`, `trace_requirement`, `get_edge_evidence`).
- FR-AI-2: Agent behavior MUST be specialized by the active profile (traversal rules, priorities, risk) — no hard-coded industry logic.
- FR-AI-3: AI-inferred edges MUST carry `source_type`, `source_id`, `confidence`, and MUST NOT silently become authoritative.
- FR-AI-4: The Agent Harness MUST enforce tenant isolation, authorization, max traversal depth, permitted tools, and action recording.
- FR-AI-5: Impact Analysis MUST return ranked results with graph evidence and risk level.
- FR-AI-6: AI MUST NOT bypass workflow authorization; it provides analysis/recommendations only.

### 8.11 Administration (FR-ADMIN)

- FR-ADMIN-1: Manage users, roles, permissions within a tenant.
- FR-ADMIN-2: Platform administrators author and publish profiles; tenant PLM administrators manage users, permissions, and tenant extensions within an assigned profile. Customers do not author profiles.
- FR-ADMIN-3: View audit logs and AI action logs.
- FR-ADMIN-4: Self-service profile extension UI (add attribute/edge type) with validation.

---

## 9. Non-Functional Requirements

| Area | Requirement |
|---|---|
| Performance | BOM traversal for 10k-node / 1M-edge tenant < 500 ms p95; search < 300 ms. |
| Scalability | Support 100 → 1,000 concurrent users; 10M+ nodes per tenant over time. |
| Availability | 99.9% monthly uptime for GA. |
| Tenant isolation | Cryptographic/row-level guarantee; verified by automated tests. |
| Security | OAuth2/OIDC, RBAC, TLS everywhere, secrets in vault, least privilege. |
| Auditability | Immutable audit log for mutations, workflow decisions, AI actions. |
| Configurability | 100% of domain semantics via profile; no app-code change for tenant needs. |
| Extensibility | Profile inheritance (CORE → DISCRETE → AUTOMOTIVE, etc.). |
| Data integrity | Versioned metadata; historical semantics preserved (e.g., STRING→ENUM). |
| Observability | Metrics, logs, traces; health checks; alerting. |
| Backup/DR | Daily backups, tested restore, RPO < 24h, RTO < 4h (prod). |
| Accessibility | WCAG 2.1 AA for generated UI. |
| Localization | Profile/UI labels externalized (post-MVP multi-language). |

---

## 10. AI Architecture & Guardrails

### 10.1 Strategic Separation

```text
GRAPH  →  PROFILE  →  AGENT  →  HARNESS  →  AI ASSISTANT  →  USER
```

- **Graph**: facts/structure.
- **Profile**: domain meaning, priority, risk, traversal rules.
- **Agent**: generic reasoning/planning.
- **Harness**: security, controls, permitted tools, evidence recording.

### 10.2 Agent Tools (controlled)

```text
find_related_nodes(node_id, edge_type, depth)
find_downstream_impact(node_id)
find_upstream_dependencies(node_id)
find_where_used(part_id)
find_documents(node_id)
find_requirements(node_id)
find_changes(node_id)
trace_requirement(requirement_id)
find_effectivity(node_id)
get_edge_evidence(edge_id)
```

### 10.3 Harness Responsibilities

1. Identify tenant. 2. Identify active profile. 3. Load agent config. 4. Load traversal rules. 5. Load risk/priority rules. 6. Apply authorization. 7. Apply tenant isolation. 8. Enforce max depth. 9. Select permitted tools. 10. Record actions/evidence. 11. Prevent unauthorized access. 12. Return structured evidence.

### 10.4 Provenance & Confidence

Every AI-inferred or imported edge carries `source_type`, `source_id`, `confidence`, `created_by`, `created_at`. AI-inferred edges are flagged and never auto-promoted to authoritative without human confirmation.

---

## 11. Data Model Summary (Logical)

Core tables (generated from profile IR):

```text
node_type
attribute_definition
node
node_attribute
edge_type
edge
edge_attribute_definition
edge_annotation
revision
lifecycle_state
workflow / workflow_instance / workflow_evidence
audit_log
tenant / user / role / permission
```

Hybrid storage: stable system fields structured; configurable domain attributes stored in `node_attribute` value columns by datatype. Edge-specific data in `edge_annotation`.

Graph-theory mapping: a node is a **vertex**, an edge is a **directed arc**, and the PLM graph is a **directed graph (digraph)**. Graph traversals are **walks** over **adjacent (neighbor)** nodes connected by an edge; `HAS_COMPONENT` is the primary arc for product structure.

---

## 12. User Experience

### 12.1 Graph-Driven Workspace

Every node has a canonical workspace, e.g. `/nodes/PART/P-1024`, dynamically exposing sections based on configured edge types:

```text
P-1024 Mounting Bracket

Connected Nodes
  Drawings        4
  Specifications  3
  Requirements    3
  Manufacturing   2
  Suppliers       1
  Changes         2
  Used In         7
```

### 12.2 Key Screens (MVP)

- Dashboard, Part List, Part Workspace, BOM, Document Workspace, Requirements, Engineering Change, Workflow, Search, AI Assistant, Impact Analysis, Administration.

### 12.3 UX Principle

Users see familiar PLM concepts (BOM, drawings, requirements); the graph provides the underlying structure invisibly.

---

## 13. Security & Compliance

- Tenant isolation enforced at every layer (see FR-TEN).
- RBAC with profile-aware permissions.
- All mutations audited; AI actions logged with evidence.
- Data encryption at rest and in transit.
- PII minimization; configurable retention.
- Compliance hooks for regulated industries (e.g., 21 CFR Part 11-style audit for Pharma profile, post-MVP).

---

## 14. Go-To-Market (Summary)

- **Entry**: Discrete PLM profile for SMB/mid-market manufacturers (fast BOM + document + change).
- **Expansion**: Pharma/Medical profiles for life sciences.
- **Monetization**: Per-tenant subscription tiers + AI add-on + storage/volume overages.
- **Differentiation message**: "Configure your PLM from one graph — no forks, no code, built-in governed AI."

---

## 15. Implementation Roadmap (aligned to meta-model)

PLM-IQ is built in 11 phases, each with define/implement/validate iterations and an explicit exit gate.

| Phase | Goal |
|---|---|
| 0 | Vertical Slice PoC (`profile.yaml → schema → API → UI → graph → lifecycle`) |
| 1 | Requirements & Scope (this PRD, core/industry requirements, scope freeze) |
| 2 | Tech stack & containers & CI/CD |
| 3 | Architecture & design (system, graph, AI/RAG/workflow) |
| 4 | User stories & mockups & UX validation |
| 5 | YAML PLM definition language & compiler (profile IR) |
| 6 | Database definition & migration/seed tooling |
| 7 | Code generation & runtime (models, APIs, Jinja UI) |
| 8 | Seed data & automated + AI/RAG testing |
| 9 | Production validation & UAT |
| 10 | Go-live & production load testing |

**Phase 0 is deliberately earliest** — it proves the central `YAML → running PLM` concept before full build-out.

---

## 16. Acceptance Criteria (High-Level)

- A new node type added to a profile regenerates DB schema, API, and UI without code changes.
- BOM traversal and Where-Used return correct results with evidence for seeded data.
- Release workflow blocks transition when graph conditions fail (e.g., missing drawing, unreleased child).
- AI Impact Analysis returns ranked, evidence-backed results bounded by profile rules.
- Cross-tenant access is prevented by automated isolation tests.
- All AI-inferred edges carry provenance and confidence and are not authoritative by default.

---

## 17. Open Questions / Decisions Needed

1. Billing provider integration (Stripe vs internal) and plan tiers.
2. Vector store choice (pgvector vs Qdrant) for post-MVP AI Search.
3. Default profile for new tenants and self-serve profile marketplace.
4. Data residency / region strategy for regulated tenants.
5. SLA and support tiers for GA.
6. Whether tenant extensions are UI-editable v1 or profile-YAML only v1.


