/**
 * Settings Page — Configure run labels, active runs, and anomaly thresholds.
 */

import { useEffect, useState } from 'react';
import { useDashboardStore } from '../state/store';
import type { RunType, ScenarioStatus } from '../types/metrics';
import { RUN_TYPE_COLORS, RUN_TYPE_LABELS } from '../types/metrics';

const RUN_TYPES: RunType[] = ['no_ddos', 'ddos_xgboost', 'ddos_txt'];

export default function Settings() {
    const {
        settings, fetchSettings, saveRunLabel, saveActiveRuns, saveThresholds,
    } = useDashboardStore();

    const [editLabel, setEditLabel] = useState<Record<string, string>>({});
    const [editType, setEditType] = useState<Record<string, RunType>>({});
    const [localThresholds, setLocalThresholds] = useState<Record<string, number>>({});

    useEffect(() => { fetchSettings(); }, [fetchSettings]);

    useEffect(() => {
        if (settings?.anomaly_thresholds) {
            setLocalThresholds(settings.anomaly_thresholds);
        }
    }, [settings]);

    if (!settings) return <div className="text-gray-400 p-8">Loading settings…</div>;

    const availableRuns = settings.available_runs || [];
    const activeRuns = settings.active_runs || [];

    const handleToggleActive = (runId: string) => {
        const next = activeRuns.includes(runId)
            ? activeRuns.filter(r => r !== runId)
            : [...activeRuns, runId].slice(0, 3);
        saveActiveRuns(next);
    };

    const handleSaveLabel = (runId: string) => {
        const label = editLabel[runId] || runId;
        const type = editType[runId] || 'no_ddos';
        saveRunLabel(runId, label, type);
        setEditLabel(prev => { const n = { ...prev }; delete n[runId]; return n; });
        setEditType(prev => { const n = { ...prev }; delete n[runId]; return n; });
    };

    const handleSaveThresholds = () => {
        saveThresholds(localThresholds);
    };

    return (
        <div className="space-y-8">
            <div>
                <h1 className="text-2xl font-bold text-white mb-1">⚙️ Settings</h1>
                <p className="text-gray-400 text-sm">Configure benchmark runs, labels, and anomaly detection thresholds.</p>
            </div>

            {/* ── Active Run Selection ── */}
            <section className="card">
                <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                    <span className="text-blue-400">📊</span> Benchmark Runs ({availableRuns.length} available)
                </h2>
                <p className="text-gray-400 text-xs mb-4">
                    Select up to 3 runs for multi-run comparison. Label each run to identify its scenario.
                </p>
                <div className="space-y-3">
                    {availableRuns.map(run => {
                        const isActive = activeRuns.includes(run.run_id);
                        const currentLabel = settings.run_labels?.[run.run_id];
                        const isEditing = run.run_id in editLabel || run.run_id in editType;
                        return (
                            <div key={run.run_id}
                                className={`border rounded-lg p-4 transition-all ${isActive
                                    ? 'border-blue-500/50 bg-blue-500/5'
                                    : 'border-gray-700 bg-gray-800/50'}`}
                            >
                                <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-3">
                                        <button
                                            onClick={() => handleToggleActive(run.run_id)}
                                            className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${isActive
                                                ? 'bg-blue-500 border-blue-500 text-white'
                                                : 'border-gray-600 hover:border-blue-400'}`}
                                        >
                                            {isActive && '✓'}
                                        </button>
                                        <div>
                                            <span className="text-white font-mono text-sm">{run.run_id}</span>
                                            {currentLabel && (
                                                <span className="ml-2 px-2 py-0.5 rounded text-xs font-medium"
                                                    style={{
                                                        backgroundColor: RUN_TYPE_COLORS[currentLabel.type as RunType] + '22',
                                                        color: RUN_TYPE_COLORS[currentLabel.type as RunType],
                                                        border: `1px solid ${RUN_TYPE_COLORS[currentLabel.type as RunType]}44`
                                                    }}>
                                                    {currentLabel.label}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2 text-xs text-gray-500">
                                        <span>{run.suite_count} suites</span>
                                        <span>•</span>
                                        <span>{run.gcs_hostname || '?'} → {run.drone_hostname || '?'}</span>
                                    </div>
                                </div>

                                {/* Edit row */}
                                <div className="flex items-center gap-2 mt-2">
                                    <input
                                        type="text"
                                        placeholder={currentLabel?.label || 'Enter label…'}
                                        value={editLabel[run.run_id] ?? ''}
                                        onChange={e => setEditLabel(p => ({ ...p, [run.run_id]: e.target.value }))}
                                        className="flex-1 bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                                    />
                                    <select
                                        value={editType[run.run_id] ?? currentLabel?.type ?? (run as any).run_type ?? 'no_ddos'}
                                        onChange={e => setEditType(p => ({ ...p, [run.run_id]: e.target.value as RunType }))}
                                        className="bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
                                    >
                                        {RUN_TYPES.map(t => (
                                            <option key={t} value={t}>{RUN_TYPE_LABELS[t]}</option>
                                        ))}
                                    </select>
                                    <button
                                        onClick={() => handleSaveLabel(run.run_id)}
                                        disabled={!isEditing}
                                        className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${isEditing
                                            ? 'bg-blue-600 text-white hover:bg-blue-500'
                                            : 'bg-gray-700 text-gray-500 cursor-not-allowed'}`}
                                    >
                                        Save
                                    </button>
                                </div>
                            </div>
                        );
                    })}
                    {availableRuns.length === 0 && (
                        <div className="text-gray-500 text-sm italic py-4 text-center">
                            No benchmark runs detected. Place benchmark data in logs/benchmarks/runs/no-ddos/, ddos-xgboost/, or ddos-txt/.
                        </div>
                    )}
                </div>
            </section>

            {/* ── Run Type Legend ── */}
            <section className="card">
                <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                    <span className="text-purple-400">🏷️</span> Run Type Legend
                </h2>
                <div className="grid grid-cols-3 gap-4">
                    {RUN_TYPES.map(t => (
                        <div key={t} className="flex items-center gap-3 p-3 rounded-lg border border-gray-700 bg-gray-800/50">
                            <div className="w-4 h-4 rounded-full" style={{ backgroundColor: RUN_TYPE_COLORS[t] }} />
                            <div>
                                <div className="text-white text-sm font-medium">{RUN_TYPE_LABELS[t]}</div>
                                <div className="text-gray-500 text-xs">
                                    {t === 'no_ddos' && 'Normal operation — no attack vectors'}
                                    {t === 'ddos_xgboost' && 'DDoS detection via XGBoost ML model'}
                                    {t === 'ddos_txt' && 'DDoS detection via TXT-based rules'}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </section>

            {/* ── Scenario Folder Status ── */}
            {settings.scenario_status && (
                <section className="card">
                    <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                        <span className="text-green-400">📁</span> Scenario Folders
                    </h2>
                    <p className="text-gray-400 text-xs mb-4">
                        Data is loaded exclusively from these 3 folders under <code className="text-gray-300">logs/benchmarks/runs/</code>.
                    </p>
                    <div className="grid grid-cols-3 gap-4">
                        {Object.entries(settings.scenario_status).map(([folder, status]) => {
                            const s = status as ScenarioStatus;
                            const rt = s.run_type as RunType;
                            const color = RUN_TYPE_COLORS[rt] || '#6b7280';
                            return (
                                <div key={folder} className="p-4 rounded-lg border border-gray-700 bg-gray-800/50">
                                    <div className="flex items-center gap-2 mb-2">
                                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
                                        <span className="text-white font-mono text-sm font-medium">{folder}/</span>
                                    </div>
                                    <div className="space-y-1 text-xs text-gray-400">
                                        <div className="flex justify-between">
                                            <span>Status</span>
                                            <span className={s.folder_exists ? 'text-green-400' : 'text-red-400'}>
                                                {s.folder_exists ? '✓ exists' : '✗ missing'}
                                            </span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span>JSON files</span>
                                            <span className="text-white">{s.file_count}</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span>Runs</span>
                                            <span className="text-white">{s.run_count}</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span>Suites loaded</span>
                                            <span className="text-white">{s.suite_count}</span>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </section>
            )}

            {/* ── Anomaly Thresholds ── */}
            <section className="card">
                <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                    <span className="text-red-400">🚨</span> Anomaly Detection Thresholds
                </h2>
                <p className="text-gray-400 text-xs mb-4">
                    No smoothing applied. Raw critical metrics are compared against these exact thresholds.
                </p>
                <div className="grid grid-cols-2 gap-4">
                    {[
                        { key: 'handshake_ms_high', label: 'Handshake Warning (ms)', desc: 'Flag handshakes exceeding this duration' },
                        { key: 'handshake_ms_critical', label: 'Handshake Critical (ms)', desc: 'Critical alert for extreme handshake times' },
                        { key: 'packet_loss_warning', label: 'Packet Loss Warning (ratio)', desc: 'Flag packet loss above this ratio (0-1)' },
                        { key: 'packet_loss_critical', label: 'Packet Loss Critical (ratio)', desc: 'Critical alert for high packet loss' },
                        { key: 'power_deviation_pct', label: 'Power Deviation (%)', desc: 'Flag power consumption anomalies' },
                        { key: 'energy_deviation_pct', label: 'Energy Deviation (%)', desc: 'Flag energy consumption anomalies' },
                    ].map(item => (
                        <div key={item.key} className="p-3 rounded-lg border border-gray-700 bg-gray-800/50">
                            <label className="text-sm text-gray-300 font-medium">{item.label}</label>
                            <p className="text-xs text-gray-500 mb-2">{item.desc}</p>
                            <input
                                type="number"
                                step="any"
                                value={localThresholds[item.key] ?? ''}
                                onChange={e => {
                                    const v = parseFloat(e.target.value);
                                    if (!Number.isNaN(v)) setLocalThresholds(p => ({ ...p, [item.key]: v }));
                                }}
                                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
                            />
                        </div>
                    ))}
                </div>
                <div className="mt-4 flex justify-end">
                    <button
                        onClick={handleSaveThresholds}
                        className="px-4 py-2 bg-red-600 text-white rounded font-medium hover:bg-red-500 transition-colors"
                    >
                        💾 Save Thresholds
                    </button>
                </div>
            </section>
        </div>
    );
}
