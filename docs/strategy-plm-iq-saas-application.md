# PLM-IQ SaaS Application Strategy Document

| Field | Value |
|---|---|
| Status | Draft |
| Version | 0.3 |
| Owner | PLM-IQ Platform Team |
| Last Updated | 2026-08-23 |
| Related Documents | `metamodel-prd.md` (metamodel and storage detail) |


## 1. Executive Summary

**PLM-IQ** is a cloud-native, AI-first, multi-tenant Product Lifecycle Management (PLM) SaaS platform. It is designed to provide a configurable, extensible digital thread across product definition, engineering, manufacturing, quality, documentation, specifications, compliance, and change processes.

The platform uses a graph-based domain model as its core architectural foundation. Business objects are represented as vertices, while relationships between those objects are represented as governed edges. This approach enables PLM-IQ to model complex product structures, traceability, dependencies, configurations, and lifecycle relationships more naturally than a rigid relational-only model.

PLM-IQ is delivered through multiple industry editions:

- **PLM-IQ Foundation** — A horizontal PLM foundation applicable to organizations in any industry.
- **PLM-IQ Discrete** — An edition for discrete manufacturing organizations, including industrial equipment, automotive, aerospace, electronics, machinery, and heavy manufacturing.
- **PLM-IQ Process** — An edition for process-driven industries such as chemicals, pharmaceuticals, cosmetics, and consumer packaged goods.
- **PLM-IQ Food** — A specialized edition for food and beverage companies, with emphasis on recipes, formulations, ingredients, allergens, nutrition, labeling, shelf life, and regulatory traceability.

Each customer operates as an isolated tenant and can extend the platform at the tenant level through configurable attributes, relationship rules, object types, workflows, views, integrations, and AI-assisted capabilities.

---

## 2. Product Vision

PLM-IQ aims to become an intelligent product lifecycle system that helps organizations manage product information and relationships from early concept through engineering, manufacturing, release, quality, regulatory compliance, and end-of-life.

The platform is built around five principles:

- **Graph-native product intelligence** — Product data is inherently connected: parts reference documents, documents describe specifications, specifications constrain materials, materials are used in formulations, and changes affect many downstream objects. PLM-IQ models these connections directly.
- **AI-first user experience** — AI is embedded into the application for search, data extraction, classification, rule validation, impact analysis, document intelligence, content generation, and workflow assistance.
- **Multi-edition product strategy** — A common platform supports industry-specific editions without duplicating the core product architecture.
- **Tenant-level extensibility** — Customers can extend data models and relationship rules without requiring source-code customization or compromising upgradeability.
- **Cloud-native SaaS delivery** — PLM-IQ is designed for scalable, secure, observable, API-driven deployment across many customers and editions.

---

## 3. Product Scope

PLM-IQ provides a common PLM platform with edition-specific capabilities layered on top.

| Area | PLM-IQ Capability |
|---|---|
| Product data management | Parts, documents, specifications, materials, products, variants, classifications, attachments, and metadata |
| Product structures | Multi-level BOMs, product configurations, reference structures, substitute parts, alternates, and approved components |
| Document management | Controlled documents, revisioning, document-to-part links, document extraction, approval workflows, and document intelligence |
| Change management | Change requests, change notices, change orders, impact analysis, affected-object tracking, and approval workflows |
| Specification management | Technical specifications, product specifications, material specifications, compliance specifications, and quality requirements |
| Configuration management | Options, features, rules, variants, effectivity, revision applicability, and configurable BOMs |
| Quality and compliance | Requirements, test plans, inspections, non-conformance records, CAPA, compliance evidence, and regulatory traceability |
| Collaboration | Comments, tasks, notifications, assignments, subscriptions, review workflows, and activity history |
| Search and analytics | Full-text search, graph navigation, semantic search, impact analysis, dashboards, reports, and traceability views |
| Integration | REST APIs, webhooks, import/export, ERP integration, MES integration, CAD integration, document repositories, and identity providers |
| AI capabilities | Conversational search, document extraction, classification, data quality checks, relationship suggestions, change impact analysis, and copilots |

This table is the capability map at product level. Section 15 decomposes these areas into functional modules with feature-level detail; the two sections are maintained together.

---

## 4. SaaS and Tenant Model

PLM-IQ is a multi-tenant SaaS application. Every customer organization is represented as a tenant, with logical and security isolation for its users, data, configuration, workflows, and integrations.

### Tenant Characteristics

Each tenant has its own:

- Users, groups, roles, and permissions
- Business objects and product data
- Core attribes with extendable Tenant-specific attributes and schemas
- Edge types and edge rule extensions
- Lifecycle states and workflow definitions
- Numbering schemes, prefixes, and naming rules
- Classifications and taxonomies
- Search indexes and saved searches
- Integrations, API credentials, webhooks, and external mappings
- AI configuration, including approved knowledge sources and model policies
- Branding, language, date/time, units, and regional configuration

Tenant-level customization must be metadata-driven rather than source-code-driven. This preserves a shared SaaS platform while enabling enterprise-specific flexibility.

### Tenant Isolation

PLM-IQ enforces tenant isolation at several layers:

- Using postrest RLS feature
- Tenant identity is resolved from the incoming domain, authenticated user, and access token.
- Every business object, relationship, workflow item, file, event, and audit record is associated with a `tenantId`.
- Data access policies enforce tenant ownership before application-level authorization is evaluated.
- Search, graph traversal, AI retrieval, caching, and analytics must remain tenant-scoped.
- Files and attachments must be stored with tenant-aware object paths and access control.
- Tenant administrators can manage only their own tenant configuration and users.

### Isolation Mechanisms

Isolation claims above are implemented through concrete, testable mechanisms:

| Layer | Default Mechanism (Shared Platform Tier) |
|---|---|
| Relational data | Shared PostgreSQL cluster; mandatory `tenant_id` on every row enforced by native row-level security (RLS) policies in addition to application-level filtering |
| Search | Tenant-scoped indices (`plm_{index}_{tenant}`) or mandatory tenant filter clauses; index names never shared across tenants |
| Object storage | Tenant-prefixed keys (`tenants/{tenantId}/…`) with signed, time-bound access URLs |
| Cache and queues | Tenant-namespaced cache keys; per-tenant message routing keys so async workers can never process cross-tenant payloads |
| AI retrieval | Retrieval queries constrained to tenant-owned sources before ranking; verified by automated isolation test suites |
| Configuration | Tenant and edition metadata cached per tenant; invalidation scoped per tenant |

A dedicated-isolation option (dedicated schema, dedicated database, or fully dedicated cell) is available for enterprise and regulated tenants; see Section 17, Deployment and Isolation Topology.

