/**
 * Overview Page v4 — Executive Dashboard with deep KPIs, distribution charts,
 * top/bottom rankings, scenario status, and aggressive visual analytics.
 */

import { useEffect, useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useDashboardStore } from '../state/store';
import { RUN_TYPE_COLORS, RUN_TYPE_LABELS, type RunType } from '../types/metrics';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Cell,
    PieChart, Pie, ScatterChart, Scatter, ZAxis,
} from 'recharts';

type HealthResponse = { status: string; suites_loaded: number; runs_loaded: number };
type AggregateRow = Record<string, string | number>;

function fmt(v: number | null | undefined, digits = 2): string {
    if (v == null || isNaN(v)) return '—';
    return v.toFixed(digits);
}

function percentile(arr: number[], p: number): number {
    const sorted = [...arr].sort((a, b) => a - b);
    const i = Math.max(0, Math.ceil(sorted.length * p) - 1);
    return sorted[Math.min(i, sorted.length - 1)] ?? 0;
}

function stdDev(arr: number[]): number {
    if (arr.length < 2) return 0;
    const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
    return Math.sqrt(arr.reduce((s, v) => s + (v - mean) ** 2, 0) / (arr.length - 1));
}

const NIST_COLORS: Record<string, string> = { L1: '#3b82f6', L3: '#8b5cf6', L5: '#ef4444', Unknown: '#6b7280' };
const KEM_COLORS: Record<string, string> = { 'ML-KEM': '#3b82f6', 'HQC': '#10b981', 'ClassicMcEliece': '#f59e0b', Other: '#6b7280' };
const SIG_COLORS: Record<string, string> = { 'ML-DSA': '#8b5cf6', 'Falcon': '#ec4899', 'SPHINCS+': '#f97316', Other: '#6b7280' };

