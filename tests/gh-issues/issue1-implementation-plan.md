## Implementation Plan

### Step 1: State Management — Add NutritionInfoData to FormDataContext

- Add `NutrientRow` and `NutritionInfoData` types
- Add `nutritionInfo` to `StepKey`, `ProgressData`, `FormData`
- Add `updateNutritionInfo` to context value
- Add initial data with 7 mandatory nutrients
- Update localStorage merge logic
- **Verify**: `tsc -b` passes

### Step 2: Navigation — Update App.tsx and LabelBusterSideNav

- Add `nutritionInfo` to `Page` type in both files
- Add page section in `App.tsx` between statements and yourLabel
- Update navigation callbacks (statements→nutritionInfo→yourLabel)
- Add step 10 in sidebar, renumber Your Label to 11
- **Verify**: `tsc -b` passes

### Step 3: NutritionInfo Page Component

- Create `src/pages/NutritionInfo.tsx`
- Serving info section (servings per package, serving size, unit select)
- Core nutrients table (7 mandatory rows, read-only name/unit, editable values)
- Optional nutrients section (add from dropdown, delete button)
- NIP exemption toggle (hides form when checked)
- Validation logic controlling Next button
- **Verify**: `tsc -b` passes, `npm run build` succeeds

### Step 4: Help Guide — NutritionInfoPage

- Create `src/pages/helpGuide/NutritionInfoPage.tsx`
- Accordion sections: What is a NIP, mandatory nutrients, serving size, per-100g calculation, exemptions, FSANZ links
- Wire into NutritionInfo page via HelpGuides component
- **Verify**: `tsc -b` passes

### Step 5: Label Generation — Update YourLabel.tsx

- Product sheet: Replace static NIP row with dynamic data (or exemption notice)
- Example label: Render formatted NIP HTML table
- PDF export: Add NIP table section using addSection helper
- **Verify**: `tsc -b` passes, `npm run build` succeeds

### Step 6: Technical Documentation

- Update architecture-overview.md (11-step wizard, new file)
- Update state-management.md (new slice)
- Update navigation-and-wizard.md (new step in flow)
- Update label-generation.md (NIP generation)
- Update component-library.md (new help guide page)
- **Verify**: All docs consistent

### Step 7: Final Verification

- `npm run lint` passes
- `npm run build` succeeds
- All acceptance criteria checked
