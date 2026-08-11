/**
 * Zustand store for dashboard state management.
 * v3: Multi-run support, settings, anomaly detection.
 */

import { create } from 'zustand';
import type {
    SuiteSummary,
    ComprehensiveSuiteMetrics,
    FiltersResponse,
    RunSummary,
    SuiteInventoryResponse,
    DashboardSettings,
    MultiRunOverviewItem,
    MultiRunCompareResult,
    AnomalyItem,
    AnomalyThresholds,
    RunType,
    CrossRunAnalysisResponse,
} from '../types/metrics';

// =============================================================================
// API FUNCTIONS
// =============================================================================

const API_BASE = '/api';

async function fetchJson<T>(url: string): Promise<T> {
    const res = await fetch(url);
    if (!res.ok) {
        throw new Error(`API error: ${res.status} ${res.statusText}`);
    }
    return res.json();
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
    const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
    return res.json();
}

// =============================================================================
// STORE TYPES
// =============================================================================

interface DashboardState {
    // Data
    suites: SuiteSummary[];
    runs: RunSummary[];
    selectedSuite: ComprehensiveSuiteMetrics | null;
    selectedSuiteInventory: SuiteInventoryResponse | null;
    comparisonSuiteA: ComprehensiveSuiteMetrics | null;
    comparisonSuiteB: ComprehensiveSuiteMetrics | null;
    filters: FiltersResponse | null;

    // Settings & Multi-run
    settings: DashboardSettings | null;
    multiRunOverview: MultiRunOverviewItem[];
    multiRunCompare: MultiRunCompareResult | null;
    anomalies: AnomalyItem[];
    buckets: Record<string, unknown> | null;
    crossRunAnalysis: CrossRunAnalysisResponse | null;

    // UI State
    isLoading: boolean;
    error: string | null;

    // Filter State
    selectedKemFamily: string | null;
    selectedSigFamily: string | null;
    selectedAead: string | null;
    selectedNistLevel: string | null;
    selectedRunId: string | null;

    // Baseline
    baselineSuiteKey: string | null;

    // Actions
    fetchSuites: () => Promise<void>;
    fetchRuns: () => Promise<void>;
    fetchFilters: () => Promise<void>;
    fetchSuiteDetail: (suiteKey: string) => Promise<void>;
    fetchSuiteInventory: (suiteKey: string) => Promise<void>;
    fetchComparison: (suiteKeyA: string, suiteKeyB: string) => Promise<void>;
    fetchSettings: () => Promise<void>;
    saveRunLabel: (runId: string, label: string, runType: RunType) => Promise<void>;
    saveActiveRuns: (runIds: string[]) => Promise<void>;
    saveThresholds: (thresholds: Partial<AnomalyThresholds>) => Promise<void>;
    fetchMultiRunOverview: () => Promise<void>;
    fetchMultiRunCompare: (suiteId: string) => Promise<void>;
    fetchAnomalies: (runId?: string) => Promise<void>;
    fetchBuckets: (runId?: string) => Promise<void>;
    fetchCrossRunAnalysis: () => Promise<void>;
    setFilter: (key: keyof Pick<DashboardState, 'selectedKemFamily' | 'selectedSigFamily' | 'selectedAead' | 'selectedNistLevel' | 'selectedRunId'>, value: string | null) => void;
    clearFilters: () => void;
    setBaseline: (suiteKey: string | null) => void;
    clearError: () => void;
}

// =============================================================================
// STORE
// =============================================================================

