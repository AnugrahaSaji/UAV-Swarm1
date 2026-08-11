/**
 * Comparison View Page - Side-by-side suite comparison
 */

import { useState, useEffect } from 'react';
import { useDashboardStore } from '../state/store';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import type { SuiteInventoryResponse, MetricInventoryItem } from '../types/metrics';

export default function ComparisonView() {
    const { suites, comparisonSuiteA, comparisonSuiteB, isLoading, fetchSuites, fetchComparison } = useDashboardStore();
    const [suiteAKey, setSuiteAKey] = useState<string>('');
    const [suiteBKey, setSuiteBKey] = useState<string>('');
    const [inventoryA, setInventoryA] = useState<SuiteInventoryResponse | null>(null);
    const [inventoryB, setInventoryB] = useState<SuiteInventoryResponse | null>(null);

    useEffect(() => {
        fetchSuites();
    }, [fetchSuites]);

    const handleCompare = () => {
        if (suiteAKey && suiteBKey) {
            fetchComparison(suiteAKey, suiteBKey);
        }
    };

    useEffect(() => {
        if (!suiteAKey) return;
        fetch(`/api/suite/${encodeURIComponent(suiteAKey)}/inventory`)
            .then(res => { if (!res.ok) throw new Error(`${res.status}`); return res.json(); })
            .then(setInventoryA)
            .catch(() => setInventoryA(null));
    }, [suiteAKey]);

    useEffect(() => {
        if (!suiteBKey) return;
        fetch(`/api/suite/${encodeURIComponent(suiteBKey)}/inventory`)
            .then(res => { if (!res.ok) throw new Error(`${res.status}`); return res.json(); })
            .then(setInventoryB)
            .catch(() => setInventoryB(null));
    }, [suiteBKey]);

    const getInventoryItem = (inventory: SuiteInventoryResponse | null, key: string): MetricInventoryItem | undefined => {
        return inventory?.metrics.find(item => item.source === 'DRONE' && item.key === key);
    };

    const getInventoryValue = (inventory: SuiteInventoryResponse | null, key: string) => {
        const item = getInventoryItem(inventory, key);
        if (!item) return null;
        if (item.status !== 'collected') return null;
        return item.value as number | null;
    };

    // Build comparison data for charts
    const comparisonData = comparisonSuiteA && comparisonSuiteB ? [
        {
            metric: 'Handshake (ms)',
            'Suite A': getInventoryValue(inventoryA, 'handshake.handshake_total_duration_ms'),
            'Suite B': getInventoryValue(inventoryB, 'handshake.handshake_total_duration_ms'),
        },
        {
            metric: 'Goodput (Mbps)',
            'Suite A': getInventoryValue(inventoryA, 'data_plane.goodput_mbps'),
            'Suite B': getInventoryValue(inventoryB, 'data_plane.goodput_mbps'),
        },
        {
            metric: 'Packet Loss (ratio)',
            'Suite A': getInventoryValue(inventoryA, 'data_plane.packet_loss_ratio'),
            'Suite B': getInventoryValue(inventoryB, 'data_plane.packet_loss_ratio'),
        },
        {
            metric: 'Power Avg (W)',
            'Suite A': getInventoryValue(inventoryA, 'power_energy.power_avg_w'),
            'Suite B': getInventoryValue(inventoryB, 'power_energy.power_avg_w'),
        },
        {
            metric: 'Energy (J)',
            'Suite A': getInventoryValue(inventoryA, 'power_energy.energy_total_j'),
            'Suite B': getInventoryValue(inventoryB, 'power_energy.energy_total_j'),
        },
        {
            metric: 'CPU Avg (%)',
            'Suite A': getInventoryValue(inventoryA, 'system_drone.cpu_usage_avg_percent'),
            'Suite B': getInventoryValue(inventoryB, 'system_drone.cpu_usage_avg_percent'),
        },
    ].filter(row => row['Suite A'] !== null && row['Suite A'] !== undefined && row['Suite B'] !== null && row['Suite B'] !== undefined) : [];

    const formatValue = (value: number | null | undefined, unit?: string) => {
        if (value === null || value === undefined) return 'Not collected';
        return `${value.toFixed(2)}${unit ? ` ${unit}` : ''}`;
    };

    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-bold">Suite Comparison</h1>

            {/* Suite Selection */}
            <div className="card">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
                    <div>
                        <label className="block text-sm text-gray-400 mb-1">Suite A (Baseline)</label>
                        <select
                            className="select-input w-full"
                            value={suiteAKey}
                            onChange={e => setSuiteAKey(e.target.value)}
                        >
                            <option value="">Select Suite A</option>
                            {suites.map(s => (
                                <option key={`${s.run_id}:${s.suite_id}`} value={`${s.run_id}:${s.suite_id}`}>
                                    {s.suite_id}
                                </option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label className="block text-sm text-gray-400 mb-1">Suite B</label>
                        <select
                            className="select-input w-full"
                            value={suiteBKey}
                            onChange={e => setSuiteBKey(e.target.value)}
                        >
                            <option value="">Select Suite B</option>
                            {suites.map(s => (
                                <option key={`${s.run_id}:${s.suite_id}`} value={`${s.run_id}:${s.suite_id}`}>
                                    {s.suite_id}
                                </option>
                            ))}
                        </select>
                    </div>

                    <button
                        onClick={handleCompare}
                        disabled={!suiteAKey || !suiteBKey || isLoading}
                        className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 px-4 py-2 rounded text-white transition-colors"
                    >
                        Compare
                    </button>
                </div>
            </div>

            {/* Comparison Results */}
            {comparisonSuiteA && comparisonSuiteB && (
                <>
                    {/* Suite Headers */}
                    <div className="grid grid-cols-2 gap-4">
                        <div className="card bg-blue-900/20">
                            <h3 className="text-lg font-semibold text-blue-400">Suite A: {comparisonSuiteA.run_context.suite_id}</h3>
                            <div className="text-sm text-gray-400 mt-1">
                                {comparisonSuiteA.crypto_identity.kem_algorithm} + {comparisonSuiteA.crypto_identity.sig_algorithm}
                            </div>
                        </div>
                        <div className="card bg-purple-900/20">
                            <h3 className="text-lg font-semibold text-purple-400">Suite B: {comparisonSuiteB.run_context.suite_id}</h3>
                            <div className="text-sm text-gray-400 mt-1">
                                {comparisonSuiteB.crypto_identity.kem_algorithm} + {comparisonSuiteB.crypto_identity.sig_algorithm}
                            </div>
                        </div>
                    </div>

                    {/* Comparison Chart */}
                    <div className="card">
                        <h3 className="card-header">Metric Comparison</h3>
                        <div className="h-80">
                            {comparisonData.length === 0 ? (
                                <div className="text-gray-400 text-sm">No comparable metrics with collected data.</div>
                            ) : (
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={comparisonData} layout="vertical">
                                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                        <XAxis type="number" stroke="#9ca3af" />
                                        <YAxis dataKey="metric" type="category" width={120} stroke="#9ca3af" />
                                        <Tooltip
                                            contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
                                        />
                                        <Legend />
                                        <Bar dataKey="Suite A" fill="#3b82f6" />
                                        <Bar dataKey="Suite B" fill="#a855f7" />
                                    </BarChart>
                                </ResponsiveContainer>
                            )}
                        </div>
                    </div>

                    {/* Detailed Comparison Table */}
                    <div className="card">
                        <h3 className="card-header">Detailed Comparison</h3>
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Metric</th>
                                    <th className="text-right">Suite A</th>
                                    <th className="text-right">Suite B</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td>Handshake Duration</td>
                                    <td className="text-right font-mono">{formatValue(getInventoryValue(inventoryA, 'handshake.handshake_total_duration_ms') as number | null, 'ms')}</td>
                                    <td className="text-right font-mono">{formatValue(getInventoryValue(inventoryB, 'handshake.handshake_total_duration_ms') as number | null, 'ms')}</td>
                                </tr>
                                <tr>
                                    <td>Power Avg</td>
                                    <td className="text-right font-mono">{formatValue(getInventoryValue(inventoryA, 'power_energy.power_avg_w') as number | null, 'W')}</td>
                                    <td className="text-right font-mono">{formatValue(getInventoryValue(inventoryB, 'power_energy.power_avg_w') as number | null, 'W')}</td>
                                </tr>
                                <tr>
                                    <td>Energy Total</td>
                                    <td className="text-right font-mono">{formatValue(getInventoryValue(inventoryA, 'power_energy.energy_total_j') as number | null, 'J')}</td>
                                    <td className="text-right font-mono">{formatValue(getInventoryValue(inventoryB, 'power_energy.energy_total_j') as number | null, 'J')}</td>
                                </tr>
                                <tr>
                                    <td>Packets Sent</td>
                                    <td className="text-right font-mono">{formatValue(getInventoryValue(inventoryA, 'data_plane.packets_sent') as number | null)}</td>
                                    <td className="text-right font-mono">{formatValue(getInventoryValue(inventoryB, 'data_plane.packets_sent') as number | null)}</td>
                                </tr>
                                <tr>
                                    <td>Goodput</td>
                                    <td className="text-right font-mono">{formatValue(getInventoryValue(inventoryA, 'data_plane.goodput_mbps') as number | null, 'Mbps')}</td>
                                    <td className="text-right font-mono">{formatValue(getInventoryValue(inventoryB, 'data_plane.goodput_mbps') as number | null, 'Mbps')}</td>
                                </tr>
                                <tr>
                                    <td>Packet Loss Ratio</td>
                                    <td className="text-right font-mono">{(() => {
                                        const val = getInventoryValue(inventoryA, 'data_plane.packet_loss_ratio') as number | null;
                                        return val === null || val === undefined ? 'Not collected' : `${(val * 100).toFixed(2)} %`;
                                    })()}</td>
                                    <td className="text-right font-mono">{(() => {
                                        const val = getInventoryValue(inventoryB, 'data_plane.packet_loss_ratio') as number | null;
                                        return val === null || val === undefined ? 'Not collected' : `${(val * 100).toFixed(2)} %`;
                                    })()}</td>
                                </tr>
                                <tr>
                                    <td>CPU Avg</td>
                                    <td className="text-right font-mono">{formatValue(getInventoryValue(inventoryA, 'system_drone.cpu_usage_avg_percent') as number | null, '%')}</td>
                                    <td className="text-right font-mono">{formatValue(getInventoryValue(inventoryB, 'system_drone.cpu_usage_avg_percent') as number | null, '%')}</td>
                                </tr>
                                <tr>
                                    <td>Memory RSS</td>
                                    <td className="text-right font-mono">{formatValue(getInventoryValue(inventoryA, 'system_drone.memory_rss_mb') as number | null, 'MB')}</td>
                                    <td className="text-right font-mono">{formatValue(getInventoryValue(inventoryB, 'system_drone.memory_rss_mb') as number | null, 'MB')}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </>
            )}

            {!comparisonSuiteA && !comparisonSuiteB && (
                <div className="text-center py-12 text-gray-400">
                    Select two suites above to compare their metrics side-by-side.
                </div>
            )}
        </div>
    );
}
