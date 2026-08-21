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