export const useDashboardStore = create<DashboardState>((set, get) => ({
    // Initial Data
    suites: [],
    runs: [],
    selectedSuite: null,
    selectedSuiteInventory: null,
    comparisonSuiteA: null,
    comparisonSuiteB: null,
    filters: null,

    // Settings & Multi-run
    settings: null,
    multiRunOverview: [],
    multiRunCompare: null,
    anomalies: [],
    buckets: null,
    crossRunAnalysis: null,

    // Initial UI State
    isLoading: false,
    error: null,

    // Initial Filters
    selectedKemFamily: null,
    selectedSigFamily: null,
    selectedAead: null,
    selectedNistLevel: null,
    selectedRunId: null,

    // Baseline
    baselineSuiteKey: null,

    // ── Data Actions ────────────────────────────────────────────────────────

    fetchSuites: async () => {
        set({ isLoading: true, error: null });
        try {
            const state = get();
            const params = new URLSearchParams();
            if (state.selectedKemFamily) params.set('kem_family', state.selectedKemFamily);
            if (state.selectedSigFamily) params.set('sig_family', state.selectedSigFamily);
            if (state.selectedAead) params.set('aead', state.selectedAead);
            if (state.selectedNistLevel) params.set('nist_level', state.selectedNistLevel);
            if (state.selectedRunId) params.set('run_id', state.selectedRunId);

            const url = `${API_BASE}/suites${params.toString() ? '?' + params.toString() : ''}`;
            const suites = await fetchJson<SuiteSummary[]>(url);
            set({ suites, isLoading: false });
        } catch (err) {
            set({ error: err instanceof Error ? err.message : 'Failed to fetch suites', isLoading: false });
        }
    },

    fetchRuns: async () => {
        set({ isLoading: true, error: null });
        try {
            const runs = await fetchJson<RunSummary[]>(`${API_BASE}/runs`);
            set({ runs, isLoading: false });
        } catch (err) {
            set({ error: err instanceof Error ? err.message : 'Failed to fetch runs', isLoading: false });
        }
    },

    fetchFilters: async () => {
        try {
            const filters = await fetchJson<FiltersResponse>(`${API_BASE}/suites/filters`);
            set({ filters });
        } catch (err) {
            console.error('Failed to fetch filters:', err);
        }
    },

    fetchSuiteDetail: async (suiteKey: string) => {
        set({ isLoading: true, error: null });
        try {
            const suite = await fetchJson<ComprehensiveSuiteMetrics>(`${API_BASE}/suite/${encodeURIComponent(suiteKey)}`);
            set({ selectedSuite: suite, isLoading: false });
        } catch (err) {
            set({ error: err instanceof Error ? err.message : 'Failed to fetch suite', isLoading: false });
        }
    },

    fetchSuiteInventory: async (suiteKey: string) => {
        set({ isLoading: true, error: null });
        try {
            const inventory = await fetchJson<SuiteInventoryResponse>(`${API_BASE}/suite/${encodeURIComponent(suiteKey)}/inventory`);
            set({ selectedSuiteInventory: inventory, isLoading: false });
        } catch (err) {
            set({ error: err instanceof Error ? err.message : 'Failed to fetch suite inventory', isLoading: false });
        }
    },

    fetchComparison: async (suiteKeyA: string, suiteKeyB: string) => {
        set({ isLoading: true, error: null });
        try {
            const [suiteA, suiteB] = await Promise.all([
                fetchJson<ComprehensiveSuiteMetrics>(`${API_BASE}/suite/${encodeURIComponent(suiteKeyA)}`),
                fetchJson<ComprehensiveSuiteMetrics>(`${API_BASE}/suite/${encodeURIComponent(suiteKeyB)}`)
            ]);
            set({ comparisonSuiteA: suiteA, comparisonSuiteB: suiteB, isLoading: false });
        } catch (err) {
            set({ error: err instanceof Error ? err.message : 'Failed to fetch comparison', isLoading: false });
        }
    },

    // ── Settings Actions ────────────────────────────────────────────────────

    fetchSettings: async () => {
        try {
            const settings = await fetchJson<DashboardSettings>(`${API_BASE}/settings`);
            set({ settings });
        } catch (err) {
            console.error('Failed to fetch settings:', err);
        }
    },

    saveRunLabel: async (runId: string, label: string, runType: RunType) => {
        try {
            await postJson(`${API_BASE}/settings/run-label`, { run_id: runId, label, run_type: runType });
            get().fetchSettings();
        } catch (err) {
            set({ error: err instanceof Error ? err.message : 'Failed to save run label' });
        }
    },

    saveActiveRuns: async (runIds: string[]) => {
        try {
            await postJson(`${API_BASE}/settings/active-runs`, { run_ids: runIds });
            get().fetchSettings();
        } catch (err) {
            set({ error: err instanceof Error ? err.message : 'Failed to save active runs' });
        }
    },

    saveThresholds: async (thresholds: Partial<AnomalyThresholds>) => {
        try {
            await postJson(`${API_BASE}/settings/thresholds`, { thresholds });
            get().fetchSettings();
        } catch (err) {
            set({ error: err instanceof Error ? err.message : 'Failed to save thresholds' });
        }
    },

    // ── Multi-run Actions ───────────────────────────────────────────────────

    fetchMultiRunOverview: async () => {
        try {
            const data = await fetchJson<{ runs: MultiRunOverviewItem[] }>(`${API_BASE}/multi-run/overview`);
            set({ multiRunOverview: data.runs });
        } catch (err) {
            console.error('Failed to fetch multi-run overview:', err);
        }
    },

    fetchMultiRunCompare: async (suiteId: string) => {
        set({ isLoading: true, error: null });
        try {
            const data = await fetchJson<MultiRunCompareResult>(`${API_BASE}/multi-run/compare?suite_id=${encodeURIComponent(suiteId)}`);
            set({ multiRunCompare: data, isLoading: false });
        } catch (err) {
            set({ error: err instanceof Error ? err.message : 'Failed to fetch multi-run comparison', isLoading: false });
        }
    },

    fetchAnomalies: async (runId?: string) => {
        try {
            const url = runId ? `${API_BASE}/anomalies?run_id=${encodeURIComponent(runId)}` : `${API_BASE}/anomalies`;
            const data = await fetchJson<{ anomalies: AnomalyItem[] }>(url);
            set({ anomalies: data.anomalies });
        } catch (err) {
            console.error('Failed to fetch anomalies:', err);
        }
    },

    fetchBuckets: async (runId?: string) => {
        try {
            const url = runId ? `${API_BASE}/buckets?run_id=${encodeURIComponent(runId)}` : `${API_BASE}/buckets`;
            const data = await fetchJson<Record<string, unknown>>(url);
            set({ buckets: data });
        } catch (err) {
            console.error('Failed to fetch buckets:', err);
        }
    },

    fetchCrossRunAnalysis: async () => {
        set({ isLoading: true, error: null });
        try {
            const data = await fetchJson<CrossRunAnalysisResponse>(`${API_BASE}/multi-run/all-suites-compare`);
            set({ crossRunAnalysis: data, isLoading: false });
        } catch (err) {
            set({ error: err instanceof Error ? err.message : 'Failed to fetch cross-run analysis', isLoading: false });
        }
    },

    // ── Filter Actions ──────────────────────────────────────────────────────

    setFilter: (key, value) => {
        set({ [key]: value } as Partial<DashboardState>);
    },

    clearFilters: () => {
        set({
            selectedKemFamily: null,
            selectedSigFamily: null,
            selectedAead: null,
            selectedNistLevel: null,
            selectedRunId: null,
        });
    },

    setBaseline: (suiteKey) => {
        set({ baselineSuiteKey: suiteKey });
    },

    clearError: () => {
        set({ error: null });
    },
}));
