import { useState } from 'react';
import { useRouter } from 'next/router';
import { joinContest } from '../lib/api';

export default function Home() {
  const [contestId, setContestId] = useState('');
  const [username, setUsername] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleJoin(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await joinContest(contestId, username);
      router.push(`/contest/${contestId}`);
    } catch (err) {
      setError('Could not join — check the Contest ID and try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <form onSubmit={handleJoin} className="w-full max-w-sm bg-gray-900 border border-gray-800 rounded-xl p-8 space-y-4">
        <h1 className="text-xl font-semibold">Shodh-a-Code</h1>
        <p className="text-sm text-gray-400">Join a contest with your Contest ID and a username.</p>
        <input
          className="w-full bg-gray-800 rounded-md px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-blue-500"
          placeholder="Contest ID"
          value={contestId}
          onChange={(e) => setContestId(e.target.value)}
          required
        />
        <input
          className="w-full bg-gray-800 rounded-md px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-blue-500"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
        {error && <p className="text-red-400 text-sm">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-md py-2 text-sm font-medium"
        >
          {loading ? 'Joining…' : 'Join Contest'}
        </button>
      </form>
    </div>
  );
}
