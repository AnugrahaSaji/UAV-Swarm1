/**
 * Latency & Transport Analysis — Handshake timing, RTT, jitter, one-way latency,
 * goodput, and packet delivery metrics from the /api/latency-summary endpoint.
 */

import { useEffect, useState } from 'react';
import { useDashboardStore } from '../state/store';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
    ScatterChart, Scatter, ZAxis, Legend,
} from 'recharts';

interface LatencySuite {
    suite_id: string;
    run_id: string;
    key: string;
    kem_algorithm: string | null;
    sig_algorithm: string | null;
    aead_algorithm: string | null;
    suite_security_level: string | null;
    kem_family: string | null;
    handshake_total_duration_ms: number | null;
    handshake_success: boolean | null;
    protocol_handshake_duration_ms: number | null;
    end_to_end_handshake_duration_ms: number | null;
    rtt_avg_ms: number | null;
    rtt_p95_ms: number | null;
    rtt_sample_count: number | null;
    rtt_valid: boolean | null;
    one_way_latency_avg_ms: number | null;
    one_way_latency_p95_ms: number | null;
    one_way_latency_valid: boolean | null;
    jitter_avg_ms: number | null;
    jitter_p95_ms: number | null;
    latency_sample_count: number | null;
    goodput_mbps: number | null;
    achieved_throughput_mbps: number | null;
    packets_sent: number | null;
    packets_received: number | null;
    packets_dropped: number | null;
    packet_loss_ratio: number | null;
    packet_delivery_ratio: number | null;
    power_avg_w: number | null;
    energy_total_j: number | null;
    benchmark_pass_fail: string | null;
}

function fmt(v: number | null | undefined, digits = 2): string {
    if (v == null || isNaN(v)) return '—';
    return v.toFixed(digits);
}

const NIST_COLORS: Record<string, string> = {
    L1: '#3b82f6',
    L3: '#8b5cf6',
    L5: '#ef4444',
};