---

## 5. Multi-Edition Strategy

PLM-IQ editions package common platform capabilities with domain-specific object types, relationship types, workflows, templates, validations, dashboards, and AI assistants.

### Edition Model

| Edition | Primary Use | Typical Industries | Key Capabilities |
|---|---|---|---|
| Foundation | General-purpose PLM | Any industry | Documents, items, parts, projects, change management, workflows, classification, search, audit trail |
| Discrete | Engineering and manufacturing PLM | Automotive, machinery, aerospace, industrial equipment, electronics | EBOM, MBOM, configurable BOM, part revisions, CAD/document links, alternates, substitutes, effectivity, manufacturing handoff |
| Process | Formula and process PLM | Chemicals, cosmetics, pharmaceuticals, CPG | Formulations, ingredients, raw materials, specifications, regulatory attributes, batch-related product definitions, process routes |
| Food | Food and beverage PLM | Food manufacturers, beverage companies, restaurants, private-label brands | Recipes, ingredients, allergens, nutrition, shelf life, labels, packaging, supplier specifications, food safety traceability |

### Common Platform vs Edition Features

The following remain common across all editions:

- Identity and access management
- Tenant administration
- Graph engine
- Lifecycle and revision management
- Workflow and approvals
- Notifications and collaboration
- Audit logging
- Search and reporting
- Integration framework
- File and document storage
- AI platform services
- Rules engine
- Extensibility framework

Each edition contributes a versioned metadata package containing:

- Vertex kinds
- Edge kinds
- Attribute definitions
- Validation rules
- Lifecycle templates
- Workflow templates
- Reports and dashboards
- UI workspaces
- AI prompts and agents
- Import/export templates
- Industry-specific integrations

### Edition Semantics and Upgrades

Editions are metadata packages layered over a shared, edition-neutral core. The `editionId` on a vertex or edge records which edition package currently governs its solution attributes, rules, lifecycles, and UI. It does not fragment the core data model.

Rules:

- A tenant activates exactly one edition at a time; the edition applies tenant-wide.
- System attributes (Section 8) are identical in every edition; only solution attributes differ. Switching editions never moves or rekeys core rows.
- Adopting a richer edition (for example, Foundation → Discrete) is a versioned metadata migration: install the edition package, extend vertex kinds with solution attribute definitions, backfill optional attributes, and re-stamp `editionId`. Objects remain valid throughout; the migration is reversible while no Discrete-specific attributes have been populated.
- Downgrades are permitted only if no edition-specific data exists; otherwise the tenant follows a controlled export/archive path.
- Cross-edition data sharing between tenants is impossible by construction because editions ride on tenant-scoped data.

---

## 6. Edition Domain Naming

Each customer tenant is accessed through an edition-aware subdomain.

### Domain Format

```text
{tenant}.{edition}.plm-iq.com
```

### Examples

```text
tesla.discrete.plm-iq.com
gucci.foundation.plm-iq.com
acme.process.plm-iq.com
freshfoods.food.plm-iq.com
```

### Naming Rules

- Tenant names must be globally unique within an edition namespace.
- Tenant names should use lowercase letters, numbers, and hyphens only.
- Edition identifiers should be controlled platform values.
- The domain identifies tenant and edition context before sign-in.
- Authentication tokens should include both `tenantId` and `editionId`.
- API requests must validate that the request tenant matches the authenticated tenant context.

| Edition | DNS Code |
|---|---|
| PLM-IQ Foundation | `foundation` |
| PLM-IQ Discrete | `discrete` |
| PLM-IQ Process | `process` |
| PLM-IQ Food | `food` |

### TLS and Custom Domains

- Because tenant subdomains are two levels below `plm-iq.com`, each edition namespace carries its own wildcard certificate (for example, `*.discrete.plm-iq.com`). Certificates are issued and renewed automatically by the edge layer.
- Enterprise tenants may map a vanity domain (for example, `plm.tenant.com`) to their tenant via CNAME; the platform provisions and renews the certificate automatically.
- Tenant subdomains are immutable through self-service. Renames are a support-managed operation that creates the new subdomain and serves redirects from the old one during a configurable grace period.

---

## 7. Graph-Based Core Model

PLM-IQ uses graph theory as the core business-modeling approach.

A graph consists of:

- **Vertices** — Business objects or entities
- **Edges** — Relationships between business objects
- **Edge annotations** — Metadata describing the relationship
- **Edge rules** — Constraints governing valid relationships
- **Graph traversal** — Navigation across connected product data
- **Graph queries** — Queries that identify dependencies, impacts, traceability, and relationship patterns

This model is particularly appropriate for PLM because product information is highly connected and changes can affect multiple downstream objects.

```text
Part → Document → Specification → Material → Supplier
Part → BOM Component → Subassembly → Product
Change Order → Affected Part → Affected Document → Affected Process Plan
Recipe → Ingredient → Allergen → Label Statement
```

A graph model allows PLM-IQ to answer business questions such as:

- Which documents define this part?
- Which products use this component?
- What is the impact of changing this material?
- Which released products contain a non-compliant supplier material?
- Which specifications are linked to a recipe?
- Which downstream manufacturing BOMs are impacted by an engineering BOM revision?
- Which objects are affected by a change order?
- Which products contain an allergen or restricted substance?

---

## 8. Vertex Model

A vertex represents a business object within the PLM-IQ graph.

Examples include:

- Part
- Document
- Specification
- Product
- Material
- Ingredient
- Recipe
- Formula
- Supplier
- Manufacturer
- Plant
- Change Request
- Change Order
- Project
- Requirement
- Test Case
- Quality Record
- CAD Model
- Packaging
- Label
- Regulation
- Classification

### Vertex Categories

Each vertex contains three categories of attributes:

| Attribute Category | Description |
|---|---|
| System attributes | Attributes managed by PLM-IQ, such as ID, tenant, creation date, revision, lifecycle state, and audit details |
| Solution attributes | Attributes defined by the relevant PLM-IQ edition, such as part number, material grade, recipe yield, or allergen status |
| Tenant extension attributes | Customer-specific attributes created through tenant configuration without platform code changes |

### Standard Vertex Schema

All examples in this document use one coherent timeline: objects are created in 2025, released on 2026-01-01, and linked specifications remain valid through 2027-01-01.

