# Full Python File Analysis (200 files)

This report is generated from static code inspection. Any item not observed in code is marked as 'Not Found In Code'.

## .agent/skills/orchestrator/scripts/run_mission.py

Summary: Not Found In Code

Imports:
- time

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## .scripts/list_tracked_sizes.py

Summary: Not Found In Code

Imports:
- os
- subprocess

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## analyze_metrics.py

Summary: analyze_metrics.py

Imports:
- argparse
- collections
- core.metrics_schema
- dataclasses
- datetime
- json
- pathlib
- statistics
- sys
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- MetricStats
- MetricsAnalyzer

Core Functions:
- __init__
- analyze_by_algorithm
- calc_stats
- compute_statistics
- data_quality_check
- generate_report
- load_data
- main
- run_full_analysis
- summarize
- validate_schema

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; time
- Logging: Not Found In Code
- Benchmark: benchmark; metrics; power

Role Hints (from identifiers):
- drone, gcs

## bench/__init__.py

Summary: Benchmark Tools Package - bench/

Imports:
- Not Found In Code

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: benchmark; metrics

Role Hints (from identifiers):
- drone, gcs

## bench/analysis/__init__.py

Summary: PQC Benchmark Analysis Package

Imports:
- Not Found In Code

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- cryptography

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: benchmark; metrics

Role Hints (from identifiers):
- Not Found In Code

## bench/analysis/benchmark_analysis.py

Summary: PQC Benchmark Data Analysis Script

Imports:
- argparse
- csv
- dataclasses
- json
- numpy
- os
- pathlib
- statistics
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- AggregateStats
- BenchmarkRecord

Core Functions:
- analyze_by_family
- analyze_by_nist_level
- analyze_operations
- analyze_same_family_different_level
- analyze_same_level_different_kem
- analyze_suite_vs_primitives
- compute_grouped_stats
- compute_stats
- export_stats_csv
- export_to_csv
- get_suite_nist_level
- ingest_all_benchmarks
- load_environment
- main
- parse_benchmark_file
- to_dict

Network I/O:
- Not Found In Code

Crypto Usage:
- ascon

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: benchmark; metrics; perf

Role Hints (from identifiers):
- Not Found In Code

## bench/analysis/benchmark_plots.py

Summary: PQC Benchmark Visualization Script

Imports:
- argparse
- csv
- json
- matplotlib
- matplotlib.patches
- matplotlib.pyplot
- matplotlib.ticker
- numpy
- os
- pathlib
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- load_csv_data
- load_raw_timings
- main
- plot_aead_comparison
- plot_family_comparison
- plot_kem_boxplots
- plot_key_sizes
- plot_nist_level_comparison
- plot_sig_boxplots
- plot_suite_handshake

Network I/O:
- Not Found In Code

Crypto Usage:
- ascon

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: benchmark; perf

Role Hints (from identifiers):
- Not Found In Code

## bench/analysis/comprehensive_plots.py

Summary: Comprehensive PQC Benchmark Visualization Suite

Imports:
- dataclasses
- json
- math
- matplotlib
- matplotlib.gridspec
- matplotlib.patches
- matplotlib.pyplot
- numpy
- os
- pathlib
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- AlgorithmMetrics

Core Functions:
- add_bar_subplot
- create_anomaly_detection_plot
- create_comprehensive_comparison_table
- create_heatmap_comparison
- create_metric_comparison_bar
- create_nist_level_progression
- create_size_timing_tradeoff
- create_spider_by_nist_level
- create_spider_chart
- create_statistical_summary_plot
- load_benchmark_data
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: benchmark; metrics; perf

Role Hints (from identifiers):
- Not Found In Code

## bench/analysis/fix_comprehensive.py

Summary: Fix and generate remaining comprehensive plots (comprehensive comparison, heatmaps, statistical summaries).

Imports:
- json
- matplotlib.patches
- matplotlib.pyplot
- numpy
- pathlib
- warnings

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- create_comprehensive_comparison
- create_heatmap
- create_statistical_summary
- detect_family
- detect_nist_level
- load_all_benchmarks
- main
- safe_bar_plot
- save_figure

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: benchmark; metrics; perf

Role Hints (from identifiers):
- Not Found In Code

## bench/analysis/run_analysis.py

Summary: Full Analysis Pipeline Execution Script

Imports:
- benchmark_analysis
- benchmark_plots
- matplotlib
- os
- pathlib
- sys
- traceback

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: benchmark; metrics

Role Hints (from identifiers):
- Not Found In Code

## bench/analyze_power_benchmark.py

Summary: Comprehensive Power & Performance Benchmark Analysis with Report Generation

Imports:
- argparse
- dataclasses
- datetime
- json
- matplotlib.lines
- matplotlib.patches
- matplotlib.pyplot
- matplotlib.ticker
- numpy
- os
- pathlib
- statistics
- sys
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- BenchmarkData

Core Functions:
- create_aead_payload_analysis
- create_comprehensive_heatmap
- create_energy_efficiency_chart
- create_nist_level_comparison
- create_power_consumption_chart
- create_time_vs_energy_scatter
- create_timing_comparison
- create_voltage_current_analysis
- format_time
- generate_markdown_report
- get_algorithm_color
- load_benchmark_data
- load_environment
- main
- mean_energy_uj
- mean_power_w
- mean_time_ms
- mean_time_us
- nist_level
- timing_ms
- timing_us

Network I/O:
- Not Found In Code

Crypto Usage:
- ascon; cryptography; oqs

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; perf_counter; perf_counter_ns; time
- Logging: Not Found In Code
- Benchmark: benchmark; ina219; latency; metrics; perf; power; throughput

Role Hints (from identifiers):
- gcs

## bench/analyze_stress_test.py

Summary: Not Found In Code

Imports:
- datetime
- fpdf
- json
- matplotlib.pyplot
- pandas
- re

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- generate_report
- parse_telemetry
- parse_thermal

Network I/O:
- Not Found In Code

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; time
- Logging: Not Found In Code
- Benchmark: metrics; perf; throughput

Role Hints (from identifiers):
- gcs

## bench/benchmark_power_perf.py

Summary: PQC Performance Benchmark with Power (INA219) and Perf Counters Integration

Imports:
- argparse
- core.aead
- core.power_monitor
- core.suites
- csv
- dataclasses
- datetime
- json
- oqs
- oqs.oqs
- os
- pathlib
- platform
- socket
- statistics
- subprocess
- sys
- threading
- time
- traceback
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- BenchmarkResult
- EnvironmentInfo
- OperationMeasurement
- PerfCounters
- PerfWrapper
- PowerMonitorWrapper
- PowerSample

Core Functions:
- __init__
- _init_oqs
- _sample_loop
- available
- benchmark_aead
- benchmark_kem
- benchmark_sig
- collect_environment
- compute_stats
- discover_aeads
- discover_kems
- discover_sigs
- discover_suites
- get_kem_class
- get_sig_class
- main
- read_counters_inline
- save_result
- start_sampling
- stop_sampling
- version

Network I/O:
- serial; socket

Crypto Usage:
- ascon; oqs

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; perf_counter; perf_counter_ns; sleep; time
- Logging: Not Found In Code
- Benchmark: benchmark; ina219; metrics; perf; power

Role Hints (from identifiers):
- gcs

## bench/benchmark_pqc.py

Summary: PQC Performance & Power Benchmarking Script

Imports:
- argparse
- core.aead
- core.config
- core.handshake
- core.suites
- csv
- dataclasses
- datetime
- hashlib
- ina219
- json
- oqs
- oqs.oqs
- os
- pathlib
- platform
- socket
- statistics
- struct
- subprocess
- sys
- time
- traceback
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- BenchmarkResult
- EnvironmentInfo
- IterationResult
- PerfCounters
- PowerMonitor

Core Functions:
- __init__
- _init_oqs_compat
- _parse_perf_output
- available
- benchmark_aead
- benchmark_kem
- benchmark_signature
- benchmark_suite_handshake
- collect_environment_info
- compute_energy
- compute_summary
- discover_aeads
- discover_kems
- discover_signatures
- discover_suites
- get_enabled_kems_func
- get_enabled_sigs_func
- get_oqs_kem_class
- get_oqs_sig_class
- main
- read_once
- run_with_perf
- sample
- save_raw_result
- save_summaries
- start_sampling
- stop_sampling

Network I/O:
- serial; socket

Crypto Usage:
- ascon; hashlib; oqs

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; perf_counter; perf_counter_ns; time
- Logging: Not Found In Code
- Benchmark: benchmark; ina219; latency; metrics; perf; power

Role Hints (from identifiers):
- drone, gcs

## bench/consolidate_metrics.py

Summary: Metrics Consolidator - bench/consolidate_metrics.py

Imports:
- argparse
- bench.generate_ieee_report
- core.config
- datetime
- json
- os
- pathlib
- subprocess
- sys
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- MetricsConsolidator

