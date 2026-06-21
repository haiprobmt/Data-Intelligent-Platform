# Finance Domain User Test Report

## Scenario
Finance Manager wants to assess month-end reporting pain points across AP invoices, GL journal entries, budget Excel upload, supplier master, and P&L mapping.

## Scan Result
Tables scanned: 5
- ap_invoices: 5 rows, entity=Supplier, PK=invoice_id
- finance_budget_excel_upload: 3 rows, entity=NOT DETECTED, PK=missing
- gl_journal_entries: 5 rows, entity=NOT DETECTED, PK=missing
- pnl_mapping_manual: 3 rows, entity=NOT DETECTED, PK=missing
- supplier_master: 3 rows, entity=Supplier, PK=vendor_id

## Quality Scores
- completeness: 92
- uniqueness: 67
- freshness: 49
- validity: 50
- consistency: 76
- overall: 67

## Issues Detected
- [Medium] No CDC column on ap_invoices: Finance month-end reporting may not support reliable incremental refresh.
- [Medium] High null percentage on ap_invoices.cost_center: Finance KPI may be incomplete or require manual correction.
- [High] Missing primary key on finance_budget_excel_upload: Finance reconciliation and incremental loading may be unreliable.
- [Medium] No CDC column on finance_budget_excel_upload: Finance month-end reporting may not support reliable incremental refresh.
- [High] Manual Excel dependency on finance_budget_excel_upload: Budget reporting depends on manually maintained spreadsheet data.
- [Medium] High null percentage on finance_budget_excel_upload.last_reviewed_by: Finance KPI may be incomplete or require manual correction.
- [High] Missing primary key on gl_journal_entries: Finance reconciliation and incremental loading may be unreliable.
- [Medium] High null percentage on gl_journal_entries.cost_center: Finance KPI may be incomplete or require manual correction.
- [High] Missing primary key on pnl_mapping_manual: Finance reconciliation and incremental loading may be unreliable.
- [Medium] No CDC column on pnl_mapping_manual: Finance month-end reporting may not support reliable incremental refresh.

## Platform Recommendation
Recommended platform: Microsoft Fabric (Fabric score=5, Databricks score=0)

## Finance Document Test
Text extracted: 169 characters
- entity_name: Requires Bedrock review
- period: Requires Bedrock review
- revenue: Requires Bedrock review
- operating_expense: Requires Bedrock review
- net_profit: Requires Bedrock review
- prepared_by: Requires Bedrock review

## Business User Verdict
- Useful: detects missing PKs, missing CDC/update columns, manual Excel dependency, high nulls, and recommends Fabric for a finance/reporting-led use case.
- Gap: finance-specific entities like GL Account, Budget, Cost Center, P&L Mapping are not detected by current entity patterns.
- Gap: document extraction depends on Bedrock; without credentials it provides no structured values and requires human review.
- Gap: duplicate journal line is not raised as a business issue because the current profiler does not create duplicate-key findings.