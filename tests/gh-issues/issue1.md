## Summary

Add a new **Nutrition Information Panel (NIP)** wizard step to Label Buster, allowing users to input nutritional data for their food product and generate a standards-compliant NIP on the product sheet, example label preview, and PDF export.

Under the [Australia New Zealand Food Standards Code — Standard 1.2.8](http://www.comlaw.gov.au/Series/F2015L00394), most packaged food products require a Nutrition Information Panel. This is one of the most complex and important elements of a food label, and its absence from Label Buster is a significant gap for users trying to produce compliant labels.

## Background

The current wizard covers food name, business details, date marks, storage & use directions, ingredients, and allergen/advisory statements — but does not address nutrition information. Users currently need to produce the NIP separately, which defeats the purpose of a one-stop labelling tool.

A compliant NIP must include:
- Servings per package
- Serving size (in grams or millilitres)
- Energy (kJ) per serving and per 100g/100mL
- Protein (g) per serving and per 100g/100mL
- Fat — total (g) per serving and per 100g/100mL
- Fat — saturated (g) per serving and per 100g/100mL
- Carbohydrate — total (g) per serving and per 100g/100mL
- Carbohydrate — sugars (g) per serving and per 100g/100mL
- Sodium (mg) per serving and per 100g/100mL
- Any additional claimed nutrients (e.g., fibre, calcium, iron)

## Requirements

### 1. New Wizard Step — "Nutrition Information"

Insert a new step between the existing **Ingredients** (Step 9) and **Your Label** (Step 10) pages, making it Step 10 and pushing Your Label to Step 11.

The step should include:
- **Serving information section**
  - Number of servings per package (numeric input)
  - Serving size value (numeric input)
  - Serving size unit (select: grams / millilitres)
- **Core nutrients table**
  - A dynamic table with pre-populated rows for the 7 mandatory nutrients (Energy, Protein, Fat-total, Fat-saturated, Carbohydrate-total, Carbohydrate-sugars, Sodium)
  - Each row has: Nutrient name (read-only for mandatory), Unit (read-only), Quantity per serving (numeric input), Quantity per 100g/100mL (numeric input)
  - Mandatory rows cannot be deleted
- **Additional nutrients section**
  - Button to add optional nutrient rows (e.g., Fibre, Calcium, Iron, Potassium, Vitamin C)
  - Select dropdown to pick from a predefined list of recognised nutrients with their units
  - Optional rows can be deleted
- **NIP exemption toggle**
  - Checkbox: "This product is exempt from requiring a Nutrition Information Panel"
  - When checked, the nutrition inputs are hidden and a note appears explaining that exemptions apply to certain foods under Standard 1.2.8 (e.g., foods in small packages, herbs/spices, tea/coffee, vinegar, salt, single-ingredient foods sold at point of sale)
  - The exemption status should be captured and reflected on the product sheet

### 2. State Management Updates

- Add a new `nutritionInfo` slice to the `FormData` interface in `FormDataContext.tsx`
- The slice should include:
  - `isExempt: boolean`
  - `servingsPerPackage: string`
  - `servingSize: string`
  - `servingSizeUnit: 'g' | 'mL'`
  - `nutrients: NutrientRow[]` where each row has `{ id: string, name: string, unit: string, perServing: string, per100: string, isMandatory: boolean }`
- Initialise with 7 pre-populated mandatory nutrient rows
- Persist to localStorage with the existing `label-buster-form-data` key
- Add a `nutritionInfo` progress flag to `ProgressData`

### 3. Help Guide Content

- Create a new help guide page `NutritionInfoPage.tsx` under `src/pages/helpGuide/`
- Include accordion sections covering:
  - What is a Nutrition Information Panel?
  - Which nutrients are mandatory?
  - How to determine serving size
  - How to calculate per-100g/100mL values
  - NIP exemptions and when they apply
  - Links to FSANZ resources
- Wire the help guide into the help panel system for the new step

### 4. Label Generation Updates

Update `YourLabel.tsx` and the label generation system to:

- **Product Sheet**: Add a "Nutrition Information Panel" section to the product sheet table, listing serving info and all nutrient rows with per-serving and per-100g values. If exempt, display "NIP Exempt — [reason]" instead.
- **Example Label Preview**: Render a formatted NIP table matching the standard Australian NIP layout (bordered table with header row, nutrient rows, serving info header). The visual format should follow the prescribed Standard 1.2.8 layout.
- **PDF Export**: Add the NIP table to the generated PDF using jspdf-autotable. The table should be formatted to closely match the physical NIP layout requirements.

### 5. Navigation Updates

- Update `App.tsx` page state machine to include the new `NutritionInfo` page
- Update the `Page` type/enum with the new page
- Update `LabelBusterSideNav.tsx` to include the new step in the sidebar
- Ensure step locking works correctly — the new step should require Ingredients (Step 9) to be complete
- Update back/next navigation callbacks to include the new step in the correct position

### 6. Validation Rules

- If not exempt: servings per package and serving size are required and must be positive numbers
- All mandatory nutrient rows must have values for both per-serving and per-100g columns
- Per-serving and per-100g values must be non-negative numbers
- Additional (optional) nutrient rows, if added, must have all fields completed or be removed
- Validation should prevent advancing to the next step until all required fields are filled

## Acceptance Criteria

- [ ] New "Nutrition Information" step appears in the wizard between Ingredients and Your Label
- [ ] Sidebar navigation shows the new step with correct step locking behaviour
- [ ] 7 mandatory nutrient rows are pre-populated and cannot be deleted
- [ ] Users can add and remove optional nutrient rows from a predefined list
- [ ] NIP exemption toggle hides/shows the nutrition input form
- [ ] Form data persists to localStorage and survives page refresh
- [ ] Product sheet includes NIP section (or exemption notice)
- [ ] Example label preview renders a formatted NIP table
- [ ] PDF export includes the NIP table
- [ ] Help guide content is accessible from the new step
- [ ] All validation rules are enforced before step completion
- [ ] Existing wizard steps continue to function correctly (no regressions)
- [ ] Technical documentation in `/docs/technical/` is updated to reflect:
  - New step in architecture overview and navigation documentation
  - New state slice in state management documentation
  - NIP generation rules in label generation documentation
  - New component(s) in component library documentation

## Technical Notes

- Follow existing patterns: controlled components, rule-based text generation, CSS visibility toggle for the page
- Reuse the existing `Table` component for the nutrients table where possible, or extend it to support read-only/locked rows
- The NIP visual layout in the example label should use a simple HTML table styled to approximate the standard format — pixel-perfect compliance is not required
- Consider the per-100g/100mL column header should change dynamically based on the selected serving size unit (g → per 100g, mL → per 100mL)