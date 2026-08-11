# Table Reasoning: Impact of DDoS Modes on PQC Runtime

## Target table
- Manuscript table: `tab:ddos-impact-on-pqc`
- File: `vtc/results.tex`

## Source of truth
- Dataset: `bench_ddos_results/20260302_135859/comparison.json`
- Field used: `per_suite[]`
  - `suite_id`
  - `baseline_mean_ms`
  - `xgb_mean_ms`
  - `tst_mean_ms`

## Level mapping rule (code-based)
The following deterministic mapping is used from `suite_id` to NIST level:
- `L1` if `suite_id` contains one of:
  - `mlkem512`, `hqc128`, `348864`
- `L3` if `suite_id` contains one of:
  - `mlkem768`, `hqc192`, `460896`
- `L5` otherwise (covers `mlkem1024`, `hqc256`, `8192128`)

## Aggregation logic
For each level bucket:
1. Collect vectors:
   - `No-DDoS` = `baseline_mean_ms`
   - `XGBoost` = `xgb_mean_ms`
   - `TST` = `tst_mean_ms`
2. Compute means of each vector.
3. Compute deltas:
   - `Δ_XGB = mean(XGBoost) - mean(No-DDoS)`
   - `Δ_TST = mean(TST) - mean(No-DDoS)`
4. `Suites` is the count of rows in that level bucket.

## Reproducible extraction command
```powershell
$cmp=Get-Content bench_ddos_results/20260302_135859/comparison.json -Raw | ConvertFrom-Json
function Mean($a){ if($a.Count -eq 0){0}else{($a|Measure-Object -Average).Average} }
function Level($sid){
  $s=$sid.ToLower()
  if($s -match 'mlkem512|hqc128|348864'){ 'L1' }
  elseif($s -match 'mlkem768|hqc192|460896'){ 'L3' }
  else { 'L5' }
}
$acc=@{}
foreach($lv in 'L1','L3','L5'){ $acc[$lv]=@{no=@();xg=@();ts=@()} }
foreach($r in $cmp.per_suite){
  $lv=Level $r.suite_id
  $acc[$lv].no += $r.baseline_mean_ms
  $acc[$lv].xg += $r.xgb_mean_ms
  $acc[$lv].ts += $r.tst_mean_ms
}
foreach($lv in 'L1','L3','L5'){
  $no=Mean $acc[$lv].no; $xg=Mean $acc[$lv].xg; $ts=Mean $acc[$lv].ts
  "$lv|$([math]::Round($no,2))|$([math]::Round($xg,2))|$([math]::Round($ts,2))|$([math]::Round($xg-$no,2))|$([math]::Round($ts-$no,2))|n=$($acc[$lv].no.Count)"
}
```

## Final values inserted into the paper
- `L1`: No-DDoS `699.37`, XGBoost `688.86`, TST `901.32`, `Δ_XGB=-10.51`, `Δ_TST=+201.95`, Suites `27`
- `L3`: No-DDoS `1939.10`, XGBoost `1852.59`, TST `2791.27`, `Δ_XGB=-86.51`, `Δ_TST=+852.17`, Suites `18`
- `L5`: No-DDoS `6582.57`, XGBoost `4577.05`, TST `6527.46`, `Δ_XGB=-2005.52`, `Δ_TST=-55.11`, Suites `27`

## Notes
- No synthetic values or interpolation are used.
- All numbers are direct means from `comparison.json` with fixed mapping and rounding to 2 decimals.
