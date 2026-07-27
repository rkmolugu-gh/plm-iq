# PLM Assistant — Test Prompts

These prompts exercise every tool available to the assistant. Each group targets a specific tool or entity. Send them one at a time in the Assistant UI (`/assistant`).

---

## Parts — `get_part`

```
Show me part BB-001
```

```
What are the details of part FRM-003?
```

```
Tell me about part WHL-002
```

```
Look up part numbers BB-001 and FRM-003 and compare them
```

---

## Parts — `search_parts`

```
Search for parts containing "Frame"
```

```
Find all parts made of Aluminum
```

```
Are there any parts with "Bracket" in the name?
```

```
Search for parts with status RELEASED that contain "Wheel"
```

---

## Parts — `create_part`

```
Create a new part similar to BB-001, call it "Front Bracket" and make the material Steel
```

```
Make a copy of part FRM-003 but change the quantity to 2 and status to DRAFT
```

```
Create a part like WHL-002 but use part number WHL-010 and name it "Test Wheel Assembly"
```

---

## Parts — `update_part_status`

```
Change the status of BB-001 to RELEASED
```

```
Set part FRM-003 to OBSOLETED
```

---

## BOM — `get_bom`

```
What's the BOM for part BB-001?
```

```
Show me the Bill of Materials for FRM-003
```

```
What components make up assembly BB-001?
```

---

## Costing — `get_costing`

```
How much does part BB-001 cost?
```

```
Show me the costing breakdown for WHL-002 including material and labor
```

```
What's the rolled total cost for part FRM-003?
```

---

## ECO — `get_eco`

```
Look up ECO-001
```

```
What are the details of engineering change ECO-002?
```

---

## ECO — `search_ecos`

```
Find all ECOs related to part BB-001
```

```
Show me all ECOs that are still in DRAFT status
```

```
Are there any engineering changes for part FRM-003?
```

---

## AML — `get_aml`

```
Who are the approved manufacturers for part BB-001?
```

```
Show me the approved manufacturer list for WHL-002, only preferred suppliers
```

```
What manufacturers supply part FRM-003 and what are their lead times?
```

---

## AVL — `get_avl`

```
Show me the approved vendors for part BB-001
```

```
Which vendors supply part WHL-002, and what are their prices?
```

```
List preferred vendors for part FRM-003 with their payment terms and ISO status
```

---

## CAD — `get_cad`

```
What CAD files are available for part BB-001?
```

```
Show me the CAD metadata for FRM-003 — what formats and systems?
```

```
Are there any drawings or 3D models for WHL-002?
```

---

## Multi-step (tool chaining)

These test the ReAct loop — the agent must call multiple tools in sequence.

```
Find all released parts made of Steel, then show me the costing for each
```

```
Look up part BB-001, show me its BOM, then find what vendors supply it
```

```
Tell me about ECO-001 — what part does it affect, what's the change, and who manufactures that part?
```

```
I want to understand part FRM-003 fully: give me its details, BOM, costing, and CAD files
```

```
Search for parts with "Wheel" in the name, then create a new part based on the first result with quantity 5
```

```
Find all ECOs for part BB-001, then check the current status of that part
```

```
What's the most expensive component in the BB-001 BOM? Show me its full costing breakdown
```
