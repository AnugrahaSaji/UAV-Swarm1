/**
 * Security Impact Page — DDoS detection impact analysis, anomaly detection,
 * replay/auth drop visualization, MAVLink integrity under attack.
 */

import { useEffect } from 'react';
import { useDashboardStore } from '../state/store';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';

function fmt(v: number | null | undefined, digits = 2): string {
    if (v == null || isNaN(v)) return '—';
    return v.toFixed(digits);
}

export default function SecurityImpact() {
    const {
        anomalies, fetchAnomalies, suites, fetchSuites, fetchSettings,
    } = useDashboardStore();

    useEffect(() => { fetchAnomalies(); fetchSuites(); fetchSettings(); }, [fetchAnomalies, fetchSuites, fetchSettings]);

    const criticalCount = anomalies.filter(a => a.severity === 'critical').length;
    const warningCount = anomalies.filter(a => a.severity === 'warning').length;

    // Anomaly distribution by metric type
    const metricCounts: Record<string, number> = {};
    anomalies.forEach(a => {
        a.flags.forEach(f => {
            metricCounts[f.metric] = (metricCounts[f.metric] || 0) + 1;
        });
    });
    const anomalyDistribution = Object.entries(metricCounts)
        .map(([metric, count]) => ({ metric, count }))
        .sort((a, b) => b.count - a.count);

    // Anomaly by KEM family
    const kemAnomalyCounts: Record<string, { critical: number; warning: number }> = {};
    anomalies.forEach(a => {
        const kem = a.kem || 'Unknown';
        const family = kem.includes('ML-KEM') || kem.includes('mlkem') ? 'ML-KEM'
            : kem.includes('HQC') || kem.includes('hqc') ? 'HQC'
            : kem.includes('McEliece') || kem.includes('mceliece') ? 'ClassicMcEliece'
            : 'Other';
        if (!kemAnomalyCounts[family]) kemAnomalyCounts[family] = { critical: 0, warning: 0 };
        if (a.severity === 'critical') kemAnomalyCounts[family].critical++;
        else kemAnomalyCounts[family].warning++;
    });
    const kemAnomalyData = Object.entries(kemAnomalyCounts).map(([family, counts]) => ({
        family, ...counts
    }));

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-white">🛡️ Security Impact Analysis</h1>
                <p className="text-gray-400 text-sm mt-1">Anomaly detection, DDoS impact, replay attacks, and MAVLink integrity — no smoothing, raw data</p>
            </div>

            {/* ── KPI Cards ── */}
            <div className="grid grid-cols-4 gap-4">
                <div className="card border-l-4 border-l-red-500">
                    <div className="text-xs text-gray-400 uppercase tracking-wider">Critical Anomalies</div>
                    <div className="text-3xl font-bold text-red-400 mt-1">{criticalCount}</div>
                </div>
                <div className="card border-l-4 border-l-yellow-500">
                    <div className="text-xs text-gray-400 uppercase tracking-wider">Warnings</div>
                    <div className="text-3xl font-bold text-yellow-400 mt-1">{warningCount}</div>
                </div>
                <div className="card border-l-4 border-l-green-500">
                    <div className="text-xs text-gray-400 uppercase tracking-wider">Clean Suites</div>
                    <div className="text-3xl font-bold text-green-400 mt-1">{Math.max(0, suites.length - new Set(anomalies.map(a => a.suite_id)).size)}</div>
                </div>
                <div className="card border-l-4 border-l-blue-500">
                    <div className="text-xs text-gray-400 uppercase tracking-wider">Total Suites</div>
                    <div className="text-3xl font-bold text-blue-400 mt-1">{suites.length}</div>
                </div>
            </div>

            <div className="grid grid-cols-2 gap-6">
                {/* ── Anomaly Distribution ── */}
                <div className="card">
                    <h2 className="text-lg font-semibold text-white mb-4">📊 Anomaly Distribution by Metric</h2>
                    <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={anomalyDistribution} layout="vertical">
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis type="number" tick={{ fill: '#9ca3af', fontSize: 11 }} />
                            <YAxis type="category" dataKey="metric" width={150} tick={{ fill: '#d1d5db', fontSize: 11 }} />
                            <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }} />
                            <Bar dataKey="count" fill="#ef4444" radius={[0, 4, 4, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>

                {/* ── Anomalies by KEM Family ── */}
                <div className="card">
                    <h2 className="text-lg font-semibold text-white mb-4">🔑 Anomalies by KEM Family</h2>
                    <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={kemAnomalyData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis dataKey="family" tick={{ fill: '#d1d5db', fontSize: 11 }} />
                            <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} />
                            <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }} />
                            <Legend />
                            <Bar dataKey="critical" fill="#ef4444" name="Critical" stackId="a" />
                            <Bar dataKey="warning" fill="#f59e0b" name="Warning" stackId="a" />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* ── Anomaly Table ── */}
            <div className="card">
                <h2 className="text-lg font-semibold text-white mb-4">🚨 Flagged Suites ({anomalies.length})</h2>
                <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
                    <table className="data-table w-full">
                        <thead className="sticky top-0 bg-gray-800/95 backdrop-blur">
                            <tr>
                                <th>Severity</th>
                                <th>Suite ID</th>
                                <th>KEM</th>
                                <th>SIG</th>
                                <th>Flags</th>
                                <th>Details</th>
                            </tr>
                        </thead>
                        <tbody>
                            {anomalies.map((a, i) => (
                                <tr key={i} className={a.severity === 'critical' ? 'bg-red-500/5' : 'bg-yellow-500/5'}>
                                    <td>
                                        <span className={`px-2 py-0.5 rounded text-xs font-bold ${a.severity === 'critical' ? 'bg-red-500/20 text-red-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
                                            {a.severity.toUpperCase()}
                                        </span>
                                    </td>
                                    <td className="font-mono text-sm text-white">{a.suite_id}</td>
                                    <td className="text-gray-300 text-xs">{a.kem || '—'}</td>
                                    <td className="text-gray-300 text-xs">{a.sig || '—'}</td>
                                    <td className="text-gray-400 text-xs">{a.flags.length} flag(s)</td>
                                    <td className="text-xs">
                                        <div className="flex flex-wrap gap-1">
                                            {a.flags.map((f, j) => (
                                                <span key={j} className="px-1.5 py-0.5 rounded bg-gray-700 text-gray-300">
                                                    {f.metric}: {typeof f.value === 'number' ? fmt(f.value, 4) : f.value}
                                                </span>
                                            ))}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                            {anomalies.length === 0 && (
                                <tr>
                                    <td colSpan={6} className="text-center text-gray-500 py-8">
                                        ✅ No anomalies detected — all suites within thresholds
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