```yaml
Vertex:
  id: "uuid"
  tenantId: "tenant-uuid"
  editionId: "discrete"
  kind: "Part"            # enum: Part | Document | EC — extended only via edition packages
  lifecycleState: "Released"
  revision: "A"
  releaseOn: "2026-01-01"
  number: "1234"
  prefix: "V"             # platform default; tenant numbering rules may override
  name: "Electric Motor Housing"
  description: "Machined aluminum housing for motor assembly"
  createdBy: "Dane"
  createdOn: "2025-06-01T09:00:00Z"
  modifiedBy: "Nick"
  modifiedOn: "2025-06-02T14:30:00Z"
  markedForDeletion: false
  version: 3              # database autoincrement; monotonic optimistic-lock token
  classificationId: "cls-metal-parts"
  solutionAttributes:
    material: "Aluminum 6061"
    makeBuyType: "Make"
    unitOfMeasure: "EA"
  tenantAttributes:
    customerPartCode: "TES-MTR-HSG-001"
    internalProgram: "EV Platform X"
```

### Required System Attributes

| Attribute | Description |
|---|---|
| `id` | Globally unique identifier for the vertex |
| `tenantId` | Identifier of the owning tenant |
| `editionId` | Edition package that governs this object's solution attributes (see Section 5) |
| `kind` | Business object type, such as Part, Document, Recipe, or Material |
| `number` | Human-readable business identifier |
| `prefix` | Numbering prefix forming the display identifier (`{prefix}-{number}`); defaults to `V` |
| `name` | Primary display name |
| `description` | Detailed description |
| `revision` | Revision identifier, such as A, B, C, 01, or 02 |
| `lifecycleState` | Current lifecycle state, such as Draft, In Review, Released, Obsolete, or Superseded |
| `releaseOn` | Effective release date |
| `createdBy` | User who created the object |
| `createdOn` | Object creation timestamp |
| `modifiedBy` | User who last updated the object |
| `modifiedOn` | Most recent modification timestamp |
| `markedForDeletion` | Soft-delete indicator |
| `version` | Autoincrementing optimistic-lock token maintained by the database; incremented automatically on every update |
| `classificationId` | Optional classification or taxonomy reference |

### Effectivity Vocabulary

One vocabulary is used platform-wide:

- `releaseOn` — vertex-level release date.
- `effectiveFrom` / `effectiveTo` — validity windows on edges and edge annotations.
No other spelling (`effectivityFrom`, `validFrom`, and similar) may appear in schemas, APIs, or documentation.

### Vertex Lifecycle Example

A standard lifecycle model can be:

```text
Draft → In Review → Approved → Released → Superseded → Obsolete
```

The exact lifecycle is configurable by edition and tenant.

```text
Food: Concept → Formulation → Sensory Review → Regulatory Review → Pilot → Approved → Commercialized → Retired
Discrete: Preliminary → Prototype → Engineering Review → Released → Production → Superseded → Obsolete
```

---

## 9. Edge Model

An edge represents a relationship between two vertices.

Edges are first-class entities because relationships in PLM carry important business meaning, governance, lifecycle context, and metadata. A part linked to a document may identify a specification, drawing, inspection report, operating instruction, or regulatory certificate.

### Kind versus Name

Every edge has exactly one structural **kind** drawn from the controlled catalog in Section 10 (for example, `REFDOCS`), plus a human-readable **name** that labels the specific relationship variant (for example, `"Has specification"`). Named variants such as `HAS_SPEC` or `HAS_PRIMARY_SPEC` are names of `REFDOCS` edges, not kinds. Validation rules bind to kinds; UI labels and saved searches bind to names. Edge endpoints (`sourceVertexKind`, `targetVertexKind`) are constrained to the Vertex.kind enum.

### Standard Edge Schema

```yaml
Edge:
  id: "uuid"
  tenantId: "tenant-uuid"
  editionId: "discrete"
  kind: "REFDOCS"
  name: "Has specification"
  sourceVertexId: "part-uuid"
  sourceVertexKind: "Part"
  targetVertexId: "document-uuid"
  targetVertexKind: "Document"
  lifecycleState: "Active"
  effectiveFrom: "2026-01-01"
  effectiveTo: "2027-01-01"
  graphRuleId: "part-document-refdocs-rule"
  prefix: "E"             # platform default; tenant numbering rules may override
  version: 1              # database autoincrement; monotonic optimistic-lock token
  createdBy: "Dane"
  createdOn: "2025-06-01T09:00:00Z"
  modifiedBy: "Nick"
  modifiedOn: "2025-06-02T14:30:00Z"
  annotation:             # inline attribute of the Edge — no separate entity or table
    note: "Specification valid until 1 January 2027"
    quantity: null
    unitOfMeasure: null
    findNumber: null
    referenceDesignator: null
    usageType: null
    percentage: null
    variantCondition: null
    substituteConditions: null
  tenantAttributes:
    referenceCategory: "Engineering Specification"
    mandatoryForRelease: true
```

### Edge Attributes

| Attribute | Description |
|---|---|
| `id` | Globally unique edge identifier |
| `tenantId` | Tenant ownership and isolation identifier |
| `editionId` | Relevant product edition |
| `kind` | Structural relationship category from the Section 10 catalog, such as BOM, REFDOCS, CONTAINS, or AFFECTS |
| `name` | Human-readable relationship variant label, such as "Has specification" or "Has drawing" |
| `sourceVertexId` | ID of the source business object |
| `sourceVertexKind` | Type of the source business object; must be a Vertex.kind enum value |
| `targetVertexId` | ID of the target business object |
| `targetVertexKind` | Type of the target business object; must be a Vertex.kind enum value |
| `annotation` | Inline structured payload persisted as part of the edge itself (Section 11) |
| `effectiveFrom` | Date when the relationship becomes valid |
| `effectiveTo` | Date when the relationship expires or is no longer valid |
| `lifecycleState` | Current state of the relationship |
| `graphRuleId` | Rule definition governing this relationship |
| `prefix` | Numbering prefix forming the display identifier (`{prefix}-{number}`); defaults to `E` |
| `version` | Autoincrementing optimistic-lock token maintained by the database; incremented automatically on every update |
| `tenantAttributes` | Configurable customer-specific relationship metadata |

---

## 10. Edge Types

PLM-IQ provides a controlled catalog of structural edge kinds while allowing each edition and tenant to define additional relationship types. Named variants (Section 9) distinguish business meanings inside one kind; for example, "Has specification" and "Has drawing" are both `REFDOCS` edges differentiated by name and by rules.

