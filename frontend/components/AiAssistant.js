import { useState } from 'react';
import { askAi } from '../lib/api';

export default function AiAssistant({ user, orgId }) {
  const [question, setQuestion] = useState('');
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);

  async function handleAsk(e) {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    const q = question;
    setQuestion('');
    try {
      const res = await askAi(q, user, orgId);
      setHistory((h) => [...h, { question: q, response: res }]);
    } catch (err) {
      setHistory((h) => [
        ...h,
        { question: q, response: { error: 'ai_unavailable', detail: 'Could not reach the AI service.' } },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-col h-full">
      <h2 className="text-sm font-semibold mb-2">Contest Assistant</h2>
      <div className="flex-1 overflow-y-auto space-y-3 mb-3 text-sm">
        {history.length === 0 && (
          <p className="text-gray-500 text-xs">
            Ask things like "why did my latest submission fail" or "what should I review next".
          </p>
        )}
        {history.map((h, i) => (
          <div key={i} className="space-y-1">
            <p className="text-blue-300">You: {h.question}</p>
            {h.response.error ? (
              <p className="text-yellow-400 text-xs">
                AI unavailable right now ({h.response.detail}). Your contest progress is unaffected — try again shortly.
              </p>
            ) : (
              <div>
                <p className="text-gray-200 whitespace-pre-wrap">{h.response.answer}</p>
                {h.response.evidence?.length > 0 && (
                  <details className="text-xs text-gray-500 mt-1">
                    <summary className="cursor-pointer">
                      {h.response.evidence.length} evidence lookup(s) used
                    </summary>
                    <pre className="whitespace-pre-wrap break-words bg-gray-950 p-2 rounded mt-1">
                      {JSON.stringify(h.response.evidence, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
      <form onSubmit={handleAsk} className="flex gap-2">
        <input
          className="flex-1 bg-gray-800 rounded-md px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-blue-500"
          placeholder="Ask the assistant…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button
          disabled={loading}
          className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-md px-3 text-sm"
        >
          {loading ? '…' : 'Ask'}
        </button>
      </form>
    </div>
  );
}
