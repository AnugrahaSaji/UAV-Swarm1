/**
 * Bucket Comparison v2 — Powerful grouped analysis with heatmap,
 * statistical summaries, efficiency scoring, sorted rankings, scatter plot,
 * and cross-bucket comparison visualizations.
 */

import { useState, useEffect, useMemo } from 'react';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Cell,
    RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
    ScatterChart, Scatter, ZAxis,
} from 'recharts';
import { useDashboardStore } from '../state/store';
import { RUN_TYPE_COLORS, RUN_TYPE_LABELS, type RunType } from '../types/metrics';

interface BucketSuite {
    key: string;
    suite_id: string;
    kem: string;
    sig: string;
    aead?: string;
    nist: string;
    handshake_ms: number | null;
    power_w: number | null;
    energy_j: number | null;
}

interface Buckets {
    nist_level: Record<string, BucketSuite[]>;
    nist_aead: Record<string, BucketSuite[]>;
    aead: Record<string, BucketSuite[]>;
    kem_family: Record<string, BucketSuite[]>;
    sig_family: Record<string, BucketSuite[]>;
}

type BucketType = 'nist_level' | 'nist_aead' | 'aead' | 'kem_family' | 'sig_family';
type SortField = 'suite_id' | 'handshake_ms' | 'power_w' | 'energy_j' | 'efficiency';

const BUCKET_LABELS: Record<BucketType, string> = {
    nist_level: 'NIST Security Level',
    nist_aead: 'NIST Level + AEAD',
    aead: 'AEAD Algorithm',
    kem_family: 'KEM Family',
    sig_family: 'Signature Family'
};

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#14b8a6'];

function avg(arr: number[]): number { return arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0; }

function stdDev(arr: number[]): number {
    if (arr.length < 2) return 0;
    const mean = avg(arr);
    return Math.sqrt(arr.reduce((s, v) => s + (v - mean) ** 2, 0) / (arr.length - 1));
}

function percentile(arr: number[], p: number): number {
    if (!arr.length) return 0;
    const sorted = [...arr].sort((a, b) => a - b);
    const i = Math.floor(sorted.length * p);
    return sorted[Math.min(i, sorted.length - 1)];
}

function coeffOfVariation(arr: number[]): number {
    const m = avg(arr);
    if (m === 0) return 0;
    return (stdDev(arr) / m) * 100;
}

function fmt(v: number | null | undefined, d = 2): string {
    if (v == null || isNaN(v)) return '—';
    return v.toFixed(d);
}

/** Efficiency score: lower is better. Combines handshake time × energy cost. */
function efficiencyScore(hs: number | null, en: number | null): number | null {
    if (hs == null || en == null || hs === 0 || en === 0) return null;
    return hs * en; // ms·J product — lower = more efficient
}

/** Grade badge for efficiency score ranking */
function efficiencyGrade(rank: number, total: number): { label: string; color: string } {
    const pct = rank / total;
    if (pct <= 0.2) return { label: 'A', color: '#10b981' };
    if (pct <= 0.4) return { label: 'B', color: '#3b82f6' };
    if (pct <= 0.6) return { label: 'C', color: '#f59e0b' };
    if (pct <= 0.8) return { label: 'D', color: '#f97316' };
    return { label: 'F', color: '#ef4444' };
}

