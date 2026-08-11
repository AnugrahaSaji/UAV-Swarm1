/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                // Custom colors for dashboard
                'verified': '#10b981',    // green-500
                'conditional': '#f59e0b', // amber-500
                'deprecated': '#6b7280',  // gray-500
                'missing': '#9ca3af',     // gray-400
                'integrity-risk': '#ef4444', // red-500
            },
        },
    },
    plugins: [],
}
