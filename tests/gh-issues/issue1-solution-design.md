## Solution Design — NIP Wizard Step

### Approach
Insert a new **Nutrition Information** page between Statements (Step 9) and Your Label (pushed to Step 11). Follow existing patterns exactly: controlled components, FormDataContext slice, CSS visibility toggle, help guide panel.

### Data Model

**New types in `FormDataContext.tsx`:**
```ts
type NutrientRow = {
  id: string; name: string; unit: string;
  perServing: string; per100: string; isMandatory: boolean;
};

type NutritionInfoData = {
  isExempt: boolean;
  servingsPerPackage: string;
  servingSize: string;
  servingSizeUnit: 'g' | 'mL';
  nutrients: NutrientRow[];
};
```

7 mandatory nutrients pre-populated: Energy (kJ), Protein (g), Fat-total (g), Fat-saturated (g), Carbohydrate (g), Sugars (g), Sodium (mg).

### Files Changed

| File                          | Change                                                                                              |
| ----------------------------- | --------------------------------------------------------------------------------------------------- |
| `FormDataContext.tsx`         | Add `NutritionInfoData` type, `nutritionInfo` slice, `updateNutritionInfo`, `nutritionInfo` StepKey |
| `App.tsx`                     | Add `nutritionInfo` to Page type, route between `statements` and `yourLabel`                        |
| `LabelBusterSideNav.tsx`      | Add step 10 "Nutrition information", renumber Your Label to 11                                      |
| `NutritionInfo.tsx` (new)     | Page component with serving info, nutrients table, optional nutrients, exemption toggle, validation |
| `NutritionInfoPage.tsx` (new) | Help guide with accordion sections                                                                  |
| `YourLabel.tsx`               | Add NIP to product sheet table, example label preview, PDF export                                   |
| `docs/technical/*.md`         | Update architecture, state, navigation, label generation, and component docs                        |

### Navigation Flow
```
… → statements → nutritionInfo → yourLabel
```
Step locking: `nutritionInfo` requires `statements` complete. `yourLabel` requires `nutritionInfo` complete.

### Validation
- If not exempt: servingsPerPackage and servingSize required (positive numbers)
- All mandatory nutrient rows must have perServing and per100 values (non-negative)
- Optional rows, if present, must be fully filled or removed
- Next button disabled until valid

### Label Generation
- **Product sheet**: Replace static NIP reference with actual data table (or "NIP Exempt" if exempt)
- **Example label**: Render formatted NIP HTML table in the third column (replacing the static image)
- **PDF**: Add NIP table via jspdf-autotable