| Edge Kind | Source | Target | Purpose |
|---|---|---|---|
| `BOM` | Part or Product | Part or Material | Defines a product structure or bill of materials |
| `REFDOCS` | Part, Product, Material, Recipe | Document | Links a business object to supporting documentation; covers specification, drawing, inspection-plan, and certificate references through named variants |
| `USES` | Product, Recipe, Formula | Material, Ingredient, Part | Identifies consumption or usage relationships |
| `MANUFACTURED_BY` | Part or Product | Manufacturer or Plant | Identifies manufacturing responsibility |
| `SUPPLIED_BY` | Material or Part | Supplier | Identifies approved or potential suppliers |
| `AFFECTS` | Change Order | Any business object | Identifies objects affected by a change |
| `SUPERSEDES` | Vertex | Vertex | Defines replacement or revision succession |
| `ALTERNATE_FOR` | Part | Part | Defines approved alternatives |
| `SUBSTITUTE_FOR` | Part or Material | Part or Material | Defines conditional replacement relationships |
| `COMPLIES_WITH` | Product, Material, Part | Regulation or Requirement | Establishes compliance traceability |
| `CONTAINS` | Recipe, Product, Assembly | Ingredient, Material, Part | Defines contained components |
| `VALIDATED_BY` | Requirement or Specification | Test Case or Quality Record | Links requirements to validation evidence |
| `PACKAGED_IN` | Product | Packaging | Links product definition to packaging components |
| `HAS_LABEL` | Product | Label | Links product to labeling content |

---

## 11. Edge Annotations

Edge annotations capture business meaning beyond simply connecting two vertices.

A BOM relationship can include quantity, unit of measure, find number, reference designator, usage type, scrap factor, effective period, variant applicability, substitute conditions, assembly notes, and manufacturing sequence.

A relationship between a food product and an ingredient can include ingredient quantity, percentage contribution, supplier qualification status, country of origin, allergen contribution, nutritional impact, organic certification status, and regulatory restrictions.

Annotation attribute names follow the Section 8 effectivity vocabulary: validity windows are always `effectiveFrom` / `effectiveTo`.

### Example BOM Edge Annotation

```yaml
Edge:
  kind: "BOM"
  sourceVertexKind: "Assembly"
  targetVertexKind: "Part"
  annotation:
    quantity: 4
    unitOfMeasure: "EA"
    findNumber: "020"
    usageType: "Required"
    effectiveFrom: "2026-01-01"
    effectiveTo: null
    variantCondition: "BatteryType = LongRange"
    referenceDesignator: "M1,M2,M3,M4"
```

### Example Food Ingredient Edge Annotation

```yaml
Edge:
  kind: "CONTAINS"
  sourceVertexKind: "Recipe"
  targetVertexKind: "Ingredient"
  annotation:
    quantity: 12.5
    unitOfMeasure: "KG"
    percentage: 8.25
    allergenContribution: "Contains milk"
    countryOfOrigin: "India"
    supplierApproved: true
    organicStatus: "Certified Organic"
```

---

## 12. Graph Rules

Graph rules govern which relationships are allowed between business objects and how those relationships behave. They enforce semantic consistency, data quality, and lifecycle integrity across the product graph.

A graph rule defines:

- Rule scope: platform, edition, or tenant
- Permitted source vertex type
- Permitted target vertex type
- Edge kind
- Direction of the relationship
- Cardinality on each side
- Participation requirements
- Lifecycle compatibility
- Revision compatibility
- Effectivity rules
- Duplicate relationship policy
- Attribute validation requirements
- Approval requirements
- Tenant-level extension behavior

### Rule Scope

Rules carry an explicit `scope` value instead of borrowing `tenantId`:

| Scope | Meaning | Author |
|---|---|---|
| `platform` | Core structural rule shipped with the product | Platform team only |
| `edition` | Refinement delivered by an edition package | Edition team only |
| `tenant` | Tenant-controlled extension within platform and edition constraints | Tenant administrator |

Tenants cannot create or modify `platform` or `edition` rules. Precedence resolution (Section 13) orders rules by scope.

### Core Graph Rule Structure

```yaml
GraphRule:
  id: "part-document-refdocs-rule"
  scope: "platform"
  editionId: "foundation"
  edgeKind: "REFDOCS"
  sourceVertexKind: "Part"
  targetVertexKind: "Document"
  sourceCardinality: "0..N"
  targetCardinality: "0..N"
  sourceParticipation: "Optional"
  targetParticipation: "Optional"
  duplicateEdgesAllowed: false
  sourceLifecycleStates:
    - Draft
    - In Review
    - Released
  targetLifecycleStates:
    - Approved
    - Released
  requiredEdgeAttributes:
    - referenceCategory
  allowTenantExtension: true
```

### Cardinality Notation

Cardinalities bound the number of relationship partners an object may have on each side independently; participation states whether the relationship is required. The canonical shorthand is:

```text
SourceKind[sourceMin..sourceMax] — EDGE-KIND → [targetMin..targetMax] TargetKind
```

| Cardinality | Meaning |
|---|---|
| `0..1` | Zero or one relationship partner on this side |
| `1..1` | Exactly one relationship partner on this side |
| `0..N` | Zero, one, or many relationship partners on this side |
| `1..N` | At least one relationship partner on this side; many are allowed |

Overall relationship multiplicity falls out of the two sides: when both sides allow N, the relationship is many-to-many.

### Example: Part to Document Rule

```text
Part[0..N] — REFDOCS → [0..N] Document
```

Interpretation:

- One part can reference many documents.
- One document can be referenced by many parts.
- The relationship is many-to-many.
- Participation is optional on both sides by default; tenant extensions may require, for example, at least one approved Drawing before a Part is Released.

```text
Part A → Drawing 1001
Part A → Specification 2010
Part A → Inspection Plan 3007

Part B → Drawing 1001
Part C → Drawing 1001
```

### Example: Assembly to Component Rule

```text
Assembly[1..N] — BOM → [0..N] Part
```

An assembly must contain at least one component to be Released; a component may be used by zero or many assemblies. The relationship is therefore many-to-many even though the assembly side enforces a minimum. The BOM edge annotation includes quantity, unit of measure, effectivity, and variant applicability.

### Example: Product to Primary Specification Rule

```text
Product[1..1] — REFDOCS("Has primary specification") → [1..1] Specification
```

Every Released product must have exactly one primary specification, modeled as a named `REFDOCS` edge (Section 9) with mandatory participation on both sides. A product cannot enter the Released state without a valid linked specification.

---

## 13. Tenant-Level Graph Rule Extensions

PLM-IQ must allow tenants to extend graph rules without changing the platform core. Tenant extensions must be controlled, versioned, validated, and auditable.

### Permitted Tenant Extensions

A tenant administrator may be allowed to:

