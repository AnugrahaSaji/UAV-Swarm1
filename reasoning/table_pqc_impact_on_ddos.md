# Table Reasoning: Impact of PQC Level on DDoS Detector Cost

## Target table
- Manuscript table: `tab:pqc-impact-on-ddos`
- File: `vtc/results.tex`

## Source of truth
- Dataset: `bench_ddos_results/20260302_135859/comparison.json`
- Field used: `per_suite[]`
  - `suite_id`
  - `baseline_cpu_avg`, `xgb_cpu_avg`, `tst_cpu_avg`
  - `baseline_power_mw`, `xgb_power_mw`, `tst_power_mw`
  - `baseline_throughput`, `xgb_throughput`, `tst_throughput`

## Level mapping rule (deterministic)
- `L1` if `suite_id` contains: `mlkem512` or `hqc128` or `348864`
- `L3` if `suite_id` contains: `mlkem768` or `hqc192` or `460896`
- `L5` otherwise (includes `mlkem1024`, `hqc256`, `8192128`)

## Aggregation logic
For each level (`L1`, `L3`, `L5`):
1. Compute mean CPU for each mode:
   - `CPU_No = mean(baseline_cpu_avg)`
   - `CPU_XGB = mean(xgb_cpu_avg)`
   - `CPU_TST = mean(tst_cpu_avg)`
2. Compute mean power for each mode:
   - `P_No = mean(baseline_power_mw)`
   - `P_XGB = mean(xgb_power_mw)`
   - `P_TST = mean(tst_power_mw)`
3. Compute mean throughput for each mode:
   - `Th_No = mean(baseline_throughput)`
   - `Th_XGB = mean(xgb_throughput)`
   - `Th_TST = mean(tst_throughput)`
4. Compute deltas:
   - `ΔCPU_XGB = CPU_XGB - CPU_No`
   - `ΔCPU_TST = CPU_TST - CPU_No`
   - `ΔP_XGB = P_XGB - P_No`
   - `ΔP_TST = P_TST - P_No`
5. `Suites` is row count per level bucket.

## Reproducible extraction command
```powershell
$cmp=Get-Content bench_ddos_results/20260302_135859/comparison.json -Raw | ConvertFrom-Json
function Mean($a){if($a.Count -eq 0){0}else{($a|Measure-Object -Average).Average}}
function Level($sid){
  $s=$sid.ToLower()
  if($s -match 'mlkem512|hqc128|348864'){ 'L1' }
  elseif($s -match 'mlkem768|hqc192|460896'){ 'L3' }
  else { 'L5' }
}
$acc=@{}
foreach($lv in 'L1','L3','L5'){
  $acc[$lv]=@{bc=@();xc=@();tc=@();bp=@();xp=@();tp=@();bt=@();xt=@();tt=@()}
}
foreach($r in $cmp.per_suite){
  $lv=Level $r.suite_id
  $acc[$lv].bc += $r.baseline_cpu_avg; $acc[$lv].xc += $r.xgb_cpu_avg; $acc[$lv].tc += $r.tst_cpu_avg
  $acc[$lv].bp += $r.baseline_power_mw; $acc[$lv].xp += $r.xgb_power_mw; $acc[$lv].tp += $r.tst_power_mw
  $acc[$lv].bt += $r.baseline_throughput; $acc[$lv].xt += $r.xgb_throughput; $acc[$lv].tt += $r.tst_throughput
}
foreach($lv in 'L1','L3','L5'){
  $bc=Mean $acc[$lv].bc; $xc=Mean $acc[$lv].xc; $tc=Mean $acc[$lv].tc
  $bp=Mean $acc[$lv].bp; $xp=Mean $acc[$lv].xp; $tp=Mean $acc[$lv].tp
  $bt=Mean $acc[$lv].bt; $xt=Mean $acc[$lv].xt; $tt=Mean $acc[$lv].tt
  "$lv|CPU:$([math]::Round($bc,2))/$([math]::Round($xc,2))/$([math]::Round($tc,2))|dCPU:$([math]::Round($xc-$bc,2))/$([math]::Round($tc-$bc,2))|P:$([math]::Round($bp,2))/$([math]::Round($xp,2))/$([math]::Round($tp,2))|dP:$([math]::Round($xp-$bp,2))/$([math]::Round($tp-$bp,2))|Th:$([math]::Round($bt,3))/$([math]::Round($xt,3))/$([math]::Round($tt,3))|n=$($acc[$lv].bc.Count)"
}
```

## Final values inserted
- `L1`: CPU `21.02 / 46.21 / 89.39`, `ΔCPU=+25.19 / +68.37`, Power `3078.56 / 4003.89 / 4107.60`, `ΔP=+925.32 / +1029.03`, Throughput `22.043 / 21.464 / 8.227`, Suites `27`
- `L3`: CPU `22.87 / 48.10 / 89.64`, `ΔCPU=+25.24 / +66.77`, Power `3038.81 / 3996.40 / 3983.94`, `ΔP=+957.59 / +945.13`, Throughput `13.406 / 13.274 / 5.721`, Suites `18`
- `L5`: CPU `22.71 / 48.16 / 89.29`, `ΔCPU=+25.45 / +66.58`, Power `3083.86 / 4019.39 / 4113.55`, `ΔP=+935.53 / +1029.69`, Throughput `17.356 / 17.191 / 6.356`, Suites `27`

## Notes
- No interpolation or synthetic values are used.
- All values are means from source data, rounded to 2 decimals (throughput 3 decimals).
