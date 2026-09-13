import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/router';
import { getContest, listProblems, submitCode, getSubmission, currentUser } from '../../lib/api';
import Leaderboard from '../../components/Leaderboard';
import AiAssistant from '../../components/AiAssistant';

export default function ContestPage() {
  const router = useRouter();
  const { id: contestId } = router.query;

  const [user, setUser] = useState(null);
  const [contest, setContest] = useState(null);
  const [problems, setProblems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [language, setLanguage] = useState('python');
  const [code, setCode] = useState('');
  const [submission, setSubmission] = useState(null);
  const [polling, setPolling] = useState(false);

  useEffect(() => {
    const u = currentUser();
    if (!u) {
      router.push('/');
      return;
    }
    setUser(u);
  }, [router]);

  useEffect(() => {
    if (!contestId || !user) return;
    getContest(contestId).then(setContest).catch(() => {});
    listProblems(contestId).then((ps) => {
      setProblems(ps);
      if (ps[0]) setSelected(ps[0]);
    }).catch(() => {});
  }, [contestId, user]);

  const pollSubmission = useCallback((id) => {
    setPolling(true);
    const interval = setInterval(async () => {
      try {
        const sub = await getSubmission(id);
        setSubmission(sub);
        if (sub.status === 'completed' || sub.status === 'infra_error') {
          clearInterval(interval);
          setPolling(false);
        }
      } catch (_) {
        clearInterval(interval);
        setPolling(false);
      }
    }, 1500);
  }, []);

  async function handleSubmit() {
    if (!selected) return;
    const sub = await submitCode(contestId, selected.id, language, code);
    setSubmission(sub);
    pollSubmission(sub.id);
  }

  if (!user || !contest) {
    return <div className="min-h-screen flex items-center justify-center text-gray-400">Loading contest…</div>;
  }

  return (
    <div className="min-h-screen p-4 grid grid-cols-12 gap-4">
      <div className="col-span-2 bg-gray-900 border border-gray-800 rounded-xl p-3 space-y-1">
        <h2 className="text-sm font-semibold mb-2">{contest.title}</h2>
        {problems.map((p) => (
          <button
            key={p.id}
            onClick={() => { setSelected(p); setSubmission(null); }}
            className={`w-full text-left text-sm px-2 py-1 rounded ${selected?.id === p.id ? 'bg-blue-600' : 'hover:bg-gray-800'}`}
          >
            {p.title}
          </button>
        ))}
      </div>

      <div className="col-span-6 bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-col">
        {selected && (
          <>
            <h1 className="text-lg font-semibold mb-2">{selected.title}</h1>
            <p className="text-sm text-gray-400 whitespace-pre-wrap mb-3">{selected.statement_md}</p>
            {selected.testCases?.filter((t) => t.is_sample).map((t) => (
              <div key={t.id} className="text-xs bg-gray-950 rounded p-2 mb-2 font-mono">
                <div>input: {t.input}</div>
                <div>expected: {t.expected_output}</div>
              </div>
            ))}
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="bg-gray-800 rounded px-2 py-1 text-sm mb-2 w-32"
            >
              <option value="python">Python</option>
              <option value="javascript">JavaScript</option>
            </select>
            <textarea
              value={code}
              onChange={(e) => setCode(e.target.value)}
              rows={14}
              className="flex-1 bg-gray-950 rounded-md p-3 text-sm font-mono outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="Write your solution here…"
            />
            <button
              onClick={handleSubmit}
              disabled={polling}
              className="mt-3 bg-green-600 hover:bg-green-500 disabled:opacity-50 rounded-md py-2 text-sm font-medium"
            >
              {polling ? 'Judging…' : 'Submit'}
            </button>

            {submission && (
              <div className="mt-3 text-sm">
                {submission.status === 'infra_error' ? (
                  <p className="text-yellow-400">
                    Judging infrastructure issue — this is not counted against you. Please resubmit.
                  </p>
                ) : submission.status === 'completed' ? (
                  <p className={submission.verdict === 'accepted' ? 'text-green-400' : 'text-red-400'}>
                    {submission.verdict} · score {submission.score}
                  </p>
                ) : (
                  <p className="text-gray-400">Status: {submission.status}…</p>
                )}
              </div>
            )}
          </>
        )}
      </div>

      <div className="col-span-4 flex flex-col gap-4">
        <Leaderboard contestId={contestId} />
        <div className="flex-1 min-h-[300px]">
          <AiAssistant user={user} orgId={contest.org_id} />
        </div>
      </div>
    </div>
  );
}