export default function LatencyAnalysis() {
    const { selectedRunId } = useDashboardStore();
    const [suites, setSuites] = useState<LatencySuite[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        setLoading(true);
        setError(null);
        const url = selectedRunId
            ? `/api/latency-summary?run_id=${encodeURIComponent(selectedRunId)}`
            : '/api/latency-summary';
        fetch(url)
            .then(res => {
                if (!res.ok) throw new Error(`API error: ${res.status}`);
                return res.json();
            })
            .then(data => {
                setSuites(data.suites || []);
                setLoading(false);
            })
            .catch(err => {
                setError(err.message);
                setLoading(false);
            });
    }, [selectedRunId]);

    // ── KPI calculations ────────────────────────────────────────────────────
    const rttValues = suites.filter(s => s.rtt_avg_ms != null).map(s => s.rtt_avg_ms!);
    const jitterValues = suites.filter(s => s.jitter_avg_ms != null).map(s => s.jitter_avg_ms!);
    const owlValues = suites.filter(s => s.one_way_latency_avg_ms != null).map(s => s.one_way_latency_avg_ms!);
    const handshakeValues = suites.filter(s => s.handshake_total_duration_ms != null).map(s => s.handshake_total_duration_ms!);
    const goodputValues = suites.filter(s => s.goodput_mbps != null).map(s => s.goodput_mbps!);
    const lossValues = suites.filter(s => s.packet_loss_ratio != null).map(s => s.packet_loss_ratio!);

    const avg = (arr: number[]) => arr.length > 0 ? arr.reduce((a, b) => a + b, 0) / arr.length : null;
    const p95 = (arr: number[]) => {
        if (arr.length === 0) return null;
        const sorted = [...arr].sort((a, b) => a - b);
        return sorted[Math.min(Math.floor(sorted.length * 0.95), sorted.length - 1)];
    };

    // ── Group by KEM family ─────────────────────────────────────────────────
    const kemFamilies: Record<string, { handshake: number[]; rtt: number[]; jitter: number[]; name: string }> = {};
    suites.forEach(s => {
        const family = s.kem_family || 'Other';
        if (!kemFamilies[family]) kemFamilies[family] = { handshake: [], rtt: [], jitter: [], name: family };
        if (s.handshake_total_duration_ms != null) kemFamilies[family].handshake.push(s.handshake_total_duration_ms);
        if (s.rtt_avg_ms != null) kemFamilies[family].rtt.push(s.rtt_avg_ms);
        if (s.jitter_avg_ms != null) kemFamilies[family].jitter.push(s.jitter_avg_ms);
    });

    const kemBarData = Object.values(kemFamilies)
        .filter(f => f.handshake.length > 0)
        .map(f => ({
            family: f.name,
            avg_handshake: avg(f.handshake),
            avg_rtt: avg(f.rtt),
            avg_jitter: avg(f.jitter),
            count: f.handshake.length,
        }))
        .sort((a, b) => (a.avg_handshake ?? 0) - (b.avg_handshake ?? 0));

    // ── Group by NIST level ─────────────────────────────────────────────────
    const nistGroups: Record<string, { hs: number[]; rtt: number[]; jitter: number[] }> = {};
    suites.forEach(s => {
        const nist = s.suite_security_level || 'Unknown';
        if (!nistGroups[nist]) nistGroups[nist] = { hs: [], rtt: [], jitter: [] };
        if (s.handshake_total_duration_ms != null) nistGroups[nist].hs.push(s.handshake_total_duration_ms);
        if (s.rtt_avg_ms != null) nistGroups[nist].rtt.push(s.rtt_avg_ms);
        if (s.jitter_avg_ms != null) nistGroups[nist].jitter.push(s.jitter_avg_ms);
    });
    const nistBarData = Object.entries(nistGroups)
        .filter(([_, v]) => v.hs.length > 0)
        .map(([level, v]) => ({
            level,
            avg_hs: avg(v.hs),
            p95_hs: p95(v.hs),
            avg_rtt: avg(v.rtt),
            avg_jitter: avg(v.jitter),
            count: v.hs.length,
        }))
        .sort((a, b) => {
            const order: Record<string, number> = { L1: 1, L3: 2, L5: 3 };
            return (order[a.level] || 99) - (order[b.level] || 99);
        });

    // ── Scatter: handshake vs RTT colored by NIST level ─────────────────────
    const scatterData = suites
        .filter(s => s.handshake_total_duration_ms != null)
        .map(s => ({
            handshake_ms: s.handshake_total_duration_ms,
            rtt_ms: s.rtt_avg_ms,
            suite_id: s.suite_id,
            nist: s.suite_security_level || 'Unknown',
            kem_algorithm: s.kem_algorithm || '',
            power: s.power_avg_w,
        }));

    // ── Transport table data ────────────────────────────────────────────────
    const transportData = suites
        .filter(s => s.handshake_total_duration_ms != null)
        .sort((a, b) => (b.handshake_total_duration_ms || 0) - (a.handshake_total_duration_ms || 0))
        .slice(0, 20);

    if (loading) return <div className="text-gray-400 p-8">Loading latency data...</div>;
    if (error) return <div className="text-red-400 p-8">Error: {error}</div>;

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-white">⏱️ Latency & Transport Analysis</h1>
                <p className="text-gray-400 text-sm mt-1">
                    Handshake timing, RTT, jitter, one-way latency, goodput, and packet delivery — raw data, no smoothing
                </p>
            </div>

            {/* ── KPI Row ── */}
            <div className="grid grid-cols-6 gap-4">
                <div className="card">
                    <div className="text-xs text-gray-400 uppercase tracking-wider">Avg RTT</div>
                    <div className="text-2xl font-bold text-blue-400 mt-1">{fmt(avg(rttValues))} ms</div>
                    <div className="text-xs text-gray-500 mt-1">P95: {fmt(p95(rttValues))} ms • {rttValues.length} suites</div>
                </div>
                <div className="card">
                    <div className="text-xs text-gray-400 uppercase tracking-wider">Avg Jitter</div>
                    <div className="text-2xl font-bold text-purple-400 mt-1">{fmt(avg(jitterValues))} ms</div>
                    <div className="text-xs text-gray-500 mt-1">P95: {fmt(p95(jitterValues))} ms</div>
                </div>
                <div className="card">
                    <div className="text-xs text-gray-400 uppercase tracking-wider">One-Way Latency</div>
                    <div className="text-2xl font-bold text-cyan-400 mt-1">{fmt(avg(owlValues))} ms</div>
                    <div className="text-xs text-gray-500 mt-1">P95: {fmt(p95(owlValues))} ms • {owlValues.length} suites</div>
                </div>
                <div className="card">
                    <div className="text-xs text-gray-400 uppercase tracking-wider">Avg Handshake</div>
                    <div className="text-2xl font-bold text-yellow-400 mt-1">{fmt(avg(handshakeValues))} ms</div>
                    <div className="text-xs text-gray-500 mt-1">P95: {fmt(p95(handshakeValues))} ms</div>
                </div>
                <div className="card">
                    <div className="text-xs text-gray-400 uppercase tracking-wider">Avg Goodput</div>
                    <div className="text-2xl font-bold text-green-400 mt-1">{fmt(avg(goodputValues), 3)} Mbps</div>
                    <div className="text-xs text-gray-500 mt-1">{goodputValues.length} suites with data</div>
                </div>
                <div className="card">
                    <div className="text-xs text-gray-400 uppercase tracking-wider">Avg Packet Loss</div>
                    <div className="text-2xl font-bold text-red-400 mt-1">
                        {avg(lossValues) != null ? `${fmt(avg(lossValues)! * 100, 4)}%` : '—'}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">{lossValues.length} suites with data</div>
                </div>
            </div>

            {/* ── NIST Level KPIs ── */}
            <div className="grid grid-cols-3 gap-4">
                {nistBarData.map(n => (
                    <div key={n.level} className="card" style={{ borderLeft: `4px solid ${NIST_COLORS[n.level] || '#6b7280'}` }}>
                        <div className="text-xs text-gray-400 uppercase tracking-wider">NIST {n.level} ({n.count} suites)</div>
                        <div className="text-lg font-bold text-white mt-1">HS: {fmt(n.avg_hs)} ms</div>
                        <div className="text-sm text-gray-300">
                            RTT: {fmt(n.avg_rtt)} ms • Jitter: {fmt(n.avg_jitter)} ms • HS P95: {fmt(n.p95_hs)} ms
                        </div>
                    </div>
                ))}
            </div>

            <div className="grid grid-cols-2 gap-6">
                {/* ── Handshake by KEM Family ── */}
                <div className="card">
                    <h2 className="text-lg font-semibold text-white mb-4">🔑 Handshake & RTT by KEM Family</h2>
                    <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={kemBarData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis dataKey="family" tick={{ fill: '#d1d5db', fontSize: 11 }} />
                            <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} label={{ value: 'ms', angle: -90, position: 'insideLeft', fill: '#6b7280' }} />
                            <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                                formatter={(v: number) => `${fmt(v)} ms`} />
                            <Legend />
                            <Bar dataKey="avg_handshake" fill="#f59e0b" name="Handshake" radius={[4, 4, 0, 0]} />
                            <Bar dataKey="avg_rtt" fill="#3b82f6" name="RTT" radius={[4, 4, 0, 0]} />
                            <Bar dataKey="avg_jitter" fill="#8b5cf6" name="Jitter" radius={[4, 4, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>

                {/* ── Handshake by NIST Level ── */}
                <div className="card">
                    <h2 className="text-lg font-semibold text-white mb-4">🏛️ Handshake by NIST Level</h2>
                    <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={nistBarData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis dataKey="level" tick={{ fill: '#d1d5db', fontSize: 12 }} />
                            <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} label={{ value: 'ms', angle: -90, position: 'insideLeft', fill: '#6b7280' }} />
                            <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                                formatter={(v: number) => `${fmt(v)} ms`} />
                            <Legend />
                            <Bar dataKey="avg_hs" fill="#f59e0b" name="Avg Handshake" radius={[4, 4, 0, 0]} />
                            <Bar dataKey="p95_hs" fill="#ef4444" name="P95 Handshake" radius={[4, 4, 0, 0]} />
                            <Bar dataKey="avg_rtt" fill="#3b82f6" name="Avg RTT" radius={[4, 4, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* ── Scatter: Handshake vs RTT ── */}
            <div className="card">
                <h2 className="text-lg font-semibold text-white mb-4">🎯 Handshake vs RTT (by NIST Level)</h2>
                <ResponsiveContainer width="100%" height={350}>
                    <ScatterChart>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis type="number" dataKey="handshake_ms" name="Handshake (ms)" tick={{ fill: '#9ca3af', fontSize: 11 }}
                            label={{ value: 'Handshake (ms)', position: 'insideBottom', fill: '#6b7280', offset: -5 }} />
                        <YAxis type="number" dataKey="rtt_ms" name="RTT (ms)" tick={{ fill: '#9ca3af', fontSize: 11 }}
                            label={{ value: 'RTT (ms)', angle: -90, position: 'insideLeft', fill: '#6b7280' }} />
                        <ZAxis type="number" dataKey="power" range={[20, 200]} name="Power (W)" />
                        <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                            formatter={(v: number | string, name: string) => [typeof v === 'number' ? fmt(v as number, 3) : v, name]}
                            labelFormatter={(_: unknown, payload?: Array<{ payload?: LatencySuite }>) => {
                                const pt = payload?.[0]?.payload;
                                return pt ? `${pt.suite_id} (${pt.kem_algorithm || ''})` : '';
                            }} />
                        <Legend />
                        {Object.entries(NIST_COLORS).map(([level, color]) => {
                            const pts = scatterData.filter(p => p.nist === level);
                            return pts.length > 0 ? (
                                <Scatter key={level} name={`NIST ${level}`} data={pts} fill={color} />
                            ) : null;
                        })}
                        {(() => {
                            const other = scatterData.filter(p => !NIST_COLORS[p.nist]);
                            return other.length > 0 ? <Scatter key="other" name="Other" data={other} fill="#6b7280" /> : null;
                        })()}
                    </ScatterChart>
                </ResponsiveContainer>
            </div>

            {/* ── Detailed Table ── */}
            <div className="card">
                <h2 className="text-lg font-semibold text-white mb-4">📊 Top 20 Suites — Full Latency & Transport Detail</h2>
                <div className="overflow-x-auto">
                    <table className="data-table w-full">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Suite ID</th>
                                <th>KEM</th>
                                <th>NIST</th>
                                <th className="text-right">Handshake (ms)</th>
                                <th className="text-right">RTT Avg (ms)</th>
                                <th className="text-right">RTT P95 (ms)</th>
                                <th className="text-right">Jitter (ms)</th>
                                <th className="text-right">OWL (ms)</th>
                                <th className="text-right">Goodput (Mbps)</th>
                                <th className="text-right">Loss %</th>
                                <th className="text-right">Power (W)</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {transportData.map((s, i) => (
                                <tr key={s.key || i}>
                                    <td className="text-gray-500">{i + 1}</td>
                                    <td className="font-mono text-sm text-white">{s.suite_id}</td>
                                    <td className="text-gray-300 text-xs">{s.kem_algorithm || '—'}</td>
                                    <td>
                                        <span className="px-1.5 py-0.5 rounded text-xs font-medium"
                                            style={{
                                                color: NIST_COLORS[s.suite_security_level ?? ''] || '#9ca3af',
                                                backgroundColor: (NIST_COLORS[s.suite_security_level ?? ''] || '#9ca3af') + '22'
                                            }}>
                                            {s.suite_security_level || '?'}
                                        </span>
                                    </td>
                                    <td className="text-right font-mono text-yellow-400">{fmt(s.handshake_total_duration_ms)}</td>
                                    <td className="text-right font-mono text-blue-400">{fmt(s.rtt_avg_ms)}</td>
                                    <td className="text-right font-mono text-blue-300">{fmt(s.rtt_p95_ms)}</td>
                                    <td className="text-right font-mono text-purple-400">{fmt(s.jitter_avg_ms)}</td>
                                    <td className="text-right font-mono text-cyan-400">{fmt(s.one_way_latency_avg_ms)}</td>
                                    <td className="text-right font-mono text-green-400">{fmt(s.goodput_mbps, 3)}</td>
                                    <td className="text-right font-mono text-red-400">
                                        {s.packet_loss_ratio != null ? fmt(s.packet_loss_ratio * 100, 4) + '%' : '—'}
                                    </td>
                                    <td className="text-right font-mono text-white">{fmt(s.power_avg_w, 3)}</td>
                                    <td>
                                        <span className={`badge-${s.benchmark_pass_fail === 'PASS' ? 'green' : s.benchmark_pass_fail === 'FAIL' ? 'red' : 'gray'}`}>
                                            {s.benchmark_pass_fail || '?'}
                                        </span>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
