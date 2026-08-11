/**
 * PQC Benchmark Dashboard v3 — Main App Component
 * Multi-run support, anomaly detection, aggressive visualization.
 */

import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import { useEffect, Component, type ErrorInfo, type ReactNode } from 'react';
import { useDashboardStore } from './state/store';
import Overview from './pages/Overview';
import SuiteExplorer from './pages/SuiteExplorer';
import SuiteDetail from './pages/SuiteDetail';
import ComparisonView from './pages/ComparisonView';
import BucketComparison from './pages/BucketComparison';
import PowerAnalysis from './pages/PowerAnalysis';
import IntegrityMonitor from './pages/IntegrityMonitor';
import MetricSemantics from './pages/MetricSemantics';
import Settings from './pages/Settings';
import MultiRunComparison from './pages/MultiRunComparison';
import SecurityImpact from './pages/SecurityImpact';
import LatencyAnalysis from './pages/LatencyAnalysis';
import CrossRunAnalysis from './pages/CrossRunAnalysis';
import SwarmSMTAudit from './pages/SwarmSMTAudit';

// Navigation groups
const NAV_GROUPS = [
    {
        label: 'OVERVIEW',
        items: [
            { path: '/', label: 'Dashboard', icon: '🔬' },
        ],
    },
    {
        label: 'ANALYSIS',
        items: [
            { path: '/suites', label: 'Suite Explorer', icon: '📋' },
            { path: '/buckets', label: 'Bucket Comparison', icon: '🪣' },
            { path: '/compare', label: 'Suite Comparison', icon: '⚖️' },
            { path: '/multi-run', label: 'Multi-Run Compare', icon: '🔀' },
            { path: '/cross-run', label: 'Cross-Run Analysis', icon: '🔬' },
        ],
    },
    {
        label: 'METRICS & SECURITY',
        items: [
            { path: '/power', label: 'Power & Energy', icon: '⚡' },
            { path: '/latency', label: 'Latency & Transport', icon: '⏱️' },
            { path: '/security', label: 'Security Impact', icon: '🛡️' },
            { path: '/integrity', label: 'Integrity Monitor', icon: '🔍' },
            { path: '/swarm-smt', label: 'Swarm & SMT Audit', icon: '🐝' },
        ],
    },
    {
        label: 'CONFIG',
        items: [
            { path: '/semantics', label: 'Metric Semantics', icon: '📖' },
            { path: '/settings', label: 'Settings', icon: '⚙️' },
        ],
    },
];

// Sidebar Navigation
function Navigation() {
    const location = useLocation();
    const anomalies = useDashboardStore(state => state.anomalies);
    const critCount = anomalies.filter(a => a.severity === 'critical').length;

    return (
        <nav className="w-56 bg-gray-800/50 border-r border-gray-700 min-h-screen fixed left-0 top-0 flex flex-col">
            {/* Logo */}
            <div className="px-4 py-4 border-b border-gray-700">
                <div className="flex items-center gap-2">
                    <div className="text-xl font-bold text-blue-400">PQC</div>
                    <div className="text-xs text-gray-500 leading-tight">Benchmark<br />Dashboard v3</div>
                </div>
            </div>

            {/* Nav Groups */}
            <div className="flex-1 overflow-y-auto py-2">
                {NAV_GROUPS.map(group => (
                    <div key={group.label} className="mb-2">
                        <div className="px-4 py-1.5 text-[10px] font-bold text-gray-500 uppercase tracking-widest">
                            {group.label}
                        </div>
                        {group.items.map(item => {
                            const isActive = location.pathname === item.path;
                            return (
                                <Link
                                    key={item.path}
                                    to={item.path}
                                    className={`flex items-center gap-2 px-4 py-2 text-sm transition-all ${
                                        isActive
                                            ? 'bg-blue-500/15 text-blue-400 border-r-2 border-blue-400'
                                            : 'text-gray-400 hover:text-white hover:bg-gray-700/50'
                                    }`}
                                >
                                    <span className="text-base">{item.icon}</span>
                                    <span>{item.label}</span>
                                    {item.path === '/security' && critCount > 0 && (
                                        <span className="ml-auto px-1.5 py-0.5 text-[10px] font-bold bg-red-500/20 text-red-400 rounded-full">
                                            {critCount}
                                        </span>
                                    )}
                                </Link>
                            );
                        })}
                    </div>
                ))}
            </div>

            {/* Footer */}
            <div className="px-4 py-3 border-t border-gray-700 text-[10px] text-gray-600">
                Secure-Tunnel PQC • Forensic
            </div>
        </nav>
    );
}