export default function BucketComparison() {
    const { settings, fetchSettings } = useDashboardStore();
    const [buckets, setBuckets] = useState<Buckets | null>(null);
    const [selectedType, setSelectedType] = useState<BucketType>('kem_family');
    const [selectedBucket, setSelectedBucket] = useState<string>('');
    const [selectedRunId, setSelectedRunId] = useState<string>('');
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [sortField, setSortField] = useState<SortField>('efficiency');
    const [sortAsc, setSortAsc] = useState(true);

    useEffect(() => { fetchSettings(); }, [fetchSettings]);

    useEffect(() => {
        async function fetchBuckets() {
            try {
                setIsLoading(true);
                const url = selectedRunId ? `/api/buckets?run_id=${encodeURIComponent(selectedRunId)}` : '/api/buckets';
                const res = await fetch(url);
                if (!res.ok) throw new Error('Failed to fetch buckets');
                const data = await res.json();
                setBuckets(data);
                const firstKey = Object.keys(data[selectedType] || {})[0];
                if (firstKey && !Object.keys(data[selectedType] || {}).includes(selectedBucket)) {
                    setSelectedBucket(firstKey);
                }
            } catch (e) {
                setError(e instanceof Error ? e.message : 'Unknown error');
            } finally {
                setIsLoading(false);
            }
        }
        fetchBuckets();
    }, [selectedRunId, selectedType, selectedBucket]);

    useEffect(() => {
        if (buckets && buckets[selectedType]) {
            const keys = Object.keys(buckets[selectedType]);
            if (keys.length > 0 && !keys.includes(selectedBucket)) {
                setSelectedBucket(keys[0]);
            }
        }
    }, [selectedType, buckets, selectedBucket]);

    const availableRuns = settings?.available_runs || [];
    const runLabels = settings?.run_labels || {};

    // ── Cross-bucket aggregate stats ──────────────────────────────────────
    const crossBucketStats = useMemo(() => {
        if (!buckets) return [];
        const currentBucketData = buckets[selectedType] || {};
        return Object.entries(currentBucketData).map(([name, suites]) => {
            const hs = suites.map(s => s.handshake_ms).filter((v): v is number => v != null);
            const pw = suites.map(s => s.power_w).filter((v): v is number => v != null);
            const en = suites.map(s => s.energy_j).filter((v): v is number => v != null);
            return {
                bucket: name,
                bucketShort: name.length > 18 ? name.substring(0, 18) + '…' : name,
                count: suites.length,
                avgHs: avg(hs), minHs: hs.length ? Math.min(...hs) : 0, maxHs: hs.length ? Math.max(...hs) : 0,
                stdHs: stdDev(hs), p95Hs: percentile(hs, 0.95), cvHs: coeffOfVariation(hs),
                avgPw: avg(pw), minPw: pw.length ? Math.min(...pw) : 0, maxPw: pw.length ? Math.max(...pw) : 0,
                avgEn: avg(en), minEn: en.length ? Math.min(...en) : 0, maxEn: en.length ? Math.max(...en) : 0,
                totalEn: en.reduce((a, b) => a + b, 0),
                efficiencyAvg: avg(hs) * avg(en), // handshake × energy product
            };
        }).sort((a, b) => a.efficiencyAvg - b.efficiencyAvg);
    }, [buckets, selectedType]);

    // Radar data for cross-bucket comparison
    const radarData = useMemo(() => {
        if (!crossBucketStats.length) return [];
        return crossBucketStats.map(s => ({
            bucket: s.bucketShort,
            Handshake: +s.avgHs.toFixed(1),
            Power: +s.avgPw.toFixed(3),
            Energy: +s.avgEn.toFixed(2),
            Suites: s.count,
        }));
    }, [crossBucketStats]);

    // ── Selected bucket suite data with efficiency ──────────────────────
    const selectedSuites = useMemo(() => {
        if (!buckets) return [];
        const suites = (buckets[selectedType] || {})[selectedBucket] || [];
        return suites
            .map(s => ({
                ...s,
                efficiency: efficiencyScore(s.handshake_ms, s.energy_j),
            }))
            .sort((a, b) => {
                let va: any, vb: any;
                if (sortField === 'efficiency') { va = a.efficiency ?? Infinity; vb = b.efficiency ?? Infinity; }
                else if (sortField === 'handshake_ms') { va = a.handshake_ms ?? Infinity; vb = b.handshake_ms ?? Infinity; }
                else if (sortField === 'power_w') { va = a.power_w ?? Infinity; vb = b.power_w ?? Infinity; }
                else if (sortField === 'energy_j') { va = a.energy_j ?? Infinity; vb = b.energy_j ?? Infinity; }
                else { va = a.suite_id; vb = b.suite_id; }
                return sortAsc ? (va < vb ? -1 : va > vb ? 1 : 0) : (va > vb ? -1 : va < vb ? 1 : 0);
            });
    }, [buckets, selectedType, selectedBucket, sortField, sortAsc]);

    // KPI for selected bucket
    const kpi = useMemo(() => {
        const hs = selectedSuites.map(s => s.handshake_ms).filter((v): v is number => v != null);
        const pw = selectedSuites.map(s => s.power_w).filter((v): v is number => v != null);
        const en = selectedSuites.map(s => s.energy_j).filter((v): v is number => v != null);
        const eff = selectedSuites.map(s => s.efficiency).filter((v): v is number => v != null);
        return {
            count: selectedSuites.length,
            avgHs: avg(hs), minHs: hs.length ? Math.min(...hs) : 0, maxHs: hs.length ? Math.max(...hs) : 0,
            stdHs: stdDev(hs), p95Hs: percentile(hs, 0.95), cvHs: coeffOfVariation(hs),
            avgPw: avg(pw), avgEn: avg(en), totalEn: en.reduce((a, b) => a + b, 0),
            bestEff: eff.length ? Math.min(...eff) : 0,
            worstEff: eff.length ? Math.max(...eff) : 0,
        };
    }, [selectedSuites]);

    // Chart data
    const chartData = selectedSuites
        .filter(s => s.handshake_ms != null && s.power_w != null && s.energy_j != null)
        .map((s, idx) => ({
            name: s.suite_id.replace(/^cs-/, '').substring(0, 30),
            handshake_ms: s.handshake_ms!,
            power_w: s.power_w!,
            energy_j: s.energy_j!,
            efficiency: s.efficiency ?? 0,
            color: COLORS[idx % COLORS.length],
        }));

    // Scatter: handshake vs energy for selected bucket
    const scatterData = selectedSuites
        .filter(s => s.handshake_ms != null && s.energy_j != null)
        .map(s => ({
            handshake_ms: s.handshake_ms!,
            energy_j: s.energy_j!,
            suite_id: s.suite_id,
            nist: s.nist,
            power_w: s.power_w ?? 0,
        }));

    const runType = selectedRunId ? (runLabels[selectedRunId] as { type?: RunType })?.type || 'no_ddos' : undefined;

    const handleSort = (field: SortField) => {
        if (sortField === field) setSortAsc(!sortAsc);
        else { setSortField(field); setSortAsc(true); }
    };
    const sortIcon = (field: SortField) => sortField === field ? (sortAsc ? ' ▲' : ' ▼') : '';

    if (isLoading && !buckets) return <div className="text-center py-12 text-gray-400">Loading comparison buckets...</div>;
    if (error) return <div className="text-center py-12 text-red-400">Error: {error}</div>;
    if (!buckets) return <div className="text-center py-12 text-gray-400">No data available</div>;

    const bucketKeys = Object.keys(buckets[selectedType] || {});

    return (
        <div className="space-y-6">
            {/* ── Header ── */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold">🪣 Comparison Buckets</h1>
                    <p className="text-sm text-gray-400 mt-1">
                        Group suites by algorithm properties — compare performance, efficiency, and statistical spread.
                    </p>
                </div>
                {runType && (
                    <span className="px-3 py-1 rounded-full text-sm font-medium" style={{
                        backgroundColor: `${RUN_TYPE_COLORS[runType as RunType]}22`,
                        color: RUN_TYPE_COLORS[runType as RunType],
                        border: `1px solid ${RUN_TYPE_COLORS[runType as RunType]}44`,
                    }}>
                        {RUN_TYPE_LABELS[runType as RunType]}
                    </span>
                )}
            </div>

            {/* ── Controls ── */}
            <div className="card">
                <div className="flex flex-wrap gap-4 items-end mb-4">
                    <div>
                        <label className="block text-sm text-gray-400 mb-1">Run / Threat Scenario</label>
                        <select className="select-input" value={selectedRunId} onChange={e => setSelectedRunId(e.target.value)}>
                            <option value="">All Runs (Combined)</option>
                            {availableRuns.map((r: { run_id: string; suite_count: number | null }) => {
                                const rl = runLabels[r.run_id] as { label?: string; type?: RunType } | undefined;
                                return (
                                    <option key={r.run_id} value={r.run_id}>
                                        {rl?.label || r.run_id} ({r.suite_count} suites) {rl?.type ? `— ${RUN_TYPE_LABELS[rl.type]}` : ''}
                                    </option>
                                );
                            })}
                        </select>
                    </div>
                </div>
                <div className="flex flex-wrap gap-2 mb-4">
                    {(Object.keys(BUCKET_LABELS) as BucketType[]).map(type => (
                        <button key={type} onClick={() => setSelectedType(type)}
                            className={`px-4 py-2 rounded transition-colors text-sm ${selectedType === type
                                ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}`}>
                            {BUCKET_LABELS[type]}
                        </button>
                    ))}
                </div>
                <div className="flex items-center gap-4">
                    <label className="text-gray-400">Select Group:</label>
                    <select className="select-input" value={selectedBucket} onChange={e => setSelectedBucket(e.target.value)}>
                        {bucketKeys.map(key => (
                            <option key={key} value={key}>{key} ({(buckets[selectedType] || {})[key]?.length || 0} suites)</option>
                        ))}
                    </select>
                </div>
            </div>

            {/* ── Cross-Bucket Ranking Table ── */}
            {crossBucketStats.length > 1 && (
                <div className="card">
                    <h3 className="card-header">🏆 Cross-Bucket Ranking — {BUCKET_LABELS[selectedType]}</h3>
                    <p className="text-xs text-gray-400 mb-3">Ranked by efficiency score (Handshake × Energy — lower is better). Click a row to select that bucket.</p>
                    <div className="overflow-x-auto">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Rank</th>
                                    <th>Bucket</th>
                                    <th className="text-right">Suites</th>
                                    <th className="text-right">Avg HS (ms)</th>
                                    <th className="text-right">P95 HS</th>
                                    <th className="text-right">σ HS</th>
                                    <th className="text-right">CV %</th>
                                    <th className="text-right">Avg Power (W)</th>
                                    <th className="text-right">Avg Energy (J)</th>
                                    <th className="text-right">Efficiency</th>
                                    <th>Grade</th>
                                </tr>
                            </thead>
                            <tbody>
                                {crossBucketStats.map((row, idx) => {
                                    const grade = efficiencyGrade(idx + 1, crossBucketStats.length);
                                    const isSelected = row.bucket === selectedBucket;
                                    return (
                                        <tr key={row.bucket}
                                            className={`cursor-pointer hover:bg-gray-700/50 transition-colors ${isSelected ? 'bg-blue-900/30 border-l-2 border-l-blue-500' : ''}`}
                                            onClick={() => setSelectedBucket(row.bucket)}>
                                            <td className="font-mono text-gray-500">{idx + 1}</td>
                                            <td className={`font-medium ${isSelected ? 'text-blue-400' : 'text-white'}`}>{row.bucket}</td>
                                            <td className="text-right font-mono">{row.count}</td>
                                            <td className="text-right font-mono">{fmt(row.avgHs)}</td>
                                            <td className="text-right font-mono text-yellow-400">{fmt(row.p95Hs)}</td>
                                            <td className="text-right font-mono text-gray-400">{fmt(row.stdHs)}</td>
                                            <td className="text-right font-mono">
                                                <span className={row.cvHs > 50 ? 'text-red-400' : row.cvHs > 25 ? 'text-yellow-400' : 'text-green-400'}>
                                                    {fmt(row.cvHs, 1)}%
                                                </span>
                                            </td>
                                            <td className="text-right font-mono">{fmt(row.avgPw, 3)}</td>
                                            <td className="text-right font-mono">{fmt(row.avgEn, 2)}</td>
                                            <td className="text-right font-mono">{fmt(row.efficiencyAvg, 0)}</td>
                                            <td>
                                                <span className="px-2 py-0.5 rounded text-xs font-bold" style={{
                                                    color: grade.color, backgroundColor: grade.color + '22'
                                                }}>{grade.label}</span>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* ── Heatmap: Cross-Bucket Metric Comparison ── */}
            {crossBucketStats.length > 1 && (
                <div className="card">
                    <h3 className="card-header">🗺️ Performance Heatmap — {BUCKET_LABELS[selectedType]}</h3>
                    <p className="text-xs text-gray-400 mb-3">Color intensity shows relative magnitude. Green = best in column, Red = worst in column.</p>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr>
                                    <th className="text-left py-2 px-3 text-gray-400 text-xs uppercase">Bucket</th>
                                    <th className="text-center py-2 px-3 text-gray-400 text-xs uppercase">Avg Handshake</th>
                                    <th className="text-center py-2 px-3 text-gray-400 text-xs uppercase">Max Handshake</th>
                                    <th className="text-center py-2 px-3 text-gray-400 text-xs uppercase">Avg Power</th>
                                    <th className="text-center py-2 px-3 text-gray-400 text-xs uppercase">Avg Energy</th>
                                    <th className="text-center py-2 px-3 text-gray-400 text-xs uppercase">Efficiency</th>
                                </tr>
                            </thead>
                            <tbody>
                                {(() => {
                                    // Compute min/max for each metric across all buckets
                                    const metrics = ['avgHs', 'maxHs', 'avgPw', 'avgEn', 'efficiencyAvg'] as const;
                                    const mins: Record<string, number> = {};
                                    const maxs: Record<string, number> = {};
                                    metrics.forEach(m => {
                                        const vals = crossBucketStats.map(s => s[m]).filter(v => v > 0);
                                        mins[m] = vals.length ? Math.min(...vals) : 0;
                                        maxs[m] = vals.length ? Math.max(...vals) : 1;
                                    });

                                    function heatColor(val: number, metric: string): string {
                                        // For all these metrics, lower is better → green. Higher → red.
                                        const range = maxs[metric] - mins[metric];
                                        if (range === 0) return 'rgba(59, 130, 246, 0.3)';
                                        const ratio = (val - mins[metric]) / range; // 0 = best, 1 = worst
                                        const r = Math.round(16 + ratio * 200);
                                        const g = Math.round(185 - ratio * 150);
                                        const b = Math.round(129 - ratio * 80);
                                        return `rgba(${r}, ${g}, ${b}, 0.3)`;
                                    }

                                    return crossBucketStats.map((row) => (
                                        <tr key={row.bucket} className="border-t border-gray-800">
                                            <td className="py-2 px-3 text-white font-medium">{row.bucketShort}</td>
                                            {[
                                                { val: row.avgHs, fmt: fmt(row.avgHs) + ' ms', metric: 'avgHs' },
                                                { val: row.maxHs, fmt: fmt(row.maxHs) + ' ms', metric: 'maxHs' },
                                                { val: row.avgPw, fmt: fmt(row.avgPw, 3) + ' W', metric: 'avgPw' },
                                                { val: row.avgEn, fmt: fmt(row.avgEn, 2) + ' J', metric: 'avgEn' },
                                                { val: row.efficiencyAvg, fmt: fmt(row.efficiencyAvg, 0), metric: 'efficiencyAvg' },
                                            ].map((cell, ci) => (
                                                <td key={ci} className="text-center py-2 px-3 font-mono text-white"
                                                    style={{ backgroundColor: heatColor(cell.val, cell.metric) }}>
                                                    {cell.fmt}
                                                </td>
                                            ))}
                                        </tr>
                                    ));
                                })()}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* ── KPI Cards for selected bucket ── */}
            {selectedSuites.length > 0 && (
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
                    <div className="card text-center">
                        <div className="text-xs text-gray-400 uppercase tracking-wider">Suites</div>
                        <div className="text-2xl font-bold text-white mt-1">{kpi.count}</div>
                    </div>
                    <div className="card text-center">
                        <div className="text-xs text-gray-400 uppercase tracking-wider">Avg HS</div>
                        <div className="text-2xl font-bold text-blue-400 mt-1">{fmt(kpi.avgHs, 0)}<span className="text-xs text-gray-500"> ms</span></div>
                    </div>
                    <div className="card text-center">
                        <div className="text-xs text-gray-400 uppercase tracking-wider">P95 HS</div>
                        <div className="text-2xl font-bold text-yellow-400 mt-1">{fmt(kpi.p95Hs, 0)}<span className="text-xs text-gray-500"> ms</span></div>
                    </div>
                    <div className="card text-center">
                        <div className="text-xs text-gray-400 uppercase tracking-wider">Min HS</div>
                        <div className="text-2xl font-bold text-green-400 mt-1">{fmt(kpi.minHs, 0)}<span className="text-xs text-gray-500"> ms</span></div>
                    </div>
                    <div className="card text-center">
                        <div className="text-xs text-gray-400 uppercase tracking-wider">Max HS</div>
                        <div className="text-2xl font-bold text-red-400 mt-1">{fmt(kpi.maxHs, 0)}<span className="text-xs text-gray-500"> ms</span></div>
                    </div>
                    <div className="card text-center">
                        <div className="text-xs text-gray-400 uppercase tracking-wider">σ / CV</div>
                        <div className="text-lg font-bold text-gray-300 mt-1">{fmt(kpi.stdHs, 0)}<span className="text-xs text-gray-500"> / {fmt(kpi.cvHs, 1)}%</span></div>
                    </div>
                    <div className="card text-center">
                        <div className="text-xs text-gray-400 uppercase tracking-wider">Avg Power</div>
                        <div className="text-2xl font-bold text-emerald-400 mt-1">{fmt(kpi.avgPw, 3)}<span className="text-xs text-gray-500"> W</span></div>
                    </div>
                    <div className="card text-center">
                        <div className="text-xs text-gray-400 uppercase tracking-wider">Total Energy</div>
                        <div className="text-2xl font-bold text-amber-400 mt-1">{fmt(kpi.totalEn, 1)}<span className="text-xs text-gray-500"> J</span></div>
                    </div>
                </div>
            )}

            {/* ── Radar + Scatter Row ── */}
            <div className="grid grid-cols-2 gap-6">
                {/* Cross-Bucket Radar */}
                {radarData.length > 1 && radarData.length <= 8 && (
                    <div className="card">
                        <h3 className="card-header">📊 Cross-Bucket Radar — {BUCKET_LABELS[selectedType]}</h3>
                        <p className="text-xs text-gray-400 mb-3">Relative averages across all groups.</p>
                        <div className="h-80">
                            <ResponsiveContainer width="100%" height="100%">
                                <RadarChart data={radarData}>
                                    <PolarGrid stroke="#374151" />
                                    <PolarAngleAxis dataKey="bucket" tick={{ fill: '#9ca3af', fontSize: 11 }} />
                                    <PolarRadiusAxis tick={{ fill: '#6b7280', fontSize: 10 }} />
                                    <Radar name="Handshake (ms)" dataKey="Handshake" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.2} />
                                    <Radar name="Power (W)" dataKey="Power" stroke="#10b981" fill="#10b981" fillOpacity={0.15} />
                                    <Radar name="Energy (J)" dataKey="Energy" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.1} />
                                    <Legend />
                                    <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }} />
                                </RadarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                )}

                {/* Scatter: Handshake vs Energy for selected bucket */}
                {scatterData.length > 1 && (
                    <div className="card">
                        <h3 className="card-header">🎯 Handshake vs Energy — {selectedBucket}</h3>
                        <p className="text-xs text-gray-400 mb-3">Bottom-left is ideal (fast + low energy). Size = power draw.</p>
                        <div className="h-80">
                            <ResponsiveContainer width="100%" height="100%">
                                <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                    <XAxis type="number" dataKey="handshake_ms" name="Handshake (ms)" tick={{ fill: '#9ca3af', fontSize: 11 }}
                                        label={{ value: 'Handshake (ms)', position: 'insideBottom', offset: -5, fill: '#6b7280' }} />
                                    <YAxis type="number" dataKey="energy_j" name="Energy (J)" tick={{ fill: '#9ca3af', fontSize: 11 }}
                                        label={{ value: 'Energy (J)', angle: -90, position: 'insideLeft', fill: '#6b7280' }} />
                                    <ZAxis type="number" dataKey="power_w" range={[30, 200]} name="Power (W)" />
                                    <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                                        formatter={(v: any, name: string) => [typeof v === 'number' ? fmt(v, 3) : v, name]}
                                        labelFormatter={() => ''} />
                                    <Scatter data={scatterData} fill="#3b82f6">
                                        {scatterData.map((entry, i) => {
                                            const nistColor: Record<string, string> = { L1: '#3b82f6', L3: '#8b5cf6', L5: '#ef4444' };
                                            return <Cell key={i} fill={nistColor[entry.nist] || '#6b7280'} />;
                                        })}
                                    </Scatter>
                                </ScatterChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                )}
            </div>

            {/* ── Handshake Comparison Bar Chart ── */}
            {chartData.length > 0 && (
                <div className="card">
                    <h3 className="card-header">🔑 Handshake Duration — {selectedBucket}</h3>
                    <div className="h-80">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={chartData} layout="vertical" margin={{ left: 150 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                <XAxis type="number" stroke="#9ca3af" />
                                <YAxis dataKey="name" type="category" width={140} stroke="#9ca3af" tick={{ fontSize: 10 }} />
                                <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
                                    formatter={(value: number) => [`${value.toFixed(2)} ms`, 'Handshake']} />
                                <Bar dataKey="handshake_ms" name="Handshake (ms)">
                                    {chartData.map((entry, index) => <Cell key={index} fill={entry.color} />)}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            )}

            {/* ── Power & Energy + Efficiency Bar Charts ── */}
            {chartData.length > 0 && (
                <div className="grid grid-cols-2 gap-6">
                    <div className="card">
                        <h3 className="card-header">⚡ Power & Energy — {selectedBucket}</h3>
                        <div className="h-80">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={chartData} layout="vertical" margin={{ left: 150 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                    <XAxis type="number" stroke="#9ca3af" />
                                    <YAxis dataKey="name" type="category" width={140} stroke="#9ca3af" tick={{ fontSize: 10 }} />
                                    <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }} />
                                    <Legend />
                                    <Bar dataKey="power_w" name="Power (W)" fill="#10b981" />
                                    <Bar dataKey="energy_j" name="Energy (J)" fill="#f59e0b" />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                    <div className="card">
                        <h3 className="card-header">📐 Efficiency Score — {selectedBucket}</h3>
                        <p className="text-xs text-gray-400 mb-2">Handshake × Energy product. Lower = more efficient.</p>
                        <div className="h-72">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={[...chartData].sort((a, b) => a.efficiency - b.efficiency)} layout="vertical" margin={{ left: 150 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                    <XAxis type="number" stroke="#9ca3af" />
                                    <YAxis dataKey="name" type="category" width={140} stroke="#9ca3af" tick={{ fontSize: 10 }} />
                                    <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
                                        formatter={(value: number) => [`${value.toFixed(0)}`, 'Efficiency (ms·J)']} />
                                    <Bar dataKey="efficiency" name="Efficiency (ms·J)">
                                        {[...chartData].sort((a, b) => a.efficiency - b.efficiency).map((_, i) => {
                                            const g = efficiencyGrade(i + 1, chartData.length);
                                            return <Cell key={i} fill={g.color} />;
                                        })}
                                    </Bar>
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Suite Detail Table ── */}
            {selectedSuites.length > 0 && (
                <div className="card">
                    <h3 className="card-header">📋 Suite Details — {selectedBucket} ({selectedSuites.length})</h3>
                    <p className="text-xs text-gray-400 mb-3">Click column headers to sort. Efficiency = Handshake × Energy (lower = better).</p>
                    <div className="overflow-x-auto">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th className="cursor-pointer hover:text-blue-400" onClick={() => handleSort('suite_id')}>
                                        Suite ID{sortIcon('suite_id')}
                                    </th>
                                    <th>KEM</th>
                                    <th>SIG</th>
                                    <th>NIST</th>
                                    <th className="text-right cursor-pointer hover:text-blue-400" onClick={() => handleSort('handshake_ms')}>
                                        Handshake (ms){sortIcon('handshake_ms')}
                                    </th>
                                    <th className="text-right cursor-pointer hover:text-blue-400" onClick={() => handleSort('power_w')}>
                                        Power (W){sortIcon('power_w')}
                                    </th>
                                    <th className="text-right cursor-pointer hover:text-blue-400" onClick={() => handleSort('energy_j')}>
                                        Energy (J){sortIcon('energy_j')}
                                    </th>
                                    <th className="text-right cursor-pointer hover:text-blue-400" onClick={() => handleSort('efficiency')}>
                                        Efficiency{sortIcon('efficiency')}
                                    </th>
                                    <th>Grade</th>
                                </tr>
                            </thead>
                            <tbody>
                                {selectedSuites.map((s, idx) => {
                                    const grade = efficiencyGrade(idx + 1, selectedSuites.length);
                                    const isBest = idx === 0 && sortField === 'efficiency' && sortAsc;
                                    const isWorst = idx === selectedSuites.length - 1 && sortField === 'efficiency' && sortAsc;
                                    return (
                                        <tr key={s.key} className={isBest ? 'bg-green-900/20' : isWorst ? 'bg-red-900/20' : ''}>
                                            <td className="text-gray-500">{idx + 1}</td>
                                            <td className="font-mono text-sm">
                                                {isBest && <span className="text-green-400 mr-1">🏆</span>}
                                                {isWorst && <span className="text-red-400 mr-1">⚠️</span>}
                                                {s.suite_id}
                                            </td>
                                            <td className="text-sm">{s.kem}</td>
                                            <td className="text-sm">{s.sig}</td>
                                            <td>
                                                <span className={`px-2 py-0.5 rounded text-xs ${
                                                    s.nist === 'L1' ? 'bg-green-500/20 text-green-400' :
                                                    s.nist === 'L3' ? 'bg-yellow-500/20 text-yellow-400' :
                                                    s.nist === 'L5' ? 'bg-red-500/20 text-red-400' : 'bg-gray-500/20'
                                                }`}>{s.nist}</span>
                                            </td>
                                            <td className="text-right font-mono">{s.handshake_ms != null ? s.handshake_ms.toFixed(2) : '—'}</td>
                                            <td className="text-right font-mono">{s.power_w != null ? s.power_w.toFixed(3) : '—'}</td>
                                            <td className="text-right font-mono">{s.energy_j != null ? s.energy_j.toFixed(2) : '—'}</td>
                                            <td className="text-right font-mono">{s.efficiency != null ? s.efficiency.toFixed(0) : '—'}</td>
                                            <td>
                                                <span className="px-2 py-0.5 rounded text-xs font-bold" style={{
                                                    color: grade.color, backgroundColor: grade.color + '22'
                                                }}>{grade.label}</span>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {selectedSuites.length === 0 && (
                <div className="text-center py-12 text-gray-400">
                    No suites in this bucket. Select a different group.
                </div>
            )}

            {/* ── Cross-Run Bucket Comparison ── */}
            <CrossRunBucketPanel
                selectedType={selectedType}
                selectedBucket={selectedBucket}
                settings={settings}
            />
        </div>
    );
}

/**
 * Cross-Run Bucket Panel — Shows same bucket across 3 runs side by side.
 */
interface CrossRunBucketPanelProps {
    selectedType: BucketType;
    selectedBucket: string;
    settings: {
        active_runs?: string[];
        run_labels?: Record<string, { label?: string; type?: RunType }>;
    } | null;
}

interface ChartRow {
    run_type: RunType;
    label: string;
    count: number;
    avgHs: number;
    avgPw: number;
    avgEn: number;
}

function CrossRunBucketPanel({ selectedType, selectedBucket, settings }: CrossRunBucketPanelProps) {
    const [crossData, setCrossData] = useState<Record<string, Buckets> | null>(null);
    const [loading, setLoading] = useState(false);
    const activeRuns: string[] = settings?.active_runs || [];
    const runLabels = settings?.run_labels || {};

    useEffect(() => {
        if (activeRuns.length < 2) return;
        let cancelled = false;
        setLoading(true);
        Promise.all(activeRuns.map((rid: string) =>
            fetch(`/api/buckets?run_id=${encodeURIComponent(rid)}`).then(r => r.json()).then(data => ({ rid, data }))
        )).then((results: { rid: string; data: Buckets }[]) => {
            if (cancelled) return;
            const map: Record<string, Buckets> = {};
            results.forEach(r => { map[r.rid] = r.data; });
            setCrossData(map);
        }).catch(() => {}).finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeRuns.join(',')]);

    const chartRows: ChartRow[] = useMemo(() => {
        if (!crossData || !selectedBucket) return [];
        return activeRuns.map((rid: string) => {
            const rl = runLabels[rid];
            const rt: RunType = rl?.type ?? 'no_ddos';
            const bucketData = (crossData[rid]?.[selectedType] || {})[selectedBucket] || [];
            const hs = bucketData.map(s => s.handshake_ms).filter((v): v is number => v != null);
            const pw = bucketData.map(s => s.power_w).filter((v): v is number => v != null);
            const en = bucketData.map(s => s.energy_j).filter((v): v is number => v != null);
            return {
                run_type: rt,
                label: rl?.label || rid,
                count: bucketData.length,
                avgHs: hs.length ? hs.reduce((a, b) => a + b, 0) / hs.length : 0,
                avgPw: pw.length ? pw.reduce((a, b) => a + b, 0) / pw.length : 0,
                avgEn: en.length ? en.reduce((a, b) => a + b, 0) / en.length : 0,
            };
        });
    }, [crossData, selectedType, selectedBucket, activeRuns, runLabels]);

    if (activeRuns.length < 2) return null;
    if (loading) return <div className="card text-gray-400 text-sm">Loading cross-run comparison…</div>;
    if (!crossData || chartRows.length === 0) return null;

    const barData = [
        { metric: 'Handshake (ms)', ...Object.fromEntries(chartRows.map((r: ChartRow) => [r.run_type, +r.avgHs.toFixed(2)])) },
        { metric: 'Power (W)', ...Object.fromEntries(chartRows.map((r: ChartRow) => [r.run_type, +r.avgPw.toFixed(3)])) },
        { metric: 'Energy (J)', ...Object.fromEntries(chartRows.map((r: ChartRow) => [r.run_type, +r.avgEn.toFixed(2)])) },
    ];

    const runTypes: RunType[] = chartRows.map((r: ChartRow) => r.run_type);

    return (
        <div className="card border border-purple-500/30">
            <h3 className="text-lg font-semibold text-purple-300 mb-2">
                🔄 Cross-Run Comparison — {selectedBucket}
            </h3>
            <p className="text-xs text-gray-400 mb-4">
                Same bucket ({BUCKET_LABELS[selectedType]}: {selectedBucket}) compared across {chartRows.length} scenario runs.
            </p>
            <div className="grid grid-cols-3 gap-4 mb-4">
                {chartRows.map((r: ChartRow) => (
                    <div key={r.run_type} className="p-3 rounded-lg border"
                        style={{ borderColor: RUN_TYPE_COLORS[r.run_type] + '44' }}>
                        <div className="flex items-center gap-2 mb-2">
                            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: RUN_TYPE_COLORS[r.run_type] }} />
                            <span className="text-white text-sm font-medium">{r.label}</span>
                        </div>
                        <div className="grid grid-cols-2 gap-1 text-xs">
                            <span className="text-gray-400">Avg HS:</span><span className="font-mono text-white">{r.avgHs.toFixed(2)} ms</span>
                            <span className="text-gray-400">Avg Power:</span><span className="font-mono text-white">{r.avgPw.toFixed(3)} W</span>
                            <span className="text-gray-400">Avg Energy:</span><span className="font-mono text-white">{r.avgEn.toFixed(2)} J</span>
                            <span className="text-gray-400">Suites:</span><span className="font-mono text-white">{r.count}</span>
                        </div>
                    </div>
                ))}
            </div>
            <ResponsiveContainer width="100%" height={200}>
                <BarChart data={barData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis dataKey="metric" tick={{ fill: '#d1d5db', fontSize: 11 }} />
                    <YAxis tick={{ fill: '#9ca3af', fontSize: 10 }} />
                    <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    {runTypes.map((rt: RunType) => (
                        <Bar key={rt} dataKey={rt} fill={RUN_TYPE_COLORS[rt]}
                            name={RUN_TYPE_LABELS[rt]} radius={[2, 2, 0, 0]} />
                    ))}
                </BarChart>
            </ResponsiveContainer>
        </div>
    );
}