- Add tenant-specific attributes to an existing vertex kind.
- Add tenant-specific attributes to an existing edge kind.
- Add new custom vertex kinds where permitted by the edition.
- Add new custom edge kinds where permitted by the edition.
- Create tenant-specific naming and numbering rules.
- Add validation rules for custom attributes.
- Define required edge annotations.
- Restrict cardinality beyond the default platform rule.
- Add lifecycle state restrictions.
- Add workflow approval requirements.
- Configure which fields are mandatory for release.
- Create custom classifications and taxonomies.
- Add custom relationship labels for the tenant UI.

All tenant-authored rules carry `scope: "tenant"` (Section 12); tenants cannot author or alter `platform` or `edition` rules.

### Controlled Extension Principles

Tenant extensions must not:

- Bypass tenant-isolation controls.
- Remove platform-level audit requirements.
- Weaken mandatory compliance validations defined by the edition.
- Break system-owned graph relationships.
- Introduce incompatible data types into core attributes.
- Create unrestricted cross-tenant relationships.
- Modify system-level object IDs, audit fields, or immutable historical records.
- Remove required relationship constraints from released data.

### Extension Precedence

Rules resolve deterministically by scope, then by specificity:

```text
Platform Core Rule (scope: platform)
→ Edition Rule (scope: edition)
→ Tenant Rule Extension (scope: tenant)
→ Object-Specific Validation
```

Example:

```text
Platform: A Part may reference Documents.
Discrete Edition: A Part can reference Drawings, Specifications, and Inspection Plans.
Tenant Extension: A released Part must reference at least one approved Drawing.
Object-Specific Validation: A safety-critical Part must reference a Safety Certification document.
```

---

## 14. AI-First Strategy

AI capabilities should be embedded into PLM-IQ workflows rather than positioned as a separate chatbot feature. The AI layer must use tenant-scoped retrieval, permissions-aware graph traversal, metadata, documents, and approved enterprise knowledge sources.

| Capability | Description |
|---|---|
| Conversational PLM search | Users ask questions in natural language, such as “Show all released assemblies affected by Supplier X.” |
| Graph impact analysis | AI identifies direct and indirect downstream effects of a change to a part, material, specification, or supplier |
| Document intelligence | AI extracts metadata, classifications, specifications, measurements, and requirements from uploaded documents |
| Relationship suggestions | AI suggests probable links between parts, documents, materials, specifications, and suppliers |
| Data quality validation | AI identifies incomplete, inconsistent, duplicate, or suspicious product records |
| Change assistant | AI summarizes changes, identifies affected objects, drafts impact assessments, and proposes change tasks |
| Classification assistance | AI suggests part classes, document categories, material types, ingredient categories, and regulatory tags |
| Specification comparison | AI identifies differences between document revisions, specifications, formulations, or product configurations |
| Regulatory traceability | AI helps identify products potentially affected by regulatory, supplier, material, or formulation changes |
| Content generation | AI drafts descriptions, release notes, change summaries, supplier communications, and documentation templates |

### AI Guardrails

- AI retrieval must be tenant-scoped and permission-aware.
- AI must not expose data from one tenant to another.
- AI-generated content must be clearly identified as generated or suggested.
- High-impact actions, such as releasing parts, approving changes, or modifying BOMs, require user approval.
- AI recommendations should include traceable source objects wherever possible.
- AI must not silently alter released product data.
- Prompts, outputs, and user approvals should be auditable based on tenant policy.
- Sensitive-data handling must align with customer contractual and regulatory requirements.

### AI Operational Risk Controls

Beyond authorization guardrails, four operational risk classes are explicitly controlled:

| Risk | Control |
|---|---|
| Prompt injection via uploaded documents | Document content is treated as untrusted input: extraction runs in a sandboxed prompt context, extracted values are validated against target schemas before persistence, and document content can never trigger tools, workflow actions, or data writes without explicit user confirmation |
| LLM provider data exposure | Only approved model endpoints with contractual no-training and bounded-retention terms may process tenant data; per-tenant provider allowlists; EU-processing option for regulated tenants; provider selection recorded in tenant AI configuration and audited |
| Uncontrolled AI spend | Per-tenant monthly AI credit budgets with soft alerts and optional hard caps; per-request token limits; circuit breakers degrade to non-AI flows when budgets are exhausted; model routing sends simple tasks to lower-cost models |
| Poor or regressing output quality | Versioned prompts and agents evaluated against per-edition golden sets before any rollout; confidence thresholds route low-confidence suggestions to human review instead of auto-applying; acceptance-rate telemetry feeds evaluation dashboards |

---

## 15. Core Functional Modules

This section decomposes the Section 3 scope table into module-level features.

### Product Definition

- Parts and product records
- Materials and ingredients
- Documents and attachments
- Specifications and requirements
- Product classifications
- Revisions and lifecycle states
- Numbering and naming rules
- Attribute management
- Tenant-specific extensions
- Product templates

### Product Structure Management

- Engineering BOMs
- Manufacturing BOMs
- Service BOMs
- Configurable BOMs
- Multi-level BOM traversal
- Alternates and substitutes
- Reference documents
- Usage relationships
- Effectivity management
- Variant conditions
- Where-used analysis
- Structure comparison across revisions

### Change Management

- Change requests
- Problem reports
- Change notices
- Change orders
- Impacted-object relationships
- Approval workflows
- Release packages
- Change implementation tasks
- Revision creation
- Effectivity management
- Audit history

### Document Management

- Document creation and upload
- Version and revision control
- Document classification
- Document approval workflows
- Document-to-object relationships
- Full-text search
- OCR and AI-assisted extraction
- Document version comparison
- Controlled access and download policies
- Document release and obsolescence

### Workflow and Lifecycle Management

- Lifecycle templates
- State-transition rules
- Approval routing
- Task assignment
- Escalations
- Notifications
- Electronic signatures where required
- Conditional workflow steps
- Role-based approvals
- Workflow audit trails

### Search, Reporting, and Analytics

- Full-text search
- Structured search
- Faceted search
- Semantic AI search
- Saved searches
- Graph traversal views
- Where-used reports
- Impact-analysis reports
- Change dashboards
- Data-quality dashboards
- Compliance dashboards
- Tenant-specific reports

---

## 16. Logical Architecture

PLM-IQ should use a modular cloud-native architecture that supports tenant isolation, edition packaging, scalable graph operations, AI workflows, and enterprise integrations.

