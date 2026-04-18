// Summary bar showing counts across the three statuses
export default function Summary({ data }) {
    if (!data) return null;
    const { total, verified, plausible, hallucinations } = data;

    const items = [
        { label: "Total Claims", value: total, color: "text-blue-400" },
        { label: "Verified", value: verified, color: "text-green-400" },
        { label: "Plausible", value: plausible, color: "text-yellow-400" },
        { label: "Hallucinations", value: hallucinations, color: "text-red-400" },
    ];

    return (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 my-6">
            {items.map(({ label, value, color }) => (
                <div
                    key={label}
                    className="bg-gray-800 rounded-xl p-4 text-center shadow"
                >
                    <p className={`text-3xl font-bold ${color}`}>{value}</p>
                    <p className="text-sm text-gray-400 mt-1">{label}</p>
                </div>
            ))}
        </div>
    );
}
