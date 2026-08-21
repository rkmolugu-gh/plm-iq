# PLM-IQ Graph-Based PLM Meta-Model

## 1. Core Model

PLM-IQ models Product Lifecycle Management as a configurable graph.

```text
GRAPH = (N, E, A)

N = Nodes / Business Objects
E = Edges / Relationships
A = Edge Annotations / Relationship-specific data
```

- Nodes represent PLM business objects.
- Edges represent meaningful relationships.
- Edge annotations represent facts specific to a relationship.
- Node attributes represent facts about an object.
- Metadata definitions make object types, attributes, edge types, and annotations configurable.

The objective is to make BOM, Documents, Requirements, Change Management, Manufacturing, Quality, Suppliers, and AI Impact Analysis graph views and traversals rather than isolated subsystems.

---

## 2. Node Meta-Model

Every node has a common envelope:

```text
Node
├── id
├── tenant_id
├── object_type_id
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
| REVISION | Version of a business object |
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

## 4. Core Relationship Vocabulary

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

Specialized relationships can serve as virtual folders:

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

Use a generic `CHANGE` object rather than separate ECR/ECO/ECN schemas.

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

An annotation describes the relationship itself, not either endpoint.

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

### Relationship note

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

Important relationships should optionally support temporal effectivity:

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

Important relationships should be traceable:

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

- verified relationships
- imported relationships
- manually authored relationships
- AI-inferred relationships

AI-generated relationships must carry provenance and confidence and must not silently become authoritative.

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

## 9. Configurable Object Types

Object types are metadata rather than hard-coded schemas.

```text
object_type
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

Object types can inherit attributes.

---

## 10. Configurable Attribute Definitions

```text
attribute_definition
--------------------
id
tenant_id
object_type_id
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
object_type_id
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
source_object_type_id
target_object_type_id
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
/objects/PART/P-1024
```

The workspace can dynamically expose sections based on configured edge types:

```text
P-1024 Mounting Bracket

Connected Objects
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
find_related_objects(object_id, edge_type, depth)
find_downstream_impact(object_id)
find_upstream_dependencies(object_id)
find_where_used(part_id)
find_documents(object_id)
find_requirements(object_id)
find_changes(object_id)
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
OBJECT_TYPE
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
    +-- Object Types
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

Object Service
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

1. Business objects are nodes.
2. Business relationships are edges.
3. Relationship-specific data belongs to edge annotations.
4. Object-specific data belongs to node attributes.
5. Stable system fields remain structured.
6. Domain-specific attributes are configurable.
7. Edge types are configurable.
8. Edge annotation definitions are configurable.
9. Virtual folders are views, never physical containment.
10. Documents can participate in multiple relationships.
11. Every node has one canonical identity.
12. Effectivity is supported for lifecycle-sensitive relationships.
13. Important relationships carry provenance.
14. AI-inferred relationships carry confidence and provenance.
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
    OBJECT TYPES                       EDGE TYPES
          |                                 |
    ATTRIBUTES                        ANNOTATIONS
          |                                 |
          +----------------+----------------+
                           |
                         GRAPH
                           |
        +------------------+------------------+
        |                  |                  |
      OBJECTS           RELATIONSHIPS      DOCUMENTS
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

Modules should be implemented as **views, workflows, queries, and traversals over the graph**, not as independent relationship systems.

The next implementation artifact should translate this meta-model into a concrete PostgreSQL/SQLite schema for:

```text
node
edge
object_type
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

Profiles can define object types, attributes, edge types, edge annotations, lifecycle definitions, workflows, document views, validation rules, UI views, and AI agent behavior.

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

important_relationships:

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

  - object_type: REGULATORY_SUBMISSION
    risk: HIGH
```

The exact storage format may be YAML, JSON, or normalized metadata tables. The semantic model is what matters.

---

# 31. Generic Impact Analysis Agent

The Impact Analysis Agent provides generic capabilities:

```text
Impact Analysis Agent
    |
    +-- identify affected objects
    +-- traverse relationships
    +-- evaluate lifecycle
    +-- collect evidence
    +-- rank impact
    +-- calculate risk
    +-- explain findings
```

The agent asks the active profile:

```text
Which relationships matter?
How far should I traverse?
Which object types are high risk?
Which relationships are critical?
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

The Pharma profile tells the generic agent that the following relationships are important:

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

# 34. Relationship Priority

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

This prevents an agent from presenting hundreds of weakly related objects as equally important.

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

  - object_type: REGULATORY_SUBMISSION
    risk: CRITICAL

  - object_type: STABILITY_STUDY
    risk: HIGH

  - object_type: DOCUMENT
    risk: MEDIUM