// Disclaimer banner
function DisclaimerBanner() {
    return (
        <div className="max-w-[1400px] mx-auto px-6 mt-4">
            <div className="disclaimer-banner flex items-center gap-2">
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                <span><strong>No smoothing. No causal inference.</strong> Raw observational forensic data. Anomalies flagged by threshold.</span>
            </div>
        </div>
    );
}

// Error display
function ErrorDisplay() {
    const error = useDashboardStore(state => state.error);
    const clearError = useDashboardStore(state => state.clearError);

    if (!error) return null;

    return (
        <div className="max-w-[1400px] mx-auto px-6 mt-4">
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 flex items-center justify-between">
                <span className="text-red-400">{error}</span>
                <button onClick={clearError} className="text-red-400 hover:text-red-300">✕</button>
            </div>
        </div>
    );
}

// Error Boundary
class ErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean; error: Error | null }> {
    constructor(props: { children: ReactNode }) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error: Error) {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, errorInfo: ErrorInfo) {
        console.error("Uncaught error:", error, errorInfo);
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="p-8 text-center text-gray-300">
                    <h1 className="text-xl font-bold text-red-500 mb-4">Something went wrong</h1>
                    <div className="text-left bg-gray-800 p-4 rounded border border-red-900/50 mb-4 overflow-auto max-w-3xl mx-auto font-mono text-xs">
                        {this.state.error?.toString()}
                    </div>
                    <button
                        className="px-4 py-2 bg-blue-600 rounded hover:bg-blue-500 text-white font-medium transition-colors"
                        onClick={() => window.location.reload()}
                    >
                        Reload Page
                    </button>
                </div>
            );
        }

        return this.props.children;
    }
}

// Main App
function App() {
    const fetchFilters = useDashboardStore(state => state.fetchFilters);
    const fetchSettings = useDashboardStore(state => state.fetchSettings);
    const fetchAnomalies = useDashboardStore(state => state.fetchAnomalies);
    const settings = useDashboardStore(state => state.settings);

    // Load filters + settings on mount
    useEffect(() => {
        fetchFilters();
        fetchSettings();
    }, [fetchFilters, fetchSettings]);

    // Load anomalies scoped to the latest significant run once settings arrive
    useEffect(() => {
        if (settings?.available_runs?.length) {
            fetchAnomalies(settings.available_runs[0].run_id);
        }
    }, [settings, fetchAnomalies]);

    return (
        <Router>
            <div className="min-h-screen bg-gray-900 flex">
                <Navigation />
                <div className="ml-56 flex-1">
                    <DisclaimerBanner />
                    <ErrorDisplay />
                    <main className="max-w-[1400px] mx-auto px-6 py-6">
                        <ErrorBoundary>
                            <Routes>
                                <Route path="/" element={<Overview />} />
                                <Route path="/suites" element={<SuiteExplorer />} />
                                <Route path="/suite/:suiteKey" element={<SuiteDetail />} />
                                <Route path="/buckets" element={<BucketComparison />} />
                                <Route path="/compare" element={<ComparisonView />} />
                                <Route path="/multi-run" element={<MultiRunComparison />} />
                                <Route path="/cross-run" element={<CrossRunAnalysis />} />
                                <Route path="/power" element={<PowerAnalysis />} />
                                <Route path="/latency" element={<LatencyAnalysis />} />
                                <Route path="/security" element={<SecurityImpact />} />
                                <Route path="/integrity" element={<IntegrityMonitor />} />
                                <Route path="/swarm-smt" element={<SwarmSMTAudit />} />
                                <Route path="/semantics" element={<MetricSemantics />} />
                                <Route path="/settings" element={<Settings />} />
                            </Routes>
                        </ErrorBoundary>
                    </main>
                </div>
            </div>
        </Router>
    );
}

export default App;
