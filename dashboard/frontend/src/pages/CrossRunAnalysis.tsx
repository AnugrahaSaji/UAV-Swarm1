/**
 * CrossRunAnalysis — "Understand Everything" Dashboard.
 * All 72 suites × 3 run types with overhead analysis, heatmaps,
 * per-metric charts, family aggregation, and delta tables.
 */

import { useEffect, useState, useMemo } from 'react';
import { useDashboardStore } from '../state/store';
import {
    RUN_TYPE_COLORS, RUN_TYPE_LABELS, type RunType,
    type CrossRunSuiteMetrics,
    type OverheadMetricDetail,
} from '../types/metrics';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
    RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
} from 'recharts';

// ─── Helpers ────────────────────────────────────────────────────────────────

function fmt(v: number | null | undefined, digits = 2): string {
    if (v == null || isNaN(v)) return '—';
    return v.toFixed(digits);
}

function deltaPct(baseline: number | null, target: number | null): number | null {
    if (baseline == null || target == null || baseline === 0) return null;
    return ((target - baseline) / Math.abs(baseline)) * 100;
}

function deltaColor(pct: number | null, inverted = false): string {
    if (pct == null) return 'text-gray-500';
    const bad = inverted ? pct < -5 : pct > 5;
    const good = inverted ? pct > 5 : pct < -5;
    if (bad) return 'text-red-400';
    if (good) return 'text-green-400';
    return 'text-yellow-400';
}

function heatBg(val: number | null, min: number, max: number): string {
    if (val == null || max === min) return '';
    const t = Math.max(0, Math.min(1, (val - min) / (max - min)));
    const r = Math.round(16 + t * 220);
    const g = Math.round(185 - t * 155);
    return `rgba(${r}, ${g}, 80, 0.2)`;
}

const RUN_ORDER: RunType[] = ['no_ddos', 'ddos_xgboost', 'ddos_txt'];

type SortField = 'suite_id' | 'handshake_ms' | 'cpu_avg_pct' | 'power_avg_w' | 'energy_j' | 'temperature_c' | 'packet_loss';
type MetricCategory = 'overview' | 'handshake' | 'crypto' | 'system' | 'power' | 'transport' | 'latency' | 'mavlink';

const METRIC_CATEGORIES: { key: MetricCategory; label: string; icon: string }[] = [
    { key: 'overview', label: 'Overview', icon: '📊' },
    { key: 'handshake', label: 'Handshake', icon: '🤝' },
    { key: 'crypto', label: 'Crypto Primitives', icon: '🔐' },
    { key: 'system', label: 'System Resources', icon: '💻' },
    { key: 'power', label: 'Power & Energy', icon: '⚡' },
    { key: 'transport', label: 'Transport', icon: '📡' },
    { key: 'latency', label: 'Latency & Jitter', icon: '⏱️' },
    { key: 'mavlink', label: 'MAVLink Integrity', icon: '🛡️' },
];

interface MetricDef {
    key: keyof CrossRunSuiteMetrics;
    label: string;
    unit: string;
    digits: number;
    inverted?: boolean; // true = higher is better (e.g., goodput)
}

