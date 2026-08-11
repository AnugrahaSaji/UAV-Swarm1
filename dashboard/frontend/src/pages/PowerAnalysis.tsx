/**
 * Power Analysis Page - Power and energy visualization
 */

import { useEffect } from 'react';
import { useDashboardStore } from '../state/store';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
    ScatterChart, Scatter, ZAxis, Legend
} from 'recharts';

export default function PowerAnalysis() {
    const { suites, isLoading, fetchSuites } = useDashboardStore();

    useEffect(() => {
        fetchSuites();
    }, [fetchSuites]);

    // Group by KEM family for energy comparison
    const energyByKem = suites.reduce((acc, suite) => {
        const kemAlg = suite.kem_algorithm || 'Unknown';
        const family = kemAlg.split('-')[0] || 'Unknown';
        if (!acc[family]) {
            acc[family] = { name: family, total: 0, count: 0, avg: 0 };
        }
        if (suite.energy_total_j !== null && suite.energy_total_j !== undefined) {
            acc[family].total += suite.energy_total_j;
            acc[family].count++;
            acc[family].avg = acc[family].total / acc[family].count;
        }
        return acc;
    }, {} as Record<string, { name: string; total: number; count: number; avg: number }>);

    const energyData = Object.values(energyByKem).sort((a, b) => b.avg - a.avg);

    // Power vs Handshake scatter data
    const scatterData = suites.map(s => ({
        name: s.suite_id,
        power: s.power_avg_w,
        handshake: s.handshake_total_duration_ms,
        energy: s.energy_total_j,
    })).filter(d => d.power !== null && d.power !== undefined && d.handshake !== null && d.handshake !== undefined);

    // Top energy consumers
    const topEnergy = [...suites]
        .filter(s => s.energy_total_j !== null && s.energy_total_j !== undefined)
        .sort((a, b) => (b.energy_total_j || 0) - (a.energy_total_j || 0))
        .slice(0, 10);

    if (isLoading && suites.length === 0) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="text-gray-400">Loading power data...</div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-bold">Power Analysis</h1>

            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="card">
                    <div className="text-gray-400 text-sm">Avg Power</div>
                    <div className="text-3xl font-bold text-green-400">
                        {(() => {
                            const values = suites.map(s => s.power_avg_w).filter(v => v !== null && v !== undefined) as number[];
                            if (values.length === 0) return 'Not collected';
                            const avg = values.reduce((sum, v) => sum + v, 0) / values.length;
                            return `${avg.toFixed(2)} W`;
                        })()}
                    </div>
                </div>
                <div className="card">
                    <div className="text-gray-400 text-sm">Total Energy</div>
                    <div className="text-3xl font-bold text-blue-400">
                        {(() => {
                            const values = suites.map(s => s.energy_total_j).filter(v => v !== null && v !== undefined) as number[];
                            if (values.length === 0) return 'Not collected';
                            const total = values.reduce((sum, v) => sum + v, 0);
                            return `${total.toFixed(1)} J`;
                        })()}
                    </div>
                </div>
                <div className="card">
                    <div className="text-gray-400 text-sm">Suites with Power Data</div>
                    <div className="text-3xl font-bold text-purple-400">
                        {suites.filter(s => s.power_avg_w !== null && s.power_avg_w !== undefined).length}
                    </div>
                </div>
                <div className="card">
                    <div className="text-gray-400 text-sm">Power Sensor</div>
                    <div className="text-2xl font-bold text-amber-400">
                        {(() => {
                            const sensors = Array.from(new Set(
                                suites
                                    .map(s => s.power_sensor_type)
                                    .filter((v): v is string => !!v && v.trim().length > 0)
                            ));
                            if (sensors.length === 0) return 'Not collected';
                            if (sensors.length === 1) return sensors[0];
                            return 'Mixed';
                        })()}
                    </div>
                </div>
            </div>

            {/* Energy by KEM Family */}
            <div className="card">
                <h3 className="card-header">Average Energy by KEM Family</h3>
                <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={energyData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis dataKey="name" stroke="#9ca3af" tick={{ fontSize: 12 }} />
                            <YAxis stroke="#9ca3af" tick={{ fontSize: 12 }} label={{ value: 'J', angle: -90, position: 'insideLeft', fill: '#9ca3af' }} />
                            <Tooltip
                                contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
                                formatter={(value: number) => [`${value.toFixed(2)} J`, 'Avg Energy']}
                            />
                            <Bar dataKey="avg" fill="#10b981" name="Avg Energy (J)" />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Power vs Handshake Scatter */}
            <div className="card">
                <h3 className="card-header">Power vs Handshake Duration</h3>
                <p className="text-sm text-gray-400 mb-4">Each point represents a suite. Bubble size indicates total energy.</p>
                <div className="h-80">
                    <ResponsiveContainer width="100%" height="100%">
                        <ScatterChart>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis
                                type="number"
                                dataKey="handshake"
                                name="Handshake"
                                unit=" ms"
                                stroke="#9ca3af"
                                label={{ value: 'Handshake (ms)', position: 'insideBottom', offset: -5, fill: '#9ca3af' }}
                            />
                            <YAxis
                                type="number"
                                dataKey="power"
                                name="Power"
                                unit=" W"
                                stroke="#9ca3af"
                                label={{ value: 'Power (W)', angle: -90, position: 'insideLeft', fill: '#9ca3af' }}
                            />
                            <ZAxis type="number" dataKey="energy" range={[50, 400]} name="Energy" />
                            <Tooltip
                                contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
                                formatter={(value: number, name: string) => {
                                    if (name === 'Power') return [`${value.toFixed(2)} W`, name];
                                    if (name === 'Handshake') return [`${value.toFixed(2)} ms`, name];
                                    return [`${value.toFixed(2)} J`, name];
                                }}
                            />
                            <Legend />
                            <Scatter name="Suites" data={scatterData} fill="#3b82f6" />
                        </ScatterChart>
                    </ResponsiveContainer>
                </div>
                <p className="text-xs text-gray-500 mt-2 italic">
                    Note: Correlation does not imply causation. No causal inference implied.
                </p>
            </div>

            {/* Top Energy Consumers */}
            <div className="card">
                <h3 className="card-header">Top 10 Energy Consumers</h3>
                <table className="data-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Suite</th>
                            <th>KEM</th>
                            <th className="text-right">Energy (J)</th>
                            <th className="text-right">Power Avg (W)</th>
                            <th className="text-right">Duration (ms)</th>
                        </tr>
                    </thead>
                    <tbody>
                        {topEnergy.map((suite, idx) => (
                            <tr key={`${suite.run_id}:${suite.suite_id}`}>
                                <td className="text-gray-500">{idx + 1}</td>
                                <td className="font-mono text-sm">{suite.suite_id}</td>
                                <td className="text-blue-400">{suite.kem_algorithm}</td>
                                <td className="text-right font-mono text-green-400">{suite.energy_total_j !== null && suite.energy_total_j !== undefined ? suite.energy_total_j.toFixed(2) : 'Not collected'}</td>
                                <td className="text-right font-mono">{suite.power_avg_w !== null && suite.power_avg_w !== undefined ? suite.power_avg_w.toFixed(2) : 'Not collected'}</td>
                                <td className="text-right font-mono">{suite.handshake_total_duration_ms !== null && suite.handshake_total_duration_ms !== undefined ? suite.handshake_total_duration_ms.toFixed(2) : 'Not collected'}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
