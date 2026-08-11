/**
 * Integrity Monitor Page - MAVLink integrity warnings
 */

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useDashboardStore } from '../state/store';
import type { SuiteSummary } from '../types/metrics';

interface IntegrityIssue {
    suite: SuiteSummary;
    issues: string[];
    severity: 'high' | 'medium' | 'low';
}

export default function IntegrityMonitor() {
    const { suites, isLoading, fetchSuites } = useDashboardStore();
    const [integrityData, setIntegrityData] = useState<IntegrityIssue[]>([]);

    useEffect(() => {
        fetchSuites();
    }, [fetchSuites]);

    useEffect(() => {
        // Analyze suites for integrity issues
        // Note: We only have summary data here, so we check available fields
        const issues: IntegrityIssue[] = [];

        suites.forEach(suite => {
            const suiteIssues: string[] = [];
            let severity: 'high' | 'medium' | 'low' = 'low';

            // Check for failed benchmarks
            if (suite.benchmark_pass_fail === 'FAIL') {
                suiteIssues.push('Benchmark marked as FAILED');
                severity = 'high';
            }

            // Check for handshake failures
            if (suite.handshake_success === false) {
                suiteIssues.push('Handshake did not succeed');
                severity = 'high';
            }

            // Check for missing power data
            if (suite.power_avg_w === null || suite.power_avg_w === undefined) {
                suiteIssues.push('Missing power data');
                if (severity !== 'high') severity = 'medium';
            }

            // Check for very high handshake times (>10s)
            if (suite.handshake_total_duration_ms !== null && suite.handshake_total_duration_ms !== undefined && suite.handshake_total_duration_ms > 10000) {
                suiteIssues.push(`Unusually high handshake duration: ${suite.handshake_total_duration_ms.toFixed(2)}ms`);
                if (severity !== 'high') severity = 'medium';
            }

            if (suiteIssues.length > 0) {
                issues.push({ suite, issues: suiteIssues, severity });
            }
        });

        // Sort by severity
        issues.sort((a, b) => {
            const order = { high: 0, medium: 1, low: 2 };
            return order[a.severity] - order[b.severity];
        });

        setIntegrityData(issues);
    }, [suites]);

    const getSeverityBadge = (severity: 'high' | 'medium' | 'low') => {
        const classes = {
            high: 'bg-red-500/20 text-red-400 px-2 py-0.5 rounded text-xs font-medium',
            medium: 'bg-amber-500/20 text-amber-400 px-2 py-0.5 rounded text-xs font-medium',
            low: 'bg-gray-500/20 text-gray-400 px-2 py-0.5 rounded text-xs font-medium',
        };
        return classes[severity];
    };

    if (isLoading && suites.length === 0) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="text-gray-400">Loading integrity data...</div>
            </div>
        );
    }

    // Count by severity
    const highCount = integrityData.filter(d => d.severity === 'high').length;
    const mediumCount = integrityData.filter(d => d.severity === 'medium').length;
    const lowCount = integrityData.filter(d => d.severity === 'low').length;
    const cleanCount = suites.length - integrityData.length;

    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-bold">Integrity Monitor</h1>

            <div className="disclaimer-banner">
                <strong>Note:</strong> This page shows data quality issues detected from suite metadata.
                For detailed MAVLink integrity analysis, view individual suite details.
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="card border-green-500/30">
                    <div className="text-gray-400 text-sm">Clean Suites</div>
                    <div className="text-3xl font-bold text-green-400">{cleanCount}</div>
                </div>
                <div className="card border-red-500/30">
                    <div className="text-gray-400 text-sm">High Severity</div>
                    <div className="text-3xl font-bold text-red-400">{highCount}</div>
                </div>
                <div className="card border-amber-500/30">
                    <div className="text-gray-400 text-sm">Medium Severity</div>
                    <div className="text-3xl font-bold text-amber-400">{mediumCount}</div>
                </div>
                <div className="card border-gray-500/30">
                    <div className="text-gray-400 text-sm">Low Severity</div>
                    <div className="text-3xl font-bold text-gray-400">{lowCount}</div>
                </div>
            </div>

            {/* Issues Table */}
            {integrityData.length > 0 ? (
                <div className="card">
                    <h3 className="card-header">Detected Issues ({integrityData.length})</h3>
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>Severity</th>
                                <th>Suite</th>
                                <th>KEM</th>
                                <th>Issues</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {integrityData.map((item, idx) => (
                                <tr key={`${item.suite.run_id}:${item.suite.suite_id}:${idx}`}>
                                    <td>
                                        <span className={getSeverityBadge(item.severity)}>
                                            {item.severity.toUpperCase()}
                                        </span>
                                    </td>
                                    <td className="font-mono text-sm">{item.suite.suite_id}</td>
                                    <td className="text-blue-400">{item.suite.kem_algorithm}</td>
                                    <td>
                                        <ul className="list-disc list-inside text-sm text-gray-300">
                                            {item.issues.map((issue, i) => (
                                                <li key={i}>{issue}</li>
                                            ))}
                                        </ul>
                                    </td>
                                    <td>
                                        <Link
                                            to={`/suite/${encodeURIComponent(item.suite.run_id + ':' + item.suite.suite_id)}`}
                                            className="text-blue-400 hover:text-blue-300 text-sm"
                                        >
                                            View Details →
                                        </Link>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            ) : (
                <div className="card text-center py-12">
                    <div className="text-green-400 text-xl mb-2">✓ All Clear</div>
                    <div className="text-gray-400">No integrity issues detected in suite metadata.</div>
                </div>
            )}

            {/* Integrity Metrics Legend */}
            <div className="card">
                <h3 className="card-header">Integrity Check Criteria</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                    <div className="p-3 bg-gray-800/50 rounded">
                        <div className="text-red-400 font-medium">High Severity</div>
                        <ul className="text-gray-400 mt-1">
                            <li>• Benchmark marked as FAIL</li>
                            <li>• Handshake did not succeed</li>
                        </ul>
                    </div>
                    <div className="p-3 bg-gray-800/50 rounded">
                        <div className="text-amber-400 font-medium">Medium Severity</div>
                        <ul className="text-gray-400 mt-1">
                            <li>• Missing power data</li>
                            <li>• Handshake duration &gt; 10s</li>
                        </ul>
                    </div>
                </div>
                <p className="text-xs text-gray-500 mt-4 italic">
                    For detailed MAVLink integrity metrics (out-of-order, CRC errors, duplicates),
                    view individual suite details.
                </p>
            </div>
        </div>
    );
}