const METRIC_DEFS: Record<MetricCategory, MetricDef[]> = {
    overview: [
        { key: 'handshake_ms', label: 'Handshake', unit: 'ms', digits: 2 },
        { key: 'cpu_avg_pct', label: 'CPU Avg', unit: '%', digits: 1 },
        { key: 'power_avg_w', label: 'Power', unit: 'W', digits: 3 },
        { key: 'energy_j', label: 'Energy', unit: 'J', digits: 2 },
        { key: 'temperature_c', label: 'Temp', unit: '°C', digits: 1 },
        { key: 'goodput_mbps', label: 'Goodput', unit: 'Mbps', digits: 3, inverted: true },
    ],
    handshake: [
        { key: 'handshake_ms', label: 'Total Duration', unit: 'ms', digits: 2 },
        { key: 'protocol_hs_ms', label: 'Protocol Duration', unit: 'ms', digits: 2 },
        { key: 'e2e_hs_ms', label: 'E2E Duration', unit: 'ms', digits: 2 },
    ],
    crypto: [
        { key: 'kem_keygen_ms', label: 'KEM Keygen', unit: 'ms', digits: 4 },
        { key: 'kem_encaps_ms', label: 'KEM Encaps', unit: 'ms', digits: 4 },
        { key: 'kem_decaps_ms', label: 'KEM Decaps', unit: 'ms', digits: 4 },
        { key: 'sig_sign_ms', label: 'SIG Sign', unit: 'ms', digits: 4 },
        { key: 'sig_verify_ms', label: 'SIG Verify', unit: 'ms', digits: 4 },
        { key: 'total_crypto_ms', label: 'Total Crypto', unit: 'ms', digits: 2 },
    ],
    system: [
        { key: 'cpu_avg_pct', label: 'CPU Avg', unit: '%', digits: 1 },
        { key: 'cpu_peak_pct', label: 'CPU Peak', unit: '%', digits: 1 },
        { key: 'memory_mb', label: 'Memory RSS', unit: 'MB', digits: 1 },
        { key: 'temperature_c', label: 'Temperature', unit: '°C', digits: 1 },
        { key: 'load_avg_1m', label: 'Load Avg 1m', unit: '', digits: 2 },
    ],
    power: [
        { key: 'power_avg_w', label: 'Power Avg', unit: 'W', digits: 3 },
        { key: 'power_peak_w', label: 'Power Peak', unit: 'W', digits: 3 },
        { key: 'energy_j', label: 'Energy Total', unit: 'J', digits: 2 },
        { key: 'energy_per_hs_j', label: 'Energy/Handshake', unit: 'J', digits: 4 },
        { key: 'voltage_v', label: 'Voltage', unit: 'V', digits: 3 },
        { key: 'current_a', label: 'Current', unit: 'A', digits: 4 },
    ],
    transport: [
        { key: 'goodput_mbps', label: 'Goodput', unit: 'Mbps', digits: 3, inverted: true },
        { key: 'packet_loss', label: 'Packet Loss', unit: '', digits: 6 },
        { key: 'packets_sent', label: 'Pkts Sent', unit: '', digits: 0 },
        { key: 'packets_dropped', label: 'Pkts Dropped', unit: '', digits: 0 },
        { key: 'drop_replay', label: 'Replay Drops', unit: '', digits: 0 },
        { key: 'drop_auth', label: 'Auth Drops', unit: '', digits: 0 },
    ],
    latency: [
        { key: 'rtt_avg_ms', label: 'RTT Avg', unit: 'ms', digits: 2 },
        { key: 'rtt_p95_ms', label: 'RTT P95', unit: 'ms', digits: 2 },
        { key: 'jitter_avg_ms', label: 'Jitter Avg', unit: 'ms', digits: 2 },
        { key: 'owl_avg_ms', label: 'One-Way Latency', unit: 'ms', digits: 2 },
    ],
    mavlink: [
        { key: 'mavlink_crc_errors', label: 'CRC Errors', unit: '', digits: 0 },
        { key: 'mavlink_decode_errors', label: 'Decode Errors', unit: '', digits: 0 },
        { key: 'mavlink_ooo', label: 'Out of Order', unit: '', digits: 0 },
        { key: 'mavlink_duplicates', label: 'Duplicates', unit: '', digits: 0 },
    ],
};

const OVERHEAD_DISPLAY: { key: string; label: string; unit: string; inverted?: boolean }[] = [
    { key: 'cpu_avg_pct', label: 'CPU Avg', unit: '%' },
    { key: 'cpu_peak_pct', label: 'CPU Peak', unit: '%' },
    { key: 'temperature_c', label: 'Temperature', unit: '°C' },
    { key: 'memory_mb', label: 'Memory', unit: 'MB' },
    { key: 'power_avg_w', label: 'Power', unit: 'W' },
    { key: 'energy_j', label: 'Energy', unit: 'J' },
    { key: 'handshake_ms', label: 'Handshake', unit: 'ms' },
    { key: 'goodput_mbps', label: 'Goodput', unit: 'Mbps', inverted: true },
    { key: 'rtt_avg_ms', label: 'RTT', unit: 'ms' },
    { key: 'jitter_avg_ms', label: 'Jitter', unit: 'ms' },
    { key: 'packet_loss', label: 'Packet Loss', unit: '' },
];