Core Functions:
- __init__
- _load_role_metrics
- _merge_drone_metrics
- _merge_gcs_metrics
- consolidate
- fetch_drone_metrics
- load_metrics_file
- log
- main
- run_ssh_command
- scp_from_drone

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; time
- Logging: log(
- Benchmark: benchmark; metrics; power

Role Hints (from identifiers):
- drone, gcs

## bench/deploy_and_run.py

Summary: Benchmark Deployment & Execution Script

Imports:
- argparse
- datetime
- os
- pathlib
- subprocess
- sys
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- check_drone_connectivity
- check_lan_connectivity
- fetch_results
- git_commit_push
- log
- main
- run_local
- run_ssh
- start_drone_benchmark
- start_gcs_server
- sync_drone

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(
- Benchmark: benchmark; power

Role Hints (from identifiers):
- drone, gcs

## bench/generate_benchmark_book.py

Summary: Professional PQC Benchmark Book Generator

Imports:
- argparse
- datetime
- json
- math
- matplotlib.patches
- matplotlib.pyplot
- matplotlib.ticker
- numpy
- pathlib
- reportlab.graphics.charts.barcharts
- reportlab.graphics.shapes
- reportlab.lib
- reportlab.lib.enums
- reportlab.lib.pagesizes
- reportlab.lib.styles
- reportlab.lib.units
- reportlab.pdfgen
- reportlab.platypus
- reportlab.platypus.tableofcontents
- scipy
- statistics
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- BenchmarkBookGenerator

Core Functions:
- __init__
- _add_algorithm_chapter
- _add_conclusions
- _add_cover_page
- _add_executive_summary
- _add_methodology
- _create_styles
- compute_statistics
- create_comparison_chart
- create_energy_analysis
- create_nist_level_analysis
- create_power_profile
- create_timing_distribution
- generate
- get_algorithm_color
- get_nist_level
- load_all_benchmarks
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- ascon; cryptography

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; perf_counter; perf_counter_ns; time
- Logging: Not Found In Code
- Benchmark: benchmark; ina219; latency; metrics; perf; power

Role Hints (from identifiers):
- gcs

## bench/generate_ieee_book.py

Summary: IEEE Book Generator with Spider Graphs

Imports:
- argparse
- dataclasses
- datetime
- json
- math
- matplotlib
- matplotlib.patches
- matplotlib.pyplot
- numpy
- os
- pathlib
- statistics
- sys
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- SuiteAnalysis

Core Functions:
- analyze_results
- create_handshake_comparison
- create_nist_level_spider
- create_power_bar_chart
- create_spider_chart
- escape_latex
- generate_comparative_analysis
- generate_latex_document
- generate_suite_page
- load_benchmark_results
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- ascon; cryptography

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; time
- Logging: Not Found In Code
- Benchmark: benchmark; ina219; metrics; perf; power; throughput

Role Hints (from identifiers):
- drone, gcs

## bench/generate_ieee_report.py

Summary: IEEE-Style Benchmark Report Generator - bench/generate_ieee_report.py

Imports:
- argparse
- datetime
- json
- os
- pathlib
- statistics
- sys
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- IEEEReportGenerator

Core Functions:
- __init__
- _generate_comparison_section
- _generate_conclusion
- _generate_document
- _generate_executive_summary
- _generate_methodology
- _generate_preamble
- _generate_suite_page
- _generate_title_page
- escape_latex
- format_number
- generate
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- cryptography; oqs

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; time
- Logging: Not Found In Code
- Benchmark: benchmark; latency; metrics; perf; power; throughput

Role Hints (from identifiers):
- drone, gcs

## bench/lan_benchmark_drone.py

Summary: Drone-side LAN Benchmark Controller

Imports:
- argparse
- core.config
- core.process
- core.suites
- dataclasses
- datetime
- ina219
- json
- os
- pathlib
- psutil
- signal
- socket
- statistics
- subprocess
- sys
- threading
- time
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ConsolidatedResult
- DroneBenchmarkController
- DroneMetrics
- DroneMetricsCollector
- DronePowerSample
- DroneProxyManager
- UdpEchoServer

Core Functions:
- __init__
- _loop
- _sample_cpu_loop
- _sample_power_loop
- benchmark_suite
- finalize
- get_available_suites
- get_stats
- is_running
- log
- log_err
- main
- record_handshake_end
- record_handshake_start
- record_traffic_end
- record_traffic_start
- reset_stats
- run_all_benchmarks
- save_results
- send_gcs_command
- signal_handler
- start
- start_suite
- stop
- to_dict
- update_network_stats
- wait_for_gcs
- wait_for_handshake

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: benchmark; ina219; latency; metrics; power

Role Hints (from identifiers):
- drone, gcs

## bench/lan_benchmark_gcs.py

Summary: GCS-side LAN Benchmark Server

Imports:
- argparse
- core.config
- core.process
- core.suites
- dataclasses
- datetime
- json
- os
- pathlib
- psutil
- signal
- socket
- statistics
- subprocess
- sys
- threading
- time
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- GcsBenchmarkServer
- GcsMetrics
- GcsMetricsCollector
- GcsProxyManager

Core Functions:
- __init__
- _handle_client
- _handle_command
- _sample_loop
- _server_loop
- finalize
- is_running
- log
- log_err
- main
- record_handshake_end
- record_handshake_start
- record_traffic_end
- record_traffic_start
- signal_handler
- start
- start_suite
- stop
- to_dict

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: benchmark; ina219; metrics; power

Role Hints (from identifiers):
- drone, gcs

## bench/md_to_pdf.py

Summary: Convert markdown benchmark report to professional PDF.

Imports:
- argparse
- datetime
- os
- pathlib
- re
- reportlab.lib
- reportlab.lib.enums
- reportlab.lib.pagesizes
- reportlab.lib.styles
- reportlab.lib.units
- reportlab.platypus

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- create_pdf
- main
- parse_markdown

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; time
- Logging: Not Found In Code
- Benchmark: benchmark; power

Role Hints (from identifiers):
- gcs

## bench/run_full_benchmark.py

Summary: Full Benchmark Runner - bench/run_full_benchmark.py

Imports:
- argparse
- core.config
- core.metrics_aggregator
- core.process
- core.suites
- dataclasses
- datetime
- json
- os
- pathlib
- signal
- socket
- statistics
- subprocess
- sys
- threading
- time
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- DroneBenchmarkController
- GcsBenchmarkServer
- ProxyManager
- SuiteBenchmarkResult
- UdpEchoServer

Core Functions:
- __init__
- _handle_client
- _handle_command
- _loop
- _server_loop
- benchmark_suite
- get_available_suites
- get_stats
- is_running
- log
- log_err
- main
- reset_stats
- run_all_benchmarks
- save_results
- send_gcs_command
- signal_handler
- start
- start_mavproxy
- stop
- to_dict
- wait_for_gcs
- wait_for_handshake

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: benchmark; latency; metrics; power

Role Hints (from identifiers):
- drone, gcs

## bench_models.py

Summary: Not Found In Code

Imports:
- __future__

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- calculate_predicted_flight_constraint

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: power

Role Hints (from identifiers):
- Not Found In Code

## check_drone_env.py

Summary: Check drone environment.

Imports:
- core.suites
- platform
- psutil

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone

## check_oqs.py

Summary: Not Found In Code

Imports:
- oqs
- sys

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- oqs

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## check_sys_keys.py

Summary: Check SystemCollector keys.

Imports:
- core.metrics_collectors

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: metrics

Role Hints (from identifiers):
- Not Found In Code

## config.remote.py

Summary: Core configuration constants for PQC drone-GCS secure proxy.

Imports:
- core.exceptions
- ipaddress
- os
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- _apply_env_overrides
- validate_config

Network I/O:
- serial

Crypto Usage:
- AESGCM; ChaCha20Poly1305; ascon; hmac

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: benchmark; ina219; metrics; perf; power

Role Hints (from identifiers):
- drone, gcs

## confirm_all_metrics.py

Summary: Comprehensive Metrics Confirmation Report

Imports:
- core.metrics_schema
- dataclasses
- datetime
- json
- pathlib
- sys
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- generate_confirmation_report
- get_category_info
- main

Network I/O:
- serial

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; time
- Logging: logging
- Benchmark: benchmark; ina219; jitter; latency; metrics; power; throughput

Role Hints (from identifiers):
- drone, gcs

## core/__init__.py

Summary: PQC Drone-GCS Secure Proxy Core Package.

Imports:
- Not Found In Code

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- cryptography

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## core/aead.py

Summary: AEAD framing for PQC drone-GCS secure proxy.

Imports:
- core
- core.config
- core.exceptions
- cryptography.exceptions
- cryptography.hazmat.primitives.ciphers.aead
- dataclasses
- pyascon
- struct
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- AeadAuthError
- AeadIds
- HeaderMismatch
- Receiver
- ReplayError
- Sender
- _AsconAdapter

Core Functions:
- __init__
- __post_init__
- _build_nonce
- _canonicalize_aead_token
- _check_replay
- _instantiate_aead
- _native_decrypt
- _native_encrypt
- _py_decrypt
- _py_encrypt
- bump_epoch
- decrypt
- encrypt
- last_error_reason
- pack_header
- reset_replay
- seq

Network I/O:
- Not Found In Code

Crypto Usage:
- AESGCM; ChaCha20Poly1305; ascon; cryptography; pyascon

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: perf

Role Hints (from identifiers):
- drone, gcs

## core/async_proxy.py

Summary: Selectors-based network transport proxy.

Imports:
- __future__
- contextlib
- core.aead
- core.config
- core.control_tcp
- core.exceptions
- core.handshake
- core.logging_utils
- core.policy_engine
- core.suites
- hashlib
- json
- pathlib
- queue
- selectors
- socket
- struct
- sys
- threading
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ProxyCounters
- _TokenBucket

Core Functions:
- __init__
- _avg_ns_for
- _build_sender_receiver
- _compute_aead_ids
- _dscp_to_tos
- _emit
- _finalize_rekey
- _launch_manual_console
- _launch_rekey
- _ns_to_ms
- _parse_header_fields
- _part_b_metrics
- _perform_handshake
- _serialize
- _setup_sockets
- _status_writer
- _update_primitive
- _validate_config
- allow
- operator_loop
- prune
- record_decrypt_fail
- record_decrypt_ok
- record_encrypt
- run_proxy
- send_control
- status_loop
- to_dict
- worker
- write_status

Network I/O:
- asyncio; selectors; serial; socket

Crypto Usage:
- AESGCM; hashlib

Timing/Logging/Benchmarking Hooks:
- Timing: monotonic; perf_counter; perf_counter_ns; sleep; time
- Logging: get_logger; logger; logging
- Benchmark: metrics; perf

Role Hints (from identifiers):
- drone, gcs

## core/clock_sync.py

Summary: Clock Synchronization Module - core/clock_sync.py

Imports:
- json
- logging
- socket
- struct
- time

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ClockSync

Core Functions:
- __init__
- client_handshake
- get_offset
- is_synced
- server_handle_sync
- set_offset
- synced_time
- update_from_rpc

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: logging
- Benchmark: perf

Role Hints (from identifiers):
- drone, gcs

## core/config.py

Summary: Core configuration constants for PQC drone-GCS secure proxy.

Imports:
- core.exceptions
- ipaddress
- os
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- _apply_env_overrides
- validate_config

Network I/O:
- serial

Crypto Usage:
- AESGCM; ChaCha20Poly1305; ascon; hmac

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: benchmark; ina219; metrics; perf; power; throughput

Role Hints (from identifiers):
- drone, gcs

## core/control_tcp.py

Summary: TCP JSON control server for core proxy.

Imports:
- __future__
- core.logging_utils
- core.policy_engine
- core.suites
- dataclasses
- json
- socket
- threading
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ControlTcpConfig
- ControlTcpServer

Core Functions:
- __init__
- _accept_loop
- _client_loop
- _handle_message
- _is_allowed_peer
- _is_allowed_rekey_peer
- _send_json
- build_allowed_peers
- build_rekey_allowed_peers
- start
- start_control_server_if_enabled
- stop

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: get_logger; logger; logging
- Benchmark: power

Role Hints (from identifiers):
- drone, gcs

## core/exceptions.py

Summary: Project-specific exception types for clearer error semantics.

Imports:
- Not Found In Code

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- AeadError
- ConfigError
- HandshakeError
- HandshakeFormatError
- HandshakeVerifyError
- SequenceOverflow

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## core/handshake.py

Summary: Not Found In Code

Imports:
- core.config
- core.exceptions
- core.logging_utils
- core.suites
- cryptography.hazmat.primitives
- cryptography.hazmat.primitives.kdf.hkdf
- dataclasses
- hashlib
- hmac
- oqs
- oqs.oqs
- os
- struct
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ServerEphemeral
- ServerHello

Core Functions:
- _drone_psk_bytes
- _export_time
- _finalize_handshake_metrics
- _ns_to_ms
- build_server_hello
- client_drone_handshake
- client_encapsulate
- derive_transport_keys
- parse_and_verify_server_hello
- server_decapsulate
- server_gcs_handshake

Network I/O:
- socket

Crypto Usage:
- HKDF; cryptography; hashlib; hmac; oqs

Timing/Logging/Benchmarking Hooks:
- Timing: perf_counter; perf_counter_ns; time
- Logging: get_logger; logger; logging
- Benchmark: metrics; perf

Role Hints (from identifiers):
- drone, gcs

## core/logging_utils.py

Summary: Not Found In Code

Imports:
- json
- logging
- pathlib
- sys
- time

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Counter
- Gauge
- JsonFormatter
- Metrics

Core Functions:
- __init__
- configure_file_logger
- counter
- format
- gauge
- get_logger
- inc
- set

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: get_logger; logger; logging
- Benchmark: metrics

Role Hints (from identifiers):
- Not Found In Code

## core/mavlink_collector.py

Summary: Not Found In Code

Imports:
- Not Found In Code

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- mavutil; pymavlink; socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; monotonic; sleep; time
- Logging: Not Found In Code
- Benchmark: benchmark; jitter; latency; metrics

Role Hints (from identifiers):
- drone, gcs

## core/metrics_aggregator.py

Summary: Comprehensive Metrics Aggregator

Imports:
- core.mavlink_collector
- core.metrics_collectors
- core.metrics_schema
- dataclasses
- datetime
- json
- logging
- os
- pathlib
- platform
- socket
- sys
- threading
- time
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- MetricsAggregator

Core Functions:
- __init__
- _detect_role
- _get_counter_int
- _mark_metric_status
- _merge_peer_data
- _save_metrics
- _start_background_collection
- _stop_background_collection
- collect_loop
- finalize_suite
- get_current_metrics
- get_exportable_data
- record_control_plane_metrics
- record_crypto_primitives
- record_data_plane_metrics
- record_handshake_end
- record_handshake_start
- record_latency_sample
- record_traffic_end
- record_traffic_start
- register_mavlink_callback
- register_proxy_callback
- save_suite_metrics
- set_clock_offset
- set_run_id
- start_suite

Network I/O:
- socket

Crypto Usage:
- AESGCM; oqs

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; monotonic; sleep; time
- Logging: logger; logging
- Benchmark: benchmark; jitter; latency; metrics; perf; power; throughput

Role Hints (from identifiers):
- drone, gcs

## core/metrics_collectors.py

Summary: Metrics Collectors - Base and System Collectors

Imports:
- dataclasses
- datetime
- ina219
- json
- oqs
- os
- pathlib
- platform
- psutil
- socket
- subprocess
- sys
- threading
- time
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- BaseCollector
- EnvironmentCollector
- LatencyTracker
- NetworkCollector
- PowerCollector
- SystemCollector

Core Functions:
- __init__
- _check_throttling
- _detect_backend
- _detect_platform
- _get_git_commit
- _get_kernel_version
- _get_oqs_version
- _init_ina219
- _is_git_dirty
- _read_rpi5_hwmon
- _read_temperature
- clear
- collect
- collect_timed
- get_cpu_stats
- get_energy_stats
- get_ip_address
- get_samples
- get_stats
- record
- sample_loop
- start_sampling
- stop_sampling

Network I/O:
- socket

Crypto Usage:
- oqs

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; monotonic; perf_counter; sleep; time
- Logging: Not Found In Code
- Benchmark: ina219; latency; metrics; perf; power

Role Hints (from identifiers):
- drone, gcs

## core/metrics_schema.py

Summary: Comprehensive Metrics Schema for PQC Benchmark

Imports:
- dataclasses
- datetime
- json
- os
- platform
- subprocess
- time
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ComprehensiveSuiteMetrics
- ControlPlaneMetrics
- CryptoPrimitiveBreakdown
- DataPlaneMetrics
- FlightControllerTelemetry
- HandshakeMetrics
- LatencyJitterMetrics
- MavLinkIntegrityMetrics
- MavProxyDroneMetrics
- MavProxyGcsMetrics
- ObservabilityMetrics
- PowerEnergyMetrics
- RekeyMetrics
- RunContextMetrics
- SuiteCryptoIdentity
- SuiteLifecycleTimeline
- SystemResourcesDrone
- SystemResourcesGcs
- ValidationMetrics

Core Functions:
- count_metrics
- from_dict
- from_json
- load_json
- save_json
- to_dict
- to_json

Network I/O:
- serial

Crypto Usage:
- AESGCM; oqs

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; time
- Logging: logging
- Benchmark: benchmark; ina219; jitter; latency; metrics; power; throughput

Role Hints (from identifiers):
- drone, gcs

## core/policy_engine.py

Summary: In-band control-plane state machine for interactive rekey negotiation.

Imports:
- __future__
- collections
- dataclasses
- queue
- secrets
- threading
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ControlResult
- ControlState

Core Functions:
- _default_safe
- _now_ms
- coordinator_role_from_config
- create_control_state
- enqueue_json
- generate_rid
- handle_control
- is_coordinator
- normalize_coordinator_role
- record_rekey_result
- request_prepare
- set_coordinator_role

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: monotonic; time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## core/power_monitor.py

Summary: High-frequency power monitoring helpers for drone follower.

Imports:
- __future__
- core.config
- csv
- dataclasses
- math
- os
- pathlib
- psutil
- random
- re
- shutil
- smbus2
- subprocess
- threading
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Ina219PowerMonitor
- MockPowerMonitor
- PowerMonitor
- PowerMonitorUnavailable
- PowerSample
- PowerSummary
- Rpi5PmicPowerMonitor
- Rpi5PowerMonitor

Core Functions:
- __init__
- _choose_voltage
- _configure
- _derive_current
- _find_hwmon_dir
- _pick_profile
- _read_bus_voltage
- _read_channel
- _read_current_voltage
- _read_measurements
- _read_once
- _read_s16
- _read_shunt_voltage
- _read_u16
- _resolve_channels
- _resolve_scale
- _resolve_sign
- _sanitize_label
- _sum_power
- capture
- create_power_monitor
- is_supported
- iter_samples
- pick
- sign_factor

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: perf_counter; sleep; time
- Logging: logging
- Benchmark: ina219; perf; power

Role Hints (from identifiers):
- drone

## core/power_monitor_full.py

Summary: Not Found In Code

Imports:
- Not Found In Code

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## core/process.py

Summary: Unified Process Lifecycle Management.

Imports:
- atexit
- ctypes
- logging
- os
- signal
- subprocess
- sys
- threading
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ManagedProcess
- _JOBOBJECT_BASIC_LIMIT_INFORMATION
- _JOBOBJECT_EXTENDED_LIMIT_INFORMATION

Core Functions:
- __init__
- _assign_process_to_job
- _create_job_object
- _linux_preexec
- _register
- _unregister
- is_running
- kill_all_managed_processes
- start
- stop
- wait

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: logger; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## core/suites.py

Summary: PQC cryptographic suite registry and algorithm ID mapping.

Imports:
- __future__
- core
- core.config
- core.logging_utils
- cryptography.hazmat.primitives.ciphers.aead
- oqs
- oqs.oqs
- os
- pyascon
- types
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- _build_alias_map
- _canonicalize_suite_id
- _compose_suite
- _generate_level_consistent_matrix
- _generate_suite_registry
- _normalize_alias
- _probe_aead_support
- _prune_suites_for_runtime
- _resolve_aead_key
- _resolve_kem_key
- _resolve_sig_key
- _safe_get_enabled_kem_mechanisms
- _safe_get_enabled_sig_mechanisms
- available_aead_tokens
- build_suite_id
- enabled_kems
- enabled_sigs
- filter_suites_by_levels
- get_suite
- header_ids_for_suite
- header_ids_from_names
- list_suites
- list_suites_for_level
- suite_bytes_for_hkdf
- unavailable_aead_reasons
- valid_nist_levels

Network I/O:
- Not Found In Code

Crypto Usage:
- AESGCM; ChaCha20Poly1305; HKDF; ascon; cryptography; oqs; pyascon

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: get_logger; logger; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## dashboard/backend/analysis.py

Summary: Analysis Module for PQC Benchmark Dashboard.

Imports:
- models
- pandas
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- aggregate_by_kem_family
- aggregate_by_nist_level
- compare_suites
- compute_comparison_table
- extract_drone_metrics
- extract_gcs_metrics
- generate_schema_definition
- get_drone_vs_gcs_summary
- get_field_reliability
- get_field_unit
- suite_to_flat_dict
- suites_to_dataframe

Network I/O:
- requests

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: benchmark; jitter; latency; metrics; power

Role Hints (from identifiers):
- drone, gcs

## dashboard/backend/ingest.py

Summary: Not Found In Code

Imports:
- glob
- json
- logging
- models
- pathlib
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- MetricsStore

Core Functions:
- __init__
- _build_minimal_suite
- _build_runs
- _get_path_for_status
- _load_comprehensive
- _load_json
- _load_jsonl_entries
- build_store
- get_store
- get_suite
- get_suite_by_key
- get_unique_values
- list_runs
- list_suites
- run_count
- suite_count

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: logger; logging
- Benchmark: benchmark; jitter; latency; metrics; power

Role Hints (from identifiers):
- drone, gcs

## dashboard/backend/main.py

Summary: Not Found In Code

Imports:
- fastapi
- fastapi.middleware.cors
- ingest
- logging
- models
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- get_run_suites
- list_runs
- read_root

Network I/O:
- http

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: logger; logging
- Benchmark: benchmark; metrics

Role Hints (from identifiers):
- gcs

## dashboard/backend/models.py

Summary: Pydantic models for PQC Benchmark Dashboard.

Imports:
- enum
- pydantic
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ComparisonResult
- ComprehensiveSuiteMetrics
- Config
- ControlPlaneMetrics
- CryptoPrimitiveBreakdown
- DataPlaneMetrics
- FlightControllerTelemetry
- HandshakeMetrics
- HealthResponse
- LatencyJitterMetrics
- MavLinkIntegrityMetrics
- MavProxyDroneMetrics
- MavProxyGcsMetrics
- ObservabilityMetrics
- PowerEnergyMetrics
- RekeyMetrics
- ReliabilityClass
- RunContextMetrics
- RunSummary
- SchemaField
- SuiteCryptoIdentity
- SuiteLifecycleTimeline
- SuiteSummary
- SystemResourcesDrone
- SystemResourcesGcs
- ValidationMetrics

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- oqs

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: logging
- Benchmark: benchmark; jitter; latency; metrics; power; throughput

Role Hints (from identifiers):
- drone, gcs

## dashboard/backend/reliability.py

Summary: Metric Reliability Classifications

Imports:
- enum
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ReliabilityClass

Core Functions:
- get_badge_class
- get_reliability
- should_display

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: benchmark; latency; metrics; power; throughput

Role Hints (from identifiers):
- drone, gcs

## dashboard/backend/routes/__init__.py

Summary: Not Found In Code

Imports:
- Not Found In Code

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## dashboard/backend/routes/suites.py

Summary: API Routes for PQC Benchmark Dashboard.

Imports:
- analysis
- fastapi
- ingest
- models
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- _nist_sort_key

Network I/O:
- http

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: benchmark; metrics; power

Role Hints (from identifiers):
- drone, gcs

## dashboard/backend/schemas.py

Summary: Not Found In Code

Imports:
- pydantic
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- CanonicalMetrics
- RunSummary
- SuiteDetail

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- oqs

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: benchmark; jitter; latency; metrics; power; throughput

Role Hints (from identifiers):
- drone, gcs

## dashboard/backend/test_ingest.py

Summary: Not Found In Code

Imports:
- dashboard.backend.ingest
- json

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- test

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: power

Role Hints (from identifiers):
- Not Found In Code

## debug_ingestion.py

Summary: Not Found In Code

Imports:
- glob
- json
- os
- requests

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- check_errors
- cleanup_old_files

Network I/O:
- http; requests

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: benchmark; metrics

Role Hints (from identifiers):
- Not Found In Code

## debug_standalone_ingest.py

Summary: Not Found In Code

Imports:
- dashboard.backend.ingest
- os
- pathlib
- sys
- traceback

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- test_load

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: metrics

Role Hints (from identifiers):
- Not Found In Code

## devtools/__init__.py

Summary: Development-Only Tooling for PQC Drone-GCS Secure Proxy

Imports:
- devtools.battery_sim
- devtools.config
- devtools.dashboard
- devtools.data_bus
- devtools.obs_emitter
- devtools.obs_receiver
- devtools.obs_schema
- logging
- pathlib
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Yes

Classes:
- Not Found In Code

Core Functions:
- _load_config
- _start_obs_receivers
- create_multi_receiver
- create_obs_emitter
- create_obs_receiver
- get_battery_provider
- get_config
- get_data_bus
- initialize
- is_enabled
- start_dashboard
- stop_all

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: logger; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## devtools/battery_bridge.py

Summary: Battery Provider Bridge

Imports:
- dataclasses
- devtools
- devtools.battery_sim
- devtools.data_bus
- logging
- sscheduler.local_mon
- threading
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- LocalMonitorBridge

Core Functions:
- __init__
- _update_data_bus
- armed
- battery_mv
- battery_pct
- cpu_pct
- create_with_devtools
- get_local_monitor
- get_metrics
- is_override_enabled
- running
- set_battery_provider
- start
- stop
- temp_c

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: logger; logging
- Benchmark: metrics

Role Hints (from identifiers):
- Not Found In Code

## devtools/battery_sim.py

Summary: Battery Provider Abstraction and Simulation

Imports:
- abc
- dataclasses
- devtools.config
- devtools.data_bus
- enum
- logging
- threading
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- BatteryProvider
- BatteryReading
- RealBatteryProvider
- SimulatedBatteryProvider
- SimulationMode

Core Functions:
- __init__
- _calc_stress
- _simulate_tick
- _update_data_bus
- _update_loop
- create_battery_provider
- get_battery_mv
- get_battery_pct
- get_battery_rate
- get_mode
- get_reading
- is_simulated
- reset
- set_drain_rate
- set_mode
- set_on_mode_change
- set_throttle_active
- set_voltage
- start
- stop
- trigger_step_drop

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: monotonic; sleep; time
- Logging: logger; logging
- Benchmark: metrics

Role Hints (from identifiers):
- Not Found In Code

## devtools/config.py

Summary: Dev Tools Configuration Loader

Imports:
- dataclasses
- json
- logging
- pathlib
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Yes

Classes:
- BatterySimConfig
- DevToolsConfig
- GuiConfig
- ObservabilityPlaneConfig

Core Functions:
- from_dict
- load_devtools_config
- save_devtools_config

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: logger; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## devtools/dashboard.py

Summary: Development Dashboard - Tkinter GUI

Imports:
- collections
- dataclasses
- devtools.battery_sim
- devtools.config
- devtools.data_bus
- logging
- threading
- time
- tkinter
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- DevDashboard
- GraphPoint

Core Functions:
- __init__
- _build_battery_panel
- _build_dataplane_panel
- _build_system_panel
- _build_telemetry_panel
- _build_timeline_panel
- _build_ui
- _format_bytes
- _on_close
- _on_mode_change
- _on_reset
- _on_step_drop
- _run_gui
- _schedule_update
- _update_graph
- _update_ui
- start
- stop

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: monotonic; time
- Logging: logger; logging
- Benchmark: jitter

Role Hints (from identifiers):
- drone, gcs

## devtools/data_bus.py

Summary: Thread-Safe Data Observability Bus

Imports:
- __future__
- collections
- dataclasses
- datetime
- devtools.obs_schema
- enum
- json
- logging
- obs_schema
- pathlib
- threading
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- BatteryState
- DataBus
- PolicyState
- ProxyState
- StressLevel
- SystemSnapshot
- TelemetryState
- TimelineEvent

Core Functions:
- __init__
- _add_event
- _log_update
- _notify
- add_event
- clear_history
- get_battery
- get_battery_history
- get_events
- get_policy
- get_proxy
- get_snapshot
- get_stats
- get_telemetry
- get_telemetry_history
- stop
- subscribe
- unsubscribe
- update_battery
- update_from_obs_snapshot
- update_policy
- update_proxy
- update_telemetry

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; monotonic; time
- Logging: logger; logging
- Benchmark: jitter

Role Hints (from identifiers):
- drone

## devtools/integration.py

Summary: Scheduler Integration for Dev Tools

Imports:
- devtools
- devtools.battery_sim
- devtools.config
- devtools.dashboard
- devtools.data_bus
- devtools.obs_emitter
- devtools.obs_schema
- logging
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- DevToolsIntegration
- NullIntegration

Core Functions:
- __init__
- _emit_obs_snapshot
- add_event
- create_if_enabled
- emit_snapshot_now
- get_battery_provider
- get_integration
- get_stats
- is_battery_simulated
- start
- stop
- update_battery
- update_policy
- update_proxy
- update_telemetry

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: logger; logging
- Benchmark: jitter

Role Hints (from identifiers):
- drone, gcs

## devtools/launcher.py

Summary: Dev Tools Launcher

Imports:
- argparse
- atexit
- devtools
- devtools.battery_sim
- devtools.config
- devtools.dashboard
- devtools.data_bus
- devtools.integration
- devtools.obs_emitter
- devtools.obs_receiver
- devtools.obs_schema
- logging
- pathlib
- random
- signal
- sscheduler
- sys
- threading
- time
- traceback
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Yes

Classes:
- Not Found In Code

Core Functions:
- cleanup
- log
- main
- on_snapshot
- run_demo_data
- run_gui_only
- run_obs_receiver_only
- run_standalone
- run_standard_scheduler
- run_with_role
- sigint_handler

Network I/O:
- Not Found In Code

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: log(; logger; logging
- Benchmark: jitter

Role Hints (from identifiers):
- drone, gcs

## devtools/obs_emitter.py

Summary: Observability Plane Emitter

Imports:
- logging
- obs_schema
- socket
- threading
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- NullEmitter
- ObsEmitter

Core Functions:
- __init__
- emit_raw
- emit_snapshot
- get_stats
- is_active
- start
- stop
- target

Network I/O:
- serial; socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: monotonic; time
- Logging: logger; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## devtools/obs_receiver.py

Summary: Observability Plane Receiver

Imports:
- dataclasses
- logging
- obs_schema
- socket
- threading
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- MultiReceiver
- NodeStats
- ObsReceiver
- ReceiverStats

Core Functions:
- __init__
- _invoke_callbacks
- _listen_loop
- _update_stats
- add_callback
- get_known_nodes
- get_last_snapshot
- get_receiver
- get_stats
- is_running
- listen_address
- remove_callback
- start
- stop

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: monotonic; time
- Logging: logger; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## devtools/obs_schema.py

Summary: Observability Plane Schema

Imports:
- dataclasses
- datetime
- enum
- json
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- BatterySnapshot
- NodeType
- ObsSnapshot
- PolicySnapshot
- ProxySnapshot
- StressLevel
- TelemetrySnapshot

Core Functions:
- create_snapshot
- from_bytes
- from_json
- to_bytes
- to_json
- validate_snapshot_size

Network I/O:
- serial

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; monotonic; time
- Logging: Not Found In Code
- Benchmark: jitter

Role Hints (from identifiers):
- drone, gcs

## devtools/test_obs_plane.py

Summary: OBS Plane Verification Test

Imports:
- datetime
- devtools.data_bus
- devtools.obs_emitter
- devtools.obs_receiver
- devtools.obs_schema
- logging
- socket
- sys
- threading
- time
- unittest

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- TestDataBusObsIntegration
- TestMultiReceiver
- TestObsEmitter
- TestObsLoopback
- TestObsReceiver
- TestObsSchema

Core Functions:
- callback
- on_receive
- run_tests
- test_bytes_roundtrip
- test_create_empty_snapshot
- test_create_full_snapshot
- test_emitter_basic
- test_emitter_disabled
- test_full_loopback
- test_invalid_json_returns_none
- test_json_roundtrip
- test_multi_receiver_setup
- test_null_emitter
- test_receiver_basic
- test_receiver_callback
- test_snapshot_size_validation
- test_update_from_obs_snapshot

Network I/O:
- serial; socket

Crypto Usage:
- AESGCM; ascon

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: logging
- Benchmark: jitter

Role Hints (from identifiers):
- drone, gcs

## diag_backend.py

Summary: Not Found In Code

Imports:
- dashboard.backend.main
- sys
- traceback

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## expert_analysis.py

Summary: Comprehensive PQC Benchmark Data Analysis

Imports:
- dataclasses
- datetime
- json
- math
- os
- pathlib
- statistics
- sys
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- BenchmarkAnalyzer
- StatsSummary
- SuiteMetrics

Core Functions:
- __init__
- _load_data
- _parse_suites
- compute_stats
- export_json
- generate_report
- main
- percentile

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; time
- Logging: Not Found In Code
- Benchmark: benchmark; latency; metrics; perf; power; throughput

Role Hints (from identifiers):
- Not Found In Code

## fix_dashboard_data.py

Summary: Not Found In Code

Imports:
- datetime
- glob
- json
- os

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- convert_summary_to_metrics

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; time
- Logging: Not Found In Code
- Benchmark: benchmark; latency; metrics; power

Role Hints (from identifiers):
- drone, gcs

## legacy/drone_follower.py

Summary: Drone follower/loopback agent driven entirely by core configuration.

Imports:
- __future__
- argparse
- bench_models
- collections
- copy
- core
- core.config
- core.power_monitor
- csv
- dataclasses
- datetime
- json
- math
- oqs
- os
- pathlib
- platform
- psutil
- queue
- shlex
- signal
- socket
- struct
- subprocess
- sys
- threading
- time
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ControlServer
- HighSpeedMonitor
- Monitors
- PowerCaptureManager
- SyntheticKinematicsModel
- TelemetryPublisher
- UdpEcho
- _TelemetryClient

Core Functions:
- __init__
- _accept_loop
- _annotate_packet
- _append_mark_entry
- _append_rekey_mark
- _bind_socket
- _coerce_float
- _coerce_int
- _collect_capabilities_snapshot
- _collect_hardware_context
- _connect_tuple
- _consume_perf
- _do_mark
- _emit_status
- _ensure_core_importable
- _merge_defaults
- _monitor_client
- _notify_artifacts
- _parse_args
- _parse_float_env
- _parse_float_optional
- _parse_int_env
- _phase
- _psutil_loop
- _record_artifacts
- _record_hardware_context
- _record_packet
- _register_client
- _remove_client
- _sample
- _send
- _start_server
- _summary_to_dict
- _tail_file_lines
- _telemetry_loop
- _warn_vcgencmd_unavailable
- _write_manifest
- attach_proxy
- configure_status_sink
- discover_initial_suite
- end_rekey
- handle
- killtree
- kinematics_summary
- log_runtime_environment
- main
- optimize_cpu_performance
- popen
- publish
- register_artifact_sink
- register_artifacts
- register_monitor_manifest
- register_telemetry_status
- resource_summary
- rotate
- run
- start
- start_capture
- start_drone_proxy
- start_rekey
- status
- step
- stop
- suite_outdir
- suite_secrets_dir
- ts
- worker
- write_marker

Network I/O:
- socket

Crypto Usage:
- AESGCM; oqs

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; monotonic; sleep; time
- Logging: Not Found In Code
- Benchmark: metrics; perf; power

Role Hints (from identifiers):
- drone, gcs

## legacy/gcs_scheduler.py

Summary: GCS scheduler that drives rekeys and UDP traffic using central configuration.

Imports:
- __future__
- argparse
- bisect
- collections
- contextlib
- copy
- core
- core.config
- csv
- ctypes
- errno
- io
- json
- math
- openpyxl
- openpyxl.chart
- os
- pathlib
- shlex
- shutil
- socket
- subprocess
- sys
- threading
- time
- tools.blackout_metrics
- tools.merge_power
- tools.power_utils
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Blaster
- P2Quantile
- SaturationTester
- SuiteSkipped
- TelemetryCollector

Core Functions:
- __init__
- _append_blackout_records
- _append_step_results
- _append_suite_text
- _apply_nist_level_filter
- _as_float
- _as_int
- _atomic_write_bytes
- _bisect_search
- _candidate_local_artifact_paths
- _clamp_to_capture
- _classify_signals
- _cleanup
- _close_file
- _close_socket
- _coarse_search
- _coerce
- _coerce_bool
- _compute_sampling_params
- _enrich_summary_rows
- _ensure_core_importable
- _ensure_local_artifact
- _ensure_local_power_artifact
- _ensure_suite_supported_remote
- _errors_indicate_fetch_disabled
- _evaluate_rate
- _extract_companion_metrics
- _extract_iperf3_udp_metrics
- _fetch_monitor_artifacts
- _fetch_power_artifacts
- _flatten_handshake_metrics
- _get
- _linear
- _linear_search
- _log_event
- _maybe_log
- _merge_defaults
- _metric_int
- _metric_ms
- _now
- _ns_to_ms
- _ns_to_us
- _parabolic
- _parse_cli_args
- _post_run_collect_local
- _post_run_fetch_artifacts
- _post_run_generate_reports
- _precise_sleep_until
- _read_proxy_counters
- _read_stream
- _record_artifact
- _remote_timestamp
- _resolve_manifest_entry
- _robust_copy
- _rounded
- _run
- _run_iperf3_client
- _run_rate
- _rx_loop
- _rx_once
- _suite_log_path
- _summarize_kinematics
- _tail_file_lines
- _to_int_or_none
- _update_history
- _windows_timer_resolution
- activate_suite
- add
- append_csv_sheet
- append_dict_sheet
- ctl_send
- dump_failure_diagnostics
- export_combined_excel
- export_excel
- filter_suites_for_follower
- ip_header_bytes_for_host
- locate_drone_session_dir
- log_runtime_environment
- main
- mkdirp
- poll_power_status
- preferred_initial_suite
- preflight_filter_suites
- read_proxy_stats_live
- read_proxy_summary
- request_power_capture
- resolve_suites
- resolve_under_root
- run
- run_suite
- run_suite_connectivity_only
- safe_sheet_name
- snapshot
- snapshot_proxy_artifacts
- start
- start_gcs_proxy
- stop
- suite_outdir
- timesync
- ts
- unique_sheet_name
- value
- wait_active_suite
- wait_handshake
- wait_pending_suite
- wait_proxy_rekey
- wait_rekey_transition
- wilson_interval
- write_summary

Network I/O:
- http; serial; socket

Crypto Usage:
- ascon

Timing/Logging/Benchmarking Hooks:
- Timing: perf_counter; perf_counter_ns; sleep; time
- Logging: log(; logging
- Benchmark: benchmark; jitter; metrics; perf; power; throughput

Role Hints (from identifiers):
- drone, gcs

## list_fast_suites.py

Summary: List only fast suites (ML-KEM based) for testing.

Imports:
- core.suites

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## log_codebase.py

Summary: Script to log all .py files in the codebase recursively.

Imports:
- os
- sys

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- log_codebase

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## modify_config.py

Summary: Not Found In Code

Imports:
- pathlib

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## run_metrics_benchmark.py

Summary: run_metrics_benchmark.py

Imports:
- argparse
- core.config
- core.metrics_aggregator
- core.metrics_collectors
- core.metrics_schema
- core.suites
- datetime
- json
- os
- pathlib
- socket
- struct
- subprocess
- sys
- threading
- time
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- MetricsBenchmark
- TrafficGenerator

Core Functions:
- __init__
- collect_baseline_metrics
- get_available_suites
- main
- run_suite
- run_traffic
- save_comprehensive_output
- start_proxy

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: Not Found In Code
- Benchmark: benchmark; latency; metrics

Role Hints (from identifiers):
- drone, gcs

## scheduler/__init__.py

Summary: Not Found In Code

Imports:
- Not Found In Code

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## scheduler/sdrone.py

Summary: Not Found In Code

Imports:
- __future__
- argparse
- core
- core.config
- core.suites
- json
- os
- pathlib
- signal
- socket
- struct
- subprocess
- sys
- threading
- time
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ControlServer
- UdpEchoServer

Core Functions:
- __init__
- _do_rekey
- _do_start
- _ensure_core_importable
- _handle_client
- _handle_command
- get_available_suites
- get_stats
- killtree
- log
- main
- parse_args
- popen
- reset_stats
- run
- signal_handler
- start_drone_proxy
- ts

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: log(
- Benchmark: benchmark; power

Role Hints (from identifiers):
- drone, gcs

## scheduler/sgcs.py

Summary: Not Found In Code

Imports:
- __future__
- argparse
- core
- core.config
- core.suites
- dataclasses
- json
- os
- pathlib
- signal
- socket
- struct
- subprocess
- sys
- threading
- time
- traceback
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- SuiteResult

Core Functions:
- _ensure_core_importable
- get_available_suites
- get_drone_status
- killtree
- log
- main
- parse_args
- ping_drone
- popen
- rekey_drone
- run_suite
- send_control_command
- start_drone_proxy
- start_gcs_proxy
- stop_drone
- ts

Network I/O:
- socket

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: log(
- Benchmark: benchmark; power; throughput

Role Hints (from identifiers):
- drone, gcs

## scripts/analyze_benchmarks.py

Summary: Benchmark Analysis Script - scripts/analyze_benchmarks.py

Imports:
- argparse
- collections
- core.suites
- csv
- datetime
- json
- os
- pathlib
- statistics
- sys
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- BenchmarkAnalyzer

Core Functions:
- __init__
- _analyze_suite
- _calc_stats
- analyze
- export_csv
- generate_policy_recommendations
- load_data
- main
- print_summary
- rank_suites

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; time
- Logging: Not Found In Code
- Benchmark: benchmark; jitter; latency; metrics; perf; power; throughput

Role Hints (from identifiers):
- drone, gcs

## scripts/regenerate_matrix_keys.py

Summary: Not Found In Code

Imports:
- core.suites
- os
- pathlib
- subprocess
- sys

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## scripts/run_gcs_metrics.py

Summary: Minimal runner for GCS Metrics Collector.

Imports:
- logging
- pathlib
- sscheduler.gcs_metrics
- sys
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: logging
- Benchmark: metrics

Role Hints (from identifiers):
- gcs

## scripts/run_gcs_telemetry_v1.py

Summary: Not Found In Code

Imports:
- Not Found In Code

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- gcs

## scripts/telemetry_recv_test.py

Summary: Telemetry Receiver Doctor (Drone Side)

Imports:
- core.config
- json
- pathlib
- socket
- sys
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: metrics

Role Hints (from identifiers):
- drone, gcs

## scripts/telemetry_send_test.py

Summary: Telemetry Sender Doctor (GCS Side)

Imports:
- json
- pathlib
- socket
- sys
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: monotonic; sleep; time
- Logging: Not Found In Code
- Benchmark: metrics

Role Hints (from identifiers):
- drone, gcs

## scripts/test_ina219.py

Summary: Quick INA219 power monitor test.

Imports:
- core.power_monitor
- pathlib
- sys
- traceback

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: ina219; power

Role Hints (from identifiers):
- Not Found In Code

## scripts/transfer_benchmark_data.py

Summary: Benchmark Data Transfer Script - scripts/transfer_benchmark_data.py

Imports:
- argparse
- datetime
- os
- pathlib
- subprocess
- sys

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- list_remote_benchmarks
- log
- main
- run_ssh_cmd
- transfer_benchmark

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; time
- Logging: log(
- Benchmark: benchmark

Role Hints (from identifiers):
- drone, gcs

## scripts/validate_drone_policy.py

Summary: Phase 5: Drone Policy Validation Script

Imports:
- argparse
- datetime
- json
- pathlib
- sscheduler.policy
- sscheduler.telemetry_window
- sys
- tempfile
- time
- traceback
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- banner
- main
- make_decision_input
- run_all_tests
- test_decision_input_immutable
- test_find_adjacent_suite
- test_policy_downgrade_at_lowest
- test_policy_downgrade_on_high_silence
- test_policy_downgrade_on_severe_stress
- test_policy_downgrade_on_stale
- test_policy_failsafe_hold
- test_policy_hold
- test_policy_hold_during_cooldown
- test_policy_hold_on_low_confidence
- test_policy_output_to_dict
- test_receiver_health_gate
- test_suite_tier_mapping
- test_telemetry_window

Network I/O:
- serial

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; monotonic; time
- Logging: Not Found In Code
- Benchmark: jitter; metrics

Role Hints (from identifiers):
- drone, gcs

## scripts/verify_rpc.py

Summary: Not Found In Code

Imports:
- os
- sscheduler.sdrone
- sys
- time

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## sdrone.remote.py

Summary: Simplified Drone Scheduler (CONTROLLER) - sscheduler/sdrone.py

Imports:
- argparse
- core.config
- core.suites
- datetime
- json
- os
- pathlib
- signal
- socket
- subprocess
- sys
- threading
- time
- tools.mavproxy_manager

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- DroneProxyManager
- UdpEchoServer

Core Functions:
- __init__
- _echo_loop
- get_stats
- is_running
- log
- main
- reset_stats
- run_suite
- send_gcs_command
- signal_handler
- start
- stop
- wait_for_gcs

Network I/O:
- socket

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## sdrone.remote2.py

Summary: Simplified Drone Scheduler (CONTROLLER) - sscheduler/sdrone.py

Imports:
- argparse
- core.config
- core.suites
- datetime
- json
- os
- pathlib
- signal
- socket
- subprocess
- sys
- threading
- time
- tools.mavproxy_manager

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- DroneProxyManager
- UdpEchoServer

Core Functions:
- __init__
- _echo_loop
- get_stats
- is_running
- log
- main
- reset_stats
- run_suite
- send_gcs_command
- signal_handler
- start
- stop
- wait_for_gcs

Network I/O:
- socket

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## snapshot/auto/drone_follower.py

Summary: Drone follower/loopback agent driven entirely by core configuration.

Imports:
- __future__
- argparse
- bench_models
- collections
- copy
- core
- core.config
- core.power_monitor
- csv
- dataclasses
- datetime
- json
- math
- oqs
- os
- pathlib
- platform
- psutil
- queue
- shlex
- signal
- socket
- struct
- subprocess
- sys
- threading
- time
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ControlServer
- HighSpeedMonitor
- Monitors
- PowerCaptureManager
- SyntheticKinematicsModel
- TelemetryPublisher
- UdpEcho
- _TelemetryClient

Core Functions:
- __init__
- _accept_loop
- _annotate_packet
- _append_mark_entry
- _append_rekey_mark
- _bind_socket
- _coerce_float
- _coerce_int
- _collect_capabilities_snapshot
- _collect_hardware_context
- _connect_tuple
- _consume_perf
- _do_mark
- _emit_status
- _ensure_core_importable
- _merge_defaults
- _monitor_client
- _notify_artifacts
- _parse_args
- _parse_float_env
- _parse_float_optional
- _parse_int_env
- _phase
- _psutil_loop
- _record_artifacts
- _record_hardware_context
- _record_packet
- _register_client
- _remove_client
- _sample
- _send
- _start_server
- _summary_to_dict
- _tail_file_lines
- _telemetry_loop
- _warn_vcgencmd_unavailable
- _write_manifest
- attach_proxy
- configure_status_sink
- discover_initial_suite
- end_rekey
- handle
- killtree
- kinematics_summary
- log_runtime_environment
- main
- optimize_cpu_performance
- popen
- publish
- register_artifact_sink
- register_artifacts
- register_monitor_manifest
- register_telemetry_status
- resource_summary
- rotate
- run
- start
- start_capture
- start_drone_proxy
- start_rekey
- status
- step
- stop
- suite_outdir
- suite_secrets_dir
- ts
- worker
- write_marker

Network I/O:
- socket

Crypto Usage:
- AESGCM; oqs

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; monotonic; sleep; time
- Logging: Not Found In Code
- Benchmark: metrics; perf; power

Role Hints (from identifiers):
- drone, gcs

## snapshot/auto/gcs_scheduler.py

Summary: GCS scheduler that drives rekeys and UDP traffic using central configuration.

Imports:
- __future__
- argparse
- bisect
- collections
- contextlib
- copy
- core
- core.config
- csv
- ctypes
- errno
- io
- json
- math
- openpyxl
- openpyxl.chart
- os
- pathlib
- shlex
- shutil
- socket
- subprocess
- sys
- threading
- time
- tools.blackout_metrics
- tools.merge_power
- tools.power_utils
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Blaster
- P2Quantile
- SaturationTester
- SuiteSkipped
- TelemetryCollector

Core Functions:
- __init__
- _append_blackout_records
- _append_step_results
- _append_suite_text
- _apply_nist_level_filter
- _as_float
- _as_int
- _atomic_write_bytes
- _bisect_search
- _candidate_local_artifact_paths
- _clamp_to_capture
- _classify_signals
- _cleanup
- _close_file
- _close_socket
- _coarse_search
- _coerce
- _coerce_bool
- _compute_sampling_params
- _enrich_summary_rows
- _ensure_core_importable
- _ensure_local_artifact
- _ensure_local_power_artifact
- _ensure_suite_supported_remote
- _errors_indicate_fetch_disabled
- _evaluate_rate
- _extract_companion_metrics
- _extract_iperf3_udp_metrics
- _fetch_monitor_artifacts
- _fetch_power_artifacts
- _flatten_handshake_metrics
- _get
- _linear
- _linear_search
- _log_event
- _maybe_log
- _merge_defaults
- _metric_int
- _metric_ms
- _now
- _ns_to_ms
- _ns_to_us
- _parabolic
- _parse_cli_args
- _post_run_collect_local
- _post_run_fetch_artifacts
- _post_run_generate_reports
- _precise_sleep_until
- _read_proxy_counters
- _read_stream
- _record_artifact
- _remote_timestamp
- _resolve_manifest_entry
- _robust_copy
- _rounded
- _run
- _run_iperf3_client
- _run_rate
- _rx_loop
- _rx_once
- _suite_log_path
- _summarize_kinematics
- _tail_file_lines
- _to_int_or_none
- _update_history
- _windows_timer_resolution
- activate_suite
- add
- append_csv_sheet
- append_dict_sheet
- ctl_send
- dump_failure_diagnostics
- export_combined_excel
- export_excel
- filter_suites_for_follower
- ip_header_bytes_for_host
- locate_drone_session_dir
- log_runtime_environment
- main
- mkdirp
- poll_power_status
- preferred_initial_suite
- preflight_filter_suites
- read_proxy_stats_live
- read_proxy_summary
- request_power_capture
- resolve_suites
- resolve_under_root
- run
- run_suite
- run_suite_connectivity_only
- safe_sheet_name
- snapshot
- snapshot_proxy_artifacts
- start
- start_gcs_proxy
- stop
- suite_outdir
- timesync
- ts
- unique_sheet_name
- value
- wait_active_suite
- wait_handshake
- wait_pending_suite
- wait_proxy_rekey
- wait_rekey_transition
- wilson_interval
- write_summary

Network I/O:
- http; serial; socket

Crypto Usage:
- ascon

Timing/Logging/Benchmarking Hooks:
- Timing: perf_counter; perf_counter_ns; sleep; time
- Logging: log(; logging
- Benchmark: benchmark; jitter; metrics; perf; power; throughput

Role Hints (from identifiers):
- drone, gcs

## snapshot/bench_models.py

Summary: Not Found In Code

Imports:
- __future__

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- calculate_predicted_flight_constraint

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: power

Role Hints (from identifiers):
- Not Found In Code

## snapshot/check_oqs.py

Summary: Not Found In Code

Imports:
- oqs
- sys

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- oqs

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## snapshot/config.remote.py

Summary: Core configuration constants for PQC drone-GCS secure proxy.

Imports:
- core.exceptions
- ipaddress
- os
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- _apply_env_overrides
- validate_config

Network I/O:
- serial

Crypto Usage:
- AESGCM; ChaCha20Poly1305; ascon; hmac

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: benchmark; ina219; metrics; perf; power

Role Hints (from identifiers):
- drone, gcs

## snapshot/core/__init__.py

Summary: PQC Drone-GCS Secure Proxy Core Package.

Imports:
- Not Found In Code

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- cryptography

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## snapshot/core/aead.py

Summary: AEAD framing for PQC drone-GCS secure proxy.

Imports:
- core
- core.config
- core.exceptions
- cryptography.exceptions
- cryptography.hazmat.primitives.ciphers.aead
- dataclasses
- pyascon
- struct
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- AeadAuthError
- AeadIds
- HeaderMismatch
- Receiver
- ReplayError
- Sender
- _AsconAdapter

Core Functions:
- __init__
- __post_init__
- _build_nonce
- _canonicalize_aead_token
- _check_replay
- _instantiate_aead
- _native_decrypt
- _native_encrypt
- _py_decrypt
- _py_encrypt
- bump_epoch
- decrypt
- encrypt
- last_error_reason
- pack_header
- reset_replay
- seq

Network I/O:
- Not Found In Code

Crypto Usage:
- AESGCM; ChaCha20Poly1305; ascon; cryptography; pyascon

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: perf

Role Hints (from identifiers):
- drone, gcs

## snapshot/core/async_proxy.py

Summary: Selectors-based network transport proxy.

Imports:
- __future__
- contextlib
- core.aead
- core.config
- core.control_tcp
- core.exceptions
- core.handshake
- core.logging_utils
- core.policy_engine
- core.suites
- hashlib
- json
- pathlib
- queue
- selectors
- socket
- struct
- sys
- threading
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ProxyCounters
- _TokenBucket

Core Functions:
- __init__
- _avg_ns_for
- _build_sender_receiver
- _compute_aead_ids
- _dscp_to_tos
- _emit
- _launch_manual_console
- _launch_rekey
- _ns_to_ms
- _parse_header_fields
- _part_b_metrics
- _perform_handshake
- _serialize
- _setup_sockets
- _status_writer
- _update_primitive
- _validate_config
- allow
- operator_loop
- prune
- record_decrypt_fail
- record_decrypt_ok
- record_encrypt
- run_proxy
- send_control
- status_loop
- to_dict
- worker
- write_status

Network I/O:
- asyncio; selectors; serial; socket

Crypto Usage:
- AESGCM; hashlib

Timing/Logging/Benchmarking Hooks:
- Timing: monotonic; perf_counter; perf_counter_ns; sleep; time
- Logging: get_logger; logger; logging
- Benchmark: metrics; perf

Role Hints (from identifiers):
- drone, gcs

## snapshot/core/config.py

Summary: Core configuration constants for PQC drone-GCS secure proxy.

Imports:
- core.exceptions
- ipaddress
- os
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- _apply_env_overrides
- validate_config

Network I/O:
- serial

Crypto Usage:
- AESGCM; ChaCha20Poly1305; ascon; hmac

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: benchmark; ina219; metrics; perf; power

Role Hints (from identifiers):
- drone, gcs

## snapshot/core/control_tcp.py

Summary: TCP JSON control server for core proxy.

Imports:
- __future__
- core.logging_utils
- core.policy_engine
- core.suites
- dataclasses
- json
- socket
- threading
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ControlTcpConfig
- ControlTcpServer

Core Functions:
- __init__
- _accept_loop
- _client_loop
- _handle_message
- _is_allowed_peer
- _is_allowed_rekey_peer
- _send_json
- build_allowed_peers
- build_rekey_allowed_peers
- start
- start_control_server_if_enabled
- stop

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: get_logger; logger; logging
- Benchmark: power

Role Hints (from identifiers):
- drone, gcs

## snapshot/core/exceptions.py

Summary: Project-specific exception types for clearer error semantics.

Imports:
- Not Found In Code

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- AeadError
- ConfigError
- HandshakeError
- HandshakeFormatError
- HandshakeVerifyError
- SequenceOverflow

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## snapshot/core/handshake.py

Summary: Not Found In Code

Imports:
- core.config
- core.exceptions
- core.logging_utils
- core.suites
- cryptography.hazmat.primitives
- cryptography.hazmat.primitives.kdf.hkdf
- dataclasses
- hashlib
- hmac
- oqs.oqs
- os
- struct
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ServerEphemeral
- ServerHello

Core Functions:
- _drone_psk_bytes
- _export_time
- _finalize_handshake_metrics
- _ns_to_ms
- build_server_hello
- client_drone_handshake
- client_encapsulate
- derive_transport_keys
- parse_and_verify_server_hello
- server_decapsulate
- server_gcs_handshake

Network I/O:
- socket

Crypto Usage:
- HKDF; cryptography; hashlib; hmac; oqs

Timing/Logging/Benchmarking Hooks:
- Timing: perf_counter; perf_counter_ns; time
- Logging: get_logger; logger; logging
- Benchmark: metrics; perf

Role Hints (from identifiers):
- drone, gcs

## snapshot/core/logging_utils.py

Summary: Not Found In Code

Imports:
- json
- logging
- pathlib
- sys
- time

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Counter
- Gauge
- JsonFormatter
- Metrics

Core Functions:
- __init__
- configure_file_logger
- counter
- format
- gauge
- get_logger
- inc
- set

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: get_logger; logger; logging
- Benchmark: metrics

Role Hints (from identifiers):
- Not Found In Code

## snapshot/core/policy_engine.py

Summary: In-band control-plane state machine for interactive rekey negotiation.

Imports:
- __future__
- collections
- dataclasses
- queue
- secrets
- threading
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ControlResult
- ControlState

Core Functions:
- _default_safe
- _now_ms
- coordinator_role_from_config
- create_control_state
- enqueue_json
- generate_rid
- handle_control
- is_coordinator
- normalize_coordinator_role
- record_rekey_result
- request_prepare
- set_coordinator_role

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: monotonic; time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## snapshot/core/power_monitor.py

Summary: High-frequency power monitoring helpers for drone follower.

Imports:
- __future__
- csv
- dataclasses
- math
- os
- pathlib
- psutil
- random
- re
- shutil
- smbus2
- subprocess
- threading
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Ina219PowerMonitor
- PowerMonitor
- PowerMonitorUnavailable
- PowerSample
- PowerSummary
- Rpi5PmicPowerMonitor
- Rpi5PowerMonitor
- SyntheticPowerMonitor

Core Functions:
- __init__
- _choose_voltage
- _compute_power
- _configure
- _derive_current
- _find_hwmon_dir
- _pick_profile
- _read_bus_voltage
- _read_channel
- _read_current_voltage
- _read_measurements
- _read_once
- _read_s16
- _read_shunt_voltage
- _read_u16
- _resolve_channels
- _resolve_scale
- _resolve_sign
- _sanitize_label
- _sum_power
- capture
- create_power_monitor
- is_supported
- iter_samples
- pick
- sign_factor

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: perf_counter; sleep; time
- Logging: logging
- Benchmark: ina219; jitter; perf; power

Role Hints (from identifiers):
- drone

## snapshot/core/process.py

Summary: Unified Process Lifecycle Management.

Imports:
- atexit
- ctypes
- logging
- os
- signal
- subprocess
- sys
- threading
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ManagedProcess
- _JOBOBJECT_BASIC_LIMIT_INFORMATION
- _JOBOBJECT_EXTENDED_LIMIT_INFORMATION

Core Functions:
- __init__
- _assign_process_to_job
- _create_job_object
- _linux_preexec
- _register
- _unregister
- is_running
- kill_all_managed_processes
- start
- stop
- wait

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: logger; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## snapshot/core/run_proxy.py

Summary: Unified CLI entrypoint for the PQC drone-GCS proxy.

Imports:
- argparse
- core.async_proxy
- core.config
- core.logging_utils
- core.suites
- json
- logging
- oqs.oqs
- os
- pathlib
- signal
- sys
- threading
- time
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- _augment_part_b_metrics
- _build_matrix_public_loader
- _build_matrix_secret_loader
- _copy_float
- _copy_int
- _flatten_part_b_metrics
- _format_duration_ns
- _ns_to_ms
- _pretty_print_counters
- _require_run_proxy
- _require_signature_class
- _resolve_suite
- create_secrets_dir
- drone_command
- gcs_command
- info
- init_identity_command
- instantiate
- load_public_for_suite
- load_secret_for_suite
- main
- signal_handler
- write_json_report

Network I/O:
- Not Found In Code

Crypto Usage:
- oqs

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: get_logger; logger; logging
- Benchmark: metrics

Role Hints (from identifiers):
- drone, gcs

## snapshot/core/suites.py

Summary: PQC cryptographic suite registry and algorithm ID mapping.

Imports:
- __future__
- core
- core.config
- core.logging_utils
- cryptography.hazmat.primitives.ciphers.aead
- oqs.oqs
- os
- pyascon
- types
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- _build_alias_map
- _canonicalize_suite_id
- _compose_suite
- _generate_level_consistent_matrix
- _generate_suite_registry
- _normalize_alias
- _probe_aead_support
- _prune_suites_for_runtime
- _resolve_aead_key
- _resolve_kem_key
- _resolve_sig_key
- _safe_get_enabled_kem_mechanisms
- _safe_get_enabled_sig_mechanisms
- available_aead_tokens
- build_suite_id
- enabled_kems
- enabled_sigs
- filter_suites_by_levels
- get_suite
- header_ids_for_suite
- header_ids_from_names
- list_suites
- list_suites_for_level
- suite_bytes_for_hkdf
- unavailable_aead_reasons
- valid_nist_levels

Network I/O:
- Not Found In Code

Crypto Usage:
- AESGCM; ChaCha20Poly1305; HKDF; ascon; cryptography; oqs; pyascon

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: get_logger; logger; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## snapshot/log_codebase.py

Summary: Script to log all .py files in the codebase recursively.

Imports:
- os
- sys

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- log_codebase

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## snapshot/modify_config.py

Summary: Not Found In Code

Imports:
- pathlib

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## snapshot/scheduler/__init__.py

Summary: Not Found In Code

Imports:
- Not Found In Code

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## snapshot/scheduler/sdrone.py

Summary: Simplified Drone Scheduler - Runs drone proxy with UDP echo for all suites.

Imports:
- __future__
- argparse
- core
- core.config
- core.suites
- json
- os
- pathlib
- signal
- socket
- struct
- subprocess
- sys
- threading
- time
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ControlServer
- UdpEchoServer

Core Functions:
- __init__
- _do_rekey
- _do_start
- _ensure_core_importable
- _handle_client
- _handle_command
- get_available_suites
- get_stats
- killtree
- log
- main
- parse_args
- popen
- reset_stats
- run
- signal_handler
- start_drone_proxy
- ts

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: log(
- Benchmark: benchmark; power

Role Hints (from identifiers):
- drone, gcs

## snapshot/scheduler/sgcs.py

Summary: Simplified GCS Scheduler - Runs all PQC suites with high-throughput traffic.

Imports:
- __future__
- argparse
- core
- core.config
- core.suites
- dataclasses
- json
- os
- pathlib
- signal
- socket
- struct
- subprocess
- sys
- threading
- time
- traceback
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- SuiteResult
- TrafficGenerator
- TrafficStats

Core Functions:
- __init__
- _ensure_core_importable
- _receiver_loop
- _transmitter_loop
- delivery_ratio
- duration_s
- get_available_suites
- get_drone_status
- killtree
- log
- main
- parse_args
- ping_drone
- popen
- rekey_drone
- run
- run_suite
- rx_mbps
- send_control_command
- start_drone_proxy
- start_gcs_proxy
- stop_drone
- ts
- tx_mbps

Network I/O:
- socket

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: perf_counter; sleep; time
- Logging: log(
- Benchmark: benchmark; perf; power; throughput

Role Hints (from identifiers):
- drone, gcs

## snapshot/scripts/regenerate_matrix_keys.py

Summary: Not Found In Code

Imports:
- core.suites
- os
- pathlib
- subprocess
- sys

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## snapshot/scripts/run_gcs_metrics.py

Summary: Minimal runner for GCS Metrics Collector.

Imports:
- logging
- pathlib
- sscheduler.gcs_metrics
- sys
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: logging
- Benchmark: metrics

Role Hints (from identifiers):
- gcs

## snapshot/scripts/run_gcs_telemetry_v1.py

Summary: Validation script for GCS Telemetry v1.

Imports:
- json
- logging
- pathlib
- socket
- sscheduler.gcs_metrics
- sys
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main
- traffic_generator

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: logging
- Benchmark: metrics

Role Hints (from identifiers):
- drone, gcs

## snapshot/sdrone.remote.py

Summary: Simplified Drone Scheduler (CONTROLLER) - sscheduler/sdrone.py

Imports:
- argparse
- core.config
- core.suites
- datetime
- json
- os
- pathlib
- signal
- socket
- subprocess
- sys
- threading
- time
- tools.mavproxy_manager

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- DroneProxyManager
- UdpEchoServer

Core Functions:
- __init__
- _echo_loop
- get_stats
- is_running
- log
- main
- reset_stats
- run_suite
- send_gcs_command
- signal_handler
- start
- stop
- wait_for_gcs

Network I/O:
- socket

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## snapshot/sdrone.remote2.py

Summary: Simplified Drone Scheduler (CONTROLLER) - sscheduler/sdrone.py

Imports:
- argparse
- core.config
- core.suites
- datetime
- json
- os
- pathlib
- signal
- socket
- subprocess
- sys
- threading
- time
- tools.mavproxy_manager

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- DroneProxyManager
- UdpEchoServer

Core Functions:
- __init__
- _echo_loop
- get_stats
- is_running
- log
- main
- reset_stats
- run_suite
- send_gcs_command
- signal_handler
- start
- stop
- wait_for_gcs

Network I/O:
- socket

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## snapshot/sscheduler/__init__.py

Summary: Not Found In Code

Imports:
- Not Found In Code

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## snapshot/sscheduler/gcs_metrics.py

Summary: GCS Telemetry Metrics Collector (Schema v1)

Imports:
- collections
- datetime
- json
- logging
- os
- pathlib
- psutil
- pymavlink
- socket
- threading
- time

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- GcsMetricsCollector

Core Functions:
- __init__
- _connect
- _process_mavlink
- _prune_windows
- _read_packets
- _run_loop
- _write_log
- add_event
- default
- get_snapshot
- start
- stop

Network I/O:
- mavutil; pymavlink; serial; socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; monotonic; sleep; time
- Logging: log(; logging
- Benchmark: jitter; metrics

Role Hints (from identifiers):
- drone, gcs

## snapshot/sscheduler/policy.py

Summary: Not Found In Code

Imports:
- random
- time

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- LinearLoopPolicy
- ManualOverridePolicy
- RandomPolicy
- SchedulingPolicy

Core Functions:
- __init__
- get_duration
- next_suite

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## snapshot/sscheduler/sdrone copy.py

Summary: Simplified Drone Scheduler (CONTROLLER) - sscheduler/sdrone.py

Imports:
- argparse
- core.config
- core.suites
- datetime
- json
- os
- pathlib
- signal
- socket
- subprocess
- sys
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- DroneProxyManager
- UdpEchoServer

Core Functions:
- __init__
- _echo_loop
- get_stats
- is_running
- log
- main
- reset_stats
- run_suite
- send_gcs_command
- signal_handler
- start
- stop
- wait_for_gcs

Network I/O:
- socket

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## snapshot/sscheduler/sdrone.py

Summary: Simplified Drone Scheduler (CONTROLLER) - sscheduler/sdrone.py

Imports:
- argparse
- atexit
- core.config
- core.process
- core.suites
- datetime
- json
- logging
- os
- pathlib
- signal
- socket
- sscheduler.policy
- subprocess
- sys
- threading
- time
- tools.mavproxy_manager

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- DecisionContext
- DroneProxyManager
- DroneScheduler
- TelemetryListener
- UdpEchoServer
- _GcsClient

Core Functions:
- __init__
- _echo_loop
- _listen_loop
- _sigint
- cleanup
- cleanup_environment
- get_gcs_status
- get_latest
- get_stats
- is_running
- log
- main
- reset_stats
- run_scheduler
- run_suite
- send_command
- send_gcs_command
- start
- start_persistent_mavproxy
- start_tunnel_for_suite
- stop
- stop_current_tunnel
- wait_for_gcs
- wait_for_handshake_completion

Network I/O:
- socket

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## snapshot/sscheduler/sgcs copy 2.py

Summary: Simplified GCS Scheduler (FOLLOWER) - sscheduler/sgcs.py

Imports:
- argparse
- core.config
- core.suites
- datetime
- json
- os
- pathlib
- signal
- socket
- subprocess
- sys
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ControlServer
- GcsProxyManager
- TrafficGenerator

Core Functions:
- __init__
- _handle_client
- _handle_command
- _receive_loop
- _send_loop
- _server_loop
- get_stats
- is_complete
- is_running
- log
- main
- signal_handler
- start
- stop

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## snapshot/sscheduler/sgcs copy.py

Summary: Simplified GCS Scheduler (FOLLOWER) - sscheduler/sgcs.py

Imports:
- argparse
- core.config
- core.suites
- datetime
- json
- os
- pathlib
- signal
- socket
- subprocess
- sys
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ControlServer
- GcsProxyManager
- TrafficGenerator

Core Functions:
- __init__
- _handle_client
- _handle_command
- _receive_loop
- _send_loop
- _server_loop
- get_stats
- is_complete
- is_running
- log
- main
- signal_handler
- start
- stop

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## snapshot/sscheduler/sgcs.py

Summary: Simplified GCS Scheduler (FOLLOWER) - sscheduler/sgcs.py

Imports:
- argparse
- atexit
- core.config
- core.process
- core.suites
- datetime
- json
- os
- pathlib
- signal
- socket
- sscheduler.gcs_metrics
- subprocess
- sys
- threading
- time
- tools.mavproxy_manager

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ControlServer
- GcsProxyManager
- TelemetrySender
- TrafficGenerator

Core Functions:
- __init__
- _handle_client
- _handle_command
- _receive_loop
- _send_loop
- _server_loop
- _telemetry_loop
- cleanup_environment
- close
- get_stats
- is_complete
- is_running
- log
- main
- send
- signal_handler
- start
- start_persistent_mavproxy
- stop
- wait_for_tcp_port

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: metrics

Role Hints (from identifiers):
- drone, gcs

## snapshot/test_all_complete_loop.py

Summary: Run complete localhost loop for all available suites in secrets/matrix.

Imports:
- argparse
- core.config
- core.suites
- os
- pathlib
- socket
- struct
- subprocess
- sys
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main
- run_echo
- run_suite
- traffic_sender

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## snapshot/test_complete_loop.py

Summary: Complete localhost loop test for PQC secure tunnel - all in one script.

Imports:
- core.config
- os
- socket
- struct
- subprocess
- sys
- threading
- time
- traceback

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main
- run_drone_echo
- run_test_client
- wait_for_port

Network I/O:
- socket

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## snapshot/test_localhost_loop.py

Summary: Localhost loop test for PQC secure tunnel.

Imports:
- socket
- struct
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main
- run_drone_echo_server
- run_gcs_sender_receiver

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## snapshot/test_multiple_suites.py

Summary: Test multiple PQC cipher suites on localhost.

Imports:
- os
- socket
- subprocess
- sys
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main
- run_echo
- test_suite
- wait_for_port_free

Network I/O:
- socket

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## snapshot/test_schedulers.py

Summary: Test scheduler pair on localhost - runs both sdrone and sgcs.

Imports:
- os
- signal
- subprocess
- sys
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## snapshot/test_simple_loop.py

Summary: Simple all-in-one localhost loop test.

Imports:
- os
- socket
- subprocess
- sys
- threading
- time
- traceback

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main
- run_echo

Network I/O:
- socket

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## snapshot/test_sscheduler.py

Summary: Test script for sscheduler (drone-controlled scheduler)

Imports:
- os
- signal
- subprocess
- sys
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## snapshot/tests/test_lifecycle.py

Summary: Not Found In Code

Imports:
- core.process
- os
- pathlib
- subprocess
- sys
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- test_lifecycle

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## snapshot/tools/__init__.py

Summary: Not Found In Code

Imports:
- Not Found In Code

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## snapshot/tools/blackout_metrics.py

Summary: Not Found In Code

Imports:
- __future__
- csv
- math
- pathlib
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- _find_mark_pair
- _percentile
- _rate_kpps
- _read_marks
- _read_packets
- compute_blackout

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## snapshot/tools/mavproxy_manager.py

Summary: Shared MavProxyManager for launching mavproxy subprocesses.

Imports:
- core.config
- core.process
- os
- pathlib
- signal
- subprocess
- sys
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- MavProxyManager

Core Functions:
- __init__
- _logs_dir_for
- is_running
- last_log
- start
- stop

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: log(
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## snapshot/tools/merge_power.py

Summary: Not Found In Code

Imports:
- __future__
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- extract_power_fields

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: power

Role Hints (from identifiers):
- Not Found In Code

## snapshot/tools/net_diag.py

Summary: Unified Network Diagnostic Tool for Secure Tunnel

Imports:
- core.config
- json
- pathlib
- platform
- select
- socket
- subprocess
- sys
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- PortTester

Core Functions:
- __init__
- _accept
- _listen
- check_firewall_binding
- check_tcp_connect
- detect_role
- get_local_ips
- log
- run_diagnostics
- start_listener
- start_tcp_acceptor

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: log(
- Benchmark: latency; perf

Role Hints (from identifiers):
- drone, gcs

## snapshot/tools/power_utils.py

Summary: Utility helpers for power trace analysis on the GCS.

Imports:
- __future__
- csv
- dataclasses
- pathlib
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- PowerSample

Core Functions:
- _detect_header
- _normalize
- _row_to_sample
- align_gcs_to_drone
- calculate_transient_energy
- integrate_energy_mj
- load_power_trace
- slice_window

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: power

Role Hints (from identifiers):
- drone, gcs

## sscheduler/__init__.py

Summary: Not Found In Code

Imports:
- Not Found In Code

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## sscheduler/benchmark_policy.py

Summary: Benchmark Policy for Comprehensive Suite Testing

Imports:
- core.suites
- dataclasses
- datetime
- enum
- json
- logging
- pathlib
- sscheduler.policy
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Yes

Classes:
- BenchmarkAction
- BenchmarkOutput
- BenchmarkPolicy
- DeterministicClockPolicy
- SuiteMetrics

Core Functions:
- __init__
- _build_suite_list
- _save_results
- _start_suite_metrics
- evaluate
- finalize_suite_metrics
- get_current_suite
- get_next_suite
- get_progress_summary
- get_suite_count
- get_suites_by_kem_family
- get_suites_by_nist_level
- load_benchmark_settings
- record_handshake_metrics
- record_runtime_metrics
- sort_key
- start_benchmark

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; monotonic; time
- Logging: logging
- Benchmark: benchmark; latency; metrics; perf; power; throughput

Role Hints (from identifiers):
- drone

## sscheduler/control_security.py

Summary: Security utilities for the control plane.

Imports:
- core.config
- hashlib
- hmac
- json
- os
- time

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- compute_response
- create_challenge
- get_drone_psk
- verify_response

Network I/O:
- Not Found In Code

Crypto Usage:
- hashlib; hmac

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone

## sscheduler/gcs_metrics.py

Summary: GCS Telemetry Metrics Collector (Schema v1)

Imports:
- collections
- core.config
- datetime
- json
- logging
- math
- os
- pathlib
- psutil
- pymavlink
- socket
- threading
- time

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- GcsMetricsCollector

Core Functions:
- __init__
- _connect
- _process_mavlink
- _prune_windows
- _read_packets
- _run_loop
- _write_log
- add_event
- default
- get_snapshot
- pct
- start
- stop

Network I/O:
- mavutil; pymavlink; serial; socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; monotonic; sleep; time
- Logging: log(; logging
- Benchmark: jitter; metrics

Role Hints (from identifiers):
- drone, gcs

## sscheduler/local_mon.py

Summary: Local System Monitor (Drone Side)

Imports:
- collections
- dataclasses
- logging
- os
- pathlib
- psutil
- pymavlink
- socket
- threading
- time

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- LocalMetrics
- LocalMonitor

Core Functions:
- __init__
- _connect_mav
- _monitor_loop
- _read_cpu
- _read_thermal
- _update_rates
- get_metrics
- start
- stop

Network I/O:
- mavutil; pymavlink; socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: logging
- Benchmark: metrics

Role Hints (from identifiers):
- drone

## sscheduler/policy.py

Summary: Scheduling policies for drone-side suite management.

Imports:
- core.suites
- dataclasses
- enum
- json
- logging
- pathlib
- random
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Yes

Classes:
- DecisionInput
- LinearLoopPolicy
- ManualOverridePolicy
- PolicyAction
- PolicyOutput
- RandomPolicy
- TelemetryAwarePolicyV2

Core Functions:
- __init__
- _add_blacklist
- _check_hysteresis
- _filter_suites
- _find_suite
- _is_blacklisted
- evaluate
- get_duration
- get_suite_tier
- load_settings
- next_suite
- record_rekey
- set_override

Network I/O:
- Not Found In Code

Crypto Usage:
- AESGCM; ascon

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: logging
- Benchmark: jitter; perf

Role Hints (from identifiers):
- drone, gcs

## sscheduler/sdrone copy.py

Summary: Simplified Drone Scheduler (CONTROLLER) - sscheduler/sdrone.py

Imports:
- argparse
- core.config
- core.suites
- datetime
- json
- os
- pathlib
- signal
- socket
- subprocess
- sys
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- DroneProxyManager
- UdpEchoServer

Core Functions:
- __init__
- _echo_loop
- get_stats
- is_running
- log
- main
- reset_stats
- run_suite
- send_gcs_command
- signal_handler
- start
- stop
- wait_for_gcs

Network I/O:
- socket

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## sscheduler/sdrone.py

Summary: Simplified Drone Scheduler (CONTROLLER) - sscheduler/sdrone.py

Imports:
- argparse
- core.config
- core.suites
- datetime
- json
- os
- pathlib
- signal
- socket
- subprocess
- sys
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- DroneProxyManager
- UdpEchoServer

Core Functions:
- __init__
- _echo_loop
- get_stats
- is_running
- log
- main
- reset_stats
- run_suite
- send_gcs_command
- signal_handler
- start
- stop
- wait_for_gcs

Network I/O:
- socket

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## sscheduler/sdrone_bench.py

Summary: Benchmark Drone Scheduler - sscheduler/sdrone_bench.py

Imports:
- argparse
- atexit
- core.clock_sync
- core.config
- core.metrics_aggregator
- core.process
- core.suites
- datetime
- json
- logging
- os
- pathlib
- signal
- socket
- sscheduler.benchmark_policy
- subprocess
- sys
- threading
- time
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- BenchmarkScheduler
- DroneProxyManager

Core Functions:
- __init__
- _activate_suite
- _atexit_cleanup
- _cleanup
- _collect_gcs_metrics
- _finalize_metrics
- _log_result
- _run_loop
- _save_final_summary
- cleanup_environment
- is_running
- log
- main
- read_handshake_status
- run
- send_gcs_command
- sigint_handler
- start
- start_mavproxy
- stop
- wait_for_gcs

Network I/O:
- socket

Crypto Usage:
- AESGCM; ascon

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; monotonic; sleep; time
- Logging: log(; logging
- Benchmark: benchmark; metrics

Role Hints (from identifiers):
- drone, gcs

## sscheduler/sdrone_mav.py

Summary: Simplified Drone Scheduler (CONTROLLER) - sscheduler/sdrone.py

Imports:
- argparse
- atexit
- core.clock_sync
- core.config
- core.process
- core.suites
- datetime
- json
- logging
- os
- pathlib
- signal
- socket
- sscheduler.policy
- subprocess
- sys
- threading
- time
- tools.mavproxy_manager

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- DecisionContext
- DroneProxyManager
- DroneScheduler
- TelemetryListener
- UdpEchoServer
- _GcsClient

Core Functions:
- __init__
- _echo_loop
- _listen_loop
- _sigint
- cleanup
- cleanup_environment
- get_gcs_status
- get_latest
- get_stats
- is_running
- log
- main
- reset_stats
- run_scheduler
- run_suite
- send_command
- send_gcs_command
- start
- start_persistent_mavproxy
- start_tunnel_for_suite
- stop
- stop_current_tunnel
- wait_for_gcs
- wait_for_handshake_completion

Network I/O:
- socket

Crypto Usage:
- AESGCM; ChaCha20Poly1305

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## sscheduler/sgcs copy 2.py

Summary: Simplified GCS Scheduler (FOLLOWER) - sscheduler/sgcs.py

Imports:
- argparse
- core.config
- core.suites
- datetime
- json
- os
- pathlib
- signal
- socket
- subprocess
- sys
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ControlServer
- GcsProxyManager
- TrafficGenerator

Core Functions:
- __init__
- _handle_client
- _handle_command
- _receive_loop
- _send_loop
- _server_loop
- get_stats
- is_complete
- is_running
- log
- main
- signal_handler
- start
- stop

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## sscheduler/sgcs copy.py

Summary: Simplified GCS Scheduler (FOLLOWER) - sscheduler/sgcs.py

Imports:
- argparse
- core.config
- core.suites
- datetime
- json
- os
- pathlib
- signal
- socket
- subprocess
- sys
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ControlServer
- GcsProxyManager
- TrafficGenerator

Core Functions:
- __init__
- _handle_client
- _handle_command
- _receive_loop
- _send_loop
- _server_loop
- get_stats
- is_complete
- is_running
- log
- main
- signal_handler
- start
- stop

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## sscheduler/sgcs.py

Summary: Simplified GCS Scheduler (FOLLOWER) - sscheduler/sgcs.py

Imports:
- argparse
- core.config
- core.suites
- datetime
- json
- os
- pathlib
- signal
- socket
- subprocess
- sys
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ControlServer
- GcsProxyManager
- TrafficGenerator

Core Functions:
- __init__
- _handle_client
- _handle_command
- _receive_loop
- _send_loop
- _server_loop
- get_stats
- is_complete
- is_running
- log
- main
- signal_handler
- start
- start_mavproxy_gui
- stop

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## sscheduler/sgcs_bench.py

Summary: GCS Benchmark Server - sscheduler/sgcs_bench.py

Imports:
- argparse
- atexit
- core.clock_sync
- core.config
- core.mavlink_collector
- core.metrics_aggregator
- core.metrics_collectors
- core.process
- core.suites
- dataclasses
- datetime
- json
- logging
- os
- pathlib
- platform
- pymavlink
- signal
- socket
- statistics
- subprocess
- sys
- threading
- time
- typing
- uuid

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- GcsBenchmarkServer
- GcsMavLinkCollector
- GcsMavProxyManager
- GcsProxyManager
- GcsSystemMetricsCollector

Core Functions:
- __init__
- _atexit_cleanup
- _handle_client
- _handle_command
- _listen_loop
- _numeric
- _process_message
- _read_proxy_status
- _server_loop
- _wait_for_handshake_ok
- get_kernel_version
- get_python_env
- is_running
- log
- loop
- main
- reset
- signal_handler
- start
- stop

Network I/O:
- mavutil; pymavlink; socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; monotonic; sleep; time
- Logging: log(; logger; logging
- Benchmark: benchmark; jitter; latency; metrics

Role Hints (from identifiers):
- drone, gcs

## sscheduler/sgcs_mav.py

Summary: Simplified GCS Scheduler (FOLLOWER) - sscheduler/sgcs.py

Imports:
- argparse
- atexit
- core.clock_sync
- core.config
- core.process
- core.suites
- datetime
- json
- os
- pathlib
- signal
- socket
- sscheduler.gcs_metrics
- subprocess
- sys
- threading
- time
- tools.mavproxy_manager

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ControlServer
- GcsProxyManager
- TelemetrySender

Core Functions:
- __init__
- _handle_client
- _handle_command
- _server_loop
- _telemetry_loop
- cleanup_environment
- close
- is_running
- log
- main
- send
- signal_handler
- start
- start_persistent_mavproxy
- stop
- wait_for_tcp_port

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: log(; logging
- Benchmark: metrics

Role Hints (from identifiers):
- drone, gcs

## sscheduler/telemetry_window.py

Summary: TelemetryWindow: bounded sliding-window of telemetry samples (monotonic-time based)

Imports:
- collections
- statistics
- threading
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- TelemetryWindow

Core Functions:
- __init__
- _prune_locked
- add
- get_confidence
- get_flight_state
- summarize

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: monotonic; time
- Logging: Not Found In Code
- Benchmark: jitter; metrics

Role Hints (from identifiers):
- gcs

## suite_benchmarks/analyze_benchmarks.py

Summary: PQC Suite Benchmark Analysis and Visualization

Imports:
- datetime
- json
- matplotlib.patches
- matplotlib.pyplot
- matplotlib.ticker
- numpy
- pandas
- pathlib
- statistics
- sys
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- add_labels
- calculate_statistics
- extract_kem_family
- extract_sig_family
- find_latest_results
- generate_latex_table
- generate_summary_report
- group_by_key
- load_benchmark_data
- load_jsonl_results
- main
- plot_energy_efficiency
- plot_handshake_by_nist_level
- plot_heatmap
- plot_kem_comparison
- plot_scatter_time_vs_size
- plot_signature_comparison
- plot_size_comparison
- process_results
- run_analysis
- setup_plot_style

Network I/O:
- Not Found In Code

Crypto Usage:
- AESGCM; ascon

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; time
- Logging: Not Found In Code
- Benchmark: benchmark; perf; power; throughput

Role Hints (from identifiers):
- drone

## suite_benchmarks/framework/suite_bench_drone.py

Summary: Suite Benchmark - Drone Side

Imports:
- __future__
- argparse
- collections
- core.config
- core.logging_utils
- core.power_monitor
- core.suites
- dataclasses
- datetime
- json
- os
- pathlib
- psutil
- signal
- smbus2
- socket
- struct
- subprocess
- sys
- threading
- time
- traceback
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- BenchmarkControlServer
- HandshakeMetrics
- LatencyTracker
- PowerCollector
- PowerSample
- ProxyManager
- RekeyMetrics
- SuiteMetrics

Core Functions:
- __init__
- _get_current_metrics
- _handle_connection
- _handle_rekey
- _process_command
- _save_result
- _start_suite
- _stop_suite
- get_stats
- get_system_metrics
- is_running
- main
- record_receive
- record_send
- reset
- run
- signal_handler
- start
- start_collection
- stop
- stop_collection

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; perf_counter; perf_counter_ns; sleep; time
- Logging: get_logger; logger; logging
- Benchmark: benchmark; ina219; latency; metrics; perf; power

Role Hints (from identifiers):
- drone, gcs

## suite_benchmarks/framework/suite_bench_gcs.py

Summary: Suite Benchmark - GCS Side (Scheduler)

Imports:
- __future__
- argparse
- collections
- core.config
- core.suites
- dataclasses
- datetime
- json
- os
- pathlib
- psutil
- signal
- socket
- subprocess
- sys
- threading
- time
- traceback
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- DroneController
- GCSProxyManager
- SuiteBenchResult
- SuiteBenchmarkRunner
- TrafficGenerator

Core Functions:
- __init__
- _generate_report
- _save_results
- _send_command
- get_available_suites
- get_metrics
- get_results
- is_running
- main
- ping
- rekey
- run
- run_suite_iteration
- shutdown
- signal_handler
- start
- start_suite
- status
- stop
- stop_suite
- verify_environment

Network I/O:
- socket

Crypto Usage:
- AESGCM; ChaCha20Poly1305; ascon; oqs

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; perf_counter; perf_counter_ns; sleep; time
- Logging: Not Found In Code
- Benchmark: benchmark; latency; metrics; perf; power; throughput

Role Hints (from identifiers):
- drone, gcs

## suite_benchmarks/generate_ieee_report.py

Summary: Comprehensive IEEE-Style PQC Benchmark Report Generator

Imports:
- collections
- dataclasses
- datetime
- json
- math
- matplotlib.patches
- matplotlib.pyplot
- numpy
- pathlib
- statistics
- sys
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- SuiteResult

Core Functions:
- aead_normalized
- categorize_results
- create_bucket_comparison_heatmap
- create_grouped_bar_chart
- create_radar_chart
- create_stacked_bar_chart
- escape_for_texttt
- escape_latex
- generate_aead_section
- generate_all_charts
- generate_full_latex_report
- generate_level_section
- generate_suite_page
- kem_total_ms
- load_results
- main
- primitive_total_ms
- sig_total_ms
- total_artifact_size

Network I/O:
- Not Found In Code

Crypto Usage:
- ascon; cryptography; oqs

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; time
- Logging: Not Found In Code
- Benchmark: benchmark; latency; metrics; perf; power; throughput

Role Hints (from identifiers):
- drone, gcs

## suite_benchmarks/generate_report.py

Summary: PQC Suite Benchmark Report Generator

Imports:
- collections
- datetime
- json
- matplotlib.patches
- matplotlib.pyplot
- numpy
- pathlib
- statistics
- sys

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- categorize_suites
- generate_charts
- generate_latex_report
- generate_latex_tables
- load_results
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- AESGCM; ascon; cryptography; oqs

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; time
- Logging: Not Found In Code
- Benchmark: benchmark; latency; perf

Role Hints (from identifiers):
- drone, gcs

## suite_benchmarks/run_full_benchmark.py

Summary: Complete Benchmark Runner - Run Full Suite Benchmark

Imports:
- argparse
- core.suites
- datetime
- json
- pathlib
- sscheduler.benchmark_policy
- sscheduler.sdrone_bench
- sys
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Args

Core Functions:
- check_prerequisites
- main
- print_banner
- print_instructions
- show_suite_plan

Network I/O:
- Not Found In Code

Crypto Usage:
- AESGCM; ascon; cryptography; oqs

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: Not Found In Code
- Benchmark: benchmark; ina219; latency; metrics; perf; power; throughput

Role Hints (from identifiers):
- drone, gcs

## test_all_complete_loop.py

Summary: Run complete localhost loop for all available suites in secrets/matrix.

Imports:
- argparse
- core.config
- core.suites
- os
- pathlib
- socket
- struct
- subprocess
- sys
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main
- run_echo
- run_suite
- traffic_sender

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## test_collectors.py

Summary: Quick test of all collectors.

Imports:
- core.metrics_aggregator
- core.metrics_collectors
- json

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: metrics

Role Hints (from identifiers):
- Not Found In Code

## test_complete_loop.py

Summary: Complete localhost loop test for PQC secure tunnel - all in one script.

Imports:
- core.config
- os
- socket
- struct
- subprocess
- sys
- threading
- time
- traceback

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main
- run_drone_echo
- run_test_client
- wait_for_port

Network I/O:
- socket

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## test_comprehensive_benchmark.py

Summary: Comprehensive Benchmark Runner

Imports:
- argparse
- core.async_proxy
- core.config
- core.metrics_aggregator
- core.metrics_collectors
- core.metrics_schema
- core.suites
- datetime
- json
- os
- pathlib
- socket
- sys
- threading
- time
- traceback
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- ComprehensiveBenchmarkRunner

Core Functions:
- __init__
- get_suite_list
- load_gcs_public_key
- load_gcs_signing_key
- main
- prepare_config
- run_all_suites
- run_proxy_thread
- run_single_suite

Network I/O:
- socket

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: Not Found In Code
- Benchmark: benchmark; metrics

Role Hints (from identifiers):
- drone, gcs

## test_gcs_ping.py

Summary: Quick test to ping GCS control server.

Imports:
- json
- socket

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- gcs

## test_localhost_loop.py

Summary: Localhost loop test for PQC secure tunnel.

Imports:
- socket
- struct
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main
- run_drone_echo_server
- run_gcs_sender_receiver

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## test_metrics_integration.py

Summary: test_metrics_integration.py

Imports:
- core.config
- core.metrics_aggregator
- core.metrics_schema
- core.suites
- datetime
- json
- os
- pathlib
- socket
- struct
- subprocess
- sys
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main
- run_echo_server
- start_proxy_process
- traffic_generator

Network I/O:
- socket

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; sleep; time
- Logging: Not Found In Code
- Benchmark: benchmark; latency; metrics

Role Hints (from identifiers):
- drone, gcs

## test_multiple_suites.py

Summary: Test multiple PQC cipher suites on localhost.

Imports:
- os
- socket
- subprocess
- sys
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main
- run_echo
- test_suite
- wait_for_port_free

Network I/O:
- socket

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## test_schedulers.py

Summary: Test scheduler pair on localhost - runs both sdrone and sgcs.

Imports:
- os
- signal
- subprocess
- sys
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## test_simple_loop.py

Summary: Simple all-in-one localhost loop test.

Imports:
- os
- socket
- subprocess
- sys
- threading
- time
- traceback

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main
- run_echo

Network I/O:
- socket

Crypto Usage:
- AESGCM

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## test_sscheduler.py

Summary: Test script for sscheduler (drone-controlled scheduler)

Imports:
- os
- signal
- subprocess
- sys
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## tests/test_lifecycle.py

Summary: Not Found In Code

Imports:
- core.process
- os
- pathlib
- subprocess
- sys
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- test_lifecycle

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## text-files/_gen_full_report.py

Summary: Not Found In Code

Imports:
- ast
- pathlib
- re

Entry Points:
- Main Guard: Not Found In Code
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Yes
- YAML: Yes
- settings.json: Yes

Classes:
- Not Found In Code

Core Functions:
- _detect_keys
- analyze_file

Network I/O:
- asyncio; grpc; http; mavutil; pymavlink; requests; selectors; serial; socket; urllib; zmq

Crypto Usage:
- AESGCM; ChaCha20Poly1305; HKDF; ascon; cryptography; hashlib; hmac; oqs; pyascon

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; monotonic; perf_counter; perf_counter_ns; sleep; time
- Logging: get_logger; log(; logger; logging
- Benchmark: benchmark; ina219; jitter; latency; metrics; perf; power; throughput

Role Hints (from identifiers):
- drone, gcs

## text-files/_gen_inventory.py

Summary: Not Found In Code

Imports:
- ast
- pathlib

Entry Points:
- Main Guard: Not Found In Code
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Yes
- JSON: Yes
- YAML: Yes
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- analyze_file

Network I/O:
- asyncio; grpc; http; mavutil; pymavlink; requests; selectors; socket; urllib; zmq

Crypto Usage:
- AESGCM; ChaCha20Poly1305; ascon; cryptography; hashlib; hmac; oqs; pyascon

Timing/Logging/Benchmarking Hooks:
- Timing: monotonic; perf_counter; perf_counter_ns; time
- Logging: get_logger; logger; logging
- Benchmark: benchmark; ina219; metrics; perf; power

Role Hints (from identifiers):
- Not Found In Code

## tools/__init__.py

Summary: Not Found In Code

Imports:
- Not Found In Code

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## tools/blackout_metrics.py

Summary: Not Found In Code

Imports:
- __future__
- csv
- math
- pathlib
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- _find_mark_pair
- _percentile
- _rate_kpps
- _read_marks
- _read_packets
- compute_blackout

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## tools/dump_suites.py

Summary: Not Found In Code

Imports:
- core.suites
- json
- pathlib
- sys

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: benchmark

Role Hints (from identifiers):
- Not Found In Code

## tools/gcs_control_ping.py

Summary: Not Found In Code

Imports:
- __future__
- argparse
- json
- socket

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## tools/ina219_read.py

Summary: Not Found In Code

Imports:
- __future__
- argparse
- ina219

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main
- try_read

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: ina219; power

Role Hints (from identifiers):
- Not Found In Code

## tools/mav_udp_sniff.py

Summary: Minimal UDP packet counter for MAVLink-forwarded streams.

Imports:
- __future__
- argparse
- select
- socket
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- Not Found In Code

## tools/mavproxy_manager.py

Summary: Shared MavProxyManager for launching mavproxy subprocesses.

Imports:
- core.config
- core.process
- os
- pathlib
- signal
- subprocess
- sys
- time
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Yes
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- MavProxyManager

Core Functions:
- __init__
- _logs_dir_for
- is_running
- last_log
- start
- stop

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: log(
- Benchmark: Not Found In Code

Role Hints (from identifiers):
- drone, gcs

## tools/merge_power.py

Summary: Not Found In Code

Imports:
- __future__
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- extract_power_fields

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: power

Role Hints (from identifiers):
- Not Found In Code

## tools/net_diag.py

Summary: Unified Network Diagnostic Tool for Secure Tunnel

Imports:
- core.config
- json
- pathlib
- platform
- select
- socket
- subprocess
- sys
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Yes
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- PortTester

Core Functions:
- __init__
- _accept
- _listen
- check_firewall_binding
- check_tcp_connect
- detect_role
- get_local_ips
- log
- run_diagnostics
- start_listener
- start_tcp_acceptor

Network I/O:
- socket

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: log(
- Benchmark: latency; perf

Role Hints (from identifiers):
- drone, gcs

## tools/orchestrate_run.py

Summary: Not Found In Code

Imports:
- os
- pathlib
- signal
- subprocess
- sys
- threading
- time

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main
- stream_reader

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: Not Found In Code
- Benchmark: benchmark

Role Hints (from identifiers):
- drone, gcs

## tools/power_utils.py

Summary: Utility helpers for power trace analysis on the GCS.

Imports:
- __future__
- csv
- dataclasses
- pathlib
- typing

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- PowerSample

Core Functions:
- _detect_header
- _normalize
- _row_to_sample
- align_gcs_to_drone
- calculate_transient_energy
- integrate_energy_mj
- load_power_trace
- slice_window

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: power

Role Hints (from identifiers):
- drone, gcs

## tools/verify_dashboard_truth.py

Summary: Verify dashboard truthfulness against comprehensive suite metrics.

Imports:
- json
- pathlib
- sys
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- _get_path
- _load_json
- main
- verify_suite

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: benchmark; jitter; latency; metrics; power

Role Hints (from identifiers):
- drone, gcs

## tools/verify_metrics_truth.py

Summary: Metrics Truth Verification Script

Imports:
- collections
- glob
- json
- pathlib
- reliability
- sys
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- is_non_default
- main
- print_results
- verify_jsonl
- verify_record

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: benchmark; metrics

Role Hints (from identifiers):
- Not Found In Code

## tools/wait_for_comprehensive_metrics.py

Summary: tools/wait_for_comprehensive_metrics.py

Imports:
- __future__
- argparse
- core.metrics_schema
- dataclasses
- json
- pathlib
- sys
- time
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: argparse/CLI

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- _expected_field_counts
- load_json
- main
- parse_filename
- validate_metrics_dict

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: sleep; time
- Logging: Not Found In Code
- Benchmark: benchmark; metrics; power

Role Hints (from identifiers):
- drone, gcs

## validate_bench.py

Summary: Validate benchmark results and extract statistics.

Imports:
- json
- pathlib
- statistics

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: benchmark; perf

Role Hints (from identifiers):
- Not Found In Code

## verify_collectors.py

Summary: Verify all 5 collectors - works on both GCS and Drone.

Imports:
- core.metrics_collectors
- json
- platform

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: latency; metrics; power

Role Hints (from identifiers):
- drone, gcs

## verify_drone_collectors.py

Summary: Drone metrics collectors verification script.

Imports:
- core.metrics_collectors
- datetime
- json
- time

Entry Points:
- Main Guard: Not Found In Code
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- Not Found In Code

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: datetime; time
- Logging: Not Found In Code
- Benchmark: latency; metrics; power

Role Hints (from identifiers):
- drone

## verify_gcs_collectors.py

Summary: Verify all 5 collectors on GCS side.

Imports:
- core.metrics_collectors
- json

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Not Found In Code
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: latency; metrics; power

Role Hints (from identifiers):
- gcs

## verify_metrics_integrity.py

Summary: Verify metrics integrity for comprehensive suite outputs.

Imports:
- json
- pathlib
- sys
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- _iter_records
- _walk_keys
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- HKDF

Timing/Logging/Benchmarking Hooks:
- Timing: time
- Logging: Not Found In Code
- Benchmark: jitter; latency; metrics; power

Role Hints (from identifiers):
- drone, gcs

## verify_metrics_output.py

Summary: Verify comprehensive metrics output files.

Imports:
- json
- pathlib
- sys
- typing

Entry Points:
- Main Guard: __main__ guard
- CLI: Not Found In Code

Config & Input Sources:
- CONFIG usage: Not Found In Code
- Env vars: Not Found In Code
- JSON: Yes
- YAML: Not Found In Code
- settings.json: Not Found In Code

Classes:
- Not Found In Code

Core Functions:
- _get_path
- _iter_records
- main

Network I/O:
- Not Found In Code

Crypto Usage:
- Not Found In Code

Timing/Logging/Benchmarking Hooks:
- Timing: Not Found In Code
- Logging: Not Found In Code
- Benchmark: metrics; power

Role Hints (from identifiers):
- Not Found In Code