```text
Web Application
    ↓
API Gateway / Edge Layer
    ↓
Identity and Tenant Resolution
    ↓
PLM-IQ Application Services
    ├── Vertex Service
    ├── Edge Service
    ├── Graph Rule Engine
    ├── Lifecycle Service
    ├── Workflow Service
    ├── Document Service
    ├── Search Service
    ├── Change Management Service
    ├── Configuration Service
    ├── Tenant Administration Service
    ├── Integration Service
    ├── Notification Service
    └── AI Orchestration Service
    ↓
Data and Platform Layer
    ├── Graph Store (Phase 1: PostgreSQL hybrid — see below)
    ├── Relational Transaction Database
    ├── Object Storage
    ├── Search Index
    ├── Vector Store (from Phase 3)
    ├── Cache
    ├── Event Bus
    ├── Audit Store
    └── Analytics Store
```

### Data Storage Decision

Phase 1 adopts the PostgreSQL-hybrid storage model defined in `metamodel-prd.md`:

- Vertices and edges are stored relationally with adjacency columns; traversals use recursive CTEs and tuned indexes.
- Configurable payloads live inline on the graph elements as JSONB documents — `solutionAttributes`/`tenantAttributes` on vertices, `tenantAttributes`/`annotation` on edges. This supersedes the metamodel PRD's typed value-column tables (`node_attribute`, `edge_annotation`); reintroduce typed columns only if attribute-level query performance demands it.
- The physical schema ships as `database/schema/001_graph_core.sql`: everything lives in the dedicated `"plm-iq"` schema (double-quoted in SQL — the name contains a hyphen) with tables `core_vertex`, `core_edge`, and `core_graph_rule`; row-level-security policies keyed on the `app.tenant_id` session setting; and database-autoincremented `version` columns. Sample data lives in `database/seed/001_graph_seed.sql` (5 rows per table, FK-consistent), applied via `deploy-schema.bat -seed`.
- Elasticsearch handles full-text and faceted search; object storage holds files; the audit store is append-only.
- A dedicated graph engine is deferred. Revisit triggers are explicit: sustained p95 where-used or impact-traversal latency beyond the Section 21 SLO at production depth (≥ 4 hops), or query classes that cannot be expressed efficiently in SQL. Until a trigger fires, no second graph technology is introduced.

This decision trades theoretical graph-database fit for one fewer datastore, mature operations, and transactional consistency during the phases where reliability and speed of delivery matter most.

### Data Storage Strategy

| Data Type | Recommended Storage Pattern |
|---|---|
| Product graph, vertices, edges, traversals | PostgreSQL hybrid graph model (above); dedicated graph database only if revisit triggers fire |
| Transactional tenant configuration, users, workflows, permissions | Relational database |
| Files, drawings, documents, images, CAD files | Object storage |
| Full-text and faceted search | Search engine |
| Embeddings and semantic retrieval | Vector store or vector-enabled database |
| Events and asynchronous processing | Event bus or message queue |
| Audit trail and immutable compliance history | Append-only audit store |
| Dashboards and reporting | Analytics warehouse or reporting datastore |

The application maintains strong transaction boundaries for critical lifecycle and release actions. Graph updates, audit records, events, search indexing, and AI indexing are coordinated using transactional-outbox and event-driven patterns.

### Cross-Store Consistency

Multiple stores must not drift silently:

- All writes originate in one relational transaction; search, AI, and analytics projections consume a transactional outbox through the event bus.
- Indexing is asynchronous with a stated freshness target: p95 index lag below 5 seconds, alerting at p99 above 30 seconds.
- Visibility rule: search results reflect committed data only; unreleased or rolled-back states are never indexed.
- Idempotent consumers and periodic reconciliation jobs compare store counts/checksums and repair drift automatically; reconciliation outcomes are themselves auditable.
- Every projection carries the source transaction id so support can trace any displayed value back to its committing write.

### Concurrency Control

- Optimistic locking (`version`) applies to all vertex and edge mutations.
- BOM and structure editing uses line-level locks plus optional document/structure checkout (reservation) for long-running edits; simultaneous edits to the same BOM line surface a merge dialog rather than silent last-writer-wins.
- Bulk edits executed under a change order are serialized per change order to keep affected-object sets coherent.
- Released objects are never mutated in place; corrections go through revision/supersession or the change process (Section 23, Design Principle 3).

### Deletion, Retention, and Erasure

- Deletion is soft (`markedForDeletion`), followed by a retention-window purge job.
- Hard purge removes business content and personal data; the append-only audit trail retains an irreducible skeleton (action, object class, timestamp) with actor identity pseudonymized after a verified erasure request, satisfying GDPR erasure without weakening audit integrity.
- Legal hold or open workflow attachment blocks purge until released.
- Retention periods are configurable per tenant within edition and regulatory minimums (see Section 20).

---

## 17. Deployment and Isolation Topology

- **Regional deployments.** Each served region hosts a complete, independently upgradable stack; tenants are pinned to a home region at provisioning (data-residency requirement), with documented cross-region read options for global enterprises later.
- **Default topology: shared platform.** Tenants run on shared Kubernetes compute and a shared PostgreSQL cluster protected by the Section 4 isolation mechanisms. Noisy-neighbor protection comes from per-tenant API rate limits, worker-queue fairness, per-tenant AI budgets (Section 14), and statement-timeout guards.
- **Premium topology: dedicated cell.** An enterprise option pins a tenant (or tenant group) to a dedicated cell: isolated compute namespace, dedicated database instance or schema, dedicated search indices, and optionally customer-managed encryption keys. Cells run the same images and metadata as the shared platform; cell membership is pure infrastructure routing.
- **Upgrades.** Blue-green or rolling deployments per region; database migrations are backward-compatible for one release (expand/contract) so shared-platform tenants never require coordinated downtime.
- **Environment promotion.** The same container images and edition metadata packages progress through dev → staging → production; tenant-visible configuration differences live only in metadata, never in code branches.

---

## 18. Migration and Onboarding

Adoption hinges on getting legacy product data in; migration is a first-class product capability, not a services afterthought.

### Import Maturity Ladder

| Stage | Capability | Availability |
|---|---|---|
| 1 | Guided CSV/XLSX import with editable templates, validation reports, and error quarantine | Phase 1 (roadmap) |
| 2 | REST bulk-import API with idempotent batches, dry-run mode, and progress tracking | Phase 2 |
| 3 | Connector-based migration from Windchill, Teamcenter, 3DEXPERIENCE, and SAP ERP (items, BOMs, documents, revisions) | Phase 5 |
| Ongoing | CAD file initial load through the integrated Git repository (Gitea) ingestion path | Phase 1 |

### Onboarding Flow

1. Discovery: automated assessment of source exports (object counts, attribute coverage, rule conflicts).
2. Sandbox import: full trial load into a tenant sandbox with a data-quality report.
3. Corrective mapping iterations using import-template configuration.
4. Production cutover with rollback-safe batching and verification counts.
5. Hypercare checklist: search sanity, workflow smoke tests, AI feature calibration.