```

Discrete PLM could instead define:

```yaml
risk_rules:

  - object_type: SAFETY_CRITICAL_PART
    risk: CRITICAL

  - object_type: PRODUCT
    risk: HIGH

  - object_type: DRAWING
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
source_object_type
target_object_type
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
find_related_objects(object_id, edge_type, depth)
find_downstream_impact(object_id)
find_upstream_dependencies(object_id)
find_where_used(object_id)
find_documents(object_id)
find_requirements(object_id)
find_changes(object_id)
trace_requirement(requirement_id)
find_effectivity(object_id)
get_relationship_evidence(edge_id)
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

Workflows sit one layer above the graph and operate on graph nodes, relationships, lifecycle state, and graph-based conditions.

A workflow is a declarative lifecycle process, not a database operation.

```text
                 PLM PROFILE
                      |
        +-------------+-------------+
        |             |             |
      Objects       Edges       Workflows
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
├── object_type
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
    object_type: part

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

    required_relationships:

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
    id: "$object.id"

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
    source: "$object.id"
    target: "$approval.user_id"

  - type: create_edge
    edge: RESULTS_IN
    source: "$change.id"
    target: "$revision.id"

  - type: transition_lifecycle
    object: "$object.id"
    state: RELEASED

  - type: create_revision
    object: "$object.id"

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
object_id
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
    +-- OBJECT TYPES
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

> **Graph defines what exists and how it is connected. Workflow defines how objects move through controlled business processes. Queries define reusable graph conditions. AI analyzes and assists. The profile defines the domain semantics.**

---

# 58. Resulting Meta-Model

PLM-IQ can therefore be viewed as five semantic layers:

```text
1. OBJECT MODEL
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
     OBJECT         GRAPH         WORKFLOW
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

This gives PLM-IQ a single declarative foundation for multiple industries while allowing each profile to define its own domain objects, relationships, queries, workflows, UI, and AI behavior.


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
Graph Relationship
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
- Define PART object.
- Define DOCUMENT object.
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
- Generate object models.
- Generate repositories.
- Generate services.
- Generate REST endpoints.
- Generate Jinja templates.
- Generate navigation.
- Generate relationship views.
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
Add object to YAML
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
- Define core business objects.
- Define lifecycle requirements.
- Define revision requirements.
- Define document requirements.
- Define relationship requirements.
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
- Identify common objects.
- Identify profile-specific objects.
- Identify profile-specific relationships.
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
- Review object workspace.
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
- Define object types.
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
object_types:
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
- Define BOM relationships.
- Define document relationships.
- Define requirement relationships.
- Define change relationships.
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
- Create object tables.
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
- Generate relationship views.

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
- Relationships.
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
- Object pages.
- Relationship tables.
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
1000+ relationships
```

Tasks:

- Create revision history.
- Create lifecycle states.
- Create BOM depth.
- Create document relationships.
- Create requirement traceability.
- Create change relationships.
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
- Test object-storage restore.
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
10,000+ objects
1M+ relationships
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

The **Vertical Slice PoC should be deliberately early**. It is the architectural litmus test for PLM-IQ: if `profile.yaml → schema → Python backend → Jinja UI → graph relationship → lifecycle` works cleanly, the rest of the platform can be built incrementally around that foundation.

---

# 59A. Part, Assembly, Component and Product Modeling

PLM-IQ should avoid treating `PRODUCT`, `ASSEMBLY`, `PART`, and `COMPONENT` as four unrelated physical object concepts when they represent overlapping engineering concepts.

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

## Recommended Core Object Model

Use one fundamental engineering object:

```text
PART
```

and distinguish its structural role with a controlled attribute:

```yaml
object_types:

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

Both share number, name, description, revision, lifecycle, documents, requirements, changes, suppliers, and manufacturing information. An assembly additionally participates as the source of BOM relationships.

```text
A-100
  |
  +-- HAS_COMPONENT --> P-101
  +-- HAS_COMPONENT --> P-102
  +-- HAS_COMPONENT --> A-200
```

This avoids duplicating the engineering data model into separate `PART` and `ASSEMBLY` tables unless a profile has a strong reason to do so.

## Component Semantics

`COMPONENT` should normally be treated as a **structural role**, not necessarily a separate database object.

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

The relationship annotation carries occurrence-specific information:

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

`PRODUCT` should generally be a separate business object when the organization needs to distinguish the market/customer offering from its engineering realization.

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
│   │   ├── objects.yaml
│   │   ├── edges.yaml
│   │   ├── lifecycles.yaml
│   │   ├── queries.yaml
│   │   ├── workflows.yaml
│   │   ├── ui.yaml
│   │   └── ai.yaml
│   ├── discrete/
│   │   ├── profile.yaml
│   │   ├── objects.yaml
│   │   ├── edges.yaml
│   │   ├── lifecycles.yaml
│   │   ├── queries.yaml
│   │   ├── workflows.yaml
│   │   ├── ui.yaml
│   │   └── ai.yaml
│   └── pharma/
│       ├── profile.yaml
│       ├── objects.yaml
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