// =============================================================================
// COMPONENT
// =============================================================================

export default function CrossRunAnalysis() {
    const { crossRunAnalysis, fetchCrossRunAnalysis, fetchSettings, isLoading } = useDashboardStore();
    const [activeCategory, setActiveCategory] = useState<MetricCategory>('overview');
    const [sortField, setSortField] = useState<SortField>('suite_id');
    const [sortAsc, setSortAsc] = useState(true);
    const [filterFamily, setFilterFamily] = useState<string>('');
    const [showDelta, setShowDelta] = useState(true);

    useEffect(() => { fetchSettings(); fetchCrossRunAnalysis(); }, [fetchSettings, fetchCrossRunAnalysis]);

    const data = crossRunAnalysis;
    const suites = data?.suites ?? [];
    const runs = data?.runs ?? [];
    const overhead = data?.overhead ?? {};

    // Filter & sort
    const filtered = useMemo(() => {
        let list = [...suites];
        if (filterFamily) {
            list = list.filter(s =>
                s.kem_family === filterFamily || s.sig_family === filterFamily
            );
        }
        list.sort((a, b) => {
            if (sortField === 'suite_id') {
                return sortAsc ? a.suite_id.localeCompare(b.suite_id) : b.suite_id.localeCompare(a.suite_id);
            }
            const av = a.runs?.no_ddos?.[sortField] ?? Infinity;
            const bv = b.runs?.no_ddos?.[sortField] ?? Infinity;
            return sortAsc ? (av as number) - (bv as number) : (bv as number) - (av as number);
        });
        return list;
    }, [suites, filterFamily, sortField, sortAsc]);

    // Available families
    const families = useMemo(() => {
        const fams = new Set<string>();
        suites.forEach(s => {
            if (s.kem_family) fams.add(s.kem_family);
            if (s.sig_family) fams.add(s.sig_family);
        });
        return [...fams].sort();
    }, [suites]);

    // Family aggregation data
    const familyAgg = useMemo(() => {
        const map: Record<string, Record<string, { vals: number[] }>> = {};
        suites.forEach(s => {
            const fam = s.kem_family || 'Other';
            if (!map[fam]) map[fam] = {};
            RUN_ORDER.forEach(rt => {
                const m = s.runs?.[rt];
                if (!m) return;
                const rk = rt;
                if (!map[fam][rk]) map[fam][rk] = { vals: [] };
                if (m.handshake_ms != null) map[fam][rk].vals.push(m.handshake_ms);
            });
        });
        return Object.entries(map).map(([fam, rtData]) => {
            const row: Record<string, unknown> = { family: fam };
            RUN_ORDER.forEach(rt => {
                const vals = rtData[rt]?.vals ?? [];
                row[`${rt}_hs`] = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
            });
            return row;
        }).sort((a, b) => ((a.no_ddos_hs as number) ?? 999) - ((b.no_ddos_hs as number) ?? 999));
    }, [suites]);

    // Family aggregation for CPU
    const familyCpuAgg = useMemo(() => {
        const map: Record<string, Record<string, number[]>> = {};
        suites.forEach(s => {
            const fam = s.kem_family || 'Other';
            if (!map[fam]) map[fam] = {};
            RUN_ORDER.forEach(rt => {
                if (!map[fam][rt]) map[fam][rt] = [];
                const v = s.runs?.[rt]?.cpu_avg_pct;
                if (v != null) map[fam][rt].push(v);
            });
        });
        return Object.entries(map).map(([fam, rtData]) => {
            const row: Record<string, unknown> = { family: fam };
            RUN_ORDER.forEach(rt => {
                const vals = rtData[rt] ?? [];
                row[`${rt}_cpu`] = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
            });
            return row;
        });
    }, [suites]);

    // Family aggregation for Power
    const familyPowerAgg = useMemo(() => {
        const map: Record<string, Record<string, number[]>> = {};
        suites.forEach(s => {
            const fam = s.kem_family || 'Other';
            if (!map[fam]) map[fam] = {};
            RUN_ORDER.forEach(rt => {
                if (!map[fam][rt]) map[fam][rt] = [];
                const v = s.runs?.[rt]?.power_avg_w;
                if (v != null) map[fam][rt].push(v);
            });
        });
        return Object.entries(map).map(([fam, rtData]) => {
            const row: Record<string, unknown> = { family: fam };
            RUN_ORDER.forEach(rt => {
                const vals = rtData[rt] ?? [];
                row[`${rt}_pwr`] = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
            });
            return row;
        });
    }, [suites]);

    // Radar data: normalized overhead
    const radarData = useMemo(() => {
        return OVERHEAD_DISPLAY.filter(m => !m.inverted).slice(0, 8).map(m => {
            const row: Record<string, unknown> = { metric: m.label };
            (['ddos_xgboost', 'ddos_txt'] as RunType[]).forEach(rt => {
                const oh = (overhead as Record<string, Record<string, OverheadMetricDetail>>)?.[rt]?.[m.key];
                row[rt] = oh?.delta_pct != null ? Math.min(Math.abs(oh.delta_pct), 100) : 0;
            });
            return row;
        });
    }, [overhead]);

    // Compute heatmap ranges
    const heatRanges = useMemo(() => {
        const metrics = METRIC_DEFS[activeCategory];
        const ranges: Record<string, { min: number; max: number }> = {};
        metrics.forEach(m => {
            const vals: number[] = [];
            filtered.forEach(s => {
                RUN_ORDER.forEach(rt => {
                    const v = s.runs?.[rt]?.[m.key];
                    if (typeof v === 'number' && !isNaN(v)) vals.push(v);
                });
            });
            ranges[m.key] = {
                min: vals.length ? Math.min(...vals) : 0,
                max: vals.length ? Math.max(...vals) : 1,
            };
        });
        return ranges;
    }, [filtered, activeCategory]);

    const handleSort = (field: SortField) => {
        if (sortField === field) setSortAsc(!sortAsc);
        else { setSortField(field); setSortAsc(true); }
    };

    if (isLoading && !data) {
        return <div className="flex items-center justify-center h-64"><div className="text-gray-400">Loading cross-run analysis…</div></div>;
    }

    if (!data || suites.length === 0) {
        return (
            <div className="text-center py-12 text-gray-500">
                <p className="text-lg mb-2">No cross-run data available</p>
                <p className="text-sm">Configure active runs in Settings first. Ensure all 3 scenario folders have data.</p>
            </div>
        );
    }

    const metrics = METRIC_DEFS[activeCategory];

    return (
        <div className="space-y-6">
            {/* ── Header ── */}
            <div>
                <h1 className="text-2xl font-bold text-white">🔬 Cross-Run Analysis</h1>
                <p className="text-gray-400 text-sm mt-1">
                    All {suites.length} suites × {runs.length} scenarios — overhead, heatmaps, family aggregation, delta tables
                </p>
            </div>

            {/* ── Overhead Summary Banner ── */}
            {(overhead.ddos_xgboost || overhead.ddos_txt) && (
                <div className="card bg-gradient-to-r from-gray-800 via-gray-900 to-gray-800">
                    <h2 className="text-lg font-semibold text-white mb-4">📈 DDoS Detection Overhead (vs Baseline)</h2>
                    <div className="grid grid-cols-2 gap-6">
                        {(['ddos_xgboost', 'ddos_txt'] as RunType[]).map(rt => {
                            const oh = (overhead as Record<string, Record<string, OverheadMetricDetail>>)?.[rt];
                            if (!oh) return null;
                            const color = RUN_TYPE_COLORS[rt];
                            return (
                                <div key={rt} className="p-4 rounded-lg border" style={{ borderColor: color + '44' }}>
                                    <div className="flex items-center gap-2 mb-3">
                                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
                                        <span className="text-white font-medium">{RUN_TYPE_LABELS[rt]}</span>
                                    </div>
                                    <div className="grid grid-cols-3 gap-3">
                                        {OVERHEAD_DISPLAY.map(m => {
                                            const d = oh[m.key];
                                            if (!d) return null;
                                            const pct = d.delta_pct;
                                            const isInverted = m.inverted;
                                            return (
                                                <div key={m.key} className="text-center">
                                                    <div className="text-xs text-gray-400">{m.label}</div>
                                                    <div className={`text-lg font-bold font-mono ${deltaColor(pct, isInverted)}`}>
                                                        {pct != null ? `${pct > 0 ? '+' : ''}${pct.toFixed(1)}%` : '—'}
                                                    </div>
                                                    <div className="text-xs text-gray-500">
                                                        {fmt(d.baseline_avg, 2)} → {fmt(d.target_avg, 2)} {m.unit}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* ── Overhead Radar ── */}
            {radarData.length > 0 && (
                <div className="card">
                    <h2 className="text-lg font-semibold text-white mb-4">🕸️ Overhead Radar (|Δ%| from baseline, capped at 100%)</h2>
                    <ResponsiveContainer width="100%" height={350}>
                        <RadarChart data={radarData}>
                            <PolarGrid stroke="#374151" />
                            <PolarAngleAxis dataKey="metric" tick={{ fill: '#d1d5db', fontSize: 11 }} />
                            <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: '#6b7280', fontSize: 10 }} />
                            {(['ddos_xgboost', 'ddos_txt'] as RunType[]).map(rt => (
                                <Radar key={rt} name={RUN_TYPE_LABELS[rt]} dataKey={rt}
                                    stroke={RUN_TYPE_COLORS[rt]} fill={RUN_TYPE_COLORS[rt]}
                                    fillOpacity={0.15} strokeWidth={2} />
                            ))}
                            <Legend />
                            <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                                formatter={(v: number) => `${v.toFixed(1)}%`} />
                        </RadarChart>
                    </ResponsiveContainer>
                </div>
            )}

            {/* ── Family Aggregation Charts ── */}
            <div className="grid grid-cols-3 gap-6">
                {/* Handshake by Family */}
                <div className="card">
                    <h3 className="text-sm font-semibold text-white mb-3">🤝 Avg Handshake by KEM Family</h3>
                    <ResponsiveContainer width="100%" height={250}>
                        <BarChart data={familyAgg}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis dataKey="family" tick={{ fill: '#d1d5db', fontSize: 10 }} />
                            <YAxis tick={{ fill: '#9ca3af', fontSize: 10 }} />
                            <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                                formatter={(v: number) => `${v?.toFixed(2) ?? '—'} ms`} />
                            <Legend wrapperStyle={{ fontSize: 10 }} />
                            {RUN_ORDER.map(rt => (
                                <Bar key={rt} dataKey={`${rt}_hs`} fill={RUN_TYPE_COLORS[rt]}
                                    name={RUN_TYPE_LABELS[rt]} radius={[2, 2, 0, 0]} />
                            ))}
                        </BarChart>
                    </ResponsiveContainer>
                </div>

                {/* CPU by Family */}
                <div className="card">
                    <h3 className="text-sm font-semibold text-white mb-3">💻 Avg CPU by KEM Family</h3>
                    <ResponsiveContainer width="100%" height={250}>
                        <BarChart data={familyCpuAgg}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis dataKey="family" tick={{ fill: '#d1d5db', fontSize: 10 }} />
                            <YAxis tick={{ fill: '#9ca3af', fontSize: 10 }} />
                            <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                                formatter={(v: number) => `${v?.toFixed(1) ?? '—'}%`} />
                            <Legend wrapperStyle={{ fontSize: 10 }} />
                            {RUN_ORDER.map(rt => (
                                <Bar key={rt} dataKey={`${rt}_cpu`} fill={RUN_TYPE_COLORS[rt]}
                                    name={RUN_TYPE_LABELS[rt]} radius={[2, 2, 0, 0]} />
                            ))}
                        </BarChart>
                    </ResponsiveContainer>
                </div>

                {/* Power by Family */}
                <div className="card">
                    <h3 className="text-sm font-semibold text-white mb-3">⚡ Avg Power by KEM Family</h3>
                    <ResponsiveContainer width="100%" height={250}>
                        <BarChart data={familyPowerAgg}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis dataKey="family" tick={{ fill: '#d1d5db', fontSize: 10 }} />
                            <YAxis tick={{ fill: '#9ca3af', fontSize: 10 }} />
                            <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                                formatter={(v: number) => `${v?.toFixed(3) ?? '—'} W`} />
                            <Legend wrapperStyle={{ fontSize: 10 }} />
                            {RUN_ORDER.map(rt => (
                                <Bar key={rt} dataKey={`${rt}_pwr`} fill={RUN_TYPE_COLORS[rt]}
                                    name={RUN_TYPE_LABELS[rt]} radius={[2, 2, 0, 0]} />
                            ))}
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* ── Controls ── */}
            <div className="card">
                <div className="flex flex-wrap gap-3 items-center">
                    <div className="flex flex-wrap gap-1">
                        {METRIC_CATEGORIES.map(cat => (
                            <button key={cat.key} onClick={() => setActiveCategory(cat.key)}
                                className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                                    activeCategory === cat.key
                                        ? 'bg-blue-600 text-white'
                                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                                }`}>
                                {cat.icon} {cat.label}
                            </button>
                        ))}
                    </div>
                    <div className="ml-auto flex items-center gap-3">
                        <select className="select-input text-sm" value={filterFamily}
                            onChange={e => setFilterFamily(e.target.value)}>
                            <option value="">All Families</option>
                            {families.map(f => <option key={f} value={f}>{f}</option>)}
                        </select>
                        <label className="flex items-center gap-1.5 text-sm text-gray-400 cursor-pointer">
                            <input type="checkbox" checked={showDelta} onChange={e => setShowDelta(e.target.checked)}
                                className="rounded" />
                            Show Δ%
                        </label>
                    </div>
                </div>
            </div>

            {/* ── Per-Metric Grouped Bar Charts ── */}
            <div className="grid grid-cols-2 gap-6">
                {metrics.slice(0, 6).map(m => {
                    const chartData = filtered.slice(0, 24).map(s => {
                        const row: Record<string, unknown> = {
                            name: s.suite_id.replace(/^cs-/, '').substring(0, 22),
                        };
                        RUN_ORDER.forEach(rt => {
                            row[rt] = s.runs?.[rt]?.[m.key] ?? null;
                        });
                        return row;
                    });
                    return (
                        <div key={m.key} className="card">
                            <h3 className="text-sm font-semibold text-white mb-2">
                                {m.label} ({m.unit}) — Top 24 suites
                            </h3>
                            <ResponsiveContainer width="100%" height={220}>
                                <BarChart data={chartData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                    <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 8 }} interval={0} angle={-45} textAnchor="end" height={60} />
                                    <YAxis tick={{ fill: '#9ca3af', fontSize: 10 }} />
                                    <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                                        formatter={(v: number) => v != null ? `${v.toFixed(m.digits)} ${m.unit}` : '—'} />
                                    <Legend wrapperStyle={{ fontSize: 10 }} />
                                    {RUN_ORDER.map(rt => (
                                        <Bar key={rt} dataKey={rt} fill={RUN_TYPE_COLORS[rt]}
                                            name={RUN_TYPE_LABELS[rt]} radius={[1, 1, 0, 0]} />
                                    ))}
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    );
                })}
            </div>

            {/* ── All-Suites Heatmap Table ── */}
            <div className="card">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold text-white">
                        📋 All Suites — {METRIC_CATEGORIES.find(c => c.key === activeCategory)?.label} Metrics
                    </h2>
                    <span className="text-gray-400 text-sm">{filtered.length} suites × {runs.length} runs</span>
                </div>
                <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
                    <table className="w-full text-xs">
                        <thead className="sticky top-0 bg-gray-800/95 backdrop-blur z-10">
                            <tr>
                                <th className="text-left py-2 px-2 text-gray-400 cursor-pointer hover:text-blue-400"
                                    onClick={() => handleSort('suite_id')}>
                                    Suite {sortField === 'suite_id' ? (sortAsc ? '▲' : '▼') : ''}
                                </th>
                                <th className="text-left py-2 px-1 text-gray-400">KEM</th>
                                <th className="text-left py-2 px-1 text-gray-400">NIST</th>
                                {metrics.flatMap(m =>
                                    RUN_ORDER.map(rt => (
                                        <th key={`${m.key}-${rt}`}
                                            className="text-right py-2 px-1 text-gray-400 whitespace-nowrap"
                                            style={{ borderBottom: `2px solid ${RUN_TYPE_COLORS[rt]}44` }}>
                                            <span className="block text-[10px]" style={{ color: RUN_TYPE_COLORS[rt] }}>
                                                {rt === 'no_ddos' ? 'Base' : rt === 'ddos_xgboost' ? 'XGB' : 'TXT'}
                                            </span>
                                            {m.label}
                                        </th>
                                    ))
                                )}
                                {showDelta && metrics.map(m => (
                                    <th key={`delta-${m.key}`} className="text-right py-2 px-1 text-gray-400 whitespace-nowrap">
                                        Δ {m.label}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.map((s, idx) => (
                                <tr key={s.suite_id} className={`border-t border-gray-800 hover:bg-gray-700/30 ${idx % 2 === 0 ? '' : 'bg-gray-800/20'}`}>
                                    <td className="py-1.5 px-2 font-mono text-white whitespace-nowrap"
                                        title={s.suite_id}>
                                        {s.suite_id.replace(/^cs-/, '').substring(0, 28)}
                                    </td>
                                    <td className="py-1.5 px-1 text-gray-300">{s.kem_family || '—'}</td>
                                    <td className="py-1.5 px-1">
                                        <span className={`px-1 py-0.5 rounded text-[10px] ${
                                            s.nist === 'L1' ? 'bg-blue-500/20 text-blue-400'
                                            : s.nist === 'L3' ? 'bg-purple-500/20 text-purple-400'
                                            : s.nist === 'L5' ? 'bg-red-500/20 text-red-400'
                                            : 'bg-gray-500/20 text-gray-400'
                                        }`}>{s.nist || '?'}</span>
                                    </td>
                                    {metrics.flatMap(m =>
                                        RUN_ORDER.map(rt => {
                                            const v = s.runs?.[rt]?.[m.key];
                                            const numV = typeof v === 'number' ? v : null;
                                            const range = heatRanges[m.key];
                                            return (
                                                <td key={`${m.key}-${rt}`}
                                                    className="text-right py-1.5 px-1 font-mono text-white"
                                                    style={{ backgroundColor: range ? heatBg(numV, range.min, range.max) : '' }}>
                                                    {numV != null ? numV.toFixed(m.digits) : '—'}
                                                </td>
                                            );
                                        })
                                    )}
                                    {showDelta && metrics.map(m => {
                                        const base = s.runs?.no_ddos?.[m.key];
                                        const baseN = typeof base === 'number' ? base : null;
                                        // Show max delta across xgb/txt
                                        const deltas = (['ddos_xgboost', 'ddos_txt'] as RunType[]).map(rt => {
                                            const tv = s.runs?.[rt]?.[m.key];
                                            const tvN = typeof tv === 'number' ? tv : null;
                                            return deltaPct(baseN, tvN);
                                        }).filter((d): d is number => d != null);
                                        const maxDelta = deltas.length ? deltas.reduce((a, b) => Math.abs(a) > Math.abs(b) ? a : b, 0) : null;
                                        return (
                                            <td key={`delta-${m.key}`}
                                                className={`text-right py-1.5 px-1 font-mono ${deltaColor(maxDelta, m.inverted)}`}>
                                                {maxDelta != null ? `${maxDelta > 0 ? '+' : ''}${maxDelta.toFixed(1)}%` : '—'}
                                            </td>
                                        );
                                    })}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* ── Run Legend ── */}
            <div className="flex items-center gap-6 text-sm text-gray-400">
                {runs.map(r => (
                    <div key={r.run_id} className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: RUN_TYPE_COLORS[r.run_type] }} />
                        <span>{r.label}</span>
                    </div>
                ))}
                <span className="ml-auto text-xs text-gray-500">
                    Heatmap: darker = higher value. Δ%: red = worse, green = better vs baseline.
                </span>
            </div>
        </div>
    );
}