Reference target: a 100,000-part discrete dataset migrates from validated CSV to a production-ready tenant in under ten working days. This target is tracked as a success metric (Section 26).

---

## 19. Commercial Model

### Packaging

Commercial offering = Edition (Section 5) × Tier. Tiers gate platform capacity and enterprise controls, not core PLM correctness:

| Tier | Positioning | Gates |
|---|---|---|
| Starter | Small teams piloting PLM | Core PLM modules, community support, shared platform only, base AI credits |
| Business | Growing organizations | SSO (OIDC/SAML), higher API and AI allowances, webhooks, sandbox environment, priority support |
| Enterprise | Regulated and large organizations | Dedicated-cell option, custom domains, IP allowlists, customer-managed keys, residency pinning, compliance attestations, premium support |

Per-edition pricing reflects package value; tier pricing reflects platform controls and scale.

### Metering

All billing-relevant consumption flows through the event bus into a metering store, making invoices reproducible from raw events:

- Billable counters: named user seats (monthly peak), object-storage GB-months, outbound API calls, webhook deliveries, AI credits consumed (per model class).
- Counters are exposed to tenant administrators in near real time via usage dashboards and a usage API.
- Monthly aggregation closes into the billing system; adjustments are themselves metered events for auditability.

### AI Cost Policy

- AI features consume credits from the tenant's monthly allowance; allowance scales with tier and purchasable overage.
- Administrators configure per-feature weights, soft-alert thresholds (80 percent by default), and optional hard caps; exceeding a hard cap degrades gracefully to non-AI flows rather than failing workflows.
- Model routing policy: extraction and classification default to efficient models; complex reasoning tasks may use premium models at higher credit cost, visible in the cost estimator before execution.

---

## 20. Compliance and Certification

Certification is a sales prerequisite in target markets and is planned, not aspirational:

| Program | Target Window | Notes |
|---|---|---|
| SOC 2 Type II | Within 12 months of GA | Trust-services security, availability, confidentiality; audit logging and access control already satisfy most criteria by design |
| ISO/IEC 27001 | Year 2 | ISMS built on the same control library as SOC 2 to avoid duplicate work |
| GDPR baseline | At GA | DPA template, SCCs for cross-border transfers, erasure flow per Section 16, data-residency pinning per Section 17 |
| FDA 21 CFR Part 11 readiness | With Food/Process editions (Phase 4) | Closed-loop e-records/e-signatures: signature manifestations, immutable audit trails, validated release workflows, vendor validation documentation package |
| EU GMP Annex 11 alignment | Year 2 after Food GA | Extends Part 11 controls for pharmaceutical tenants |

Supporting assets maintained continuously: penetration-test summaries, architecture security whitepaper, standard questionnaires (CAIQ, SIG), subprocessor list, and status page — packaged for procurement review.

---

## 21. Service Levels, Observability, and Disaster Recovery

### Service-Level Objectives

| Objective | Target |
|---|---|
| API availability (monthly) | 99.9% (Business/Enterprise; 99.5% Starter) |
| API latency | p95 < 400 ms for interactive reads; p95 < 800 ms for writes |
| Search index freshness | p95 lag < 5 s behind commit |
| Where-used / impact traversal (≤ 4 hops) | p95 < 2 s on reference-scale datasets |
| Webhook delivery | p95 < 30 s from triggering event |

### Observability

- Unified metrics, distributed traces, and structured logs across all services; traces propagate tenant and request identifiers for support triage.
- Per-tenant usage analytics power both the Section 19 dashboards and abuse detection.
- Synthetic probes exercise sign-in, search, BOM view, and document download per region; SLO burn-rate alerts page on-call.
- Error budgets gate release velocity: a exhausted quarterly budget freezes feature deploys in favor of reliability work.

### Incident Management and DR

- Severity matrix (SE1–SE4) with response and update-cadence commitments tied to support tier.
- Backups: continuous WAL archiving with point-in-time restore retained 35 days; object storage versioned; search indices rebuildable from source-of-truth stores (verified by restore drills).
- Targets: RPO ≤ 15 minutes; RTO ≤ 4 hours per region.
- Regional failover runbook rehearsed semiannually; DR drill results summarized to enterprise customers on request.

---

## 22. Security and Governance

PLM-IQ manages sensitive product, engineering, supplier, formula, quality, and compliance information. Security and governance must therefore be core platform capabilities.

### Security Requirements

- Tenant-level logical data isolation (mechanisms in Section 4, topology options in Section 17)
- Role-based access control
- Attribute-level and relationship-level access control where required
- Permission-aware graph traversal
- Single sign-on using SAML 2.0 or OpenID Connect
- Multi-factor authentication support
- Encryption in transit and at rest
- Secure file access with time-bound signed URLs
- Immutable audit history for critical actions
- Configurable retention policies (Section 16)
- IP allowlists and session controls for enterprise tenants
- Secrets management for integrations
- API rate limiting and abuse protection
- Tenant-scoped encryption keys where required by enterprise customers (customer-managed keys available as an Enterprise-tier option from Phase 2)

### Governance Requirements

- Full audit history for vertex, edge, attribute, lifecycle, and workflow changes
- Revision and release traceability
- Configurable approval and electronic-signature controls (Part 11-capable per Section 20)
- Controlled deletion using soft-delete and retention policies
- Data-export capabilities for tenant offboarding
- Data residency support where commercially required (Section 17)
- Edition and tenant configuration versioning
- Rule versioning for graph rules and validation logic

---

## 23. Key Design Principles

1. **Relationships are first-class data.** Edges must carry metadata, governance, lifecycle state, audit history, and business meaning.
2. **Configuration over customization.** Customers should extend the solution through metadata, attributes, rules, workflows, and templates rather than custom code.
3. **Released data is governed.** Released vertices and edges must be immutable or controlled through revision, supersession, and approved change processes.
4. **Every action is tenant-aware.** Tenant context must be mandatory in all APIs, events, storage paths, search indexes, AI retrieval, and audit records.
5. **Every important change is traceable.** The platform must track who changed what, when, why, and through which workflow.
6. **AI is assistive, not uncontrolled.** AI can recommend, summarize, classify, and detect risks, but critical business actions require human authorization — and AI operations are subject to the Section 14 operational risk controls.
7. **Edition packages remain upgradeable.** Industry-specific editions should be delivered as versioned metadata and service capabilities without separate codebases.
8. **Graph rules protect semantic consistency.** Object types and relationships must be validated against platform, edition, and tenant-level rules.
9. **Everything billable is measured.** Seats, storage, API usage, and AI consumption emit metering events (Section 19); commercial boundaries are enforced by the same platform primitives that isolate tenants.

