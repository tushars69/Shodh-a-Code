import { useEffect, useState } from 'react';
import { getLeaderboard } from '../lib/api';

export default function Leaderboard({ contestId }) {
  const [rows, setRows] = useState([]);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const data = await getLeaderboard(contestId);
        if (!cancelled) setRows(data);
      } catch (_) {
        // leaderboard fetch failures are non-fatal — just skip this tick
      }
    }
    poll();
    const interval = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [contestId]);

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <h2 className="text-sm font-semibold mb-2">Leaderboard</h2>
      <table className="w-full text-sm">
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.user_id} className="border-t border-gray-800">
              <td className="py-1 pr-2 text-gray-500">{i + 1}</td>
              <td className="py-1">{r.username}</td>
              <td className="py-1 text-right font-medium">{r.total_score}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td className="text-gray-500 text-xs py-2">No judged submissions yet.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
