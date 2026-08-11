/**
 * Suite Explorer Page - Browse and filter all suites with heatmap coloring & anomaly flags
 */

import { useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useDashboardStore } from '../state/store';

// Heatmap: map value to color intensity (0→green, 1→red)
function heatColor(value: number | null | undefined, min: number, max: number, invert = false): string {
    if (value == null || max === min) return '';
    let t = Math.max(0, Math.min(1, (value - min) / (max - min)));
    if (invert) t = 1 - t;
    // green → yellow → red
    if (t < 0.5) {
        const g = Math.round(200 + 55 * (1 - t * 2));
        const r = Math.round(255 * t * 2);
        return `rgba(${r}, ${g}, 50, 0.15)`;
    }
    const r = 255;
    const g = Math.round(200 * (1 - (t - 0.5) * 2));
    return `rgba(${r}, ${g}, 50, 0.15)`;
}

export default function SuiteExplorer() {
    const {
        suites,
        filters,
        isLoading,
        selectedKemFamily,
        selectedSigFamily,
        selectedAead,
        selectedNistLevel,
        selectedRunId,
        fetchSuites,
        setFilter,
        clearFilters,
        anomalies,
        fetchAnomalies,
    } = useDashboardStore();

    useEffect(() => {
        fetchSuites();
        fetchAnomalies();
    }, [fetchSuites, fetchAnomalies, selectedKemFamily, selectedSigFamily, selectedAead, selectedNistLevel, selectedRunId]);

    // Build anomaly lookup: key → severity
    const anomalyMap = useMemo(() => {
        const map: Record<string, { severity: string; count: number }> = {};
        for (const a of anomalies) {
            map[a.key] = { severity: a.severity, count: a.flags.length };
        }
        return map;
    }, [anomalies]);

    // Compute min/max for heatmap columns
    const { hsMin, hsMax, pwrMin, pwrMax, enMin, enMax } = useMemo(() => {
        const hs = suites.map(s => s.handshake_total_duration_ms).filter((v): v is number => v != null);
        const pw = suites.map(s => s.power_avg_w).filter((v): v is number => v != null);
        const en = suites.map(s => s.energy_total_j).filter((v): v is number => v != null);
        return {
            hsMin: Math.min(...hs, 0), hsMax: Math.max(...hs, 1),
            pwrMin: Math.min(...pw, 0), pwrMax: Math.max(...pw, 1),
            enMin: Math.min(...en, 0), enMax: Math.max(...en, 1),
        };
    }, [suites]);

    // Get unique run IDs from suites for run filter
    const runIds = useMemo(() => {
        const ids = Array.from(new Set(suites.map(s => s.run_id).filter(Boolean)));
        ids.sort();
        return ids;
    }, [suites]);

    const getPassBadge = (status: string | null | undefined) => {
        if (status === 'PASS') return 'badge-verified';
        if (status === 'FAIL') return 'bg-red-500/20 text-red-400 px-2 py-0.5 rounded text-xs font-medium';
        return 'badge-missing';
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold">📋 Suite Explorer</h1>
                    <p className="text-sm text-gray-400 mt-1">
                        Heatmap coloring: <span className="text-green-400">green</span> = low,{' '}
                        <span className="text-yellow-400">yellow</span> = mid,{' '}
                        <span className="text-red-400">red</span> = high.{' '}
                        🔴 = critical anomaly, 🟡 = warning.
                    </p>
                </div>
                <div className="text-gray-400 text-lg font-mono">{suites.length} suites</div>
            </div>

            {/* Filters */}
            <div className="card">
                <div className="flex flex-wrap gap-4 items-end">
                    <div>
                        <label className="block text-sm text-gray-400 mb-1">Run ID</label>
                        <select
                            className="select-input"
                            value={selectedRunId || ''}
                            onChange={e => setFilter('selectedRunId', e.target.value || null)}
                        >
                            <option value="">All Runs</option>
                            {runIds.map(r => (
                                <option key={r} value={r}>{r}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm text-gray-400 mb-1">KEM Family</label>
                        <select
                            className="select-input"
                            value={selectedKemFamily || ''}
                            onChange={e => setFilter('selectedKemFamily', e.target.value || null)}
                        >
                            <option value="">All KEM</option>
                            {filters?.kem_families.map(f => (
                                <option key={f} value={f}>{f}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm text-gray-400 mb-1">Signature</label>
                        <select
                            className="select-input"
                            value={selectedSigFamily || ''}
                            onChange={e => setFilter('selectedSigFamily', e.target.value || null)}
                        >
                            <option value="">All Signatures</option>
                            {filters?.sig_families.map(f => (
                                <option key={f} value={f}>{f}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm text-gray-400 mb-1">AEAD</label>
                        <select
                            className="select-input"
                            value={selectedAead || ''}
                            onChange={e => setFilter('selectedAead', e.target.value || null)}
                        >
                            <option value="">All AEAD</option>
                            {filters?.aead_algorithms.map(f => (
                                <option key={f} value={f}>{f}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm text-gray-400 mb-1">NIST Level</label>
                        <select
                            className="select-input"
                            value={selectedNistLevel || ''}
                            onChange={e => setFilter('selectedNistLevel', e.target.value || null)}
                        >
                            <option value="">All Levels</option>
                            {filters?.nist_levels.map(f => (
                                <option key={f} value={f}>{f}</option>
                            ))}
                        </select>
                    </div>
                    <button onClick={clearFilters} className="px-3 py-2 text-sm text-gray-400 hover:text-white transition-colors">
                        ✕ Clear
                    </button>
                </div>
            </div>

            {/* Suite Table with heatmap */}
            <div className="card overflow-x-auto">
                {isLoading ? (
                    <div className="text-center py-8 text-gray-400">Loading suites...</div>
                ) : suites.length === 0 ? (
                    <div className="text-center py-8 text-gray-400">No suites found with current filters</div>
                ) : (
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Suite ID</th>
                                <th>KEM</th>
                                <th>Signature</th>
                                <th>AEAD</th>
                                <th>Level</th>
                                <th>Handshake (ms)</th>
                                <th>Power (W)</th>
                                <th>Energy (J)</th>
                                <th>Status</th>
                                <th>⚠️</th>
                            </tr>
                        </thead>
                        <tbody>
                            {suites.map((suite, idx) => {
                                const key = `${suite.run_id}:${suite.suite_id}`;
                                const anomaly = anomalyMap[key];
                                return (
                                    <tr key={key} className={anomaly?.severity === 'critical' ? 'border-l-2 border-l-red-500' : anomaly ? 'border-l-2 border-l-yellow-500' : ''}>
                                        <td className="text-gray-500">{idx + 1}</td>
                                        <td>
                                            <Link
                                                to={`/suite/${encodeURIComponent(key)}`}
                                                className="text-blue-400 hover:text-blue-300 hover:underline"
                                            >
                                                {suite.suite_id}
                                            </Link>
                                        </td>
                                        <td className="font-mono text-sm">{suite.kem_algorithm || '—'}</td>
                                        <td className="font-mono text-sm">{suite.sig_algorithm || '—'}</td>
                                        <td className="font-mono text-sm">{suite.aead_algorithm || '—'}</td>
                                        <td>
                                            {suite.suite_security_level ? (
                                                <span className="bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded text-xs">
                                                    {suite.suite_security_level}
                                                </span>
                                            ) : '—'}
                                        </td>
                                        <td className="text-right font-mono" style={{ background: heatColor(suite.handshake_total_duration_ms, hsMin, hsMax) }}>
                                            {suite.handshake_total_duration_ms != null ? suite.handshake_total_duration_ms.toFixed(2) : '—'}
                                        </td>
                                        <td className="text-right font-mono" style={{ background: heatColor(suite.power_avg_w, pwrMin, pwrMax) }}>
                                            {suite.power_avg_w != null ? suite.power_avg_w.toFixed(3) : '—'}
                                        </td>
                                        <td className="text-right font-mono" style={{ background: heatColor(suite.energy_total_j, enMin, enMax) }}>
                                            {suite.energy_total_j != null ? suite.energy_total_j.toFixed(2) : '—'}
                                        </td>
                                        <td>
                                            <span className={getPassBadge(suite.benchmark_pass_fail)}>
                                                {suite.benchmark_pass_fail || '—'}
                                            </span>
                                        </td>
                                        <td className="text-center">
                                            {anomaly ? (
                                                <span title={`${anomaly.count} flag(s)`} className={anomaly.severity === 'critical' ? 'text-red-400' : 'text-yellow-400'}>
                                                    {anomaly.severity === 'critical' ? '🔴' : '🟡'} {anomaly.count}
                                                </span>
                                            ) : (
                                                <span className="text-green-400 opacity-50">✓</span>
                                            )}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}
