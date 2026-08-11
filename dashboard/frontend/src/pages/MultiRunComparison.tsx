/**
 * MultiRunComparison Page — Compare same suite across 3 run scenarios.
 * No DDoS vs DDoS XGBoost vs DDoS TXT — side-by-side.
 * v2: Full category coverage, delta %, per-category bar charts.
 */

import { useEffect, useState, useMemo } from 'react';
import { useDashboardStore } from '../state/store';
import { RUN_TYPE_COLORS, RUN_TYPE_LABELS, type RunType } from '../types/metrics';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
    RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
} from 'recharts';

function fmt(v: number | null | undefined, digits = 2): string {
    if (v == null || isNaN(v)) return '—';
    return v.toFixed(digits);
}

function deltaPctStr(values: (number | null | undefined)[]): string {
    const nums = values.filter((v): v is number => v != null && !isNaN(v));
    if (nums.length < 2) return '—';
    const base = nums[0]; // first run = baseline
    const maxOther = Math.max(...nums.slice(1));
    if (base === 0) return '—';
    const pct = ((maxOther - base) / Math.abs(base)) * 100;
    return `${pct > 0 ? '+' : ''}${pct.toFixed(1)}%`;
}

function deltaPctColor(values: (number | null | undefined)[], inverted = false): string {
    const nums = values.filter((v): v is number => v != null && !isNaN(v));
    if (nums.length < 2) return 'text-gray-600';
    const base = nums[0];
    const maxOther = Math.max(...nums.slice(1));
    if (base === 0) return 'text-gray-600';
    const pct = ((maxOther - base) / Math.abs(base)) * 100;
    const bad = inverted ? pct < -5 : pct > 5;
    const good = inverted ? pct > 5 : pct < -5;
    if (bad) return 'text-red-400';
    if (good) return 'text-green-400';
    return 'text-yellow-400';
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Extractor = (s: any) => number | null | undefined;

interface MetricRow {
    cat: string;
    metric: string;
    extract: Extractor;
    digits?: number;
    inverted?: boolean; // higher = better
}

const ALL_METRIC_ROWS: MetricRow[] = [
    // Handshake
    { cat: 'Handshake', metric: 'Total Duration (ms)', extract: s => s.handshake?.handshake_total_duration_ms },
    { cat: 'Handshake', metric: 'Protocol Duration (ms)', extract: s => s.handshake?.protocol_handshake_duration_ms },
    { cat: 'Handshake', metric: 'E2E Duration (ms)', extract: s => s.handshake?.end_to_end_handshake_duration_ms },
    // Crypto
    { cat: 'Crypto', metric: 'KEM Keygen (ms)', extract: s => s.crypto_primitives?.kem_keygen_time_ms, digits: 4 },
    { cat: 'Crypto', metric: 'KEM Encaps (ms)', extract: s => s.crypto_primitives?.kem_encapsulation_time_ms, digits: 4 },
    { cat: 'Crypto', metric: 'KEM Decaps (ms)', extract: s => s.crypto_primitives?.kem_decapsulation_time_ms, digits: 4 },
    { cat: 'Crypto', metric: 'Sig Sign (ms)', extract: s => s.crypto_primitives?.signature_sign_time_ms, digits: 4 },
    { cat: 'Crypto', metric: 'Sig Verify (ms)', extract: s => s.crypto_primitives?.signature_verify_time_ms, digits: 4 },
    { cat: 'Crypto', metric: 'Total Crypto (ms)', extract: s => s.crypto_primitives?.total_crypto_time_ms },
    // System
    { cat: 'System', metric: 'Drone CPU Avg (%)', extract: s => s.system_drone?.cpu_usage_avg_percent },
    { cat: 'System', metric: 'Drone CPU Peak (%)', extract: s => s.system_drone?.cpu_usage_peak_percent },
    { cat: 'System', metric: 'Drone Mem RSS (MB)', extract: s => s.system_drone?.memory_rss_mb },
    { cat: 'System', metric: 'Drone Temp (°C)', extract: s => s.system_drone?.temperature_c },
    { cat: 'System', metric: 'Load Avg 1m', extract: s => s.system_drone?.load_avg_1m },
    { cat: 'System', metric: 'GCS CPU Avg (%)', extract: s => s.system_gcs?.cpu_usage_avg_percent },
    { cat: 'System', metric: 'GCS CPU Peak (%)', extract: s => s.system_gcs?.cpu_usage_peak_percent },
    { cat: 'System', metric: 'GCS Mem RSS (MB)', extract: s => s.system_gcs?.memory_rss_mb },
    // Power
    { cat: 'Power', metric: 'Power Avg (W)', extract: s => s.power_energy?.power_avg_w, digits: 3 },
    { cat: 'Power', metric: 'Power Peak (W)', extract: s => s.power_energy?.power_peak_w, digits: 3 },
    { cat: 'Power', metric: 'Energy Total (J)', extract: s => s.power_energy?.energy_total_j },
    { cat: 'Power', metric: 'Energy/Handshake (J)', extract: s => s.power_energy?.energy_per_handshake_j, digits: 4 },
    { cat: 'Power', metric: 'Voltage Avg (V)', extract: s => s.power_energy?.voltage_avg_v, digits: 3 },
    { cat: 'Power', metric: 'Current Avg (A)', extract: s => s.power_energy?.current_avg_a, digits: 4 },
    // Data Plane
    { cat: 'Transport', metric: 'Goodput (Mbps)', extract: s => s.data_plane?.goodput_mbps, digits: 3, inverted: true },
    { cat: 'Transport', metric: 'Throughput (Mbps)', extract: s => s.data_plane?.achieved_throughput_mbps, digits: 3, inverted: true },
    { cat: 'Transport', metric: 'Packets Sent', extract: s => s.data_plane?.packets_sent, digits: 0 },
    { cat: 'Transport', metric: 'Packets Received', extract: s => s.data_plane?.packets_received, digits: 0, inverted: true },
    { cat: 'Transport', metric: 'Packets Dropped', extract: s => s.data_plane?.packets_dropped, digits: 0 },
    { cat: 'Transport', metric: 'Packet Loss Ratio', extract: s => s.data_plane?.packet_loss_ratio, digits: 6 },
    { cat: 'Transport', metric: 'Delivery Ratio', extract: s => s.data_plane?.packet_delivery_ratio, digits: 6, inverted: true },
    { cat: 'Transport', metric: 'Replay Drops', extract: s => s.data_plane?.drop_replay, digits: 0 },
    { cat: 'Transport', metric: 'Auth Drops', extract: s => s.data_plane?.drop_auth, digits: 0 },
    // Latency
    { cat: 'Latency', metric: 'RTT Avg (ms)', extract: s => s.latency_jitter?.rtt_avg_ms },
    { cat: 'Latency', metric: 'RTT P95 (ms)', extract: s => s.latency_jitter?.rtt_p95_ms },
    { cat: 'Latency', metric: 'Jitter Avg (ms)', extract: s => s.latency_jitter?.jitter_avg_ms },
    { cat: 'Latency', metric: 'One-Way Avg (ms)', extract: s => s.latency_jitter?.one_way_latency_avg_ms },
    { cat: 'Latency', metric: 'One-Way P95 (ms)', extract: s => s.latency_jitter?.one_way_latency_p95_ms },
    // MAVLink
    { cat: 'MAVLink', metric: 'CRC Errors', extract: s => s.mavlink_integrity?.mavlink_packet_crc_error_count, digits: 0 },
    { cat: 'MAVLink', metric: 'Decode Errors', extract: s => s.mavlink_integrity?.mavlink_decode_error_count, digits: 0 },
    { cat: 'MAVLink', metric: 'Out of Order', extract: s => s.mavlink_integrity?.mavlink_out_of_order_count, digits: 0 },
    { cat: 'MAVLink', metric: 'Duplicates', extract: s => s.mavlink_integrity?.mavlink_duplicate_count, digits: 0 },
    // FC Telemetry
    { cat: 'FC Telem', metric: 'Battery Voltage (V)', extract: s => s.fc_telemetry?.fc_battery_voltage_v, digits: 2 },
    { cat: 'FC Telem', metric: 'Battery (%)', extract: s => s.fc_telemetry?.fc_battery_remaining_percent, digits: 1, inverted: true },
];

const BAR_CHART_METRICS: { key: string; label: string; extract: Extractor; digits: number }[] = [
    { key: 'hs', label: 'Handshake (ms)', extract: s => s.handshake?.handshake_total_duration_ms, digits: 2 },
    { key: 'cpu', label: 'Drone CPU Avg (%)', extract: s => s.system_drone?.cpu_usage_avg_percent, digits: 1 },
    { key: 'pwr', label: 'Power Avg (W)', extract: s => s.power_energy?.power_avg_w, digits: 3 },
    { key: 'nrg', label: 'Energy (J)', extract: s => s.power_energy?.energy_total_j, digits: 2 },
    { key: 'rtt', label: 'RTT Avg (ms)', extract: s => s.latency_jitter?.rtt_avg_ms, digits: 2 },
    { key: 'gput', label: 'Goodput (Mbps)', extract: s => s.data_plane?.goodput_mbps, digits: 3 },
    { key: 'ploss', label: 'Packet Loss', extract: s => s.data_plane?.packet_loss_ratio, digits: 6 },
    { key: 'jitter', label: 'Jitter (ms)', extract: s => s.latency_jitter?.jitter_avg_ms, digits: 2 },
    { key: 'temp', label: 'Temperature (°C)', extract: s => s.system_drone?.temperature_c, digits: 1 },
    { key: 'mem', label: 'Memory RSS (MB)', extract: s => s.system_drone?.memory_rss_mb, digits: 1 },
];

const CATEGORIES = [...new Set(ALL_METRIC_ROWS.map(r => r.cat))];

export default function MultiRunComparison() {
    const {
        suites, fetchSuites, multiRunCompare, fetchMultiRunCompare, fetchSettings,
    } = useDashboardStore();

    const [selectedSuiteId, setSelectedSuiteId] = useState<string>('');
    const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set(CATEGORIES));

    useEffect(() => { fetchSuites(); fetchSettings(); }, [fetchSuites, fetchSettings]);

    const uniqueSuiteIds = useMemo(() => [...new Set(suites.map(s => s.suite_id))].sort(), [suites]);

    useEffect(() => {
        if (uniqueSuiteIds.length > 0 && !selectedSuiteId) {
            setSelectedSuiteId(uniqueSuiteIds[0]);
        }
    }, [uniqueSuiteIds, selectedSuiteId]);

    useEffect(() => {
        if (selectedSuiteId) fetchMultiRunCompare(selectedSuiteId);
    }, [selectedSuiteId, fetchMultiRunCompare]);

    const runs = multiRunCompare?.runs || [];

    const barData = useMemo(() => BAR_CHART_METRICS.map(m => {
        const row: Record<string, unknown> = { metric: m.label };
        runs.forEach(r => { row[r.run_type] = m.extract(r.suite); });
        return row;
    }), [runs]);

    // Radar data (normalized to 0-100)
    const radarData = useMemo(() => {
        const radarMetrics = [
            { key: 'Handshake', extract: (s: unknown) => (s as Record<string, unknown> & { handshake?: { handshake_total_duration_ms?: number } }).handshake?.handshake_total_duration_ms ?? 0, max: 50000 },
            { key: 'Power', extract: (s: unknown) => (s as Record<string, unknown> & { power_energy?: { power_avg_w?: number } }).power_energy?.power_avg_w ?? 0, max: 10 },
            { key: 'Energy', extract: (s: unknown) => (s as Record<string, unknown> & { power_energy?: { energy_total_j?: number } }).power_energy?.energy_total_j ?? 0, max: 200 },
            { key: 'CPU', extract: (s: unknown) => (s as Record<string, unknown> & { system_drone?: { cpu_usage_avg_percent?: number } }).system_drone?.cpu_usage_avg_percent ?? 0, max: 100 },
            { key: 'Memory', extract: (s: unknown) => (s as Record<string, unknown> & { system_drone?: { memory_rss_mb?: number } }).system_drone?.memory_rss_mb ?? 0, max: 500 },
            { key: 'RTT', extract: (s: unknown) => (s as Record<string, unknown> & { latency_jitter?: { rtt_avg_ms?: number } }).latency_jitter?.rtt_avg_ms ?? 0, max: 100 },
            { key: 'Jitter', extract: (s: unknown) => (s as Record<string, unknown> & { latency_jitter?: { jitter_avg_ms?: number } }).latency_jitter?.jitter_avg_ms ?? 0, max: 50 },
            { key: 'PktLoss', extract: (s: unknown) => ((s as Record<string, unknown> & { data_plane?: { packet_loss_ratio?: number } }).data_plane?.packet_loss_ratio ?? 0) * 10000, max: 100 },
        ];
        return radarMetrics.map(m => {
            const row: Record<string, unknown> = { metric: m.key };
            runs.forEach(r => {
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const raw = m.extract(r.suite as any);
                row[r.run_type] = Math.min((raw / m.max) * 100, 100);
            });
            return row;
        });
    }, [runs]);

    const toggleCat = (cat: string) => {
        setExpandedCats(prev => {
            const next = new Set(prev);
            if (next.has(cat)) next.delete(cat); else next.add(cat);
            return next;
        });
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-white">🔀 Multi-Run Comparison</h1>
                    <p className="text-gray-400 text-sm mt-1">Same suite across different threat scenarios — 42 metrics, raw critical data</p>
                </div>
                <select
                    value={selectedSuiteId}
                    onChange={e => setSelectedSuiteId(e.target.value)}
                    className="select-input w-80"
                >
                    <option value="">Select Suite…</option>
                    {uniqueSuiteIds.map(id => (
                        <option key={id} value={id}>{id}</option>
                    ))}
                </select>
            </div>

            {runs.length === 0 ? (
                <div className="card text-center py-12 text-gray-500">
                    <p className="text-lg mb-2">No comparison data available</p>
                    <p className="text-sm">Configure active runs in Settings, then select a suite above.</p>
                </div>
            ) : (
                <>
                    {/* ── Run Summary Cards ── */}
                    <div className="grid grid-cols-3 gap-4">
                        {runs.map(r => {
                            const color = RUN_TYPE_COLORS[r.run_type as RunType] || '#888';
                            const s = r.suite;
                            return (
                                <div key={r.run_id} className="card" style={{ borderTop: `3px solid ${color}` }}>
                                    <div className="flex items-center gap-2 mb-3">
                                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
                                        <span className="text-white font-medium">{r.label}</span>
                                        <span className="badge-blue text-xs">{RUN_TYPE_LABELS[r.run_type as RunType]}</span>
                                    </div>
                                    <div className="grid grid-cols-2 gap-1.5 text-sm">
                                        <div className="text-gray-400">Handshake</div>
                                        <div className="text-white font-mono">{fmt(s.handshake?.handshake_total_duration_ms)} ms</div>
                                        <div className="text-gray-400">CPU Avg</div>
                                        <div className="text-white font-mono">{fmt(s.system_drone?.cpu_usage_avg_percent, 1)}%</div>
                                        <div className="text-gray-400">Power</div>
                                        <div className="text-white font-mono">{fmt(s.power_energy?.power_avg_w, 3)} W</div>
                                        <div className="text-gray-400">Energy</div>
                                        <div className="text-white font-mono">{fmt(s.power_energy?.energy_total_j, 2)} J</div>
                                        <div className="text-gray-400">Temp</div>
                                        <div className="text-white font-mono">{fmt(s.system_drone?.temperature_c, 1)}°C</div>
                                        <div className="text-gray-400">RTT</div>
                                        <div className="text-white font-mono">{fmt(s.latency_jitter?.rtt_avg_ms)} ms</div>
                                        <div className="text-gray-400">Goodput</div>
                                        <div className="text-white font-mono">{fmt(s.data_plane?.goodput_mbps, 3)} Mbps</div>
                                        <div className="text-gray-400">Pkt Loss</div>
                                        <div className="text-white font-mono">{fmt(s.data_plane?.packet_loss_ratio, 6)}</div>
                                        <div className="text-gray-400">Status</div>
                                        <div className={`font-mono font-bold ${s.validation?.benchmark_pass_fail === 'PASS' ? 'text-green-400' : 'text-red-400'}`}>
                                            {s.validation?.benchmark_pass_fail || '—'}
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>

                    {/* ── Per-Metric Bar Charts (10 key metrics) ── */}
                    <div className="card">
                        <h2 className="text-lg font-semibold text-white mb-4">📊 Per-Metric Comparison (3 scenarios)</h2>
                        <div className="grid grid-cols-2 gap-6">
                            {BAR_CHART_METRICS.map((m, idx) => {
                                const singleData = [barData[idx]];
                                return (
                                    <div key={m.key}>
                                        <h3 className="text-sm text-gray-400 mb-2">{m.label}</h3>
                                        <ResponsiveContainer width="100%" height={100}>
                                            <BarChart data={singleData} layout="vertical">
                                                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                                <XAxis type="number" tick={{ fill: '#9ca3af', fontSize: 10 }} />
                                                <YAxis type="category" dataKey="metric" hide />
                                                <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                                                    formatter={(v: number) => v != null ? v.toFixed(m.digits) : '—'} />
                                                {['no_ddos', 'ddos_xgboost', 'ddos_txt'].map(rt => (
                                                    <Bar key={rt} dataKey={rt} fill={RUN_TYPE_COLORS[rt as RunType]}
                                                        name={RUN_TYPE_LABELS[rt as RunType]} barSize={16} />
                                                ))}
                                            </BarChart>
                                        </ResponsiveContainer>
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {/* ── Radar ── */}
                    {runs.length >= 2 && (
                        <div className="card">
                            <h2 className="text-lg font-semibold text-white mb-4">🕸️ Radar Footprint (Normalized 0–100)</h2>
                            <ResponsiveContainer width="100%" height={380}>
                                <RadarChart data={radarData}>
                                    <PolarGrid stroke="#374151" />
                                    <PolarAngleAxis dataKey="metric" tick={{ fill: '#d1d5db', fontSize: 11 }} />
                                    <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: '#6b7280', fontSize: 10 }} />
                                    {['no_ddos', 'ddos_xgboost', 'ddos_txt'].filter(rt => runs.some(r => r.run_type === rt)).map(rt => (
                                        <Radar key={rt} name={RUN_TYPE_LABELS[rt as RunType]} dataKey={rt}
                                            stroke={RUN_TYPE_COLORS[rt as RunType]} fill={RUN_TYPE_COLORS[rt as RunType]}
                                            fillOpacity={0.15} strokeWidth={2} />
                                    ))}
                                    <Legend />
                                    <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                                        formatter={(v: number) => `${v?.toFixed(1)}%`} />
                                </RadarChart>
                            </ResponsiveContainer>
                        </div>
                    )}

                    {/* ── Full Detail Table (Collapsible by Category) ── */}
                    <div className="card">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-semibold text-white">📋 Complete Metric Table ({ALL_METRIC_ROWS.length} metrics)</h2>
                            <div className="flex gap-2">
                                <button onClick={() => setExpandedCats(new Set(CATEGORIES))}
                                    className="text-xs px-2 py-1 bg-gray-700 text-gray-300 rounded hover:bg-gray-600">Expand All</button>
                                <button onClick={() => setExpandedCats(new Set())}
                                    className="text-xs px-2 py-1 bg-gray-700 text-gray-300 rounded hover:bg-gray-600">Collapse All</button>
                            </div>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="data-table w-full text-sm">
                                <thead>
                                    <tr>
                                        <th className="text-left w-32">Category</th>
                                        <th className="text-left">Metric</th>
                                        {runs.map(r => (
                                            <th key={r.run_id} className="text-right">
                                                <span style={{ color: RUN_TYPE_COLORS[r.run_type as RunType] }}>{r.label}</span>
                                            </th>
                                        ))}
                                        <th className="text-right">Δ (range)</th>
                                        <th className="text-right">Δ%</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {CATEGORIES.map(cat => {
                                        const rows = ALL_METRIC_ROWS.filter(r => r.cat === cat);
                                        const isExpanded = expandedCats.has(cat);
                                        return [
                                            <tr key={`cat-${cat}`}
                                                className="cursor-pointer hover:bg-gray-700/30 border-t-2 border-gray-700"
                                                onClick={() => toggleCat(cat)}>
                                                <td colSpan={runs.length + 4}
                                                    className="py-2 px-2 text-gray-300 font-semibold text-xs uppercase tracking-wide">
                                                    {isExpanded ? '▼' : '▶'} {cat} ({rows.length} metrics)
                                                </td>
                                            </tr>,
                                            ...(isExpanded ? rows.map((row, i) => {
                                                const values = runs.map(r => row.extract(r.suite));
                                                const numValues = values.filter((v): v is number => v != null && !isNaN(v));
                                                const delta = numValues.length >= 2 ? Math.max(...numValues) - Math.min(...numValues) : null;
                                                const dPct = deltaPctStr(values);
                                                const dColor = deltaPctColor(values, row.inverted);
                                                const digits = row.digits ?? 2;
                                                return (
                                                    <tr key={`${cat}-${i}`} className="hover:bg-gray-800/40">
                                                        <td className="text-gray-600 text-xs pl-6">{cat}</td>
                                                        <td className="text-gray-300">{row.metric}</td>
                                                        {values.map((v, j) => (
                                                            <td key={j} className="text-right font-mono text-white">
                                                                {v != null ? (typeof v === 'number' ? fmt(v, digits) : String(v)) : '—'}
                                                            </td>
                                                        ))}
                                                        <td className={`text-right font-mono ${delta && delta > 0 ? 'text-yellow-400' : 'text-gray-600'}`}>
                                                            {delta != null ? `±${fmt(delta, digits)}` : '—'}
                                                        </td>
                                                        <td className={`text-right font-mono font-semibold ${dColor}`}>
                                                            {dPct}
                                                        </td>
                                                    </tr>
                                                );
                                            }) : []),
                                        ];
                                    }).flat()}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}