---

## 24. Illustrative Example

Consider a discrete manufacturing tenant named Tesla using PLM-IQ Discrete.

```text
URL: tesla.discrete.plm-iq.com
```

The tenant creates a released assembly (created June 2025, released January 2026):

```text
Kind: Assembly
Number: ASM-1000
Name: Electric Drive Unit
Revision: B
Created On: 2025-06-01
Lifecycle State: Released
Release On: 2026-01-01
```

The assembly has a BOM relationship to an electric motor:

```text
Kind: BOM
Source: ASM-1000 Electric Drive Unit
Target: PRT-2001 Electric Motor
Quantity: 1
Unit of Measure: EA
Effective From: 1 January 2026
```

The electric motor has a named reference-document relationship to a technical specification:

```text
Kind: REFDOCS
Name: Has specification
Source: PRT-2001 Electric Motor
Target: DOC-3010 Motor Technical Specification
Effective From: 1 January 2026
Effective To: 1 January 2027
Annotation: Approved specification valid until 1 January 2027
```

A supplier-material change may affect the motor, the drive-unit assembly, and vehicle configurations using that assembly. PLM-IQ traverses graph relationships to identify the full impact chain.

```text
Supplier Material Change
→ Motor Part
→ Drive Unit Assembly
→ Vehicle Product Configuration
→ Released Manufacturing BOM
→ Service Documentation
```

This illustrates the central value of the graph-based PLM-IQ model: direct, explainable traceability from a change or issue to all related product records.

---

## 25. Product Roadmap

Phases are sliced so each delivers a usable product increment with measurable exit criteria (consolidated metrics in Section 26).

### Phase 1: Thin Vertical Slice — Foundation MVP

Goal: one tenant journey end-to-end — import parts and documents, connect them, search them, release them, audit it all.

- Multi-tenant core: shared PostgreSQL with row-level security, tenant resolution from domain and token
- Identity, roles, groups, access control; SSO via OIDC
- Foundation edition subset: Parts, Documents, Specifications
- Edges: `BOM` and `REFDOCS` with cardinality, duplicate-policy, and lifecycle-state rules
- Lifecycle and revision management: Draft → In Review → Approved → Released
- Document upload/download with Gitea-backed CAD/file storage
- Elasticsearch full-text search and basic graph navigation (where-used)
- Audit logging, REST API v1 (versioning policy fixed: `/v1` compatible for 12 months)
- CSV import with validation reports (Migration Stage 1)
- Tenant-level attribute extension

Exit criteria: pilot tenant completes import-to-release of a 1,000-part dataset; where-used p95 < 2 s; isolation test suite passes; CSV import success rate > 95% on well-formed input.

### Phase 2: Discrete Manufacturing Depth

- Part and assembly management; EBOM and multi-level BOM
- Change requests and change-order workflows with impact analysis
- Where-used analysis, effectivity management
- Alternates and substitutes; configurable BOM foundation
- AI document classification and extraction (sandboxed per Section 14)
- Integration framework contract v1: outbound event catalog (JSON Schema), webhooks with retries and signatures, OAuth2 client credentials, rate-limit and pagination standards
- Bulk-import REST API (Migration Stage 2); customer-managed keys available as Enterprise option
- Onboarding toward SOC 2 Type II evidence collection

Exit criteria: change-order cycle (request → affected objects → approval → release) usable without support; 3 design-partner tenants in weekly production use; webhook/event contract published and consumed by one external system.

### Phase 3: Advanced Intelligence

- AI-powered semantic search (vector store introduced here)
- AI-assisted graph relationship suggestions and impact analysis
- AI change-summary generation; document comparison
- Data quality and duplicate detection; rule recommendation engine
- Tenant knowledge-base retrieval; prompt/agent evaluation harness with golden sets
- AI credit metering dashboards (Section 19) generally available

Exit criteria: AI suggestion acceptance rate > 40%; semantic search judged better than keyword baseline on the evaluation set; zero tenant-boundary findings in AI red-team exercises.

### Phase 4: Process and Food Editions

- Materials, formulas, recipes, and ingredients
- Formula and recipe revision management
- Supplier and raw-material qualification
- Allergen and nutrition management; shelf life; labels and packaging
- Regulatory and compliance traceability
- FDA 21 CFR Part 11 e-signature and e-record controls (Section 20)
- Food safety and quality workflows

Exit criteria: Food edition design partner passes a Part 11 readiness assessment on the platform; allergen traceability query (product → ingredient → lot → supplier) answered end-to-end.

### Phase 5: Enterprise Scale

- Advanced analytics, dashboards, and data warehouse integration
- ERP, MES, QMS connectors; connector-based legacy-PLM migration (Windchill, Teamcenter, 3DEXPERIENCE)
- Advanced workflow orchestration
- Dedicated cells for residency and large tenants; ISO 27001 certification
- Advanced API marketplace and partner ecosystem

Exit criteria: first dedicated-cell enterprise tenant live; connector-based migration executed successfully for one legacy PLM; ISO 27001 stage 1 passed.

---

## 26. Success Metrics

Strategy execution is judged against these measures, reported quarterly:

| Metric | Definition | Target |
|---|---|---|
| Time to activate | Provisioning to first Released part in production tenant | ≤ 5 working days |
| Migration effort | Validated 100k-part dataset to production-ready tenant | ≤ 10 working days |
| Weekly active seats / licensed seats | Product engagement depth | > 50% steady state |
| Search success rate | Searches ending in opened result | > 70% |
| Index freshness compliance | Hours within p95 < 5 s lag SLO | > 99% of hours |
| AI suggestion acceptance | Accepted suggestions ÷ shown suggestions | > 40% |
| AI credit predictability | Tenants exceeding budget without prior soft alert | < 5% monthly |
| Isolation assurance | Cross-tenant leakage findings in continuous test suite and red teams | Zero tolerance |
| Gross retention | Logo retention, trailing 12 months | ≥ 90% |
| Support burden | SE1/SE2 incidents per 100 tenants per quarter | Declining trend |
| Infra cost efficiency | Infrastructure cost per average tenant | Declining trend |
| Certification milestones | SOC 2 / Part 11 / ISO dates vs Section 20 plan | On schedule |

These metrics close the loop on Sections 18–21: onboarding (migration effort), platform health (freshness, incidents), AI strategy (acceptance, cost predictability), and commercial viability (retention, unit cost).