export default function Overview() {
    const {
        runs, suites, isLoading, fetchSuites, fetchRuns, clearFilters,
        multiRunOverview, fetchMultiRunOverview, anomalies, fetchAnomalies, fetchSettings, settings,
    } = useDashboardStore();
    const [health, setHealth] = useState<HealthResponse | null>(null);
    const [kemFamilyData, setKemFamilyData] = useState<AggregateRow[]>([]);
    const [aggWarning, setAggWarning] = useState<string | null>(null);

    useEffect(() => {
        clearFilters();
        fetchSuites();
        fetchRuns();
        fetchSettings();
        fetchMultiRunOverview();
        fetchAnomalies();
        fetch('/api/health')
            .then(res => { if (!res.ok) throw new Error(`${res.status}`); return res.json(); })
            .then(setHealth)
            .catch(() => setHealth(null));
        fetch('/api/aggregate/kem-family')
            .then(res => { if (!res.ok) throw new Error(`${res.status}`); return res.json(); })
            .then(payload => {
                if (payload?.warning) { setAggWarning(payload.warning); setKemFamilyData([]); }
                else { setAggWarning(null); setKemFamilyData(payload?.data ?? []); }
            })
            .catch(() => { setAggWarning('Aggregation unavailable'); setKemFamilyData([]); });
    }, [fetchSuites, fetchRuns, clearFilters, fetchMultiRunOverview, fetchSettings, fetchAnomalies]);

    // ── Computed stats ──────────────────────────────────────────────────────
    const stats = useMemo(() => {
        if (!suites.length) return null;
        const total = suites.length;
        const passed = suites.filter(s => s.benchmark_pass_fail === 'PASS').length;
        const failed = suites.filter(s => s.benchmark_pass_fail === 'FAIL').length;
        const passRate = (passed / total) * 100;

        const hs = suites.map(s => s.handshake_total_duration_ms).filter((v): v is number => v != null);
        const pw = suites.map(s => s.power_avg_w).filter((v): v is number => v != null);
        const en = suites.map(s => s.energy_total_j).filter((v): v is number => v != null);
        const loss: number[] = [];
        const goodput: number[] = [];

        const avgHs = hs.length ? hs.reduce((a, b) => a + b, 0) / hs.length : 0;
        const avgPw = pw.length ? pw.reduce((a, b) => a + b, 0) / pw.length : 0;
        const totalEn = en.length ? en.reduce((a, b) => a + b, 0) : 0;
        const avgEn = en.length ? totalEn / en.length : 0;
        const avgLoss = loss.length ? loss.reduce((a, b) => a + b, 0) / loss.length : 0;
        const avgGoodput = goodput.length ? goodput.reduce((a, b) => a + b, 0) / goodput.length : 0;

        // Best & worst suites
        const sortedByHs = [...suites].filter(s => s.handshake_total_duration_ms != null)
            .sort((a, b) => (a.handshake_total_duration_ms ?? 0) - (b.handshake_total_duration_ms ?? 0));
        const fastest = sortedByHs[0];
        const slowest = sortedByHs[sortedByHs.length - 1];

        // NIST distribution
        const nistDist: Record<string, number> = {};
        suites.forEach(s => {
            const n = s.suite_security_level || 'Unknown';
            nistDist[n] = (nistDist[n] || 0) + 1;
        });

        // KEM family distribution
        const kemDist: Record<string, number> = {};
        suites.forEach(s => {
            const kem = s.kem_algorithm || '';
            const family = kem.includes('ML-KEM') || kem.includes('mlkem') ? 'ML-KEM'
                : kem.includes('HQC') || kem.includes('hqc') ? 'HQC'
                : kem.includes('McEliece') || kem.includes('mceliece') ? 'ClassicMcEliece'
                : 'Other';
            kemDist[family] = (kemDist[family] || 0) + 1;
        });

        // SIG family distribution
        const sigDist: Record<string, number> = {};
        suites.forEach(s => {
            const sig = s.sig_algorithm || '';
            const family = sig.includes('ML-DSA') || sig.includes('mldsa') ? 'ML-DSA'
                : sig.includes('Falcon') || sig.includes('falcon') ? 'Falcon'
                : sig.includes('SPHINCS') || sig.includes('sphincs') ? 'SPHINCS+'
                : 'Other';
            sigDist[family] = (sigDist[family] || 0) + 1;
        });

        return {
            total, passed, failed, passRate,
            avgHs, p95Hs: hs.length ? percentile(hs, 0.95) : 0,
            maxHs: hs.length ? Math.max(...hs) : 0,
            minHs: hs.length ? Math.min(...hs) : 0,
            stdHs: stdDev(hs),
            avgPw, avgEn, totalEn, avgLoss, avgGoodput,
            fastest, slowest,
            nistDist, kemDist, sigDist,
        };
    }, [suites]);

    const criticalAnomalies = anomalies.filter(a => a.severity === 'critical').length;
    const warningAnomalies = anomalies.filter(a => a.severity === 'warning').length;

    // Scenario status from settings (typed via DashboardSettings → ScenarioStatus)
    const scenarioStatus = settings?.scenario_status;

    // Distribution pie data
    const nistPieData = stats ? Object.entries(stats.nistDist).map(([name, value]) => ({
        name, value, fill: NIST_COLORS[name] || '#6b7280'
    })) : [];
    const kemPieData = stats ? Object.entries(stats.kemDist).map(([name, value]) => ({
        name, value, fill: KEM_COLORS[name] || '#6b7280'
    })) : [];
    const sigPieData = stats ? Object.entries(stats.sigDist).map(([name, value]) => ({
        name, value, fill: SIG_COLORS[name] || '#6b7280'
    })) : [];

    // Scatter data: handshake vs energy colored by NIST level
    const scatterData = useMemo(() => {
        return suites
            .filter(s => s.handshake_total_duration_ms != null && s.energy_total_j != null)
            .map(s => ({
                handshake_ms: s.handshake_total_duration_ms,
                energy_j: s.energy_total_j,
                nist: s.suite_security_level || 'Unknown',
                suite_id: s.suite_id,
                kem: s.kem_algorithm,
            }));
    }, [suites]);

    if (isLoading && runs.length === 0) {
        return <div className="flex items-center justify-center h-64"><div className="text-gray-400">Loading dashboard…</div></div>;
    }

    return (
        <div className="space-y-6">
            {/* ── Header ── */}
            <div className="flex items-center justify-between">
                <h1 className="text-2xl font-bold text-white">🔬 PQC Benchmark Overview</h1>
                <div className="flex gap-2">
                    <Link to="/settings" className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm text-gray-300 transition-colors">⚙️ Settings</Link>
                    <Link to="/security" className="px-3 py-1.5 bg-red-900/30 hover:bg-red-900/50 border border-red-500/30 rounded text-sm text-red-400 transition-colors">
                        🚨 {criticalAnomalies} Critical
                    </Link>
                </div>
            </div>

            {/* ── Scenario Status Banner ── */}
            {scenarioStatus && (
                <div className="grid grid-cols-3 gap-4">
                    {Object.entries(scenarioStatus).map(([scenario, info]) => {
                        const label = scenario === 'no-ddos' ? '🛡️ No DDoS' : scenario === 'ddos-xgboost' ? '🤖 DDoS + XGBoost' : '📝 DDoS + TXT';
                        const color = scenario === 'no-ddos' ? '#10b981' : scenario === 'ddos-xgboost' ? '#f59e0b' : '#ef4444';
                        return (
                            <div key={scenario} className="card flex items-center gap-3" style={{ borderLeft: `4px solid ${color}` }}>
                                <div className={`w-3 h-3 rounded-full ${info.folder_exists ? 'animate-pulse' : ''}`}
                                     style={{ backgroundColor: info.folder_exists ? color : '#374151' }} />
                                <div>
                                    <div className="text-sm font-medium text-white">{label}</div>
                                    <div className="text-xs text-gray-400">
                                        {info.folder_exists
                                            ? `${info.run_count} run${info.run_count !== 1 ? 's' : ''} • ${info.suite_count} suites`
                                            : 'No data yet'}
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* ── Primary KPI Row ── */}
            <div className="grid grid-cols-5 gap-4">
                <div className="card border-l-4 border-l-blue-500">
                    <div className="text-xs text-gray-400 uppercase tracking-wider">Total Suites</div>
                    <div className="text-3xl font-bold text-blue-400">{health?.suites_loaded ?? '—'}</div>
                    <div className="text-xs text-gray-500 mt-1">{health?.runs_loaded ?? 0} run{(health?.runs_loaded ?? 0) !== 1 ? 's' : ''}</div>
                </div>
                <div className="card border-l-4 border-l-green-500">
                    <div className="text-xs text-gray-400 uppercase tracking-wider">Pass Rate</div>
                    <div className={`text-3xl font-bold ${(stats?.passRate ?? 0) >= 95 ? 'text-green-400' : (stats?.passRate ?? 0) >= 80 ? 'text-yellow-400' : 'text-red-400'}`}>
                        {stats ? `${stats.passRate.toFixed(1)}%` : '—'}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">{stats?.passed ?? 0} passed, {stats?.failed ?? 0} failed</div>
                </div>
                <div className="card border-l-4 border-l-cyan-500">
                    <div className="text-xs text-gray-400 uppercase tracking-wider">Avg Handshake</div>
                    <div className="text-3xl font-bold text-cyan-400">{fmt(stats?.avgHs)}<span className="text-sm text-gray-500"> ms</span></div>
                    <div className="text-xs text-gray-500 mt-1">P95: {fmt(stats?.p95Hs)} ms • σ: {fmt(stats?.stdHs)}</div>
                </div>
                <div className="card border-l-4 border-l-emerald-500">
                    <div className="text-xs text-gray-400 uppercase tracking-wider">Avg Power</div>
                    <div className="text-3xl font-bold text-emerald-400">{fmt(stats?.avgPw, 3)}<span className="text-sm text-gray-500"> W</span></div>
                    <div className="text-xs text-gray-500 mt-1">Energy avg: {fmt(stats?.avgEn, 2)} J</div>
                </div>
                <div className="card border-l-4 border-l-yellow-500">
                    <div className="text-xs text-gray-400 uppercase tracking-wider">Anomalies</div>
                    <div className="text-3xl font-bold text-yellow-400">{anomalies.length}</div>
                    <div className="text-xs text-gray-500 mt-1">
                        <span className="text-red-400">{criticalAnomalies} critical</span> • <span className="text-yellow-500">{warningAnomalies} warning</span>
                    </div>
                </div>
            </div>

            {/* ── Secondary KPI Row ── */}
            {stats && (
                <div className="grid grid-cols-4 gap-4">
                    <div className="card bg-gradient-to-br from-gray-800 to-gray-900">
                        <div className="text-xs text-gray-400 uppercase tracking-wider">🏆 Fastest Suite</div>
                        <div className="text-lg font-bold text-green-400 mt-1 truncate" title={stats.fastest?.suite_id}>
                            {stats.fastest?.suite_id?.replace(/^cs-/, '').substring(0, 35) || '—'}
                        </div>
                        <div className="text-sm text-gray-400 mt-0.5">{fmt(stats.fastest?.handshake_total_duration_ms)} ms</div>
                    </div>
                    <div className="card bg-gradient-to-br from-gray-800 to-gray-900">
                        <div className="text-xs text-gray-400 uppercase tracking-wider">🐌 Slowest Suite</div>
                        <div className="text-lg font-bold text-red-400 mt-1 truncate" title={stats.slowest?.suite_id}>
                            {stats.slowest?.suite_id?.replace(/^cs-/, '').substring(0, 35) || '—'}
                        </div>
                        <div className="text-sm text-gray-400 mt-0.5">{fmt(stats.slowest?.handshake_total_duration_ms)} ms</div>
                    </div>
                    <div className="card bg-gradient-to-br from-gray-800 to-gray-900">
                        <div className="text-xs text-gray-400 uppercase tracking-wider">📡 Avg Goodput</div>
                        <div className="text-2xl font-bold text-sky-400 mt-1">{fmt(stats.avgGoodput, 1)}<span className="text-sm text-gray-500"> Mbps</span></div>
                    </div>
                    <div className="card bg-gradient-to-br from-gray-800 to-gray-900">
                        <div className="text-xs text-gray-400 uppercase tracking-wider">🔋 Total Energy</div>
                        <div className="text-2xl font-bold text-amber-400 mt-1">{fmt(stats.totalEn, 1)}<span className="text-sm text-gray-500"> J</span></div>
                        <div className="text-xs text-gray-500 mt-0.5">across {stats.total} suites</div>
                    </div>
                </div>
            )}

            {/* ── Distribution Pie Charts ── */}
            {stats && (
                <div className="grid grid-cols-3 gap-6">
                    <div className="card">
                        <h3 className="card-header">🏛️ NIST Level Distribution</h3>
                        <div className="h-56 flex items-center justify-center">
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie data={nistPieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={3} dataKey="value" label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}>
                                        {nistPieData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                                    </Pie>
                                    <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }} />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                    <div className="card">
                        <h3 className="card-header">🔑 KEM Family Distribution</h3>
                        <div className="h-56 flex items-center justify-center">
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie data={kemPieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={3} dataKey="value" label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}>
                                        {kemPieData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                                    </Pie>
                                    <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }} />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                    <div className="card">
                        <h3 className="card-header">✍️ SIG Family Distribution</h3>
                        <div className="h-56 flex items-center justify-center">
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie data={sigPieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={3} dataKey="value" label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}>
                                        {sigPieData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                                    </Pie>
                                    <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }} />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Multi-Run Comparison Cards ── */}
            {multiRunOverview.length > 0 && (
                <div>
                    <h2 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                        <span>📊</span> Run Comparison
                    </h2>
                    <div className="grid grid-cols-3 gap-4">
                        {multiRunOverview.map(r => {
                            const color = RUN_TYPE_COLORS[r.run_type as RunType] || '#6b7280';
                            return (
                                <div key={r.run_id} className="card" style={{ borderTop: `3px solid ${color}` }}>
                                    <div className="flex items-center gap-2 mb-3">
                                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
                                        <span className="text-white font-medium">{r.label}</span>
                                        <span className="text-xs px-1.5 py-0.5 rounded" style={{ color, backgroundColor: color + '22' }}>
                                            {RUN_TYPE_LABELS[r.run_type as RunType] || r.run_type}
                                        </span>
                                    </div>
                                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                                        <span className="text-gray-400">Suites</span>
                                        <span className="text-white font-mono">{r.total_suites}</span>
                                        <span className="text-gray-400">Pass Rate</span>
                                        <span className={`font-mono font-bold ${r.pass_rate >= 95 ? 'text-green-400' : r.pass_rate >= 80 ? 'text-yellow-400' : 'text-red-400'}`}>{r.pass_rate}%</span>
                                        <span className="text-gray-400">Avg Handshake</span>
                                        <span className="text-white font-mono">{fmt(r.avg_handshake_ms)} ms</span>
                                        <span className="text-gray-400">Max Handshake</span>
                                        <span className="text-white font-mono">{fmt(r.max_handshake_ms)} ms</span>
                                        <span className="text-gray-400">Avg Power</span>
                                        <span className="text-white font-mono">{fmt(r.avg_power_w, 3)} W</span>
                                        <span className="text-gray-400">Total Energy</span>
                                        <span className="text-white font-mono">{fmt(r.total_energy_j, 2)} J</span>
                                        <span className="text-gray-400">Avg Pkt Loss</span>
                                        <span className="text-white font-mono">{fmt(r.avg_packet_loss, 6)}</span>
                                        <span className="text-gray-400">Anomalies</span>
                                        <span className={`font-mono font-bold ${r.anomaly_count > 0 ? 'text-red-400' : 'text-green-400'}`}>{r.anomaly_count}</span>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* ── Handshake vs Energy Scatter ── */}
            {scatterData.length > 0 && (
                <div className="card">
                    <h3 className="card-header">🎯 Handshake vs Energy Trade-off (All Suites)</h3>
                    <p className="text-xs text-gray-400 mb-3">Each dot is one cipher suite. Color = NIST security level. Trade-off: fast + low energy is ideal (bottom-left).</p>
                    <div className="h-80">
                        <ResponsiveContainer width="100%" height="100%">
                            <ScatterChart margin={{ top: 10, right: 30, bottom: 10, left: 10 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                <XAxis type="number" dataKey="handshake_ms" name="Handshake (ms)" tick={{ fill: '#9ca3af', fontSize: 11 }}
                                    label={{ value: 'Handshake (ms)', position: 'insideBottom', offset: -5, fill: '#6b7280' }} />
                                <YAxis type="number" dataKey="energy_j" name="Energy (J)" tick={{ fill: '#9ca3af', fontSize: 11 }}
                                    label={{ value: 'Energy (J)', angle: -90, position: 'insideLeft', fill: '#6b7280' }} />
                                <ZAxis range={[30, 30]} />
                                <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                                    formatter={(v: any, name: string) => [typeof v === 'number' ? fmt(v, 3) : v, name]}
                                    labelFormatter={() => ''} />
                                <Legend />
                                {Object.entries(NIST_COLORS).filter(([k]) => k !== 'Unknown').map(([level, color]) => {
                                    const pts = scatterData.filter(p => p.nist === level);
                                    return pts.length > 0 ? <Scatter key={level} name={`NIST ${level}`} data={pts} fill={color} /> : null;
                                })}
                                {(() => {
                                    const other = scatterData.filter(p => !['L1', 'L3', 'L5'].includes(p.nist));
                                    return other.length > 0 ? <Scatter name="Other" data={other} fill="#6b7280" /> : null;
                                })()}
                            </ScatterChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            )}

            {/* ── KEM Family Charts Row ── */}
            <div className="grid grid-cols-2 gap-6">
                <div className="card">
                    <h3 className="card-header">🔑 Avg Handshake by KEM Family</h3>
                    <div className="h-64">
                        {aggWarning ? <div className="text-gray-400 text-sm">{aggWarning}</div> : (
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={kemFamilyData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                    <XAxis dataKey="crypto_identity_kem_family" tick={{ fill: '#d1d5db', fontSize: 11 }} />
                                    <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} label={{ value: 'ms', angle: -90, position: 'insideLeft', fill: '#6b7280' }} />
                                    <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }} />
                                    <Legend />
                                    <Bar dataKey="handshake_handshake_total_duration_ms_mean" fill="#3b82f6" name="Avg (ms)" radius={[4, 4, 0, 0]} />
                                    <Bar dataKey="handshake_handshake_total_duration_ms_std" fill="#60a5fa" name="Std Dev" radius={[4, 4, 0, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        )}
                    </div>
                </div>
                <div className="card">
                    <h3 className="card-header">⚡ Avg Power by KEM Family</h3>
                    <div className="h-64">
                        {aggWarning ? <div className="text-gray-400 text-sm">{aggWarning}</div> : (
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={kemFamilyData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                    <XAxis dataKey="crypto_identity_kem_family" tick={{ fill: '#d1d5db', fontSize: 11 }} />
                                    <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} label={{ value: 'W', angle: -90, position: 'insideLeft', fill: '#6b7280' }} />
                                    <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }} />
                                    <Legend />
                                    <Bar dataKey="power_energy_power_avg_w_mean" fill="#10b981" name="Avg (W)" radius={[4, 4, 0, 0]} />
                                    <Bar dataKey="power_energy_energy_total_j_mean" fill="#f59e0b" name="Avg Energy (J)" radius={[4, 4, 0, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        )}
                    </div>
                </div>
            </div>

            {/* ── Goodput & Packet Loss ── */}
            <div className="grid grid-cols-2 gap-6">
                <div className="card">
                    <h3 className="card-header">📡 Avg Goodput by KEM Family</h3>
                    <div className="h-64">
                        {aggWarning ? <div className="text-gray-400 text-sm">{aggWarning}</div> : (
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={kemFamilyData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                    <XAxis dataKey="crypto_identity_kem_family" tick={{ fill: '#d1d5db', fontSize: 11 }} />
                                    <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} label={{ value: 'Mbps', angle: -90, position: 'insideLeft', fill: '#6b7280' }} />
                                    <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }} />
                                    <Bar dataKey="data_plane_goodput_mbps_mean" fill="#0ea5e9" name="Avg Goodput (Mbps)" radius={[4, 4, 0, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        )}
                    </div>
                </div>
                <div className="card">
                    <h3 className="card-header">📉 Avg Packet Loss by KEM Family</h3>
                    <div className="h-64">
                        {aggWarning ? <div className="text-gray-400 text-sm">{aggWarning}</div> : (
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={kemFamilyData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                    <XAxis dataKey="crypto_identity_kem_family" tick={{ fill: '#d1d5db', fontSize: 11 }} />
                                    <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} label={{ value: 'ratio', angle: -90, position: 'insideLeft', fill: '#6b7280' }} />
                                    <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }} />
                                    <Bar dataKey="data_plane_packet_loss_ratio_mean" fill="#f59e0b" name="Avg Loss Ratio" radius={[4, 4, 0, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        )}
                    </div>
                </div>
            </div>

            {/* ── Benchmark Runs Table ── */}
            <div className="card">
                <h3 className="card-header">📋 Benchmark Runs</h3>
                <table className="data-table">
                    <thead>
                        <tr>
                            <th>Run ID</th>
                            <th>Scenario</th>
                            <th>Start Time</th>
                            <th>GCS</th>
                            <th>Drone</th>
                            <th>Suites</th>
                            <th>Git Commit</th>
                        </tr>
                    </thead>
                    <tbody>
                        {runs.slice(0, 10).map(run => {
                            const rt = (settings?.available_runs as any[])?.find((r: any) => r.run_id === run.run_id)?.run_type;
                            const color = rt ? RUN_TYPE_COLORS[rt as RunType] : undefined;
                            return (
                                <tr key={run.run_id}>
                                    <td className="font-mono text-blue-400">{run.run_id}</td>
                                    <td>
                                        {rt && <span className="px-2 py-0.5 rounded text-xs" style={{
                                            color: color,
                                            backgroundColor: color ? color + '22' : undefined,
                                        }}>{RUN_TYPE_LABELS[rt as RunType] || rt}</span>}
                                    </td>
                                    <td>{run.run_start_time_wall ? new Date(run.run_start_time_wall).toLocaleString() : '—'}</td>
                                    <td>{run.gcs_hostname || '—'}</td>
                                    <td>{run.drone_hostname || '—'}</td>
                                    <td>{run.suite_count}</td>
                                    <td className="font-mono text-xs">{run.git_commit_hash?.slice(0, 8) || '—'}</td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {/* ── Quick Navigation ── */}
            <div className="flex flex-wrap gap-3">
                <Link to="/suites" className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-white text-sm font-medium transition-colors">Browse All Suites →</Link>
                <Link to="/multi-run" className="px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded text-white text-sm font-medium transition-colors">Multi-Run Compare →</Link>
                <Link to="/buckets" className="px-4 py-2 bg-teal-600 hover:bg-teal-500 rounded text-white text-sm font-medium transition-colors">Bucket Comparison →</Link>
                <Link to="/latency" className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded text-white text-sm font-medium transition-colors">Latency Analysis →</Link>
                <Link to="/security" className="px-4 py-2 bg-red-600 hover:bg-red-500 rounded text-white text-sm font-medium transition-colors">Security Impact →</Link>
            </div>
        </div>
    );
}
